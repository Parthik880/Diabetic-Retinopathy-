from __future__ import annotations

import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from PIL import Image
import torch

import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.batch import BatchAnalysisManager, _batch_size_for_device, discover_input_folder
from app.history import HistoryStore
from inference.pipeline import PipelineState


def make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (18, 12), (32, 96, 64)).save(path)


class FakeRegistry:
    def __init__(self):
        self.models = {name: object() for name in ("quality", "restoration", "grading", "lesion")}
        self.lock = Lock()
        self.device = "cuda"
        self.device_name = "Test GPU"


def completed_result(run_id: str, eye: str, state: str = "COMPLETE") -> dict:
    return {
        "run_id": run_id, "eye": eye, "state": state,
        "state_history": [{"state": "WAITING", "at": "test"}, {"state": state, "at": "test"}],
        "invocation_counts": {"iqa": 1, "nafnet": 0, "grading": 1 if state == "COMPLETE" else 0, "lesions": 1 if state == "COMPLETE" else 0},
        "quality": {"quality": "Good" if state == "COMPLETE" else "Reject", "confidence": 0.91, "probabilities": {}},
        "grading": {"predicted_grade": 2, "confidence": 0.82, "probabilities": []} if state == "COMPLETE" else None,
        "lesions": {"combined_overlay_path": "", "lesions": {"MA": {"num_regions": 2}}} if state == "COMPLETE" else None,
        "analysis_source": "original", "original_image_url": "", "restored_image_url": None,
    }


def fake_export(_destination: Path, *, run_dir: Path, patient: dict, logo_path: Path, report_root: Path) -> dict:
    del logo_path
    result = json.loads((run_dir / "response.json").read_text(encoding="utf-8"))
    eye_folder = report_root / ("Left_OS" if patient["eye"] == "OS" else "Right_OD")
    eye_folder.mkdir(parents=True)
    report = eye_folder / "report.pdf"
    report.write_bytes(b"%PDF-test")
    (eye_folder / "results.json").write_text(json.dumps({
        "report_id": result["run_id"], "pipeline_state": result["state"], "restored_image_file": None,
    }), encoding="utf-8")
    return {"folder": str(report_root), "eye_folder": str(eye_folder), "report": str(report), "files": [str(report)]}


