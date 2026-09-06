"""Trained image-quality classification head."""

from torch import nn

from models.checkpoints import IQA_CHECKPOINT


DEFAULT_CHECKPOINT_PATH = IQA_CHECKPOINT
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
