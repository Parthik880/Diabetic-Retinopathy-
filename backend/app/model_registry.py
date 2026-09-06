from __future__ import annotations

from threading import RLock
from typing import Any

import torch

from models.grade.model import DEFAULT_CHECKPOINT_PATH as GRADE_CHECKPOINT
from models.grade.model import load_grade_model
from models.iqa.inference import EfficientNetIQAService
from models.iqa.model import DEFAULT_CHECKPOINT_PATH as IQA_CHECKPOINT
from models.lesion.model import DEFAULT_CHECKPOINT_PATH as LESION_CHECKPOINT
from models.lesion.model import load_lesion_model
from models.restoration.model import DEFAULT_CHECKPOINT_PATH as RESTORATION_CHECKPOINT
from models.restoration.model import load_restoration_model


MODEL_DEFINITIONS = {
    "quality": {
        "label": "Image Quality Assessment",
        "architecture": "EfficientNet-B0 + calibrated MLP",
        "checkpoint": IQA_CHECKPOINT,
    },
    "restoration": {
        "label": "Image Restoration",
        "architecture": "NAFNet width-32",
        "checkpoint": RESTORATION_CHECKPOINT,
    },
    "grade": {
        "label": "DR Grade Classification",
        "architecture": "ConvNeXt Tiny (5 classes)",
        "checkpoint": GRADE_CHECKPOINT,
    },
    "lesion": {
        "label": "Lesion Segmentation",
        "architecture": "MobileNetV3-Large UNet++ (4 channels)",
        "checkpoint": LESION_CHECKPOINT,
    },
}


class ModelRegistry:
    """Lazily load and reuse the repository's unchanged model instances."""

    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._models: dict[str, Any] = {}
        self._lock = RLock()

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "id": model_id,
                "label": definition["label"],
                "architecture": definition["architecture"],
                "checkpoint": str(definition["checkpoint"]),
                "checkpoint_present": definition["checkpoint"].is_file(),
            }
            for model_id, definition in MODEL_DEFINITIONS.items()
        ]

    def get(self, model_id: str) -> Any:
        with self._lock:
            if model_id in self._models:
                return self._models[model_id]

            if model_id == "quality":
                model = EfficientNetIQAService(device=self.device)
            elif model_id == "restoration":
                model, _ = load_restoration_model(device=self.device)
            elif model_id == "grade":
                model = load_grade_model(device=self.device)
            elif model_id == "lesion":
                model, _ = load_lesion_model(device=self.device)
            else:
                raise KeyError(f"Unknown model id: {model_id}")

            self._models[model_id] = model
            return model


registry = ModelRegistry()
INFERENCE_LOCK = RLock()
