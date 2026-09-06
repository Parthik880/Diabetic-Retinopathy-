"""Validation and reusable single-image quality classification."""

from __future__ import annotations

from functools import lru_cache
from threading import Lock
from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError

from runtime_device import resolve_cpu_device
from .model import DEFAULT_CHECKPOINT_PATH, METRIC_ID, MODEL_LABEL
from .inference import EfficientNetIQAService

IQAModel = EfficientNetIQAService
_MODEL_LOCK = Lock()


@lru_cache(maxsize=4)
def _cached_model(checkpoint: str, device: str) -> EfficientNetIQAService:
    return EfficientNetIQAService(checkpoint_path=checkpoint, device=device)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def validate_image(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"Image file does not exist: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported image extension '{resolved.suffix}'. Supported: {allowed}"
        )
    try:
        with Image.open(resolved) as image:
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Image is unreadable or invalid: {resolved} ({exc})") from exc
    return resolved


def predict_iqa(
    image_path: str | Path,
    model: IQAModel | None = None,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
) -> dict:
    """Return calibrated classes; reuse an explicit service or a cached model."""
    path = validate_image(image_path)
    if model is None:
        selected_device = resolve_cpu_device(device)
        with _MODEL_LOCK:
            model = _cached_model(
                str(Path(checkpoint_path).expanduser().resolve()), str(selected_device)
            )
    with Image.open(path) as image:
        prediction = model.predict(image)

    return {
        "image": str(path),
        **prediction,
        "metric": MODEL_LABEL,
        "metric_id": METRIC_ID,
        "checkpoint_path": str(model.checkpoint_path),
        "device": str(model.device),
    }
