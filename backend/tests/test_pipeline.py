from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest
from unittest.mock import patch
import sys

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.jobs import AnalysisJobManager
from inference.pipeline import PipelineState, normalize_quality_result, run_analysis_pipeline


class FakeRegistry:
    def __init__(self):
        self.models = {name: object() for name in ("quality", "restoration", "grading", "lesion")}
        self.device = "cuda"
        self.device_name = "test GPU"
        self.lock = Lock()


class PipelineRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.runs = Path(self.temp.name)
        self.run_id = "a" * 32
        self.run_dir = self.runs / self.run_id
        self.run_dir.mkdir()
        self.original = self.run_dir / "input.png"
        Image.new("RGB", (16, 12), (40, 80, 120)).save(self.original)
        self.registry = FakeRegistry()

    def tearDown(self):
        self.temp.cleanup()

    def run_case(self, label: str):
        quality_result = {
            "class_id": {"Good": 0, "Usable": 1, "Reject": 2}[label],
            "quality": label,
            "confidence": 0.91,
            "probabilities": {"Good": 0.03, "Usable": 0.06, "Reject": 0.91},
        }
        restored_path = self.run_dir / "restoration" / "input_restored.png"

        def restore(source, model, output_dir):
            restored_path.parent.mkdir(parents=True, exist_ok=True)
            Image.open(source).save(restored_path)
            return {"output_path": str(restored_path), "image_path": str(source), "width": 16, "height": 12}

        def lesion_predict(path, *_, **kwargs):
            downstream_paths.append(Path(path))
            for state in ("LESION_INFERENCE", "LESION_MASK_PROCESSING", "LESION_REGION_EXTRACTION", "LESION_RESULTS_SAVING"):
                if kwargs.get("on_stage"):
                    kwargs["on_stage"](state)
            return {"lesions": {}, "forward_count": 1}

        downstream_paths = []
        with (
            patch("inference.pipeline.quality.predict", return_value=quality_result) as iqa,
            patch("inference.pipeline.restoration.restore", side_effect=restore) as nafnet,
            patch("inference.pipeline.grading.predict", side_effect=lambda path, *_: downstream_paths.append(Path(path)) or {"predicted_grade": 2}) as grade,
            patch("inference.pipeline.lesions.predict", side_effect=lesion_predict) as lesion,
        ):
            result = run_analysis_pipeline(
                original_path=self.original,
                registry=self.registry,
                run_id=self.run_id,
                runs_root=self.runs,
                eye="OS",
            )
        return result, iqa, nafnet, grade, lesion, downstream_paths

    def test_deployed_iqa_mapping_is_explicit(self):
        self.assertEqual(normalize_quality_result({"class_id": 0, "quality": "Good"}), "GOOD")
        self.assertEqual(normalize_quality_result({"class_id": 1, "quality": "Usable"}), "USABLE")
        self.assertEqual(normalize_quality_result({"class_id": 2, "quality": "Reject"}), "RECAPTURE")
        with self.assertRaises(ValueError):
            normalize_quality_result({"class_id": 1, "quality": "Good"})

    def test_good_uses_original_and_completes(self):
        result, iqa, nafnet, grade, lesion, paths = self.run_case("Good")
        self.assertEqual((iqa.call_count, nafnet.call_count, grade.call_count, lesion.call_count), (1, 0, 1, 1))
        self.assertEqual(paths, [self.original, self.original])
        self.assertEqual(result["analysis_source"], "original")
        self.assertIsNone(result["restored_image_url"])
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual([item["state"] for item in result["state_history"]], ["WAITING", "IQA", "IQA_GOOD", "GRADING", "LESION_ANALYSIS", "LESION_INFERENCE", "LESION_MASK_PROCESSING", "LESION_REGION_EXTRACTION", "LESION_RESULTS_SAVING", "PREPARING_RESULTS", "COMPLETE"])

    def test_usable_restores_once_and_sends_restored_image_downstream(self):
        result, iqa, nafnet, grade, lesion, paths = self.run_case("Usable")
        self.assertEqual((iqa.call_count, nafnet.call_count, grade.call_count, lesion.call_count), (1, 1, 1, 1))
        self.assertEqual(paths, [self.run_dir / "restoration" / "input_restored.png"] * 2)
        self.assertEqual(result["analysis_source"], "restored")
        self.assertTrue(result["restored_image_url"].endswith("input_restored.png"))
        self.assertEqual(result["state"], "COMPLETE")
        self.assertEqual([item["state"] for item in result["state_history"]], ["WAITING", "IQA", "IQA_USABLE", "RESTORING", "RESTORATION_COMPLETE", "GRADING", "LESION_ANALYSIS", "LESION_INFERENCE", "LESION_MASK_PROCESSING", "LESION_REGION_EXTRACTION", "LESION_RESULTS_SAVING", "PREPARING_RESULTS", "COMPLETE"])

    def test_reject_stops_with_recapture_terminal_state(self):
        result, iqa, nafnet, grade, lesion, paths = self.run_case("Reject")
        self.assertEqual((iqa.call_count, nafnet.call_count, grade.call_count, lesion.call_count), (1, 0, 0, 0))
        self.assertEqual(paths, [])
        self.assertEqual(result["state"], "RECAPTURE_REQUIRED")
        self.assertEqual([item["state"] for item in result["state_history"]], ["WAITING", "IQA", "IQA_REJECTED", "RECAPTURE_REQUIRED"])

    def test_nafnet_failure_is_terminal_and_never_falls_through(self):
        states = []
        with (
            patch("inference.pipeline.quality.predict", return_value={"class_id": 1, "quality": "Usable", "confidence": 1.0}),
            patch("inference.pipeline.restoration.restore", side_effect=RuntimeError("controlled NAFNet failure")),
            patch("inference.pipeline.grading.predict") as grade,
            patch("inference.pipeline.lesions.predict") as lesion,
        ):
            with self.assertRaisesRegex(RuntimeError, "controlled NAFNet failure"):
                run_analysis_pipeline(
                    original_path=self.original,
                    registry=self.registry,
                    run_id=self.run_id,
                    runs_root=self.runs,
                    on_state=states.append,
                )
        self.assertEqual(states[-1], PipelineState.RESTORING)
        grade.assert_not_called()
        lesion.assert_not_called()
        self.assertTrue((self.run_dir / "failure.json").is_file())

    def test_bilateral_usable_and_good_route_independently(self):
        left, left_iqa, left_nafnet, left_grade, left_lesion, _ = self.run_case("Usable")
        right, right_iqa, right_nafnet, right_grade, right_lesion, _ = self.run_case("Good")
        self.assertEqual((left["state"], right["state"]), ("COMPLETE", "COMPLETE"))
        self.assertEqual((left_iqa.call_count, left_nafnet.call_count, left_grade.call_count, left_lesion.call_count), (1, 1, 1, 1))
        self.assertEqual((right_iqa.call_count, right_nafnet.call_count, right_grade.call_count, right_lesion.call_count), (1, 0, 1, 1))

    def test_bilateral_usable_routes_each_restore_once(self):
        first, first_iqa, first_nafnet, _, _, _ = self.run_case("Usable")
        second, second_iqa, second_nafnet, _, _, _ = self.run_case("Usable")
        self.assertEqual((first["state"], second["state"]), ("COMPLETE", "COMPLETE"))
        self.assertEqual((first_iqa.call_count, first_nafnet.call_count), (1, 1))
        self.assertEqual((second_iqa.call_count, second_nafnet.call_count), (1, 1))

    def test_bilateral_reject_does_not_block_good_eye(self):
        left, left_iqa, left_nafnet, left_grade, left_lesion, _ = self.run_case("Reject")
        right, right_iqa, right_nafnet, right_grade, right_lesion, _ = self.run_case("Good")
        self.assertEqual((left["state"], right["state"]), ("RECAPTURE_REQUIRED", "COMPLETE"))
        self.assertEqual((left_iqa.call_count, left_nafnet.call_count, left_grade.call_count, left_lesion.call_count), (1, 0, 0, 0))
        self.assertEqual((right_iqa.call_count, right_nafnet.call_count, right_grade.call_count, right_lesion.call_count), (1, 0, 1, 1))


