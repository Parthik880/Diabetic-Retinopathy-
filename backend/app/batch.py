"""Bounded, resumable orchestration for RetinaGram batch analysis."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from copy import deepcopy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from threading import Condition, Lock, RLock
from uuid import uuid4

from PIL import Image

from inference.pipeline import PipelineState, run_analysis_pipeline
from utils.reporting import export_report_bundle, sanitize_windows_name


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}
IGNORED_SUPPORT_FILES = {"desktop.ini", "thumbs.db", ".ds_store"}
TERMINAL_EYE_STATES = {"Completed", "Recapture Required", "Failed"}
ACTIVE_BATCH_STATES = {"Processing", "Pausing", "Paused", "Cancelling"}
CSV_FIELDS = [
    "patient_id", "patient_name", "session_id", "eye", "iqa_class",
    "iqa_confidence", "dr_grade", "dr_confidence", "lesion_count",
    "status", "report_path",
]

STAGE_LOG_LABELS = {
    PipelineState.WAITING: "Image loaded",
    PipelineState.IQA: "Image quality assessment",
    PipelineState.IQA_GOOD: "IQA complete: good quality",
    PipelineState.IQA_USABLE: "IQA complete: restoration required",
    PipelineState.IQA_REJECTED: "IQA complete: recapture required",
    PipelineState.RESTORING: "Restoration started",
    PipelineState.RESTORATION_COMPLETE: "Restoration complete",
    PipelineState.GRADING: "DR grading",
    PipelineState.LESION_ANALYSIS: "Lesion analysis",
    PipelineState.LESION_INFERENCE: "Lesion inference",
    PipelineState.LESION_MASK_PROCESSING: "Processing lesion masks",
    PipelineState.LESION_REGION_EXTRACTION: "Extracting lesion regions",
    PipelineState.LESION_RESULTS_SAVING: "Saving lesion results",
    PipelineState.PREPARING_RESULTS: "Preparing results",
    PipelineState.COMPLETE: "Analysis pipeline complete",
    PipelineState.RECAPTURE_REQUIRED: "Recapture required",
    PipelineState.FAILED: "Analysis failed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _display_time() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")


def _normalize_patient_id(value: object) -> str:
    text = str(value or "").strip().lstrip("#").strip()
    matched = re.fullmatch(r"([A-Za-z]+)[\s_-]?(\d+)", text)
    return f"{matched.group(1).upper()}-{matched.group(2)}" if matched else text


def _folder_identity(name: str) -> tuple[str, str]:
    matched = re.fullmatch(r"\s*#?([A-Za-z]+)[\s_-]?(\d+)(.*)", name)
    if matched is None:
        return "", ""
    patient_id = _normalize_patient_id(f"{matched.group(1)}{matched.group(2)}")
    patient_name = re.sub(r"\s+", " ", matched.group(3).strip(" _-").replace("_", " ")).strip()
    return patient_id, patient_name


def _canonical_eye(alias: str) -> str:
    normalized = re.sub(r"[^A-Z]", "", alias.upper())
    return "OS" if normalized in {"OS", "LEFT", "LEFTEYE", "LE", "L"} else "OD"


def _eye_from_name(path: Path) -> str | None:
    stem = path.stem.upper()
    tokens = [token for token in re.split(r"[^A-Z0-9]+", stem) if token]
    joined = "_".join(tokens)
    sides: set[str] = set()
    if "LEFT_EYE" in joined or any(token in {"OS", "LEFT", "LE"} for token in tokens):
        sides.add("OS")
    if "RIGHT_EYE" in joined or any(token in {"OD", "RIGHT", "RE"} for token in tokens):
        sides.add("OD")
    # One-letter aliases are accepted only as a complete or terminal token.
    if (tokens and tokens[-1] in {"L", "R"}) or (len(tokens) > 1 and tokens[-1].isdigit() and tokens[-2] in {"L", "R"}):
        alias = tokens[-2] if tokens[-1].isdigit() else tokens[-1]
        sides.add(_canonical_eye(alias))
    return next(iter(sides)) if len(sides) == 1 else None


FLAT_IMAGE_PATTERN = re.compile(r"^\s*#?([A-Za-z]+)[\s_-]?(\d+)(.*)$", re.IGNORECASE)
EYE_SUFFIX_PATTERN = re.compile(
    r"(?:^|[\s_-])(LEFT(?:[\s_-]?EYE)?|RIGHT(?:[\s_-]?EYE)?|OS|OD|LE|RE|L|R)(?:[\s_-]?\d+)?\s*$",
    re.IGNORECASE,
)


def _flat_identity(path: Path) -> tuple[str, str, str | None]:
    matched = FLAT_IMAGE_PATTERN.fullmatch(path.stem)
    if matched is None:
        return "", "", None
    patient_id = _normalize_patient_id(f"{matched.group(1)}{matched.group(2)}")
    remainder = matched.group(3)
    eye_match = EYE_SUFFIX_PATTERN.search(remainder)
    if eye_match is None:
        return patient_id, "", None
    patient_name = re.sub(r"\s+", " ", remainder[:eye_match.start()].strip(" _-").replace("_", " ")).strip()
    return patient_id, patient_name, _canonical_eye(eye_match.group(1))


def _is_ignored_support_file(path: Path) -> bool:
    name = path.name.casefold()
    return name in IGNORED_SUPPORT_FILES or name.startswith("readme.")


def _invalid_item(path: Path, reason: str) -> dict:
    return {"path": str(path.resolve()), "name": path.name, "reason": reason}


def _validate_image(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            image.verify()
    except (OSError, ValueError, SyntaxError):
        return "image is corrupt or unreadable"
    return None


def _new_eye(eye: str, path: Path) -> dict:
    return {
        "eye": eye,
        "source_path": str(path.resolve()),
        "source_name": path.name,
        "status": "Queued",
        "stage": PipelineState.WAITING.value,
        "quality_route": None,
        "run_id": None,
        "result": None,
        "report_path": None,
        "error": None,
    }


def _public_patient(patient: dict) -> dict:
    return {
        "index": patient["index"],
        "patient_id": patient["patient_id"],
        "name": patient["name"],
        "images": [eye for eye in ("OS", "OD") if patient["eye_candidates"].get(eye)],
        "status": patient["status"],
        "discovery_status": patient["discovery_status"],
        "issues": list(patient["issues"]),
        "eye_candidates": {
            eye: [{"source_name": item["source_name"], "source_path": item["source_path"]} for item in candidates]
            for eye, candidates in patient["eye_candidates"].items()
        },
        "progress": f"{sum(1 for eye in patient['eyes'].values() if eye['status'] in {'Completed', 'Recapture Required'})}/{len(patient['eyes'])}",
        "eyes": {
            key: {field: value for field, value in eye.items() if field not in {"source_path", "result"}}
            for key, eye in patient["eyes"].items()
        },
    }


def _read_patient_metadata(folder: Path) -> tuple[dict, dict | None]:
    metadata_path = folder / "patient.json"
    if not metadata_path.is_file():
        return {}, None
    try:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, _invalid_item(metadata_path, "invalid patient metadata JSON")
    if not isinstance(value, dict):
        return {}, _invalid_item(metadata_path, "patient metadata must be a JSON object")
    return value, None


def discover_input_folder(input_path: Path) -> dict:
    """Discover flexible structured and flat patient-image layouts."""
    root = input_path.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("The selected input folder does not exist.")

    invalid_items: list[dict] = []
    discovery_logs: list[dict] = []
    patients: dict[str, dict] = {}

    def log(patient_id: str, eye: str | None, message: str) -> None:
        discovery_logs.append({"time": _display_time(), "patient_id": patient_id, "eye": eye, "message": message})

    def reject(path: Path, reason: str) -> None:
        invalid_items.append(_invalid_item(path, reason))
        log("Batch", None, f"rejected {path.name}: {reason}")

    def ensure_patient(patient_id: str, name: str, metadata: dict | None = None) -> dict:
        key = patient_id.casefold()
        item = patients.get(key)
        if item is None:
            item = {
                "index": 0,
                "patient_id": patient_id,
                "name": name,
                "metadata": deepcopy(metadata or {}),
                "session_id": uuid4().hex,
                "eyes": {},
                "eye_candidates": {"OS": [], "OD": []},
                "issues": [],
                "hard_invalid": False,
                "discovery_status": "READY",
                "status": "Queued",
            }
            patients[key] = item
        else:
            if not item["name"] and name:
                item["name"] = name
            elif name and item["name"] and item["name"].casefold() != name.casefold():
                issue = f"Conflicting patient names: {item['name']} / {name}"
                if issue not in item["issues"]:
                    item["issues"].append(issue)
            item["metadata"].update({key: value for key, value in (metadata or {}).items() if value not in (None, "")})
        return item

    def add_image(patient: dict, eye: str, path: Path) -> None:
        reason = _validate_image(path)
        log("Batch", None, f"image found: {path}")
        if reason:
            reject(path, reason)
            return
        patient["eye_candidates"][eye].append(_new_eye(eye, path))
        log(patient["patient_id"], eye, f"patient={patient['patient_id']} eye={eye}")

    def process_structured_folder(folder: Path) -> None:
        inferred_id, inferred_name = _folder_identity(folder.name)
        metadata, metadata_error = _read_patient_metadata(folder)
        patient_id = _normalize_patient_id(metadata.get("patient_id")) or inferred_id
        name = str(metadata.get("name") or inferred_name).strip()
        files = [item for item in folder.iterdir() if item.is_file()]
        images = [item for item in files if item.suffix.casefold() in IMAGE_EXTENSIONS]
        if metadata_error:
            invalid_items.append(metadata_error)
            log("Batch", None, f"rejected {metadata_error['name']}: {metadata_error['reason']}")
        if not patient_id:
            for image in images:
                reject(image, "could not determine patient ID")
            if not images:
                reject(folder, "could not determine patient ID or find retinal images")
            return
        patient = ensure_patient(patient_id, name, metadata)
        if metadata_error:
            patient["hard_invalid"] = True
        for image in sorted(images, key=lambda item: item.name.casefold()):
            eye = _eye_from_name(image)
            if eye is None:
                reject(image, "patient recognized, eye side unknown")
            else:
                add_image(patient, eye, image)
        for item in files:
            if item in images or item.name.casefold() == "patient.json" or _is_ignored_support_file(item):
                continue
            if item.suffix.casefold() == ".json" and "patient" in item.stem.casefold():
                try:
                    json.loads(item.read_text(encoding="utf-8"))
                    reject(item, "metadata file must be named patient.json")
                except (OSError, json.JSONDecodeError):
                    reject(item, "invalid patient metadata JSON")
            else:
                reject(item, "unsupported file type")

    log("Batch", None, f"scanning: {root}")
    root_files = [item for item in root.iterdir() if item.is_file()]
    root_images = [item for item in root_files if item.suffix.casefold() in IMAGE_EXTENSIONS]
    root_id, _ = _folder_identity(root.name)
    root_metadata_exists = (root / "patient.json").is_file()
    root_is_patient = root_metadata_exists or bool(root_id and any(_eye_from_name(image) for image in root_images) and not any(_flat_identity(image)[2] for image in root_images))

    # The selected folder itself may be a single patient folder.
    if root_is_patient:
        process_structured_folder(root)

    # Structured mode: each immediate subfolder is one patient.
    folders = sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name.casefold())
    for folder in folders:
        process_structured_folder(folder)

    # Simple filename mode at the selected folder root.
    if not root_is_patient:
        for item in sorted(root_files, key=lambda entry: entry.name.casefold()):
            if item.name.casefold() == "patient.json" or _is_ignored_support_file(item):
                continue
            if item.suffix.casefold() not in IMAGE_EXTENSIONS:
                if item.suffix.casefold() == ".json" and "patient" in item.stem.casefold():
                    try:
                        json.loads(item.read_text(encoding="utf-8"))
                        reject(item, "metadata file is not associated with a patient folder")
                    except (OSError, json.JSONDecodeError):
                        reject(item, "invalid patient metadata JSON")
                else:
                    reject(item, "unsupported file type")
                continue
            patient_id, name, eye = _flat_identity(item)
            if not patient_id:
                reject(item, "could not determine patient ID or eye")
                continue
            if eye is None:
                reject(item, "patient recognized, eye side unknown")
                continue
            patient = ensure_patient(patient_id, name)
            add_image(patient, eye, item)

    detected = list(patients.values())
    for index, patient in enumerate(detected, 1):
        patient["index"] = index
        for eye, candidates in patient["eye_candidates"].items():
            if len(candidates) == 1:
                patient["eyes"][eye] = candidates[0]
            elif len(candidates) > 1:
                patient["issues"].append(f"Duplicate {eye} images")
        if patient["hard_invalid"] or not any(patient["eye_candidates"].values()):
            patient["discovery_status"] = "INVALID"
            patient["status"] = "Invalid"
        elif patient["issues"]:
            patient["discovery_status"] = "NEEDS_REVIEW"
            patient["status"] = "Needs Review"
        else:
            patient["discovery_status"] = "READY"
            patient["status"] = "Queued"

    ready = sum(patient["discovery_status"] == "READY" for patient in detected)
    review = sum(patient["discovery_status"] == "NEEDS_REVIEW" for patient in detected)
    invalid = len(invalid_items)
    log("Batch", None, f"{ready} patient{'s' if ready != 1 else ''} ready")
    log("Batch", None, f"{review} need review")
    log("Batch", None, f"{invalid} invalid")

    if root_is_patient and folders:
        mode = "mixed"
    elif root_is_patient or folders and not root_images:
        mode = "structured"
    elif folders and root_images:
        mode = "mixed"
    else:
        mode = "simple"

    return {
        "input_path": str(root),
        "patients": detected,
        "invalid_files": [item["path"] for item in invalid_items],
        "invalid_items": invalid_items,
        "logs": discovery_logs,
        "mode": mode,
    }


class BatchAnalysisManager:
    """Own one scheduling lane and a small CPU finalization pool."""

    def __init__(self, *, registry, history, runs_root: Path, logo_path: Path):
        self.registry = registry
        self.history = history
        self.runs_root = runs_root
        self.logo_path = logo_path
        self._scheduler = ThreadPoolExecutor(max_workers=1, thread_name_prefix="retina-batch")
        self._cpu = ThreadPoolExecutor(max_workers=2, thread_name_prefix="retina-batch-output")
        self._lock = RLock()
        self._io_lock = Lock()
        self._condition = Condition(self._lock)
        self._batches: dict[str, dict] = {}

    def discover(self, input_path: Path) -> dict:
        discovered = discover_input_folder(input_path)
        batch_id = uuid4().hex
        batch = {
            "batch_id": batch_id,
            "state": "Review",
            "created_at": _now(),
            "updated_at": _now(),
            "input_path": discovered["input_path"],
            "output_root": None,
            "mode": discovered["mode"],
            "patients": discovered["patients"],
            "invalid_files": discovered["invalid_files"],
            "invalid_items": discovered["invalid_items"],
            "logs": discovered["logs"],
            "currently_processing": None,
            "pause_requested": False,
            "cancel_requested": False,
            "error": None,
        }
        with self._lock:
            self._batches[batch_id] = batch
        return self.get(batch_id)

    def _log(self, batch: dict, patient_id: str, eye: str | None, message: str) -> None:
        with self._lock:
            batch["logs"].append({"time": _display_time(), "patient_id": patient_id, "eye": eye, "message": message})
            batch["logs"] = batch["logs"][-200:]
            batch["updated_at"] = _now()

    def _counts(self, batch: dict) -> dict:
        patients = batch["patients"]
        statuses = [patient["status"] for patient in patients]
        return {
            "total_patients": len(patients),
            "total_images": sum(sum(len(candidates) for candidates in patient["eye_candidates"].values()) for patient in patients),
            "paired_patients": sum(all(patient["eye_candidates"].get(eye) for eye in ("OS", "OD")) for patient in patients),
            "single_eye_patients": sum(sum(bool(patient["eye_candidates"].get(eye)) for eye in ("OS", "OD")) == 1 for patient in patients),
            "invalid_files": len(batch["invalid_files"]),
            "ready": sum(patient["discovery_status"] == "READY" for patient in patients),
            "needs_review": sum(patient["discovery_status"] == "NEEDS_REVIEW" for patient in patients),
            "invalid": len(batch["invalid_items"]),
            "completed": statuses.count("Completed"),
            "processing": sum(status in {"Processing", "Finalizing"} for status in statuses),
            "queued": statuses.count("Queued"),
            "recapture_required": statuses.count("Recapture Required"),
            "failed": statuses.count("Failed"),
        }

    def get(self, batch_id: str) -> dict | None:
        with self._lock:
            batch = self._batches.get(batch_id)
            if batch is None:
                return None
            public = {key: deepcopy(value) for key, value in batch.items() if key not in {"pause_requested", "cancel_requested"}}
            public["patients"] = [_public_patient(patient) for patient in batch["patients"]]
            public["counts"] = self._counts(batch)
            public["can_pause"] = batch["state"] == "Processing"
            public["can_resume"] = batch["state"] == "Paused"
            public["can_cancel"] = batch["state"] in ACTIVE_BATCH_STATES
            return public

    def start(
        self,
        batch_id: str,
        output_path: Path,
        create_patient_folders: bool = True,
        selections: dict | None = None,
        skip_unresolved: bool = True,
    ) -> dict:
        output = output_path.expanduser().resolve()
        if not output.is_dir():
            raise ValueError("The selected output folder does not exist.")
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            if batch["state"] != "Review":
                raise ValueError("This batch has already been started.")
            selections = selections if isinstance(selections, dict) else {}
            runnable = 0
            for patient in batch["patients"]:
                if patient["discovery_status"] == "NEEDS_REVIEW":
                    patient_choices = selections.get(patient["patient_id"], {})
                    patient_choices = patient_choices if isinstance(patient_choices, dict) else {}
                    unresolved_duplicates = False
                    for eye, candidates in patient["eye_candidates"].items():
                        if len(candidates) <= 1:
                            continue
                        selected_path = str(patient_choices.get(eye) or "")
                        selected = next((item for item in candidates if item["source_path"] == selected_path), None)
                        if selected is None:
                            unresolved_duplicates = True
                        else:
                            patient["eyes"][eye] = selected
                    non_duplicate_issues = [issue for issue in patient["issues"] if not issue.startswith("Duplicate ")]
                    if not unresolved_duplicates and not non_duplicate_issues:
                        patient["discovery_status"] = "READY"
                        patient["status"] = "Queued"
                        patient["issues"] = []
                if patient["discovery_status"] == "READY":
                    runnable += 1
                elif skip_unresolved:
                    patient["status"] = "Skipped"
                    for eye_data in patient["eyes"].values():
                        if eye_data["status"] == "Queued":
                            eye_data["status"] = "Skipped"
                    self._log(batch, patient["patient_id"], None, f"Skipped unresolved patient: {'; '.join(patient['issues']) or patient['discovery_status']}")
                else:
                    raise ValueError(f"Resolve or skip {patient['patient_id']} before starting the batch.")
            if not runnable:
                raise ValueError("No READY patients are available to start.")
            batch["state"] = "Processing"
            batch["create_patient_folders"] = bool(create_patient_folders)
            batch["output_root"] = str(self._select_output_root(output, batch))
            self._write_manifest(batch)
            self._log(batch, "BATCH", None, f"Started {runnable} patient batch")
        self._scheduler.submit(self._run, batch_id)
        return self.get(batch_id)

    def _select_output_root(self, output: Path, batch: dict) -> Path:
        for candidate in sorted(output.glob("Batch_Results_*"), reverse=True):
            manifest = candidate / ".batch_state.json"
            if not manifest.is_file():
                continue
            try:
                state = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if state.get("input_path") == batch["input_path"] and state.get("state") != "Completed":
                return candidate
        stem = datetime.now().astimezone().strftime("Batch_Results_%Y%m%d_%H%M%S")
        candidate = output / stem
        suffix = 2
        while candidate.exists():
            candidate = output / f"{stem}_{suffix}"
            suffix += 1
        candidate.mkdir(parents=True)
        return candidate

    def pause(self, batch_id: str) -> dict:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            if batch["state"] == "Processing":
                batch["pause_requested"] = True
                batch["state"] = "Pausing"
                self._log(batch, "BATCH", None, "Pause requested; waiting for the current safe operation")
            return self.get_unlocked(batch)

    def resume(self, batch_id: str) -> dict:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            if batch["state"] in {"Paused", "Pausing"}:
                batch["pause_requested"] = False
                batch["state"] = "Processing"
                self._log(batch, "BATCH", None, "Batch resumed")
                self._condition.notify_all()
            return self.get_unlocked(batch)

    def cancel(self, batch_id: str) -> dict:
        with self._condition:
            batch = self._batches.get(batch_id)
            if batch is None:
                raise KeyError(batch_id)
            if batch["state"] in ACTIVE_BATCH_STATES:
                batch["cancel_requested"] = True
                batch["pause_requested"] = False
                batch["state"] = "Cancelling"
                self._log(batch, "BATCH", None, "Cancel requested; stopping after the current safe operation")
                self._condition.notify_all()
            return self.get_unlocked(batch)

    def get_unlocked(self, batch: dict) -> dict:
        public = {key: deepcopy(value) for key, value in batch.items() if key not in {"pause_requested", "cancel_requested"}}
        public["patients"] = [_public_patient(patient) for patient in batch["patients"]]
        public["counts"] = self._counts(batch)
        public["can_pause"] = batch["state"] == "Processing"
        public["can_resume"] = batch["state"] == "Paused"
        public["can_cancel"] = batch["state"] in ACTIVE_BATCH_STATES
        return public

    def _safe_boundary(self, batch: dict) -> bool:
        with self._condition:
            if batch["cancel_requested"]:
                return False
            if batch["pause_requested"]:
                batch["state"] = "Paused"
                self._write_manifest(batch)
                while batch["pause_requested"] and not batch["cancel_requested"]:
                    self._condition.wait()
            return not batch["cancel_requested"]

    def _patient_folder(self, batch: dict, patient: dict) -> Path:
        root = Path(batch["output_root"])
        identity = sanitize_windows_name(patient["patient_id"] + (f"_{patient['name']}" if patient["name"] else ""))
        return root / identity if batch.get("create_patient_folders", True) else root / f"Patient_{patient['index']:03d}_{identity}"

    def _resume_eye(self, batch: dict, patient: dict, eye_data: dict) -> bool:
        eye_folder = self._patient_folder(batch, patient) / ("Left_OS" if eye_data["eye"] == "OS" else "Right_OD")
        results_path = eye_folder / "results.json"
        if not results_path.is_file():
            return False
        try:
            result = json.loads(results_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        state = result.get("pipeline_state")
        if state not in {PipelineState.COMPLETE.value, PipelineState.RECAPTURE_REQUIRED.value}:
            return False
        eye_data["status"] = "Completed" if state == PipelineState.COMPLETE.value else "Recapture Required"
        eye_data["stage"] = state
        eye_data["quality_route"] = "GOOD" if state == PipelineState.COMPLETE.value and result.get("analysis_source") == "original" else "USABLE" if result.get("analysis_source") == "restored" else "RECAPTURE"
        eye_data["run_id"] = result.get("report_id")
        full_result = eye_folder / ".analysis_result.json"
        if full_result.is_file():
            try:
                eye_data["result"] = json.loads(full_result.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                eye_data["result"] = None
        eye_data["report_path"] = str(eye_folder / "report.pdf") if (eye_folder / "report.pdf").is_file() else None
        self._log(batch, patient["patient_id"], eye_data["eye"], "Existing completed result found; skipped inference")
        return True

    def _prepare_run(self, eye_data: dict) -> tuple[str, Path]:
        run_id = uuid4().hex
        run_dir = self.runs_root / run_id
        run_dir.mkdir()
        source = Path(eye_data["source_path"])
        destination = run_dir / f"input{source.suffix.casefold()}"
        shutil.copy2(source, destination)
        return run_id, destination

    def _run_eye(self, batch: dict, patient: dict, eye_data: dict) -> Future | None:
        if self._resume_eye(batch, patient, eye_data):
            return None
        eye = eye_data["eye"]
        run_id, input_path = self._prepare_run(eye_data)
        eye_data.update(status="Processing", stage=PipelineState.WAITING.value, run_id=run_id, error=None)
        patient["status"] = "Processing"
        batch["currently_processing"] = {"patient_id": patient["patient_id"], "eye": eye, "stage": PipelineState.WAITING.value}
        self._log(batch, patient["patient_id"], eye, "Analysis started")

        def on_state(state: PipelineState) -> None:
            with self._lock:
                eye_data["stage"] = state.value
                if state in {PipelineState.IQA_GOOD, PipelineState.IQA_USABLE, PipelineState.IQA_REJECTED}:
                    eye_data["quality_route"] = {
                        PipelineState.IQA_GOOD: "GOOD", PipelineState.IQA_USABLE: "USABLE", PipelineState.IQA_REJECTED: "RECAPTURE",
                    }[state]
                batch["currently_processing"] = {"patient_id": patient["patient_id"], "eye": eye, "stage": state.value}
                self._log(batch, patient["patient_id"], eye, STAGE_LOG_LABELS[state])

        try:
            result = run_analysis_pipeline(
                original_path=input_path,
                registry=self.registry,
                run_id=run_id,
                runs_root=self.runs_root,
                eye=eye,
                on_state=on_state,
            )
            with self._lock:
                eye_data["result"] = result
                eye_data["stage"] = result["state"]
                if result["state"] == PipelineState.RECAPTURE_REQUIRED.value:
                    eye_data["status"] = "Recapture Required"
                    self._log(batch, patient["patient_id"], eye, "Recapture required; downstream models skipped")
                else:
                    eye_data["status"] = "Finalizing"
                    self._log(batch, patient["patient_id"], eye, "Analysis complete; generating report")
            return self._cpu.submit(self._finalize_eye, batch, patient, eye_data, input_path.parent)
        except Exception as exc:
            with self._lock:
                eye_data.update(status="Failed", stage=PipelineState.FAILED.value, error=str(exc) or exc.__class__.__name__)
                self._log(batch, patient["patient_id"], eye, f"Failed: {eye_data['error']}")
            return None
        finally:
            with self._lock:
                current = batch.get("currently_processing")
                if eye_data["status"] != "Finalizing" and current and current["patient_id"] == patient["patient_id"] and current["eye"] == eye:
                    batch["currently_processing"] = None

    def _recapture_output(self, batch: dict, patient: dict, eye_data: dict) -> None:
        result = eye_data["result"] or {}
        root = self._patient_folder(batch, patient)
        eye_folder = root / ("Left_OS" if eye_data["eye"] == "OS" else "Right_OD")
        eye_folder.mkdir(parents=True, exist_ok=True)
        with Image.open(eye_data["source_path"]) as image:
            image.convert("RGB").save(eye_folder / "original_fundus.jpg", "JPEG", quality=95, optimize=True)
        quality = result.get("quality") or {}
        structured = {
            "report_id": result.get("run_id"),
            "patient": {key: value for key, value in {"name": patient["name"], "id": patient["patient_id"], "eye": eye_data["eye"]}.items() if value},
            "image_quality": {"class": quality.get("quality"), "confidence": quality.get("confidence"), "probabilities": quality.get("probabilities")},
            "dr_grading": None,
            "lesions": {},
            "pipeline_state": result.get("state"),
            "analysis_source": result.get("analysis_source"),
            "original_image_file": "original_fundus.jpg",
            "restored_image_file": None,
            "generated_at": _now(),
        }
        (eye_folder / "results.json").write_text(json.dumps(structured, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        (eye_folder / ".analysis_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def _finalize_eye(self, batch: dict, patient: dict, eye_data: dict, run_dir: Path) -> None:
        try:
            result = eye_data["result"] or {}
            if result.get("state") == PipelineState.RECAPTURE_REQUIRED.value:
                self._recapture_output(batch, patient, eye_data)
            else:
                root = self._patient_folder(batch, patient)
                root.mkdir(parents=True, exist_ok=True)
                exported = export_report_bundle(
                    Path(batch["output_root"]),
                    run_dir=run_dir,
                    patient={
                        **{key: value for key, value in patient["metadata"].items() if value not in (None, "")},
                        "name": patient["name"], "id": patient["patient_id"], "eye": eye_data["eye"], "scan_datetime": _now(),
                    },
                    logo_path=self.logo_path,
                    report_root=root,
                )
                eye_folder = Path(exported["eye_folder"])
                restored_png = eye_folder / "restored_fundus.png"
                if restored_png.is_file():
                    with Image.open(restored_png) as image:
                        image.convert("RGB").save(eye_folder / "restored_fundus.jpg", "JPEG", quality=95, optimize=True)
                    restored_png.unlink()
                    results_path = eye_folder / "results.json"
                    exported_result = json.loads(results_path.read_text(encoding="utf-8"))
                    exported_result["restored_image_file"] = "restored_fundus.jpg"
                    results_path.write_text(json.dumps(exported_result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                (eye_folder / ".analysis_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                with self._lock:
                    eye_data["report_path"] = exported["report"]
                    eye_data["status"] = "Completed"
                self._log(batch, patient["patient_id"], eye_data["eye"], "Report generation complete")
            self._write_summary(batch)
        except Exception as exc:
            with self._lock:
                eye_data.update(status="Failed", stage=PipelineState.FAILED.value, error=f"Output generation failed: {exc}")
                self._log(batch, patient["patient_id"], eye_data["eye"], eye_data["error"])
        finally:
            with self._lock:
                current = batch.get("currently_processing")
                if current and current["patient_id"] == patient["patient_id"] and current["eye"] == eye_data["eye"]:
                    batch["currently_processing"] = None

    def _history_eye(self, eye_data: dict | None) -> dict:
        if eye_data is None:
            return {"available": False, "completed": False, "state": None, "result_data": None, "original_path": None, "restored_path": None, "overlay_path": None, "report_path": None, "captured_at": None}
        result = eye_data.get("result") or {}
        return {
            "available": True,
            "completed": result.get("state") == PipelineState.COMPLETE.value or eye_data.get("status") == "Completed",
            "state": result.get("state") or eye_data.get("stage"),
            "result_data": result or None,
            "original_path": result.get("original_image_url") or eye_data.get("source_path"),
            "restored_path": result.get("restored_image_url"),
            "overlay_path": (result.get("lesions") or {}).get("combined_overlay_path"),
            "report_path": eye_data.get("report_path"),
            "captured_at": _now(),
        }

    def _finalize_patient(self, batch: dict, patient: dict, futures: list[Future]) -> None:
        if futures:
            wait(futures)
        with self._lock:
            eye_statuses = [eye["status"] for eye in patient["eyes"].values()]
            if any(status == "Failed" for status in eye_statuses):
                patient["status"] = "Failed"
            elif any(status == "Recapture Required" for status in eye_statuses):
                patient["status"] = "Recapture Required"
            else:
                patient["status"] = "Completed"
            record = {
                "session_id": patient["session_id"],
                "patient_id": patient["patient_id"],
                "patient_name": patient["name"],
                "patient": {
                    **{key: value for key, value in patient["metadata"].items() if key not in {"patient_id", "name"} and value not in (None, "")},
                    "id": patient["patient_id"],
                },
                "scan_datetime": batch["created_at"],
                "left_eye": self._history_eye(patient["eyes"].get("OS")),
                "right_eye": self._history_eye(patient["eyes"].get("OD")),
            }
        try:
            self.history.upsert(record)
            with self._lock:
                self._log(batch, patient["patient_id"], None, f"Patient finished: {patient['status']}")
        except Exception as exc:
            with self._lock:
                patient["status"] = "Failed"
                self._log(batch, patient["patient_id"], None, f"History update failed: {exc}")
        self._write_summary(batch)

    def _summary_rows(self, batch: dict) -> list[dict]:
        rows = []
        for patient in batch["patients"]:
            for eye_name, eye_data in patient["eyes"].items():
                result = eye_data.get("result") or {}
                quality = result.get("quality") or {}
                grading = result.get("grading") or {}
                lesions = (result.get("lesions") or {}).get("lesions") or {}
                rows.append({
                    "patient_id": patient["patient_id"],
                    "patient_name": patient["name"],
                    "session_id": patient["session_id"],
                    "eye": eye_name,
                    "iqa_class": quality.get("quality", ""),
                    "iqa_confidence": quality.get("confidence", ""),
                    "dr_grade": grading.get("predicted_grade", ""),
                    "dr_confidence": grading.get("confidence", ""),
                    "lesion_count": sum(int(item.get("num_regions") or 0) for item in lesions.values()) if lesions else "",
                    "status": eye_data["status"],
                    "report_path": eye_data.get("report_path") or "",
                })
        return rows

    def _write_summary(self, batch: dict) -> None:
        if not batch.get("output_root"):
            return
        with self._lock:
            rows = self._summary_rows(batch)
            path = Path(batch["output_root"]) / "batch_summary.csv"
        with self._io_lock:
            temporary = path.with_suffix(".csv.tmp")
            with temporary.open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            temporary.replace(path)

    def _write_manifest(self, batch: dict) -> None:
        if not batch.get("output_root"):
            return
        with self._lock:
            value = {
                "batch_id": batch["batch_id"], "input_path": batch["input_path"], "state": batch["state"],
                "created_at": batch["created_at"], "updated_at": _now(),
            }
            path = Path(batch["output_root"]) / ".batch_state.json"
        with self._io_lock:
            path.write_text(json.dumps(value, indent=2), encoding="utf-8")

    def _run(self, batch_id: str) -> None:
        with self._lock:
            batch = self._batches[batch_id]
        patient_futures: list[Future] = []
        try:
            for patient in batch["patients"]:
                if patient["status"] == "Skipped":
                    continue
                eye_futures: list[Future] = []
                for eye_name in ("OS", "OD"):
                    eye_data = patient["eyes"].get(eye_name)
                    if eye_data is None:
                        continue
                    if not self._safe_boundary(batch):
                        break
                    future = self._run_eye(batch, patient, eye_data)
                    if future is not None:
                        eye_futures.append(future)
                if eye_futures or all(eye["status"] in TERMINAL_EYE_STATES for eye in patient["eyes"].values()):
                    patient["status"] = "Finalizing"
                    patient_futures.append(self._cpu.submit(self._finalize_patient, batch, patient, eye_futures))
                if batch["cancel_requested"]:
                    break
            if patient_futures:
                wait(patient_futures)
            with self._lock:
                batch["state"] = "Cancelled" if batch["cancel_requested"] else "Completed"
                batch["currently_processing"] = None
                self._write_summary(batch)
                self._write_manifest(batch)
                self._log(batch, "BATCH", None, "Batch cancelled safely" if batch["cancel_requested"] else "Batch completed")
        except Exception as exc:
            with self._lock:
                batch["state"] = "Failed"
                batch["error"] = str(exc) or exc.__class__.__name__
                batch["currently_processing"] = None
                self._write_manifest(batch)
                self._log(batch, "BATCH", None, f"Batch failed: {batch['error']}")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=True, cancel_futures=False)
        self._cpu.shutdown(wait=True, cancel_futures=False)
