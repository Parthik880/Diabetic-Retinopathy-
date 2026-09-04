"""Inference-only wrapper around pyiqa's official pretrained TOPIQ-NR model."""

from __future__ import annotations

from pathlib import Path

import pyiqa
import torch

from models.checkpoints import checkpoint_path


METRIC_ID = "topiq_nr"
MODEL_LABEL = "TOPIQ-NR"
PRETRAINED_VARIANT = "cfanet_nr_koniq_res50"
DEFAULT_CHECKPOINT_PATH = checkpoint_path(
    "iqa", "cfanet_nr_koniq_res50-9a73138b.pth"
)


class IQAModel:
    """Initialize TOPIQ-NR once so it can be reused for many predictions."""

    def __init__(
        self,
        checkpoint: str | Path = DEFAULT_CHECKPOINT_PATH,
        device: str | torch.device | None = None,
    ) -> None:
        path = Path(checkpoint).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                f"TOPIQ checkpoint not found: {path}. Extract the offline "
                "checkpoint bundle, set DR_CHECKPOINT_DIR, or pass --checkpoint."
            )
        self.device = torch.device(
            device
            if device is not None
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested, but torch.cuda.is_available() is false"
            )

        # Disable both pyiqa's remote CFANet load and timm's ImageNet backbone
        # load. The local checkpoint contains the complete trained network.
        self.metric = pyiqa.create_metric(
            METRIC_ID,
            device=self.device,
            pretrained=False,
            backbone_pretrain=False,
        )
        # InferenceModel.load_weights delegates to a strict state-dict load.
        self.metric.load_weights(str(path), weight_keys="params")
        self.metric.eval()
        self.checkpoint_path = path

    @property
    def model(self):
        """Expose the loaded pyiqa metric for advanced callers."""
        return self.metric
