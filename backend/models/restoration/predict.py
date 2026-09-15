"""Reusable full-resolution NAFNet restoration inference."""

from __future__ import annotations

from pathlib import Path
import time

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError

from .model import DEFAULT_CHECKPOINT_PATH, NAFNet, load_restoration_model


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}
DEFAULT_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "inference" / "outputs" / "restoration"
)


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


def _next_output_path(image_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"{image_path.stem}_restored.png"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{image_path.stem}_restored_{suffix}.png"
        suffix += 1
    return candidate


def restore_image(
    image_path: str | Path,
    checkpoint: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    output_dir: str | Path | None = None,
    model: NAFNet | None = None,
    timing: dict | None = None,
) -> dict:
    """Restore one RGB image without resizing or applying ImageNet normalization."""
    timing = timing if timing is not None else {}
    total_started = time.perf_counter_ns()
    started = time.perf_counter_ns()
    path = validate_image(image_path)
    timing["validation_ms"] = timing.get("validation_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    checkpoint_info = {}
    if model is None:
        model, checkpoint_info = load_restoration_model(checkpoint, device=device)
    try:
        model_device = next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError("Restoration model has no parameters") from exc

    started = time.perf_counter_ns()
    with Image.open(path) as image:
        rgb_image = image.convert("RGB")
        pixels = np.asarray(rgb_image, dtype=np.float32) / 255.0
        input_size = rgb_image.size
    timing["preprocessing_ms"] = timing.get("preprocessing_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    input_tensor = (
        torch.from_numpy(np.ascontiguousarray(pixels.transpose(2, 0, 1)))
        .unsqueeze(0)
        .to(model_device)
    )
    if model_device.type == "cuda":
        torch.cuda.synchronize(model_device)
    timing["h2d_transfer_ms"] = timing.get("h2d_transfer_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    with torch.inference_mode():
        restored_tensor = model(input_tensor)
    if model_device.type == "cuda":
        torch.cuda.synchronize(model_device)
    timing["nafnet_forward_ms"] = timing.get("nafnet_forward_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    restored = (
        restored_tensor.squeeze(0)
        .detach()
        .float()
        .cpu()
        .clamp(0.0, 1.0)
        .permute(1, 2, 0)
        .numpy()
    )
    timing["d2h_transfer_ms"] = timing.get("d2h_transfer_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    if restored.shape[:2] != (input_size[1], input_size[0]):
        raise RuntimeError("NAFNet output dimensions do not match the input")

    destination = _next_output_path(
        path,
        Path(output_dir).expanduser().resolve()
        if output_dir is not None
        else DEFAULT_OUTPUT_DIR,
    )
    started = time.perf_counter_ns()
    output_pixels = np.rint(restored * 255.0).astype(np.uint8)
    Image.fromarray(output_pixels, mode="RGB").save(destination)
    timing["png_writing_ms"] = timing.get("png_writing_ms", 0.0) + (time.perf_counter_ns() - started) / 1_000_000
    timing["total_ms"] = timing.get("total_ms", 0.0) + (time.perf_counter_ns() - total_started) / 1_000_000
    return {
        "restored_image": restored,
        "output_path": str(destination.resolve()),
        "image_path": str(path),
        "width": input_size[0],
        "height": input_size[1],
        "device": str(model_device),
        "checkpoint": checkpoint_info,
    }
