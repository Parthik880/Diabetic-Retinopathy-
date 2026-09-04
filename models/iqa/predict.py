"""Validation and reusable single-image TOPIQ-NR prediction."""

from __future__ import annotations

import math
from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError

from .model import DEFAULT_CHECKPOINT_PATH, METRIC_ID, MODEL_LABEL, IQAModel

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
    """Return the raw TOPIQ-NR score for one image without thresholds."""
    path = validate_image(image_path)
    iqa_model = (
        model
        if model is not None
        else IQAModel(checkpoint=checkpoint_path, device=device)
    )

    with torch.inference_mode():
        output = iqa_model.metric(str(path))
    if output.numel() != 1:
        raise RuntimeError(
            f"Expected one TOPIQ score, received shape {tuple(output.shape)}"
        )

    score = float(output.detach().cpu().item())
    if not math.isfinite(score):
        raise RuntimeError(f"TOPIQ returned a non-finite score: {score}")

    return {
        "image": str(path),
        "score": score,
        "metric": MODEL_LABEL,
        "metric_id": METRIC_ID,
        "checkpoint_path": str(iqa_model.checkpoint_path),
        "device": str(iqa_model.device),
    }
