"""Reusable UNet++ prediction, localization metadata, and visualizations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import time
from typing import Callable, Iterator

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, UnidentifiedImageError

from .dataset import IMAGE_SIZE, LESION_CLASSES
from .gradcam import (
    GRADCAM_TARGET_FORMULATION,
    GRADCAM_TARGET_LAYER,
    SegmentationGradCAM,
)
from .model import DEFAULT_CHECKPOINT_PATH, LesionUNetPlusPlus, load_lesion_model
from .postprocess import extract_predicted_regions
from .visualization import (
    create_bounding_box_image,
    create_center_image,
    save_analysis_dashboard,
    save_binary_mask,
    save_combined_overlay,
    save_gradcam_overlay,
    save_probability_map,
)


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
DEFAULT_THRESHOLD = 0.5
DEFAULT_MIN_COMPONENT_AREA = 3
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "inference" / "outputs" / "lesion"
)


def _cuda_sync(device: torch.device | None) -> None:
    if device is not None and device.type == "cuda":
        torch.cuda.synchronize(device)


@contextmanager
def _timed(timing: dict[str, object], key: str, device: torch.device | None = None) -> Iterator[None]:
    _cuda_sync(device)
    started = time.perf_counter_ns()
    try:
        yield
    finally:
        _cuda_sync(device)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        timing[key] = timing.get(key, 0.0) + elapsed


def validate_image(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Image file does not exist: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported image extension: {resolved.suffix}")
    try:
        with Image.open(resolved) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Image is unreadable or invalid: {resolved}") from exc
    return resolved


def preprocess_lesion_image(image_path: str | Path, timing: dict[str, object] | None = None) -> tuple[Path, torch.Tensor]:
    """Apply the unchanged 768px resize and ImageNet normalization."""
    timing = timing if timing is not None else {}
    with _timed(timing, "image_validation_decode_ms"):
        path = validate_image(image_path)
    with Image.open(path) as image:
        with _timed(timing, "image_decode_load_ms"):
            image.load()
            rgb = image.convert("RGB")
        with _timed(timing, "image_resize_ms"):
            resized = rgb.resize((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.BILINEAR)
        with _timed(timing, "preprocessing_ms"):
            tensor = torch.from_numpy(np.array(resized)).permute(2, 0, 1).float() / 255.0
    with _timed(timing, "normalization_ms"):
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        normalized = ((tensor - mean) / std).unsqueeze(0)
    return path, normalized


def _unique_run_stem(output_dir: Path, image_stem: str) -> str:
    candidate = image_stem
    suffix = 2
    while (output_dir / "json" / f"{candidate}_lesions.json").exists():
        candidate = f"{image_stem}_{suffix}"
        suffix += 1
    return candidate


def _load_original_rgb(path: Path, timing: dict[str, object] | None = None) -> np.ndarray:
    timing = timing if timing is not None else {}
    with Image.open(path) as image:
        with _timed(timing, "original_image_decode_ms"):
            image.load()
            return np.array(image.convert("RGB"), copy=True)


def predict_lesions(
    image_path: str | Path,
    model: LesionUNetPlusPlus | None = None,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    min_component_area: int = DEFAULT_MIN_COMPONENT_AREA,
    max_regions_per_class: int | None = None,
    output_dir: str | Path | None = None,
    save_probability_maps: bool = True,
    generate_gradcam: bool = True,
    save_analysis: bool = True,
    timing: dict[str, object] | None = None,
    stage_callback: Callable[[str], None] | None = None,
    save_probability_plot_images: bool = True,
    save_gradcam_overlay_images: bool = True,
    generate_localization_images: bool = True,
    defer_region_extraction: bool = False,
) -> dict:
    """Predict lesions and return JSON-compatible estimated localization data.

    Probability maps are resized back to the original image before thresholding.
    Eight-connected components smaller than ``min_component_area`` are removed.
    Optional top-N filtering keeps the largest components first.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if min_component_area < 1:
        raise ValueError("min_component_area must be at least 1")
    if max_regions_per_class is not None and max_regions_per_class < 1:
        raise ValueError("max_regions_per_class must be at least 1 when provided")

    timing = timing if timing is not None else {}
    total_started = time.perf_counter_ns()
    path, image_tensor = preprocess_lesion_image(image_path, timing)
    original_rgb = _load_original_rgb(path, timing)
    image_height, image_width = original_rgb.shape[:2]
    destination = (
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else DEFAULT_OUTPUT_DIR
    )
    destination.mkdir(parents=True, exist_ok=True)
    run_stem = _unique_run_stem(destination, path.stem)

    checkpoint_metadata = {}
    if model is None:
        with _timed(timing, "model_load_ms"):
            model, checkpoint_metadata = load_lesion_model(checkpoint_path, device=device)
    try:
        model_device = next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError("Lesion model has no parameters") from exc
    model.eval()
    if stage_callback is not None:
        stage_callback("LESION_INFERENCE")
    with _timed(timing, "h2d_transfer_ms", model_device):
        model_input = image_tensor.to(model_device)

    timing["model_device"] = str(model_device)
    timing["input_device"] = str(model_input.device)
    timing["grad_enabled_before_forward"] = bool(torch.is_grad_enabled())
    if model_device.type == "cuda":
        timing["memory_allocated_before_mib"] = torch.cuda.memory_allocated(model_device) / 1048576
        timing["memory_reserved_before_mib"] = torch.cuda.memory_reserved(model_device) / 1048576

    gradcam = SegmentationGradCAM(model) if generate_gradcam else None
    try:
        forward_context = (
            torch.enable_grad() if generate_gradcam else torch.inference_mode()
        )
        with forward_context:
            with _timed(timing, "model_forward_ms", model_device):
                logits = model(model_input)
            timing["grad_enabled_inside_forward"] = bool(torch.is_grad_enabled())
            timing["model_forward_count"] = int(timing.get("model_forward_count", 0)) + 1
            with _timed(timing, "sigmoid_ms", model_device):
                probabilities = torch.sigmoid(logits)

        expected_shape = (1, len(LESION_CLASSES), IMAGE_SIZE, IMAGE_SIZE)
        if tuple(logits.shape) != expected_shape:
            raise RuntimeError(
                f"Expected raw lesion logits with shape {expected_shape}, "
                f"received {tuple(logits.shape)}"
            )
        with _timed(timing, "mask_resize_to_original_ms", model_device):
            resized_probabilities = F.interpolate(
                probabilities,
                size=(image_height, image_width),
                mode="bilinear",
                align_corners=False,
            )[0]
        with _timed(timing, "d2h_transfer_ms", model_device):
            original_probabilities = resized_probabilities.detach().float().cpu().numpy()

        lesion_metadata: dict[str, dict] = {}
        filtered_masks: dict[str, np.ndarray] = {}
        if stage_callback is not None:
            stage_callback("LESION_MASK_PROCESSING")
        for lesion, channel in LESION_CLASSES.items():
            probability_map = original_probabilities[channel]
            with _timed(timing, "mask_thresholding_ms"):
                thresholded_mask = probability_map >= threshold
            if defer_region_extraction:
                filtered_mask, regions = thresholded_mask, []
            else:
                if stage_callback is not None:
                    stage_callback("LESION_REGION_EXTRACTION")
                filtered_mask, regions = extract_predicted_regions(
                    thresholded_mask,
                    probability_map,
                    min_component_area=min_component_area,
                    max_regions_per_class=max_regions_per_class,
                    timing=timing,
                )
            filtered_masks[lesion] = filtered_mask
            with _timed(timing, "lesion_counting_ms"):
                total_area = int(filtered_mask.sum())
            mask_path = destination / "masks" / f"{run_stem}_{lesion}_mask.tiff"
            with _timed(timing, "mask_saving_ms"):
                save_binary_mask(filtered_mask, mask_path)

            probability_map_path = None
            probability_values_path = None
            if save_probability_maps:
                probability_map_path = (
                    destination
                    / "probability_maps"
                    / f"{run_stem}_{lesion}_probability.png"
                )
                probability_values_path = (
                    destination
                    / "probability_maps"
                    / f"{run_stem}_{lesion}_probability.npy"
                )
                if save_probability_plot_images:
                    with _timed(timing, "probability_plot_saving_ms"):
                        save_probability_map(probability_map, lesion, probability_map_path)
                else:
                    probability_map_path = None
                with _timed(timing, "probability_array_saving_ms"):
                    probability_values_path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(probability_values_path, probability_map, allow_pickle=False)

            lesion_metadata[lesion] = {
                "channel": int(channel),
                "detected": bool(regions),
                "num_regions": int(len(regions)),
                "regions": regions,
                "total_area_pixels": total_area,
                "image_fraction": float(total_area / (image_width * image_height)),
                "image_percentage": float(
                    100.0 * total_area / (image_width * image_height)
                ),
                "thresholded_area_pixels": int(thresholded_mask.sum()),
                "probability_statistics": {
                    "minimum": float(probability_map.min()),
                    "maximum": float(probability_map.max()),
                    "mean": float(probability_map.mean()),
                },
                "mask_path": str(mask_path.resolve()),
                "probability_map_path": (
                    str(probability_map_path.resolve())
                    if probability_map_path is not None
                    else None
                ),
                "probability_values_path": (
                    str(probability_values_path.resolve())
                    if probability_values_path is not None
                    else None
                ),
                "gradcam_path": None,
            }

        gradcam_overlays: dict[str, np.ndarray | None] = {
            lesion: None for lesion in LESION_CLASSES
        }
        if gradcam is not None:
            for lesion, channel in LESION_CLASSES.items():
                with _timed(timing, "gradcam_generation_ms", model_device):
                    cam = gradcam.generate(logits, channel, filtered_masks[lesion])
                if cam is None:
                    continue
                gradcam_path = (
                    destination / "gradcam" / f"{run_stem}_{lesion}_gradcam.png"
                )
                # Keep the actual normalized CAM for a separate pixel-aligned
                # browser layer; the original overlay output is retained.
                gradcam_path.parent.mkdir(parents=True, exist_ok=True)
                cam_values_path = gradcam_path.with_suffix('.npy')
                np.save(cam_values_path, cam, allow_pickle=False)
                lesion_metadata[lesion]['gradcam_values_path'] = str(cam_values_path.resolve())
                if save_gradcam_overlay_images:
                    with _timed(timing, "gradcam_overlay_saving_ms"):
                        gradcam_overlays[lesion] = save_gradcam_overlay(
                            original_rgb, cam, lesion, gradcam_path
                        )
                    lesion_metadata[lesion]["gradcam_path"] = str(gradcam_path.resolve())
    finally:
        if gradcam is not None:
            gradcam.close()

    overlay_path = destination / f"{run_stem}_lesion_overlay.png"
    boxes_path = destination / f"{run_stem}_lesion_boxes.png"
    centers_path = destination / f"{run_stem}_lesion_centers.png"
    analysis_path = destination / f"{run_stem}_analysis.png"
    with _timed(timing, "overlay_generation_saving_ms"):
        overlay = save_combined_overlay(original_rgb, filtered_masks, overlay_path)
    boxes = original_rgb
    centers = original_rgb
    if generate_localization_images:
        with _timed(timing, "bounding_box_render_saving_ms"):
            boxes = create_bounding_box_image(original_rgb, lesion_metadata, boxes_path)
        with _timed(timing, "center_render_saving_ms"):
            centers = create_center_image(original_rgb, lesion_metadata, centers_path)
    if save_analysis:
        with _timed(timing, "analysis_dashboard_saving_ms"):
            save_analysis_dashboard(
                original_rgb,
                overlay,
                boxes,
                centers,
                gradcam_overlays,
                analysis_path,
            )

    json_path = destination / "json" / f"{run_stem}_lesions.json"
    result = {
        "image": str(path),
        "image_width": int(image_width),
        "image_height": int(image_height),
        "model_input_shape": [int(value) for value in model_input.shape],
        "logits_shape": [int(value) for value in logits.shape],
        "probability_maps_shape": [
            int(len(LESION_CLASSES)),
            int(image_height),
            int(image_width),
        ],
        "channel_order": [
            lesion for lesion, _ in sorted(LESION_CLASSES.items(), key=lambda item: item[1])
        ],
        "threshold": float(threshold),
        "component_filter": {
            "connectivity": 8,
            "min_component_area": int(min_component_area),
            "max_regions_per_class": (
                int(max_regions_per_class)
                if max_regions_per_class is not None
                else None
            ),
            "sort_order": "area descending, then mean_probability descending",
        },
        "coordinate_space": "original input image pixels",
        "bbox_convention": "inclusive [x_min, y_min, x_max, y_max]",
        "lesions": lesion_metadata,
        "gradcam": {
            "enabled": bool(generate_gradcam),
            "target_layer": GRADCAM_TARGET_LAYER,
            "target_formulation": GRADCAM_TARGET_FORMULATION,
            "absent_class_behavior": "skipped; no heatmap is fabricated",
        },
        "combined_overlay_path": str(overlay_path.resolve()),
        "bounding_box_image_path": str(boxes_path.resolve()) if generate_localization_images else None,
        "center_point_image_path": str(centers_path.resolve()) if generate_localization_images else None,
        "analysis_image_path": str(analysis_path.resolve()) if save_analysis else None,
        "json_path": str(json_path.resolve()),
        "device": str(model_device),
        "timing_ms": timing,
        "forward_count": int(timing.get("model_forward_count", 0)),
        "checkpoint": checkpoint_metadata,
        "localization_note": (
            "Coordinates and boxes are estimates derived from predicted masks; "
            "they are not ground-truth annotations or clinical confidence scores."
        ),
    }
    with _timed(timing, "json_result_serialization_ms"):
        json.dumps(result, indent=2, allow_nan=False)
    with _timed(timing, "json_result_saving_ms"):
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
    if model_device.type == "cuda":
        timing["memory_allocated_after_mib"] = torch.cuda.memory_allocated(model_device) / 1048576
        timing["memory_reserved_after_mib"] = torch.cuda.memory_reserved(model_device) / 1048576
        timing["peak_memory_allocated_mib"] = torch.cuda.max_memory_allocated(model_device) / 1048576
    timing["total_predict_lesions_ms"] = (time.perf_counter_ns() - total_started) / 1_000_000
    return result
