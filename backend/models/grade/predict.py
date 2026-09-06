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
DEFAULT_GRADCAM_OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / "inference" / "outputs" / "gradcam"
)

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


def _next_gradcam_path(image_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"{image_path.stem}_gradcam.png"
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = output_dir / f"{image_path.stem}_gradcam_{suffix}.png"
        if not candidate.exists():
            return candidate
        suffix += 1


def _save_gradcam_overlay(
    image_path: Path, cam: torch.Tensor, output_dir: Path
) -> Path:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    with Image.open(image_path) as image:
        original_array = np.array(image.convert("RGB").resize((224, 224)))

    output_path = _next_gradcam_path(image_path, output_dir)
    figure, axis = plt.subplots(figsize=(6, 6))
    axis.imshow(original_array)
    axis.imshow(cam.numpy(), alpha=0.4, cmap="jet")
    axis.axis("off")
    figure.savefig(output_path, bbox_inches="tight", pad_inches=0)
    plt.close(figure)
    return output_path.resolve()


def predict_grade(
    image_path: str | Path,
    model: Convextnet | None = None,
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    save_gradcam: bool = True,
    gradcam_output_dir: str | Path | None = None,
) -> dict:
    """Return JSON-safe logits, probabilities, grade, confidence, and Grad-CAM path.

    Pass a loaded model to reuse it across images. Otherwise the trained
    checkpoint is loaded from ``checkpoint_path``. Grad-CAM is saved by default
    under ``inference/outputs/gradcam`` and can be disabled explicitly.
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

    if save_gradcam:
        gradcam = GradCAM(model)
        try:
            cam, logits, probabilities, predicted_class = gradcam.generate(image_tensor)
        finally:
            gradcam.remove_hooks()
    else:
        with torch.inference_mode():
            logits = model(image_tensor)
            probabilities = torch.softmax(logits, dim=1).detach().cpu()
            logits = logits.detach().cpu()
        predicted_class = int(probabilities.argmax(dim=1).item())

    if tuple(logits.shape) != (1, 5) or tuple(probabilities.shape) != (1, 5):
        raise RuntimeError(
            "Expected grade logits and probabilities with shape (1, 5), "
            f"received {tuple(logits.shape)} and {tuple(probabilities.shape)}"
        )

    predicted_grade = GRADE_CLASS_MAPPING[predicted_class]
    confidence = float(probabilities[0, predicted_class])
    gradcam_path = None
    if save_gradcam:
        output_dir = Path(
            gradcam_output_dir
            if gradcam_output_dir is not None
            else DEFAULT_GRADCAM_OUTPUT_DIR
        ).expanduser()
        gradcam_path = str(_save_gradcam_overlay(path, cam, output_dir.resolve()))

    return {
        "image_path": str(path),
        "logits": [float(value) for value in logits[0]],
        "probabilities": [float(value) for value in probabilities[0]],
        "predicted_class": predicted_class,
        "predicted_grade": predicted_grade,
        "confidence": confidence,
        "gradcam_path": gradcam_path,
        "device": str(model_device),
    }
