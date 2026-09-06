"""Single-pass retinal analysis orchestration.

The quality classifier is deliberately invoked in exactly one place in this
module.  Its retained result selects the one image used by every downstream
model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import json
import logging
from pathlib import Path
from typing import Callable

from PIL import Image

from inference import grading, lesions, quality, restoration
from models.iqa.model import IQA_CLASS_NAMES


LOGGER = logging.getLogger("uvicorn.error")


class PipelineState(StrEnum):
    WAITING = "WAITING"
    IQA = "IQA"
    IQA_GOOD = "IQA_GOOD"
    IQA_USABLE = "IQA_USABLE"
    IQA_REJECTED = "IQA_REJECTED"
    RESTORING = "RESTORING"
    RESTORATION_COMPLETE = "RESTORATION_COMPLETE"
    GRADING = "GRADING"
    LESION_ANALYSIS = "LESION_ANALYSIS"
    PREPARING_RESULTS = "PREPARING_RESULTS"
    COMPLETE = "COMPLETE"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"
    FAILED = "FAILED"


TERMINAL_STATES = {
    PipelineState.COMPLETE,
    PipelineState.RECAPTURE_REQUIRED,
    PipelineState.FAILED,
}

_NORMALIZED_LABELS = {
    "good": "GOOD",
    "usable": "USABLE",
    "bad": "RECAPTURE",
    "reject": "RECAPTURE",
    "recapture": "RECAPTURE",
    "recapture_required": "RECAPTURE",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_quality_result(result: dict) -> str:
    """Normalize the deployed IQA mapping once for all routing decisions."""
    raw_label = str(result.get("quality") or "").strip()
    class_id = result.get("class_id")
    if isinstance(class_id, int) and 0 <= class_id < len(IQA_CLASS_NAMES):
        expected = IQA_CLASS_NAMES[class_id]
        if raw_label and raw_label.casefold() != expected.casefold():
            raise ValueError(
                f"IQA class mapping mismatch: class_id={class_id} maps to {expected!r}, "
                f"but inference returned {raw_label!r}."
            )
        raw_label = expected
    normalized = _NORMALIZED_LABELS.get(raw_label.casefold())
    if normalized is None:
        raise ValueError(f"Unsupported IQA quality label: {raw_label or '<missing>'}")
    return normalized


def public_paths(value, runs_root: Path):
    if isinstance(value, dict):
        return {key: public_paths(item, runs_root) for key, item in value.items()}
    if isinstance(value, list):
        return [public_paths(item, runs_root) for item in value]
    if isinstance(value, str):
        try:
            return "/artifacts/" + Path(value).resolve().relative_to(runs_root.resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return value


def run_analysis_pipeline(
    *,
    original_path: Path,
    registry,
    run_id: str,
    runs_root: Path,
    eye: str | None = None,
    on_state: Callable[[PipelineState], None] | None = None,
) -> dict:
    """Run IQA once, route once, and drive every branch to a terminal state."""
    destination = original_path.parent
    state_history = [{"state": PipelineState.WAITING.value, "at": utc_now()}]
    invocation_counts = {"iqa": 0, "nafnet": 0, "grading": 0, "lesions": 0}

    def transition(state: PipelineState) -> None:
        if state_history[-1]["state"] != state.value:
            state_history.append({"state": state.value, "at": utc_now()})
        LOGGER.info("[PIPELINE] image=%s run=%s state=%s", original_path.name, run_id, state.value)
        # The job manager publishes terminal state atomically with its result or
        # error payload. Exposing COMPLETE/FAILED here creates a poll race.
        if on_state is not None and state not in TERMINAL_STATES:
            on_state(state)

    eye_label = eye or "UNKNOWN"
    LOGGER.info("[RetinaGram][%s] Analysis started run=%s", eye_label, run_id)
    try:
        with Image.open(original_path) as source:
            width, height = source.size
            iqa_image = source.convert("RGB")

        if "quality" not in registry.models:
            raise RuntimeError("IQA model is unavailable; analysis cannot be routed safely.")

        with registry.lock:
            transition(PipelineState.IQA)
            LOGGER.info("[RetinaGram][%s] IQA started run=%s call=1", eye_label, run_id)
            invocation_counts["iqa"] += 1
            quality_result = quality.predict(iqa_image, registry.models["quality"])
            normalized_quality = normalize_quality_result(quality_result)
            quality_result = {**quality_result, "normalized_quality": normalized_quality}
            transition({
                "GOOD": PipelineState.IQA_GOOD,
                "USABLE": PipelineState.IQA_USABLE,
                "RECAPTURE": PipelineState.IQA_REJECTED,
            }[normalized_quality])
            LOGGER.info(
                "[RetinaGram][%s] IQA result=%s confidence=%.6f calls=%d run=%s",
                eye_label,
                normalized_quality,
                float(quality_result.get("confidence") or 0.0),
                invocation_counts["iqa"],
                run_id,
            )

            result = {
                "run_id": run_id,
                "eye": eye,
                "state": None,
                "state_history": state_history,
                "quality": quality_result,
                "grading": None,
                "lesions": None,
                "warnings": [],
                "device": str(registry.device),
                "device_name": registry.device_name,
                "image_width": width,
                "image_height": height,
                "image_url": str(original_path.resolve()),
                "original_image_url": str(original_path.resolve()),
                "restored_image_url": None,
                "analysis_image_url": str(original_path.resolve()),
                "analysis_source": "original",
                "invocation_counts": invocation_counts,
            }

            if normalized_quality == "RECAPTURE":
                LOGGER.info("[PIPELINE] run=%s routing=RECAPTURE", run_id)
                result["warnings"].append(
                    "IQA rejected this image. Recapture is required; restoration, grading, and lesion analysis were not run."
                )
                transition(PipelineState.RECAPTURE_REQUIRED)
                result["state"] = PipelineState.RECAPTURE_REQUIRED.value
            else:
                analysis_path = original_path
                if normalized_quality == "USABLE":
                    if "restoration" not in registry.models:
                        raise RuntimeError("NAFNet restoration is unavailable for this usable image.")
                    LOGGER.info("[PIPELINE] run=%s routing=RESTORE", run_id)
                    transition(PipelineState.RESTORING)
                    LOGGER.info("[RetinaGram][%s] NAFNet started run=%s", eye_label, run_id)
                    invocation_counts["nafnet"] += 1
                    restored = restoration.restore(
                        original_path,
                        registry.models["restoration"],
                        destination / "restoration",
                    )
                    analysis_path = Path(restored["output_path"]).resolve()
                    if not analysis_path.is_file():
                        raise RuntimeError("NAFNet completed without producing a restored image.")
                    result["restored_image_url"] = str(analysis_path)
                    result["analysis_image_url"] = str(analysis_path)
                    result["analysis_source"] = "restored"
                    result["restoration"] = {
                        key: value for key, value in restored.items() if key != "restored_image"
                    }
                    result["warnings"].append(
                        "IQA marked the image usable; downstream models ran on the NAFNet-restored image."
                    )
                    LOGGER.info("[RetinaGram][%s] NAFNet complete run=%s output=%s", eye_label, run_id, analysis_path.name)
                    transition(PipelineState.RESTORATION_COMPLETE)
                else:
                    LOGGER.info("[PIPELINE] run=%s routing=ORIGINAL", run_id)

                LOGGER.info("[PIPELINE] run=%s analysis_image=%s", run_id, result["analysis_source"])
                if "grading" not in registry.models:
                    raise RuntimeError("DR grading model is unavailable.")
                transition(PipelineState.GRADING)
                LOGGER.info("[RetinaGram][%s] DR grading started run=%s", eye_label, run_id)
                invocation_counts["grading"] += 1
                result["grading"] = grading.predict(
                    analysis_path, registry.models["grading"], destination / "grading"
                )
                LOGGER.info(
                    "[GRADE] run=%s completed grade=%s",
                    run_id,
                    result["grading"].get("predicted_grade"),
                )

                if "lesion" not in registry.models:
                    raise RuntimeError("Lesion analysis model is unavailable.")
                transition(PipelineState.LESION_ANALYSIS)
                LOGGER.info("[RetinaGram][%s] Lesion analysis started run=%s", eye_label, run_id)
                invocation_counts["lesions"] += 1
                result["lesions"] = lesions.predict(
                    analysis_path, registry.models["lesion"], destination / "lesions"
                )
                LOGGER.info("[LESIONS] run=%s completed", run_id)
                result["warnings"].append(
                    "Lesion region scores are mean pixel probabilities, not clinical confidence or severity."
                )
                transition(PipelineState.PREPARING_RESULTS)
                transition(PipelineState.COMPLETE)
                result["state"] = PipelineState.COMPLETE.value

        result["state_history"] = state_history
        result["invocation_counts"] = invocation_counts
        public_result = public_paths(result, runs_root)
        (destination / "response.json").write_text(
            json.dumps(public_result, indent=2, allow_nan=False), encoding="utf-8"
        )
        LOGGER.info(
            "[RetinaGram][%s] Analysis terminal=%s calls=%s run=%s",
            eye_label,
            public_result["state"],
            invocation_counts,
            run_id,
        )
        return public_result
    except Exception:
        transition(PipelineState.FAILED)
        failure = {
            "run_id": run_id,
            "state": PipelineState.FAILED.value,
            "state_history": state_history,
            "invocation_counts": invocation_counts,
        }
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "failure.json").write_text(
            json.dumps(failure, indent=2), encoding="utf-8"
        )
        LOGGER.exception("[PIPELINE] run=%s FAILED", run_id)
        raise
