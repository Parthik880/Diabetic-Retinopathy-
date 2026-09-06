"""Trained image-quality classification head."""

from pathlib import Path
from torch import nn

DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[2]
    / "model" / "checkpoints" / "final_efficientnet_iqa.pth"
)
IQA_CLASS_NAMES = ["Good", "Usable", "Reject"]
MODEL_LABEL = "EfficientNet-B0 + MLP"
METRIC_ID = "efficientnet_b0_iqa"


class EfficientNetIQA(nn.Module):
    def __init__(self, num_classes=3):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(1280, 128),
            nn.ReLU(),
            nn.Dropout(0.30),
            nn.Linear(128, num_classes),
        )

    def forward(self, x):
        return self.network(x)


def __getattr__(name):
    # Preserve the historical import without duplicating the service.
    if name == "IQAModel":
        from .inference import EfficientNetIQAService
        return EfficientNetIQAService
    raise AttributeError(name)
