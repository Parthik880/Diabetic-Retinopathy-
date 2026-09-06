from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest
from unittest.mock import patch

from PIL import Image

import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.batch import BatchAnalysisManager, discover_input_folder
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
        self.manager = BatchAnalysisManager(registry=self.registry, history=self.history, runs_root=self.runs, logo_path=self.root / "logo.jpg")

    def tearDown(self):
        self.manager.shutdown()
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
