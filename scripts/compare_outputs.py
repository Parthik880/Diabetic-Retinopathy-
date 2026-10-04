"""Summarize Python/C++ output parity without altering either application."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "build/validation"
REFERENCE = VALIDATION / "reference"
CLASSES = ("MA", "HE", "EX", "SE")


def mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image) > 0


def cam_similarity(reference_values: Path, native_heatmap: Path) -> dict:
    original = np.load(reference_values).astype(np.float32)
    with Image.fromarray(original) as image:
        old = np.asarray(image.resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32)
    with Image.open(native_heatmap) as image:
        colors = np.asarray(image.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR), dtype=np.float32)
    positions = np.linspace(0, 1, 256, dtype=np.float32)
    palette = np.stack([np.clip(1.5 - np.abs(4 * positions - shift), 0, 1)
                        for shift in (3, 2, 1)], axis=1) * 255
    flattened = colors.reshape(-1, 3)
    decoded = np.empty(len(flattened), dtype=np.float32)
    for start in range(0, len(flattened), 4096):
        section = flattened[start:start + 4096]
        distance = np.square(section[:, None, :] - palette[None, :, :]).sum(axis=2)
        decoded[start:start + 4096] = distance.argmin(axis=1) / 255.0
    new = decoded.reshape(256, 256)
    high_old = old >= 0.75
    high_new = new >= 0.75
    union = np.logical_or(high_old, high_new).sum()
    correlation = (1.0 if np.allclose(old, new) else None) if (old.std() == 0 or new.std() == 0) else float(np.corrcoef(old.ravel(), new.ravel())[0, 1])
    return {"mean_abs_normalized": float(np.abs(old - new).mean()),
            "correlation": correlation,
            "high_attention_iou": float(np.logical_and(high_old, high_new).sum() / union) if union else 1.0}


def main() -> None:
    rows = []
    for index in range(5):
        reference = json.loads((REFERENCE / f"reference_{index}/response.json").read_text())
        native = json.loads((VALIDATION / f"native_{index}.json").read_text())
        overlaps = {}
        for name in CLASSES:
            source_path = REFERENCE / reference["lesions"]["lesions"][name]["mask_path"].removeprefix("/artifacts/")
            old = mask(source_path)
            new = mask(Path(native["lesion_mask_paths"][name]))
            if old.shape != new.shape:
                raise ValueError(f"{index} {name}: mask size mismatch {old.shape} vs {new.shape}")
            union = np.logical_or(old, new).sum()
            overlaps[name] = {
                "reference_pixels": int(old.sum()),
                "native_pixels": int(new.sum()),
                "pixel_iou": float(np.logical_and(old, new).sum() / union) if union else 1.0,
                "reference_regions": reference["lesions"]["lesions"][name]["num_regions"],
                "native_regions": native["lesion_counts"][name],
            }
        restoration = None
        if reference["analysis_source"] == "restored":
            source_path = REFERENCE / reference["restored_image_url"].removeprefix("/artifacts/")
            with Image.open(source_path) as image:
                old = np.asarray(image.convert("RGB"), dtype=np.float32)
            with Image.open(native["restored_image_path"]) as image:
                new = np.asarray(image.convert("RGB"), dtype=np.float32)
            if old.shape != new.shape:
                raise ValueError(f"Restored shape mismatch: {old.shape} vs {new.shape}")
            mse = float(np.mean((old - new) ** 2))
            difference = np.abs(old - new)
            non_dark = old.mean(axis=2) > 30
            restoration = {"size": list(old.shape), "mean_abs_uint8": float(np.mean(np.abs(old - new))),
                           "max_abs_uint8": float(difference.max()),
                           "pixels_with_any_channel_difference_gt_30": int((difference.max(axis=2) > 30).sum()),
                           "non_dark_mean_abs_uint8": float(difference[non_dark].mean()) if non_dark.any() else None,
                           "non_dark_max_abs_uint8": float(difference[non_dark].max()) if non_dark.any() else None,
                           "psnr_db": float(10 * np.log10(255 * 255 / mse)) if mse else None}
        rows.append({
            "image": Path(reference["original_image_url"]).name,
            "reference_quality": reference["quality"]["quality"],
            "native_quality": native["quality"],
            "reference_quality_confidence": reference["quality"]["confidence"],
            "native_quality_confidence": native["quality_confidence"],
            "reference_grade": reference["grading"]["predicted_grade"],
            "native_grade": native["grade"],
            "reference_grade_probabilities": reference["grading"]["probabilities"],
            "native_grade_probabilities": native["grade_probabilities"],
            "lesions": overlaps,
            "restoration": restoration,
            "grade_cam": cam_similarity(
                REFERENCE / reference["grading"]["gradcam"]["values_path"].removeprefix("/artifacts/"),
                Path(native["gradcam_path"])),
        })
    rejected = json.loads((REFERENCE / "reference_5/response.json").read_text())
    native_rejected = json.loads((VALIDATION / "native_5.json").read_text())
    reject_case = {"image": Path(rejected["original_image_url"]).name,
                   "reference_state": rejected["state"], "native_state": native_rejected["state"],
                   "reference_quality": rejected["quality"]["quality"],
                   "native_quality": native_rejected["quality"],
                   "reference_confidence": rejected["quality"]["confidence"],
                   "native_confidence": native_rejected["quality_confidence"],
                   "native_grade_skipped": native_rejected["grade"] == -1}
    report = {
        "images": rows,
        "recapture_case": reject_case,
        "quality_class_agreement": sum(x["reference_quality"] == x["native_quality"] for x in rows) +
                                   int(reject_case["reference_quality"] == reject_case["native_quality"]),
        "grade_class_agreement": sum(x["reference_grade"] == x["native_grade"] for x in rows),
        "image_count": len(rows) + 1,
        "note": "The source checkpoints are FP32; the native lesion and grade models were converted to BF16 at user request. Pixel IoU uses the source full threshold masks in original image coordinates.",
    }
    (VALIDATION / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for row in rows:
        print(row["image"], row["reference_quality"], row["native_quality"],
              row["reference_grade"], row["native_grade"],
              {key: round(value["pixel_iou"], 3) for key, value in row["lesions"].items()},
              row["restoration"], row["grade_cam"])


if __name__ == "__main__":
    main()
