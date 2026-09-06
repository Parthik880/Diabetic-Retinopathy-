from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from models.grade.predict import predict_grade
from models.iqa.predict import predict_iqa
from models.lesion.predict import predict_lesions
from models.restoration.predict import restore_image

from backend.app.model_registry import INFERENCE_LOCK, registry
from backend.app.services.image_store import media_url, write_manifest


STAGE_DEFINITIONS = (
    ("input", "Input Image", "Validated local upload"),
    ("quality", "Quality Check", "EfficientNet-B0 calibrated quality assessment"),
    ("restoration", "NAFNet Restoration", "Noise reduction and structural restoration"),
    ("grade", "Grade Classification", "Five-class ConvNeXt DR grading"),
    ("lesion", "Lesion Segmentation", "Four-channel UNet++ lesion localization"),
    ("report", "Final Report", "Combined visualizer summary"),
)


def pipeline_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": stage_id,
            "number": index,
            "label": label,
            "description": description,
            "state": "pending",
            "error": None,
        }
        for index, (stage_id, label, description) in enumerate(STAGE_DEFINITIONS, 1)
    ]


def _stage(stages: list[dict[str, Any]], stage_id: str) -> dict[str, Any]:
    return next(item for item in stages if item["id"] == stage_id)


def _public_quality(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality": result["quality"],
        "confidence": result["confidence"],
        "probabilities": result["probabilities"],
        "metric": result["metric"],
        "device": result["device"],
    }


def _public_grade(result: dict[str, Any], session_id: str) -> dict[str, Any]:
    return {
        "predicted_grade": result["predicted_grade"],
        "confidence": result["confidence"],
        "probabilities": result["probabilities"],
        "device": result["device"],
        "gradcam_url": (
            media_url(result["gradcam_path"], session_id)
            if result.get("gradcam_path")
            else None
        ),
    }


def _public_lesions(result: dict[str, Any], session_id: str) -> dict[str, Any]:
    classes = {}
    for name, data in result["lesions"].items():
        mask_url = None
        if data.get("mask_path"):
            mask_path = Path(data["mask_path"])
            browser_mask = mask_path.with_suffix(".png")
            if not browser_mask.is_file():
                with Image.open(mask_path) as mask:
                    mask.convert("L").save(browser_mask)
            mask_url = media_url(browser_mask, session_id)
        classes[name] = {
            "detected": data["detected"],
            "num_regions": data["num_regions"],
            "image_percentage": data["image_percentage"],
            "probability_map_url": (
                media_url(data["probability_map_path"], session_id)
                if data.get("probability_map_path")
                else None
            ),
            "mask_url": mask_url,
        }
    return {
        "classes": classes,
        "channel_order": result["channel_order"],
        "threshold": result["threshold"],
        "overlay_url": media_url(result["combined_overlay_path"], session_id),
        "device": result["device"],
        "localization_note": result["localization_note"],
    }


def run_analysis(session_id: str, session_dir: Path, image_path: Path) -> dict[str, Any]:
    """Run the real pipeline serially; model instances are cached across requests."""
    stages = pipeline_stages()
    _stage(stages, "input")["state"] = "complete"
    payload: dict[str, Any] = {
        "session_id": session_id,
        "device": str(registry.device),
        "input_image_url": media_url(image_path, session_id),
        "stages": stages,
        "quality": None,
        "restoration": None,
        "grade": None,
        "lesions": None,
        "features": {},
        "warnings": [
            "This visualizer exposes model output for research and development; it is not a clinical diagnosis."
        ],
    }

    with INFERENCE_LOCK:
        try:
            quality_model = registry.get("quality")
            quality = predict_iqa(image_path, model=quality_model)
            payload["quality"] = _public_quality(quality)
            _stage(stages, "quality")["state"] = "complete"
        except Exception as exc:  # Return honest partial results for optional stages.
            _stage(stages, "quality").update(state="error", error=str(exc))
            payload["warnings"].append(f"Quality stage unavailable: {exc}")

        selected_image = image_path
        try:
            restoration_model = registry.get("restoration")
            restoration = restore_image(
                image_path,
                model=restoration_model,
                output_dir=session_dir / "restoration",
            )
            selected_image = Path(restoration["output_path"])
            payload["restoration"] = {
                "output_image_url": media_url(selected_image, session_id),
                "width": restoration["width"],
                "height": restoration["height"],
                "device": restoration["device"],
                "checkpoint": restoration["checkpoint"],
            }
            _stage(stages, "restoration")["state"] = "complete"
        except Exception as exc:
            _stage(stages, "restoration").update(state="error", error=str(exc))
            payload["warnings"].append(f"Restoration stage unavailable: {exc}")

        try:
            grade_model = registry.get("grade")
            grade = predict_grade(
                selected_image,
                model=grade_model,
                save_gradcam=True,
                gradcam_output_dir=session_dir / "grade",
            )
            payload["grade"] = _public_grade(grade, session_id)
            _stage(stages, "grade")["state"] = "complete"
        except Exception as exc:
            _stage(stages, "grade").update(state="error", error=str(exc))
            payload["warnings"].append(f"Grade stage unavailable: {exc}")

        try:
            lesion_model = registry.get("lesion")
            lesions = predict_lesions(
                selected_image,
                model=lesion_model,
                output_dir=session_dir / "lesion",
                generate_gradcam=False,
                save_analysis=False,
            )
            payload["lesions"] = _public_lesions(lesions, session_id)
            _stage(stages, "lesion")["state"] = "complete"
        except Exception as exc:
            _stage(stages, "lesion").update(state="error", error=str(exc))
            payload["warnings"].append(f"Lesion stage unavailable: {exc}")

    if payload["grade"] is not None or payload["lesions"] is not None:
        _stage(stages, "report")["state"] = "complete"
    else:
        _stage(stages, "report").update(
            state="error", error="No downstream model result was available."
        )

    write_manifest(session_dir, payload)
    return payload
