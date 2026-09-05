"""Reusable calibrated EfficientNet-B0 image-quality inference."""

from __future__ import annotations

import math
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms

from .model import DEFAULT_CHECKPOINT_PATH, IQA_CLASS_NAMES, EfficientNetIQA

IMAGE_SIZE = 224


class EfficientNetIQAService:
    """Load once at application startup, then reuse predict for each image."""

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
        device: str | torch.device | None = None,
        *,
        checkpoint: str | Path | None = None,
    ):
        # Support the existing IQAModel(checkpoint=...) keyword.
        self.checkpoint_path = Path(
            checkpoint if checkpoint is not None else checkpoint_path
        ).expanduser().resolve()
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"IQA checkpoint not found: {self.checkpoint_path}")
        self.device = torch.device(
            device if device is not None else
            ("cuda" if torch.cuda.is_available() else "cpu")
        )
        saved = torch.load(
            self.checkpoint_path, map_location=self.device, weights_only=False
        )
        self.temperature = float(saved.get("temperature", 1.0))
        if not math.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("Checkpoint temperature must be finite and positive")
        self.classifier = EfficientNetIQA()
        self.classifier.load_state_dict(saved["model_state_dict"], strict=True)
        self.classifier = self.classifier.to(self.device).eval()
        efficientnet = models.efficientnet_b0(
            weights=models.EfficientNet_B0_Weights.DEFAULT
        )
        efficientnet.eval()
        for parameter in efficientnet.parameters():
            parameter.requires_grad = False
        self.feature_extractor = nn.Sequential(
            efficientnet.features, efficientnet.avgpool
        ).to(self.device).eval()
        self.transform = transforms.Compose([
            transforms.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    @torch.inference_mode()
    def predict(self, image: Image.Image) -> dict:
        images = self.transform(image.convert("RGB")).unsqueeze(0).to(self.device)
        features = self.feature_extractor(images).flatten(start_dim=1)
        logits = self.classifier(features)
        probabilities = torch.softmax(logits / self.temperature, dim=1)
        if not torch.isfinite(probabilities).all():
            raise RuntimeError("IQA returned non-finite probabilities")
        values = probabilities[0].cpu().tolist()
        class_id = int(probabilities.argmax(dim=1).item())
        return {
            "class_id": class_id,
            "quality": IQA_CLASS_NAMES[class_id],
            "confidence": values[class_id],
            "probabilities": dict(zip(IQA_CLASS_NAMES, values)),
        }