class BatchDiscoveryTests(unittest.TestCase):
    def test_structured_and_simple_modes_find_paired_and_single_eye_patients(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            structured = root / "RH9344_Kate"
            structured.mkdir()
            (structured / "patient.json").write_text(json.dumps({"patient_id": "RH-9344", "name": "Kate", "age": 54}), encoding="utf-8")
            make_image(structured / "left_os.jpg")
            make_image(structured / "right_od.jpg")
            make_image(root / "RH9687_Jonathan_OS.jpg")
            (root / "notes.txt").write_text("ignored invalid input", encoding="utf-8")

            result = discover_input_folder(root)
            self.assertEqual(result["mode"], "mixed")
            self.assertEqual(len(result["patients"]), 2)
            self.assertEqual([len(patient["eyes"]) for patient in result["patients"]], [2, 1])
            self.assertEqual(result["patients"][0]["metadata"]["age"], 54)
            self.assertEqual(len(result["invalid_files"]), 1)

    def test_ten_patients_and_od_only_are_supported(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index in range(10):
                make_image(root / f"RH{1000 + index}_Patient{index}_{'OD' if index == 0 else 'OS'}.jpg")
            result = discover_input_folder(root)
            self.assertEqual(len(result["patients"]), 10)
            self.assertEqual(result["patients"][0]["patient_id"], "RH-1000")
            self.assertIn("OD", result["patients"][0]["eyes"])

    def test_selected_folder_can_itself_be_a_patient_folder(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "patient.json").write_text(json.dumps({"patient_id": "#RH-4242", "name": "BatchQA"}), encoding="utf-8")
            make_image(root / "left_os.jpg")
            make_image(root / "right_od.jpg")

            result = discover_input_folder(root)

            self.assertEqual(result["mode"], "structured")
            self.assertEqual(result["invalid_items"], [])
            self.assertEqual(result["patients"][0]["patient_id"], "RH-4242")
            self.assertEqual(set(result["patients"][0]["eyes"]), {"OS", "OD"})
            self.assertEqual(result["patients"][0]["discovery_status"], "READY")

    def test_structured_folder_without_metadata_and_bare_eye_names(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            patient = root / "RH4242_Kate"
            patient.mkdir()
            make_image(patient / "OS.jpg")
            make_image(patient / "OD.jpg")

            result = discover_input_folder(root)

            self.assertEqual(result["patients"][0]["patient_id"], "RH-4242")
            self.assertEqual(result["patients"][0]["name"], "Kate")
            self.assertEqual(set(result["patients"][0]["eyes"]), {"OS", "OD"})

    def test_flat_names_optional_name_aliases_and_case_insensitive_extensions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_image(root / "RH4242_Kate_OS.JPG")
            make_image(root / "RH4242_Kate_OD.PNG")
            make_image(root / "RH4243_LEFT.TIF")
            make_image(root / "RH4244_RIGHT.TIFF")
            make_image(root / "RH4245_LE.BMP")
            make_image(root / "RH4246_RE.JPEG")

            result = discover_input_folder(root)

            self.assertEqual(len(result["patients"]), 5)
            self.assertEqual(result["patients"][1]["name"], "")
            self.assertIn("OS", result["patients"][1]["eyes"])
            self.assertIn("OD", result["patients"][2]["eyes"])
            self.assertEqual(result["invalid_items"], [])

    def test_id_variants_merge_and_short_aliases_are_terminal_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_image(root / "RH4242_L.jpg")
            make_image(root / "#RH-4242_R.jpg")

            result = discover_input_folder(root)

            self.assertEqual(len(result["patients"]), 1)
            self.assertEqual(result["patients"][0]["patient_id"], "RH-4242")
            self.assertEqual(set(result["patients"][0]["eyes"]), {"OS", "OD"})

    def test_duplicate_eye_needs_review_and_keeps_every_candidate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_image(root / "RH4242_Kate_OS_1.jpg")
            make_image(root / "RH4242_Kate_OS_2.jpg")
            make_image(root / "RH4242_Kate_OD.jpg")

            result = discover_input_folder(root)
            patient = result["patients"][0]

            self.assertEqual(patient["discovery_status"], "NEEDS_REVIEW")
            self.assertEqual(patient["issues"], ["Duplicate OS images"])
            self.assertEqual(len(patient["eye_candidates"]["OS"]), 2)
            self.assertNotIn("OS", patient["eyes"])
            self.assertIn("OD", patient["eyes"])

    def test_unknown_corrupt_and_metadata_errors_have_reasons_but_system_files_are_ignored(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            make_image(root / "RH4242_OD.jpg")
            make_image(root / "RH4242_front.jpg")
            (root / "RH4243_OS.jpg").write_bytes(b"not an image")
            (root / "bad_patient.json").write_text("{broken", encoding="utf-8")
            for name in ("README.txt", "desktop.ini", "Thumbs.db", ".DS_Store"):
                (root / name).write_text("support", encoding="utf-8")

            result = discover_input_folder(root)
            reasons = {item["name"]: item["reason"] for item in result["invalid_items"]}

            self.assertEqual(len(result["invalid_items"]), 3)
            self.assertEqual(reasons["RH4242_front.jpg"], "patient recognized, eye side unknown")
            self.assertEqual(reasons["RH4243_OS.jpg"], "image is corrupt or unreadable")
            self.assertEqual(reasons["bad_patient.json"], "invalid patient metadata JSON")
            self.assertFalse(any(name in reasons for name in ("README.txt", "desktop.ini", "Thumbs.db", ".DS_Store")))

    def test_folder_names_with_spaces_and_unicode_are_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            patient = root / "RH-4242 José Álvarez"
            patient.mkdir()
            make_image(patient / "LEFT_EYE.jpg")

            result = discover_input_folder(root)

            self.assertEqual(result["patients"][0]["patient_id"], "RH-4242")
            self.assertEqual(result["patients"][0]["name"], "José Álvarez")
            self.assertIn("OS", result["patients"][0]["eyes"])


class BatchSizeTests(unittest.TestCase):
    def test_vram_bytes_are_converted_to_mb_and_fractional_results_are_floored(self):
        for vram_mb, expected in ((4096, 66), (8192, 90), (12288, 115), (12890.25, 119), (1 / 1048576, 41)):
            with (
                self.subTest(vram_mb=vram_mb),
                patch("app.batch.torch.cuda.is_available", return_value=True),
                patch("app.batch.torch.cuda.get_device_properties", return_value=SimpleNamespace(total_memory=vram_mb * 1048576)) as properties,
                self.assertLogs("uvicorn.error", level="INFO") as logs,
            ):
                self.assertEqual(_batch_size_for_device("cuda:1"), expected)
                properties.assert_called_once_with(torch.device("cuda:1"))
                self.assertIn(f"Calculated batch size: {expected}", logs.output[-1])
                self.assertIn("Detected GPU VRAM:", logs.output[0])

    def test_cpu_or_unavailable_cuda_keeps_single_image_fallback_without_querying_vram(self):
        for device, available in (("cpu", True), ("cpu", False), ("cuda:0", False)):
            with (
                self.subTest(device=device, available=available),
                patch("app.batch.torch.cuda.is_available", return_value=available),
                patch("app.batch.torch.cuda.get_device_properties") as properties,
            ):
                self.assertEqual(_batch_size_for_device(device), 1)
                properties.assert_not_called()

    def test_invalid_vram_or_detection_errors_fall_back_without_fake_gpu_logs(self):
        for memory in (0, -1, float("nan"), float("inf"), None, "unknown"):
            with (
                self.subTest(memory=memory),
                patch("app.batch.torch.cuda.is_available", return_value=True),
                patch("app.batch.torch.cuda.get_device_properties", return_value=SimpleNamespace(total_memory=memory)),
                self.assertLogs("uvicorn.error", level="WARNING") as logs,
            ):
                self.assertEqual(_batch_size_for_device("cuda:0"), 1)
                self.assertNotIn("Detected GPU VRAM:", " ".join(logs.output))
        for function in ("is_available", "get_device_properties"):
            with (
                self.subTest(function=function),
                patch("app.batch.torch.cuda.is_available", return_value=True),
                patch(f"app.batch.torch.cuda.{function}", side_effect=RuntimeError("CUDA driver error")),
                self.assertLogs("uvicorn.error", level="WARNING"),
            ):
                self.assertEqual(_batch_size_for_device("cuda:0"), 1)

    @unittest.skipUnless(torch.cuda.is_available(), "Requires a CUDA-enabled test runtime")
    def test_actual_cuda_vram_and_tensor_execution(self):
        import math

        device = torch.device("cuda:0")
        vram_mb = torch.cuda.get_device_properties(device).total_memory / 1048576
        self.assertGreater(vram_mb, 0)
        self.assertEqual(_batch_size_for_device(device), max(1, math.floor(0.006 * vram_mb + 41.66)))
        tensor = torch.ones((16, 16), device=device)
        self.assertEqual((tensor @ tensor).sum().item(), 4096)


class BatchManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "input"
        self.output = self.root / "output"
        self.runs = self.root / "runs"
        self.input.mkdir(); self.output.mkdir(); self.runs.mkdir()
        self.history = HistoryStore(self.root / "history.json")
        self.registry = FakeRegistry()
        self.capacity_patch = patch("app.batch._gpu_capacity", return_value={
            "available": True, "name": "Test GPU", "vram_mb": 12288.0, "max_batch_size": 115,
        })
        self.capacity_patch.start()
        self.manager = BatchAnalysisManager(registry=self.registry, history=self.history, runs_root=self.runs, logo_path=self.root / "logo.jpg")

    def tearDown(self):
        self.manager.shutdown()
        self.capacity_patch.stop()
        self.temp.cleanup()

    def wait_terminal(self, batch_id: str) -> dict:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = self.manager.get(batch_id)
            if value["state"] in {"Completed", "Cancelled", "Failed"}:
                return value
            time.sleep(0.01)
        self.fail("Batch did not reach a terminal state")

    def test_duplicate_eye_selection_is_resolved_before_start(self):
        make_image(self.input / "RH300_Kate_OS_1.jpg")
        selected = self.input / "RH300_Kate_OS_2.jpg"
        make_image(selected)
        make_image(self.input / "RH300_Kate_OD.jpg")
        discovered = self.manager.discover(self.input)
        calls = []

        def analyze(*, original_path, registry, run_id, runs_root, eye, on_state):
            del registry, runs_root
            calls.append((eye, Image.open(original_path).getpixel((0, 0))))
            on_state(PipelineState.IQA_GOOD)
            result = completed_result(run_id, eye)
            (original_path.parent / "response.json").write_text(json.dumps(result), encoding="utf-8")
            return result

        with patch("app.batch.run_analysis_pipeline", side_effect=analyze), patch("app.batch.export_report_bundle", side_effect=fake_export):
            self.manager.start(
                discovered["batch_id"], self.output, selections={"RH-300": {"OS": str(selected.resolve())}}, skip_unresolved=False,
            )
            final = self.wait_terminal(discovered["batch_id"])

        self.assertEqual(final["patients"][0]["discovery_status"], "READY")
        self.assertEqual([eye for eye, _pixel in calls], ["OS", "OD"])
        self.assertEqual(final["patients"][0]["eyes"]["OS"]["source_name"], selected.name)

    def test_five_patients_enter_one_real_tensor_batch_together(self):
        shapes, forwards, status_at_forward = {}, {name: 0 for name in ("iqa", "grading", "lesion")}, []
        forward_entered, polled_statuses = Event(), []
        for index in range(5):
            make_image(self.input / f"RH{5000 + index}_Patient{index}_OS.jpg")

        class QualityModel:
            def predict_batch(_self, images, **_kwargs):
                tensor = torch.stack([torch.zeros(3, 224, 224) for _ in images])
                shapes["iqa"] = list(tensor.shape)
                forwards["iqa"] += 1
                status_at_forward.append([patient["status"] for patient in self.manager.get(batch_id)["patients"]])
                forward_entered.set()
                logging.getLogger("uvicorn.error").info("IQA tensor shape: %s", shapes["iqa"])
                return [{"class_id": 0, "quality": "Good", "confidence": 0.9,
                         "probabilities": {"Good": 0.9, "Usable": 0.08, "Reject": 0.02}}
                        for _ in images]

        self.registry.models["quality"] = QualityModel()
        discovered = self.manager.discover(self.input)
        batch_id = discovered["batch_id"]

        def grade(paths, _model, _outputs, **_kwargs):
            tensor = torch.stack([torch.zeros(3, 224, 224) for _ in paths])
            shapes["grading"] = list(tensor.shape)
            forwards["grading"] += 1
            logging.getLogger("uvicorn.error").info("Grade tensor shape: %s", shapes["grading"])
            return [{"predicted_class": index, "predicted_grade": index, "confidence": 0.8,
                     "probabilities": [0.2] * 5, "image_path": str(path)}
                    for index, path in enumerate(paths)]

        def lesion(paths, _model, _outputs, callbacks, **_kwargs):
            tensor = torch.stack([torch.zeros(3, 768, 768) for _ in paths])
            shapes["lesion"] = list(tensor.shape)
            forwards["lesion"] += 1
            logging.getLogger("uvicorn.error").info("Lesion tensor shape: %s", shapes["lesion"])
            for callback in callbacks:
                callback("LESION_INFERENCE")
            return [{"lesions": {}, "image": str(path)} for path in paths]

        with (
            patch("app.batch._batch_size_for_device", return_value=115),
            patch("inference.batch_pipeline.grading.predict_batch", side_effect=grade),
            patch("inference.batch_pipeline.lesions.predict_batch", side_effect=lesion),
            patch("app.batch.export_report_bundle", side_effect=fake_export),
            patch.object(self.manager, "_run_eye", side_effect=AssertionError("per-patient GPU path used")),
            self.assertLogs("uvicorn.error", level="INFO") as logs,
        ):
            def poll():
                while not forward_entered.is_set():
                    polled_statuses.append([patient["status"] for patient in self.manager.get(batch_id)["patients"]])

            poller = Thread(target=poll)
            poller.start()
            self.manager.start(batch_id, self.output)
            final = self.wait_terminal(batch_id)
            forward_entered.set()
            poller.join()

        self.assertEqual(shapes, {"iqa": [5, 3, 224, 224], "grading": [5, 3, 224, 224],
                                  "lesion": [5, 3, 768, 768]})
        self.assertEqual(forwards, {"iqa": 1, "grading": 1, "lesion": 1})
        self.assertEqual(status_at_forward, [["Processing"] * 5])
        self.assertTrue(polled_statuses)
        self.assertTrue(all(sum(status == "Processing" for status in snapshot) in {0, 5}
                            for snapshot in polled_statuses))
        self.assertEqual([patient["status"] for patient in final["patients"]], ["Completed"] * 5)
        records = {record["patient_id"]: record for record in self.history.list()}
        self.assertEqual([records[f"RH-{5000 + index}"]["left_eye"]["result_data"]["grading"]["predicted_grade"]
                          for index in range(5)], list(range(5)))
        joined_logs = " ".join(logs.output)
        self.assertIn("GPU mini-batch entered: 5 items", joined_logs)
        for stage in range(1, 5):
            self.assertIn(f"STAGE {stage} PROFILE", joined_logs)
        self.assertEqual(joined_logs.count("GPU mini-batch entered:"), 1)
        for shape in shapes.values():
            self.assertIn(str(shape), joined_logs)

    def test_110_images_run_as_one_operation_without_queued_state(self):
        sizes = []
        for index in range(110):
            make_image(self.input / f"RH{7000 + index}_Patient_OS.jpg")

        class QualityModel:
            def predict_batch(_self, images, **_kwargs):
                sizes.append(("iqa", len(images)))
                return [{"quality": "Good", "confidence": 1.0, "probabilities": {}} for _ in images]

        self.registry.models["quality"] = QualityModel()
        discovered = self.manager.discover(self.input)

        def grade(paths, _model, _outputs, **_kwargs):
            sizes.append(("grade", len(paths)))
            return [{"predicted_grade": 0, "confidence": 1.0, "probabilities": [1, 0, 0, 0, 0]} for _ in paths]

        def lesion(paths, _model, _outputs, _callbacks, **_kwargs):
            sizes.append(("lesion", len(paths)))
            return [{"lesions": {}} for _ in paths]

        with patch("inference.batch_pipeline.grading.predict_batch", side_effect=grade), \
             patch("inference.batch_pipeline.lesions.predict_batch", side_effect=lesion), \
             patch("app.batch.export_report_bundle", side_effect=fake_export):
            started = self.manager.start(discovered["batch_id"], self.output)
            self.assertEqual({patient["status"] for patient in started["patients"]}, {"Processing"})
            self.assertNotIn("Queued", json.dumps(started))
            final = self.wait_terminal(discovered["batch_id"])

        self.assertEqual(sizes, [("iqa", 110), ("grade", 110), ("lesion", 110)])
        self.assertEqual(final["counts"]["completed"], 110)
        self.assertEqual(final["stage_index"], 4)
        self.assertEqual(final["progress_percent"], 100)

    def test_capacity_accepts_115_and_rejects_116_and_150_before_inference(self):
        for index in range(115):
            make_image(self.input / f"RH{8000 + index}_Patient_OS.jpg")
        accepted = self.manager.discover(self.input)
        with patch.object(self.manager._scheduler, "submit") as submit:
            snapshot = self.manager.start(accepted["batch_id"], self.output)
        submit.assert_called_once()
        self.assertEqual(snapshot["gpu_capacity"]["max_batch_size"], 115)
        self.assertEqual({patient["status"] for patient in snapshot["patients"]}, {"Processing"})

        for count in (116, 150):
            folder = self.root / f"input-{count}"
            folder.mkdir()
            for index in range(count):
                make_image(folder / f"RH{9000 + index}_Patient_OS.jpg")
            rejected = self.manager.discover(folder)
            with self.subTest(count=count), patch.object(self.manager._scheduler, "submit") as submit:
                with self.assertRaisesRegex(ValueError, rf"supports up to 115.*contains {count}"):
                    self.manager.start(rejected["batch_id"], self.output)
                submit.assert_not_called()
            self.assertEqual(self.manager.get(rejected["batch_id"])["state"], "Review")

    def test_cuda_unavailable_has_no_invented_capacity(self):
        make_image(self.input / "RH9999_Patient_OS.jpg")
        with patch("app.batch._gpu_capacity", return_value={
            "available": False, "name": "CPU", "vram_mb": None, "max_batch_size": None,
        }):
            discovered = self.manager.discover(self.input)
        self.assertIsNone(discovered["gpu_capacity"]["vram_mb"])
        self.assertIsNone(discovered["gpu_capacity"]["max_batch_size"])
        with self.assertRaisesRegex(ValueError, "GPU batch analysis is unavailable"):
            self.manager.start(discovered["batch_id"], self.output)

    def test_full_pipeline_cpu_and_cuda_preserve_progress_results_and_pause_resume(self):
        from threading import Event

        make_image(self.input / "RH800_Kate_OS.jpg")
        make_image(self.input / "RH800_Kate_OD.jpg")
        self.registry.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        discovered = self.manager.discover(self.input)
        entered, release = Event(), Event()
        devices = []

        def quality_predict(image, model):
            devices.append(str(torch.ones(1, device=self.registry.device).device))
            if len(devices) == 1:
                entered.set()
                self.assertTrue(release.wait(5))
            return {"class_id": 0, "quality": "Good", "confidence": 0.91}

        with (
            patch("inference.pipeline.quality.predict", side_effect=quality_predict),
            patch("inference.pipeline.grading.predict", return_value={"predicted_grade": 2, "confidence": 0.82}),
            patch("inference.pipeline.lesions.predict", return_value={"lesions": {}, "forward_count": 1}),
            patch("app.batch.torch.cuda.get_device_properties", wraps=torch.cuda.get_device_properties) as properties,
        ):
            self.manager.start(discovered["batch_id"], self.output)
            try:
                self.assertTrue(entered.wait(5))
                pausing = self.manager.pause(discovered["batch_id"])
                self.assertEqual(pausing["state"], "Pausing")
                self.assertEqual(pausing["currently_processing"]["stage"], "IQA")
                release.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    paused = self.manager.get(discovered["batch_id"])
                    if paused["state"] == "Paused":
                        break
                    time.sleep(0.01)
                self.assertEqual(paused["state"], "Paused")
                self.assertTrue(paused["can_resume"])
            finally:
                release.set()
                self.manager.resume(discovered["batch_id"])
            final = self.wait_terminal(discovered["batch_id"])
            # Capacity is detected and cached during discovery, before this start-time patch.
            self.assertEqual(properties.call_count, 0)

        self.assertEqual(devices, [str(self.registry.device)] * 2)
        self.assertEqual(final["state"], "Completed")
        self.assertEqual(final["counts"]["completed"], 1)
        self.assertFalse(final["can_pause"] or final["can_resume"] or final["can_cancel"])
        self.assertEqual(final["patients"][0]["progress"], "2/2")
        for eye in ("OS", "OD"):
            result = self.history.list()[0]["left_eye" if eye == "OS" else "right_eye"]["result_data"]
            self.assertEqual(result["invocation_counts"], {"iqa": 1, "nafnet": 0, "grading": 1, "lesions": 1})
            self.assertEqual(result["device"], str(self.registry.device))
            self.assertTrue(Path(final["patients"][0]["eyes"][eye]["report_path"]).is_file())

    def test_failed_eye_does_not_block_other_eye_and_history_gets_one_session(self):
        make_image(self.input / "RH100_Kate_OS.jpg")
        make_image(self.input / "RH100_Kate_OD.jpg")
        discovered = self.manager.discover(self.input)
        registry_ids = []

        def analyze(*, original_path, registry, run_id, runs_root, eye, on_state):
            del runs_root
            registry_ids.append(id(registry))
            on_state(PipelineState.IQA)
            if eye == "OS":
                raise RuntimeError("controlled eye failure")
            result = completed_result(run_id, eye)
            (original_path.parent / "response.json").write_text(json.dumps(result), encoding="utf-8")
            return result

        with patch("app.batch.run_analysis_pipeline", side_effect=analyze), patch("app.batch.export_report_bundle", side_effect=fake_export):
            self.manager.start(discovered["batch_id"], self.output)
            final = self.wait_terminal(discovered["batch_id"])

        patient = final["patients"][0]
        self.assertEqual(patient["status"], "Failed")
        self.assertEqual(patient["eyes"]["OS"]["status"], "Failed")
        self.assertEqual(patient["eyes"]["OD"]["status"], "Completed")
        self.assertEqual(registry_ids, [id(self.registry), id(self.registry)])
        self.assertEqual(len(self.history.list()), 1)
        self.assertTrue(self.history.list()[0]["right_eye"]["completed"])
        self.assertTrue((Path(final["output_root"]) / "batch_summary.csv").is_file())

    def test_reject_and_resume_skip_completed_eye(self):
        make_image(self.input / "RH200_Amina_OS.jpg")
        make_image(self.input / "RH200_Amina_OD.jpg")
        prior = self.output / "Batch_Results_20260906_010101"
        eye_folder = prior / "RH-200_Amina" / "Left_OS"
        eye_folder.mkdir(parents=True)
        (prior / ".batch_state.json").write_text(json.dumps({"input_path": str(self.input.resolve()), "state": "Cancelled"}), encoding="utf-8")
        prior_result = completed_result("a" * 32, "OS")
        (eye_folder / "results.json").write_text(json.dumps({"report_id": "a" * 32, "pipeline_state": "COMPLETE"}), encoding="utf-8")
        (eye_folder / ".analysis_result.json").write_text(json.dumps(prior_result), encoding="utf-8")
        (eye_folder / "report.pdf").write_bytes(b"%PDF-existing")
        discovered = self.manager.discover(self.input)
        calls = []

        def reject(*, original_path, registry, run_id, runs_root, eye, on_state):
            del registry, runs_root
            calls.append(eye)
            on_state(PipelineState.IQA_REJECTED)
            result = completed_result(run_id, eye, "RECAPTURE_REQUIRED")
            (original_path.parent / "response.json").write_text(json.dumps(result), encoding="utf-8")
            return result

        with patch("app.batch.run_analysis_pipeline", side_effect=reject), patch("app.batch.export_report_bundle", side_effect=fake_export):
            self.manager.start(discovered["batch_id"], self.output)
            final = self.wait_terminal(discovered["batch_id"])

        self.assertEqual(Path(final["output_root"]), prior)
        self.assertEqual(calls, ["OD"])
        self.assertEqual(final["patients"][0]["eyes"]["OS"]["status"], "Completed")
        self.assertEqual(final["patients"][0]["eyes"]["OD"]["status"], "Recapture Required")
        self.assertTrue((prior / "RH-200_Amina" / "Right_OD" / "results.json").is_file())


if __name__ == "__main__":
    unittest.main()
