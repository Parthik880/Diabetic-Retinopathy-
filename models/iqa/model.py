"""Inference-only wrapper around pyiqa's official pretrained TOPIQ-NR model."""

from __future__ import annotations

import pyiqa
import torch

METRIC_ID = "topiq_nr"
MODEL_LABEL = "TOPIQ-NR"
PRETRAINED_VARIANT = "cfanet_nr_koniq_res50"


class IQAModel:
    """Initialize TOPIQ-NR once so it can be reused for many predictions."""

    def __init__(self, device: str | torch.device | None = None) -> None:
        self.device = torch.device(
            device
            if device is not None
            else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested, but torch.cuda.is_available() is false"
            )

        self.metric = pyiqa.create_metric(METRIC_ID, device=self.device)
        self.metric.eval()

    @property
    def model(self):
        """Expose the loaded pyiqa metric for advanced callers."""
        return self.metric
