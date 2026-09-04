"""Preprocessing and reusable single-image grade prediction."""

from __future__ import annotations

from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError
from torchvision import transforms

from .gradcam import GradCAM
from .model import DEFAULT_CHECKPOINT_PATH, Convextnet, load_grade_model

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
GRADE_CLASS_MAPPING = {index: index for index in range(5)}

# This is intentionally identical to the transform from the original inference.py.
GRADE_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ]
)


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


def preprocess_grade_image(image_path: str | Path) -> tuple[Path, torch.Tensor]:
    path = validate_image(image_path)
    with Image.open(path) as image:
        image_tensor = GRADE_TRANSFORM(image.convert("RGB"))
    return path, image_tensor.unsqueeze(0)


def predict_grade(
    image_path: str | Path,
    model: Convextnet | None = None,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    return_gradcam: bool = False,
) -> dict:
    """Predict the unchanged grade index/probabilities for one image.

    Pass a loaded model to reuse it across images. Otherwise the trained
    checkpoint is loaded from ``checkpoint_path``.
    """
    path, image_tensor = preprocess_grade_image(image_path)
    if model is None:
        model = load_grade_model(checkpoint_path=checkpoint_path, device=device)

    try:
        model_device = next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError("Grade model has no parameters") from exc

    image_tensor = image_tensor.to(model_device)
    model.eval()

    cam = None
    if return_gradcam:
        gradcam = GradCAM(model, model.model.features[-1][-1])
        try:
            cam, probabilities, predicted_class = gradcam.generate(image_tensor)
        finally:
            gradcam.remove_hooks()
    else:
        with torch.inference_mode():
            logits = model(image_tensor)
            probabilities = torch.softmax(logits, dim=1).detach().cpu()
        predicted_class = int(probabilities.argmax(dim=1).item())

    result = {
        "image": str(path),
        "grade": GRADE_CLASS_MAPPING[predicted_class],
        "probabilities": [float(value) for value in probabilities[0]],
        "device": str(model_device),
    }
    if cam is not None:
        result["gradcam"] = cam
    return result
