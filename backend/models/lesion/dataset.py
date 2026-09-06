"""Explicit CSV image/TIFF pairs for DDR/IDRiD lesion supervision."""

import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset

from .constants import IMAGE_SIZE, LESION_CLASSES


CSV_PATH = Path(os.environ.get(
    "DR_LESION_CSV", Path(__file__).resolve().parent / "idrid+ddr_lesion.csv"
))
VALIDATION_FRACTION = 0.20


def read_annotation(mask_path, expected_size=None):
    """Read categorical pixels unchanged; reject unsupported encodings."""
    path = Path(mask_path)
    if path.suffix.lower() not in {".tif", ".tiff"}:
        raise ValueError(f"Expected a TIFF annotation: {path}")
    try:
        with Image.open(path) as mask:
            if getattr(mask, "n_frames", 1) != 1:
                raise ValueError(f"Ambiguous multi-page TIFF annotation: {path}")
            mode, size = mask.mode, mask.size
            array = np.array(mask)
            mask.close()
    except OSError as exc:
        raise ValueError(f"Unreadable TIFF annotation: {path}: {exc}") from exc
    if expected_size is not None and size != expected_size:
        raise ValueError(
            f"Original image/mask dimensions differ: image={expected_size}, "
            f"mask={size}, mask_path={path}"
        )
    encoding = "single-channel binary"
    raw_shape = list(array.shape)
    if mode == "RGBA" and array.ndim == 3 and array.shape[2] == 4:
        # Observed IDRiD EX encoding: opaque black background/red foreground.
        # Alpha is not lesion data. Reject all other colors/transparency.
        if (np.isin(array[:, :, 0], [0, 255]).all()
                and (array[:, :, 1:3] == 0).all()
                and (array[:, :, 3] == 255).all()):
            array = array[:, :, 0].copy()
            encoding = "opaque black/red RGBA: red channel 0/255"
        else:
            raise ValueError(f"Unsupported RGBA annotation colors or alpha: {path}")
    if array.ndim != 2:
        raise ValueError(f"Expected a single-channel categorical mask: {path} ({mode})")
    values = np.unique(array)
    # This CSV supplies one binary annotation per lesion, not a class-ID map.
    if not (np.isin(values, [0, 1]).all() or np.isin(values, [0, 255]).all()):
        raise ValueError(
            f"Unsupported or multi-class mask values {values.tolist()}: {path}; "
            "provide an explicit class-ID mapping instead of collapsing labels"
        )
    return array, {
        "mode": mode, "size": size, "values": values.tolist(),
        "raw_shape": raw_shape, "encoding": encoding,
    }


class DDRLesionDataset(Dataset):
    """One image/mask/lesion row from an external combined DDR + IDRiD CSV."""

    def __init__(
        self,
        csv_path=CSV_PATH,
        image_size=IMAGE_SIZE,
        target_lesion=None,
        split=None,
        split_seed=42,
        return_metadata=False,
    ):
        self.csv_path = Path(csv_path).resolve()
        self.image_size = image_size
        self.return_metadata = return_metadata
        rows = pd.read_csv(self.csv_path)

        if target_lesion is not None and target_lesion not in LESION_CLASSES:
            raise ValueError("target_lesion must be None, 'MA', 'HE', 'EX', or 'SE'")
        if split not in (None, "train", "val"):
            raise ValueError("split must be None, 'train', or 'val'")

        required_columns = [
            "image_path",
            "mask_path",
            "lesion_class",
            "source_dataset",
            "original_split",
        ]
        missing_columns = set(required_columns) - set(rows.columns)
        if missing_columns:
            raise ValueError(f"Missing CSV columns: {sorted(missing_columns)}")
        if rows.empty or rows[required_columns].isna().any().any():
            raise ValueError(
                "CSV rows must contain valid annotation paths and metadata; "
                "missing masks are not negatives."
            )
        if not rows["lesion_class"].isin(LESION_CLASSES).all():
            raise ValueError("CSV contains unknown lesion classes; use MA, HE, EX, SE")
        for column in ("image_path", "mask_path"):
            rows[column] = rows[column].map(
                lambda value: str((self.csv_path.parent / value).resolve())
            )
        if rows.duplicated(["image_path", "mask_path", "lesion_class"]).any():
            raise ValueError("Duplicate image/mask/lesion rows found in the CSV")
        if rows.groupby("mask_path")["lesion_class"].nunique().gt(1).any():
            raise ValueError("The same mask cannot belong to multiple lesion classes")

        if rows.groupby(["image_path", "lesion_class"])["mask_path"].nunique().gt(1).any():
            raise ValueError("Ambiguous masks: multiple annotations for one image/lesion")
        if rows.groupby("mask_path")["image_path"].nunique().gt(1).any():
            raise ValueError("Ambiguous annotation: one mask assigned to multiple images")
        for column in ("image_path", "mask_path"):
            missing = [path for path in rows[column].unique() if not Path(path).is_file()]
            if missing:
                raise ValueError(f"Missing {column} files ({len(missing)}): {missing[:5]}")
        non_tiff = [p for p in rows["mask_path"] if Path(p).suffix.lower() not in {".tif", ".tiff"}]
        if non_tiff:
            raise ValueError(f"Expected TIFF mask paths: {non_tiff[:5]}")

        if split is not None:
            image_keys = rows["image_path"].str.casefold()
            unique_images = sorted(image_keys.unique())
            if len(unique_images) < 2 or not 0 < VALIDATION_FRACTION < 1:
                raise ValueError("An image-level split needs at least two images")
            generator = torch.Generator().manual_seed(split_seed)
            shuffled_indices = torch.randperm(
                len(unique_images), generator=generator
            ).tolist()
            val_count = max(1, int(len(unique_images) * VALIDATION_FRACTION))
            val_images = {unique_images[index] for index in shuffled_indices[:val_count]}
            in_validation = image_keys.isin(val_images)
            rows = rows[in_validation if split == "val" else ~in_validation]

        if target_lesion is not None:
            rows = rows[rows["lesion_class"] == target_lesion]
        if rows.empty:
            raise ValueError("No annotations remain for this split and lesion filter")
        self.samples = rows.rename(columns={"lesion_class": "lesion"}).reset_index(
            drop=True
        )
        self.mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        self.std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)

    def __len__(self):
        return len(self.samples)

    def load_mask(self, index):
        sample = self.samples.iloc[index]
        with Image.open(sample["image_path"]) as image:
            original_size = image.size
        array, _ = read_annotation(sample["mask_path"], original_size)
        # Validate palette indices before converting to a binary training target.
        binary = Image.fromarray((array > 0).astype(np.uint8))
        binary = binary.resize(
            (self.image_size, self.image_size), Image.Resampling.NEAREST
        )
        return torch.from_numpy(np.array(binary, dtype=np.float32)).unsqueeze(0)

    def __getitem__(self, index):
        sample = self.samples.iloc[index]
        image_path = sample["image_path"]
        mask = self.load_mask(index)  # Check original dimensions before any resize.
        size = (self.image_size, self.image_size)
        with Image.open(image_path) as image:
            image = image.convert("RGB").resize(size, Image.Resampling.BILINEAR)
            image = torch.from_numpy(np.array(image)).permute(2, 0, 1).float() / 255.0
        image = (image - self.mean) / self.std
        lesion_class = LESION_CLASSES[sample["lesion"]]
        if self.return_metadata:
            return {
                "image": image, "mask": mask, "lesion_class": lesion_class,
                "image_path": str(image_path), "mask_path": str(sample["mask_path"]),
            }
        return image, mask, lesion_class
