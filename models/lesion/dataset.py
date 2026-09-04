"""Original DDR/IDRiD dataset adapter and lesion channel mapping."""

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset


IMAGE_SIZE = 768
CSV_PATH = Path(__file__).resolve().parent / "idrid+ddr_lesion.csv"
VALIDATION_FRACTION = 0.20
LESION_CLASSES = {"MA": 0, "HE": 1, "EX": 2, "SE": 3}


class DDRLesionDataset(Dataset):
    """One image/mask/lesion row from an external combined DDR + IDRiD CSV."""

    def __init__(
        self,
        csv_path=CSV_PATH,
        image_size=IMAGE_SIZE,
        target_lesion=None,
        split=None,
        split_seed=42,
    ):
        self.csv_path = Path(csv_path).resolve()
        self.image_size = image_size
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
        mask_path = self.csv_path.parent / self.samples.iloc[index]["mask_path"]
        with Image.open(mask_path) as mask:
            if mask.mode in ("RGB", "RGBA"):
                mask = mask.convert("RGB")
            mask = mask.resize(
                (self.image_size, self.image_size), Image.Resampling.NEAREST
            )
            mask = np.array(mask)
            if mask.ndim == 3 and mask.shape[2] == 3:
                mask = mask.max(axis=2)
            mask = torch.from_numpy((mask > 0).astype(np.float32))
        if mask.ndim != 2:
            raise ValueError(f"Expected a single-channel lesion mask: {mask_path}")
        return mask.unsqueeze(0)

    def __getitem__(self, index):
        sample = self.samples.iloc[index]
        image_path = self.csv_path.parent / sample["image_path"]
        size = (self.image_size, self.image_size)
        with Image.open(image_path) as image:
            image = image.convert("RGB").resize(size, Image.Resampling.BILINEAR)
            image = torch.from_numpy(np.array(image)).permute(2, 0, 1).float() / 255.0
        image = (image - self.mean) / self.std
        mask = self.load_mask(index)
        return image, mask, LESION_CLASSES[sample["lesion"]]
