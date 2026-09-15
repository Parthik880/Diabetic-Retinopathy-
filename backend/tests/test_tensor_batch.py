from concurrent.futures import ThreadPoolExecutor
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

from inference.batch_pipeline import _adaptive_map, _postprocess_worker_count, run_analysis_batch
from inference import lesions as lesion_inference


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

    def run_mocked(self, count, target, malformed=None, stages=None):
        calls = {"iqa": [], "grading": [], "lesion": []}

        def iqa(images, _model, **_kwargs):
            calls["iqa"].append(len(images))
            return [{"class_id": 0, "quality": "Good", "confidence": 0.9,
                     "probabilities": {"Good": 0.9, "Usable": 0.08, "Reject": 0.02}}
                    for _ in images]

        def grading(paths, _model, _outputs, **_kwargs):
            calls["grading"].append(len(paths))
            return [{"predicted_class": index % 5, "predicted_grade": index % 5,
                     "confidence": 0.8, "probabilities": [0.2] * 5, "image_path": str(path)}
                    for index, path in enumerate(paths)]

        def lesion(paths, _model, _outputs, callbacks, **_kwargs):
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
                                         runs_root=self.root, target_batch_size=target,
                                         on_batch_start=(lambda indices: stages.append((1, indices))) if stages is not None else None,
                                         on_display_stage=(lambda indices, stage: stages.append((stage, indices))) if stages is not None else None)
        return outcome, calls

    def test_b1_smaller_and_equal_to_target_use_one_forward(self):
        for count, target, expected in ((1, 1, [1]), (2, 5, [2]), (3, 3, [3])):
            with self.subTest(count=count, target=target):
                outcome, calls = self.run_mocked(count, target)
                self.assertEqual(calls["iqa"], expected)
                self.assertEqual(calls["grading"], expected)
                self.assertEqual(calls["lesion"], expected)
                self.assertTrue(all(result["state"] == "COMPLETE" for result in outcome["results"]))

    def test_oom_stops_without_retrying_as_smaller_batches(self):
        seen = []

        def run(chunk):
            seen.append(list(chunk))
            raise torch.cuda.OutOfMemoryError("forced")

        with patch("inference.batch_pipeline.torch.cuda.empty_cache") as empty_cache:
            with self.assertRaisesRegex(RuntimeError, "could not fit into GPU memory"):
                _adaptive_map(list(range(7)), 7, "test", run)
        self.assertEqual(seen, [list(range(7))])
        empty_cache.assert_called_once()

    def test_postprocess_workers_are_capped_by_cpu_and_available_ram(self):
        with patch("inference.batch_pipeline.os.cpu_count", return_value=12), \
             patch("inference.batch_pipeline._available_ram_bytes", return_value=16 * 1024 ** 3):
            self.assertEqual(_postprocess_worker_count(), 4)
        with patch("inference.batch_pipeline.os.cpu_count", return_value=2), \
             patch("inference.batch_pipeline._available_ram_bytes", return_value=1024 ** 3):
            self.assertEqual(_postprocess_worker_count(), 1)

    def test_over_limit_is_rejected_before_any_forward(self):
        with self.assertRaisesRegex(ValueError, "Maximum 2 images; received 3"):
            self.run_mocked(3, 2)

    def test_display_stages_are_emitted_in_backend_order(self):
        stages = []
        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            self.run_mocked(5, 5, stages=stages)
        self.assertEqual([stage for stage, _indices in stages], [1, 2, 3, 4])
        self.assertTrue(all(indices == list(range(5)) for _stage, indices in stages))
        self.assertIn("STAGE 3 PROFILE", " ".join(logs.output))

    def test_malformed_image_fails_only_that_item_and_mapping_is_exact(self):
        outcome, calls = self.run_mocked(3, 3, malformed=1)
        self.assertEqual(calls["iqa"], [2])
        self.assertEqual(outcome["results"][0]["run_id"], f"{0:032x}")
        self.assertIsInstance(outcome["results"][1], Exception)
        self.assertEqual(outcome["results"][2]["run_id"], f"{2:032x}")
        self.assertEqual(Path(outcome["results"][2]["grading"]["image_path"]).parent.name, f"{2:032x}")

    def test_lesion_postprocessing_is_bounded_ordered_after_one_batched_forward(self):
        items = self.make_items(5)
        paths = [Path(item["original_path"]) for item in items]
        outputs = [path.parent / "lesion" for path in paths]
        index_by_path = {path.resolve(): index for index, path in enumerate(paths)}

        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.anchor = torch.nn.Parameter(torch.zeros(1))
                self.calls = 0

            def forward(self, tensor):
                self.calls += 1
                self.batch_shape = list(tensor.shape)
                return tensor[:, :1].repeat(1, 4, 1, 1)

        model = Model()

        def preprocess(path):
            index = index_by_path[Path(path).resolve()]
            return Path(path).resolve(), torch.full((1, 3, 8, 8), float(index))

        def finish(path, _model, _output, **kwargs):
            index = index_by_path[Path(path).resolve()]
            self.assertEqual(kwargs["prevalidated_image"][0], Path(path).resolve())
            return {"image": str(path), "marker": float(kwargs["precomputed_original_probabilities"][0, 0, 0]),
                    "timing_ms": {}}

        timing = {}
        with ThreadPoolExecutor(max_workers=2) as executor, \
             patch.object(lesion_inference, "IMAGE_SIZE", 8), \
             patch.object(lesion_inference, "preprocess_lesion_image", side_effect=preprocess), \
             patch.object(lesion_inference, "predict", side_effect=finish):
            results = lesion_inference.predict_batch(
                paths, model, outputs, executor=executor, max_workers=2, timing=timing)

        self.assertEqual(model.calls, 1)
        self.assertEqual(model.batch_shape, [5, 3, 8, 8])
        expected = [float(torch.sigmoid(torch.tensor(float(index)))) for index in range(5)]
        self.assertEqual([result["marker"] for result in results], expected)
        self.assertIn("postprocessing_wall_ms", timing)


if __name__ == "__main__":
    unittest.main()
