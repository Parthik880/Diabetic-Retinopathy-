from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from models.grade.predict import predict_grade
from models.iqa.predict import predict_iqa
from models.lesion.predict import predict_lesions
from models.lesion.visualization import LESION_COLORS, save_combined_overlay
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


LESION_NAMES = {
    "MA": "Microaneurysm",
    "HE": "Hemorrhage",
    "EX": "Hard Exudate",
    "SE": "Soft Exudate",
}


def _component_for_region(mask: np.ndarray, region: dict[str, Any]) -> np.ndarray:
    labels, _ = ndimage.label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    x_min, y_min, x_max, y_max = region["bbox_pixels"]
    window = labels[y_min:y_max + 1, x_min:x_max + 1]
    values, counts = np.unique(window[window > 0], return_counts=True)
    if not len(values):
        return np.zeros_like(mask, dtype=bool)
    return labels == int(values[int(counts.argmax())])


def _public_lesions(result: dict[str, Any], session_id: str, top_k: int = 25) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for lesion, data in result["lesions"].items():
        for region in data.get("regions", []):
            ranked.append({
                **region,
                "class_code": lesion,
                "class_name": LESION_NAMES.get(lesion, lesion),
                "confidence": float(region["max_probability"]),
            })
    ranked.sort(key=lambda item: (-item["confidence"], -item["mean_probability"], -item["area_pixels"], item["y_min"], item["x_min"]))
    ranked = ranked[:top_k]

    output_root = Path(result["combined_overlay_path"]).parent / "top-regions"
    output_root.mkdir(parents=True, exist_ok=True)
    with Image.open(result["image"]) as source_image:
        source = source_image.convert("RGB")
        source_array = np.asarray(source)
        image_width, image_height = source.size

        retained_masks: dict[str, np.ndarray] = {}
        retained_counts: dict[str, int] = {}
        for lesion, data in result["lesions"].items():
            with Image.open(data["mask_path"]) as mask_image:
                complete_mask = np.asarray(mask_image.convert("L")) > 0
            retained = np.zeros_like(complete_mask, dtype=bool)
            selected = [region for region in ranked if region["class_code"] == lesion]
            for region in selected:
                retained |= _component_for_region(complete_mask, region)
            retained_masks[lesion] = retained
            retained_counts[lesion] = len(selected)
            Image.fromarray(retained.astype(np.uint8) * 255, mode="L").save(output_root / f"{lesion.lower()}-retained-mask.png")

        for rank, region in enumerate(ranked, 1):
            region["rank"] = rank
            x_min, y_min, x_max, y_max = region["bbox_pixels"]
            padding = min(72, max(18, int(round(max(region["width"], region["height"]) * 1.5))))
            left, top = max(0, x_min - padding), max(0, y_min - padding)
            right, bottom = min(image_width, x_max + padding + 1), min(image_height, y_max + padding + 1)
            crop = source.crop((left, top, right, bottom))
            draw = ImageDraw.Draw(crop)
            color = LESION_COLORS[region["class_code"]]
            line_width = max(2, int(round(min(crop.size) / 90)))
            draw.rectangle([x_min - left, y_min - top, x_max - left, y_max - top], outline=color, width=line_width)
            crop_path = output_root / f"region-{rank:02d}-{region['class_code'].lower()}.png"
            crop.save(crop_path, optimize=True)
            region["crop_url"] = media_url(crop_path, session_id)
            region["download_name"] = f"lesion_{region['class_code'].lower()}_region_{rank:02d}.png"

    overlay_path = output_root / "retained-overlay.png"
    save_combined_overlay(source_array, retained_masks, overlay_path)
    classes = {}
    for name, data in result["lesions"].items():
        mask_url = media_url(output_root / f"{name.lower()}-retained-mask.png", session_id)
        classes[name] = {
            "detected": retained_counts[name] > 0,
            "num_regions": retained_counts[name],
            "total_valid_regions": data["num_regions"],
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
        "overlay_url": media_url(overlay_path, session_id),
        "regions": ranked,
        "region_count": len(ranked),
        "region_limit": top_k,
        "confidence_method": "Maximum predicted class probability within each connected component.",
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
        "warnings": [],
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
