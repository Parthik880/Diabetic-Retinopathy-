"""Headless visualizations for predicted lesion masks and feature attribution."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from PIL import Image, ImageDraw


LESION_COLORS = {
    "MA": (255, 45, 45),
    "HE": (255, 126, 34),
    "EX": (255, 224, 32),
    "SE": (35, 210, 255),
}


def save_binary_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255).save(
        path, format="TIFF", compression="tiff_deflate"
    )


def save_probability_map(probability_map: np.ndarray, lesion: str, path: Path) -> None:
    """Save a viewable heatmap; callers separately retain the numeric array."""
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(7, 7))
    image = axis.imshow(probability_map, cmap="magma", vmin=0.0, vmax=1.0)
    axis.set_title(f"{lesion} probability map")
    axis.axis("off")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.05)
    plt.close(figure)


def blend_lesion_masks(
    original_rgb: np.ndarray,
    masks: dict[str, np.ndarray],
    alpha: float = 0.45,
) -> np.ndarray:
    blended = np.asarray(original_rgb, dtype=np.float32).copy()
    for lesion, color in LESION_COLORS.items():
        mask = np.asarray(masks[lesion], dtype=bool)
        color_array = np.asarray(color, dtype=np.float32)
        blended[mask] = blended[mask] * (1.0 - alpha) + color_array * alpha
    return np.clip(np.rint(blended), 0, 255).astype(np.uint8)


def save_combined_overlay(
    original_rgb: np.ndarray,
    masks: dict[str, np.ndarray],
    path: Path,
) -> np.ndarray:
    overlay = blend_lesion_masks(original_rgb, masks)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(8, 8))
    axis.imshow(overlay)
    axis.set_title("Predicted lesion segmentation overlay")
    axis.axis("off")
    handles = [
        Patch(color=np.asarray(color) / 255.0, label=lesion)
        for lesion, color in LESION_COLORS.items()
    ]
    axis.legend(handles=handles, loc="lower right", framealpha=0.8)
    figure.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.05)
    plt.close(figure)
    return overlay


def _line_width(image_width: int, image_height: int) -> int:
    return max(1, int(round(min(image_width, image_height) / 512)))


def create_bounding_box_image(
    original_rgb: np.ndarray,
    lesion_metadata: dict[str, dict],
    path: Path,
) -> np.ndarray:
    image = Image.fromarray(original_rgb.copy())
    draw = ImageDraw.Draw(image)
    width, height = image.size
    line_width = _line_width(width, height)
    for lesion, metadata in lesion_metadata.items():
        color = LESION_COLORS[lesion]
        for region in metadata["regions"]:
            x_min, y_min, x_max, y_max = region["bbox_pixels"]
            draw.rectangle(
                [x_min, y_min, x_max, y_max], outline=color, width=line_width
            )
            label = f"{lesion} {region['mean_probability']:.2f}"
            text_box = draw.textbbox((x_min, y_min), label)
            text_width = text_box[2] - text_box[0]
            text_height = text_box[3] - text_box[1]
            text_x = min(max(0, x_min), max(0, width - text_width - 2))
            text_y = y_min - text_height - 2
            if text_y < 0:
                text_y = min(height - text_height - 2, y_max + 2)
            draw.rectangle(
                [
                    text_x,
                    text_y,
                    min(width - 1, text_x + text_width + 2),
                    min(height - 1, text_y + text_height + 2),
                ],
                fill=color,
            )
            draw.text((text_x + 1, text_y + 1), label, fill=(0, 0, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, compress_level=1)
    return np.asarray(image)


def create_center_image(
    original_rgb: np.ndarray,
    lesion_metadata: dict[str, dict],
    path: Path,
) -> np.ndarray:
    image = Image.fromarray(original_rgb.copy())
    draw = ImageDraw.Draw(image)
    width, height = image.size
    radius = max(2, int(round(min(width, height) / 300)))
    line_width = _line_width(width, height)
    for lesion, metadata in lesion_metadata.items():
        color = LESION_COLORS[lesion]
        for region in metadata["regions"]:
            center_x, center_y = region["center_pixels"]
            draw.ellipse(
                [
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                ],
                outline=color,
                width=line_width,
            )
            draw.text(
                (
                    min(max(0, center_x + radius + 1), max(0, width - 85)),
                    min(max(0, center_y - radius), max(0, height - 12)),
                ),
                f"{lesion} ({center_x}, {center_y})",
                fill=color,
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, compress_level=1)
    return np.asarray(image)


def gradcam_overlay_array(
    original_rgb: np.ndarray, gradcam: np.ndarray, alpha: float = 0.4
) -> np.ndarray:
    heatmap = matplotlib.colormaps["jet"](np.clip(gradcam, 0.0, 1.0))[..., :3]
    heatmap = heatmap * 255.0
    overlay = original_rgb.astype(np.float32) * (1.0 - alpha) + heatmap * alpha
    return np.clip(np.rint(overlay), 0, 255).astype(np.uint8)


def save_gradcam_overlay(
    original_rgb: np.ndarray,
    gradcam: np.ndarray,
    lesion: str,
    path: Path,
) -> np.ndarray:
    overlay = gradcam_overlay_array(original_rgb, gradcam)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(8, 8))
    axis.imshow(overlay)
    axis.set_title(f"{lesion} segmentation Grad-CAM")
    axis.axis("off")
    figure.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0.05)
    plt.close(figure)
    return overlay


def save_analysis_dashboard(
    original_rgb: np.ndarray,
    lesion_overlay: np.ndarray,
    bounding_boxes: np.ndarray,
    centers: np.ndarray,
    gradcam_overlays: dict[str, np.ndarray | None],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(2, 4, figsize=(20, 10))
    panels = [
        (original_rgb, "Original"),
        (lesion_overlay, "Lesion overlay"),
        (bounding_boxes, "Bounding boxes"),
        (centers, "Estimated centers"),
    ]
    for axis, (image, title) in zip(axes[0], panels):
        axis.imshow(image)
        axis.set_title(title)
        axis.axis("off")

    for axis, lesion in zip(axes[1], LESION_COLORS):
        overlay = gradcam_overlays.get(lesion)
        if overlay is None:
            axis.imshow(original_rgb)
            axis.text(
                0.5,
                0.5,
                "No lesion predicted",
                transform=axis.transAxes,
                ha="center",
                va="center",
                bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
            )
        else:
            axis.imshow(overlay)
        axis.set_title(f"{lesion} Grad-CAM")
        axis.axis("off")

    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
