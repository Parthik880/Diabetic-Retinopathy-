from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import torch

import sys
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from inference.batch_pipeline import _adaptive_map, run_analysis_batch


class Registry:
    def __init__(self):
        self.models = {name: object() for name in ("quality", "grading", "lesion", "restoration")}
        self.lock = Lock()
        self.device = torch.device("cpu")
        self.device_name = "Test device"


class TensorBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.items = []
        self.run_number = 0

    def tearDown(self):
        self.temp.cleanup()

    def make_items(self, count, malformed=None):
        self.run_number += 1
        root = self.root / str(self.run_number)
        root.mkdir()
        items = []
        for index in range(count):
            run = root / f"{index:032x}"
            run.mkdir()
            path = run / "input.png"
            if index == malformed:
                path.write_bytes(b"malformed")
            else:
                Image.new("RGB", (16 + index, 12 + index), (index, 80, 120)).save(path)
            items.append({"original_path": path, "run_id": run.name, "eye": "OS"})
        return items

    def run_mocked(self, count, target, malformed=None):
        calls = {"iqa": [], "grading": [], "lesion": []}

        def iqa(images, _model):
            calls["iqa"].append(len(images))
            return [{"class_id": 0, "quality": "Good", "confidence": 0.9,
                     "probabilities": {"Good": 0.9, "Usable": 0.08, "Reject": 0.02}}
                    for _ in images]

        def grading(paths, _model, _outputs):
            calls["grading"].append(len(paths))
            return [{"predicted_class": index % 5, "predicted_grade": index % 5,
                     "confidence": 0.8, "probabilities": [0.2] * 5, "image_path": str(path)}
                    for index, path in enumerate(paths)]

        def lesion(paths, _model, _outputs, callbacks):
            calls["lesion"].append(len(paths))
            for callback in callbacks:
                for state in ("LESION_INFERENCE", "LESION_MASK_PROCESSING", "LESION_REGION_EXTRACTION", "LESION_RESULTS_SAVING"):
                    callback(state)
            return [{"lesions": {}, "forward_count": 1, "image": str(path)} for path in paths]

        with (
            patch("inference.batch_pipeline.quality.predict_batch", side_effect=iqa),
            patch("inference.batch_pipeline.grading.predict_batch", side_effect=grading),
            patch("inference.batch_pipeline.lesions.predict_batch", side_effect=lesion),
        ):
            outcome = run_analysis_batch(items=self.make_items(count, malformed), registry=Registry(),
                                         runs_root=self.root, target_batch_size=target)
        return outcome, calls

    def test_b1_smaller_equal_and_larger_than_target(self):
        for count, target, expected in ((1, 1, [1]), (2, 5, [2]), (3, 3, [3]), (5, 2, [2, 2, 1])):
            with self.subTest(count=count, target=target):
                outcome, calls = self.run_mocked(count, target)
                self.assertEqual(calls["iqa"], expected)
                self.assertEqual(calls["grading"], expected)
                self.assertEqual(calls["lesion"], expected)
                self.assertTrue(all(result["state"] == "COMPLETE" for result in outcome["results"]))

    def test_adaptive_oom_retries_same_order_and_caches_reduced_size(self):
        seen = []

        def run(chunk):
            seen.append(list(chunk))
            if len(chunk) > 2:
                raise torch.cuda.OutOfMemoryError("forced")
            return [f"result-{item}" for item in chunk]

        with patch("inference.batch_pipeline.torch.cuda.empty_cache") as empty_cache:
            results, effective, largest, fell_back = _adaptive_map(list(range(7)), 7, "test", run)
        self.assertEqual(seen, [list(range(7)), [0, 1, 2], [0], [1], [2], [3], [4], [5], [6]])
        self.assertEqual(results, [f"result-{index}" for index in range(7)])
        self.assertEqual((effective, largest, fell_back), (1, 1, True))
        self.assertEqual(empty_cache.call_count, 2)

    def test_malformed_image_fails_only_that_item_and_mapping_is_exact(self):
        outcome, calls = self.run_mocked(3, 3, malformed=1)
        self.assertEqual(calls["iqa"], [2])
        self.assertEqual(outcome["results"][0]["run_id"], f"{0:032x}")
        self.assertIsInstance(outcome["results"][1], Exception)
        self.assertEqual(outcome["results"][2]["run_id"], f"{2:032x}")
        self.assertEqual(Path(outcome["results"][2]["grading"]["image_path"]).parent.name, f"{2:032x}")


if __name__ == "__main__":
    unittest.main()