class AnalysisQueueTests(unittest.TestCase):
    def test_multiple_jobs_are_isolated_and_leave_waiting(self):
        manager = AnalysisJobManager(max_workers=1)
        order = []
        ids = [f"{index:032x}" for index in range(4)]
        try:
            for index, job_id in enumerate(ids):
                manager.create(job_id, "OS" if index % 2 == 0 else "OD")

                def worker(job_id=job_id, index=index):
                    manager.transition(job_id, PipelineState.IQA)
                    time.sleep(0.01)
                    order.append(index)
                    history = manager.get(job_id)["state_history"] + [{"state": "COMPLETE", "at": "test"}]
                    return {"run_id": job_id, "state": "COMPLETE", "state_history": history, "marker": index}

                manager.submit(job_id, worker)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                snapshots = [manager.get(job_id) for job_id in ids]
                if all(item["state"] == "COMPLETE" for item in snapshots):
                    break
                time.sleep(0.01)
            self.assertEqual(order, [0, 1, 2, 3])
            for index, snapshot in enumerate(snapshots):
                self.assertEqual(snapshot["result"]["run_id"], ids[index])
                self.assertEqual(snapshot["result"]["marker"], index)
                self.assertNotIn(snapshot["state"], {"WAITING", "IQA", "RESTORING", "GRADING", "LESION_ANALYSIS"})
        finally:
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()
