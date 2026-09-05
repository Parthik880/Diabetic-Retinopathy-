"""Regression tests for explicit categorical TIFF annotation pairing."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd
from PIL import Image

from models.lesion.dataset import DDRLesionDataset


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGB", (8, 6), "gray").save(self.root / "eye.jpg")
        array = np.zeros((6, 8), dtype=np.uint8)
        array[2:4, 3:5] = 1
        Image.fromarray(array).save(self.root / "mask.tiff")
        self.row = dict(image_path="eye.jpg", mask_path="mask.tiff",
                        lesion_class="MA", source_dataset="fixture", original_split="train")

    def dataset(self, rows=None, **kwargs):
        path = self.root / "pairs.csv"
        pd.DataFrame(rows if rows is not None else [self.row]).to_csv(path, index=False)
        return DDRLesionDataset(path, image_size=12, **kwargs)

    def test_pair_and_nearest_resize(self):
        sample = self.dataset(return_metadata=True)[0]
        self.assertEqual(tuple(sample["image"].shape), (3, 12, 12))
        self.assertEqual(tuple(sample["mask"].shape), (1, 12, 12))
        self.assertEqual(set(sample["mask"].unique().tolist()), {0.0, 1.0})
        self.assertEqual(sample["mask_path"], str((self.root / "mask.tiff").resolve()))
        self.assertEqual(len(self.dataset()[0]), 3)

    def test_palette_indices_preserved(self):
        with Image.open(self.root / "mask.tiff") as mask:
            array = np.array(mask)
            mask.close()
        palette = Image.fromarray(array).convert("P")
        # Both palette colors are nonblack; converting to RGB would corrupt background.
        palette.putpalette([100, 100, 100, 255, 0, 0] + [0] * 762)
        palette.save(self.root / "mask.tiff")
        mask = self.dataset()[0][1]
        self.assertEqual(set(mask.unique().tolist()), {0.0, 1.0})

    def test_rejects_multi_class_and_rgb(self):
        for array in [np.full((6, 8), 2, dtype=np.uint8),
                      np.zeros((6, 8, 3), dtype=np.uint8)]:
            Image.fromarray(array).save(self.root / "mask.tiff")
            with self.assertRaises(ValueError):
                self.dataset()[0]

    def test_explicit_opaque_black_red_rgba(self):
        array = np.zeros((6, 8, 4), dtype=np.uint8)
        array[:, :, 3] = 255
        array[2:4, 3:5, 0] = 255
        Image.fromarray(array).save(self.root / "mask.tiff")
        self.assertEqual(set(self.dataset()[0][1].unique().tolist()), {0.0, 1.0})
        array[0, 0, 1] = 255
        Image.fromarray(array).save(self.root / "mask.tiff")
        with self.assertRaisesRegex(ValueError, "Unsupported RGBA"):
            self.dataset()[0]

    def test_original_dimension_mismatch(self):
        Image.new("L", (7, 6)).save(self.root / "mask.tiff")
        with self.assertRaisesRegex(ValueError, "dimensions differ"):
            self.dataset()[0]

    def test_missing_and_unreadable(self):
        (self.root / "mask.tiff").unlink()
        with self.assertRaisesRegex(ValueError, "Missing mask_path"):
            self.dataset()
        (self.root / "mask.tiff").write_bytes(b"broken tiff")
        with self.assertRaisesRegex(ValueError, "Unreadable TIFF"):
            self.dataset()[0]

    def test_duplicate_and_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.dataset([self.row, self.row])
        Image.new("L", (8, 6)).save(self.root / "second.tif")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.dataset([self.row, dict(self.row, mask_path="second.tif")])

    def test_multiple_lesions_and_reordered_rows(self):
        Image.new("L", (8, 6), 255).save(self.root / "he.tif")
        dataset = self.dataset([dict(self.row, mask_path="he.tif", lesion_class="HE"), self.row])
        self.assertEqual(dataset[0][2], 1)
        self.assertEqual(dataset[0][1].min().item(), 1)
        self.assertEqual(dataset[1][2], 0)
        self.assertEqual(dataset[1][1].min().item(), 0)


if __name__ == "__main__":
    unittest.main()
