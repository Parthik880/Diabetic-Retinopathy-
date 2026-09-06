"""ConvNeXt grade architecture, checkpoint loading, and device selection."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import torch
from torch import nn

from models.checkpoints import checkpoint_path
from runtime_device import resolve_cpu_device


DEFAULT_CHECKPOINT_PATH = checkpoint_path("grade", "convnext_tiny.pth")


def resolve_device(device: str | torch.device | None = None) -> torch.device:
    """Resolve the CPU-only device used by this desktop edition."""
    return resolve_cpu_device(device)


class Convextnet(nn.Module):
    """Original five-class ConvNeXt grade architecture.

    The historical class name is retained so existing checkpoints and callers
    remain compatible. ``pretrained_backbone`` defaults to the original ImageNet
    initialization; checkpoint loading disables it because every parameter is
    immediately replaced by the trained state dictionary.
    """

    def __init__(
        self,
        numclasses: int = 5,
        type: str = "Tiny",
        pretrained_backbone: bool = True,
    ) -> None:
        super().__init__()
        self.num = numclasses

        if type == "Tiny":
            from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny

            weights = (
                ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained_backbone else None
            )
            self.model = convnext_tiny(weights=weights)
        elif type == "Small":
            from torchvision.models import ConvNeXt_Small_Weights, convnext_small

            weights = (
                ConvNeXt_Small_Weights.IMAGENET1K_V1 if pretrained_backbone else None
            )
            self.model = convnext_small(weights=weights)
        else:
            from torchvision.models import ConvNeXt_Base_Weights, convnext_base

            weights = (
                ConvNeXt_Base_Weights.IMAGENET1K_V1 if pretrained_backbone else None
            )
            self.model = convnext_base(weights=weights)

        in_features = self.model.classifier[2].in_features
        self.model.classifier[2] = nn.Linear(in_features, self.num)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model(x)


def _load_checkpoint(path: Path) -> Mapping[str, torch.Tensor]:
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:  # Compatibility with older supported PyTorch releases.
        checkpoint = torch.load(path, map_location="cpu")

    if not isinstance(checkpoint, Mapping):
        raise TypeError(f"Unsupported checkpoint format in {path}")

    for key in ("model_state_dict", "state_dict", "model"):
        nested = checkpoint.get(key)
        if isinstance(nested, Mapping):
            checkpoint = nested
            break

    if not checkpoint or not all(isinstance(key, str) for key in checkpoint):
        raise ValueError(
            f"Checkpoint does not contain a valid state dictionary: {path}"
        )

    if all(key.startswith("module.") for key in checkpoint):
        checkpoint = {
            key.removeprefix("module."): value for key, value in checkpoint.items()
        }

    return checkpoint


def load_grade_model(
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
    numclasses: int = 5,
    model_type: str = "Tiny",
) -> Convextnet:
    """Load a trained grade checkpoint without changing its architecture."""
    path = Path(checkpoint_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Grade checkpoint not found: {path}. "
            "Extract the offline checkpoint bundle, set DR_CHECKPOINT_DIR, "
            "or pass --checkpoint."
        )

    resolved_device = resolve_device(device)
    model = Convextnet(
        numclasses=numclasses,
        type=model_type,
        pretrained_backbone=False,
    )
    model.load_state_dict(_load_checkpoint(path), strict=True)
    model.to(resolved_device)
    model.eval()
    return model
