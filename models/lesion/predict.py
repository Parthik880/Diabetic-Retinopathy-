"""Reusable four-channel UNet++ lesion prediction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError

from .dataset import IMAGE_SIZE, LESION_CLASSES
from .model import DEFAULT_CHECKPOINT_PATH, LesionUNetPlusPlus, load_lesion_model


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
DEFAULT_THRESHOLD = 0.5


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


def preprocess_lesion_image(image_path: str | Path) -> tuple[Path, torch.Tensor]:
    """Apply the unchanged 768px resize and ImageNet normalization."""
    path = validate_image(image_path)
    with Image.open(path) as image:
        image = image.convert("RGB").resize(
            (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.BILINEAR
        )
        tensor = torch.from_numpy(np.array(image)).permute(2, 0, 1).float() / 255.0
    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    return path, ((tensor - mean) / std).unsqueeze(0)


def predict_lesions(
    image_path: str | Path,
    model: LesionUNetPlusPlus | None = None,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict:
    """Return MA/HE/EX/SE probability maps and masks in trained channel order."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    path, image_tensor = preprocess_lesion_image(image_path)
    metadata = {}
    if model is None:
        model, metadata = load_lesion_model(checkpoint_path, device=device)
    try:
        model_device = next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError("Lesion model has no parameters") from exc

    with torch.inference_mode():
        logits = model(image_tensor.to(model_device))
        probabilities = torch.sigmoid(logits.float()).cpu()[0]
    expected_shape = (len(LESION_CLASSES), IMAGE_SIZE, IMAGE_SIZE)
    if tuple(probabilities.shape) != expected_shape:
        raise RuntimeError(
            f"Expected lesion probabilities with shape {expected_shape}, "
            f"received {tuple(probabilities.shape)}"
        )

    predictions = {}
    for lesion, channel in LESION_CLASSES.items():
        probability = probabilities[channel].numpy()
        predictions[lesion] = {
            "probability": probability,
            "mask": probability >= threshold,
            "channel": channel,
        }
    return {
        "image_path": str(path),
        "lesions": predictions,
        "threshold": threshold,
        "device": str(model_device),
        "checkpoint": metadata,
    }
