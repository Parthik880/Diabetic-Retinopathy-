"""MobileNetV3-Large UNet++ lesion architecture and checkpoint loading."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import (
    ConvNeXt_Tiny_Weights,
    MobileNet_V3_Large_Weights,
    convnext_tiny,
    mobilenet_v3_large,
)


DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[2]
    / "model" / "checkpoints" / "epoch_018_best_dice.pth"
)
DEFAULT_BACKBONE = "mobilenet_v3_large"
NUM_LESION_CLASSES = 4


class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.layers(x)


class LesionUNetPlusPlus(nn.Module):
    """ImageNet encoder and the original four-level nested U-Net++ decoder."""

    def __init__(self, backbone="mobilenet_v3_large", num_classes=1, pretrained=True):
        super().__init__()
        self.backbone = backbone
        if backbone == "mobilenet_v3_large":
            weights = MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
            self.encoder = mobilenet_v3_large(weights=weights).features
            self.feature_indices = (3, 6, 12, 16)
            encoder_channels = (24, 40, 112, 960)
        elif backbone == "convnext_tiny":
            weights = ConvNeXt_Tiny_Weights.DEFAULT if pretrained else None
            self.encoder = convnext_tiny(weights=weights).features
            self.feature_indices = (1, 3, 5, 7)
            encoder_channels = (96, 192, 384, 768)
        else:
            raise ValueError("backbone must be 'mobilenet_v3_large' or 'convnext_tiny'")

        decoder_channels = (32, 64, 128, 256)
        self.projections = nn.ModuleList(
            [
                nn.Conv2d(in_channels, out_channels, kernel_size=1)
                for in_channels, out_channels in zip(
                    encoder_channels, decoder_channels
                )
            ]
        )

        self.conv0_1 = ConvBlock(32 + 64, 32)
        self.conv1_1 = ConvBlock(64 + 128, 64)
        self.conv2_1 = ConvBlock(128 + 256, 128)
        self.conv0_2 = ConvBlock(32 * 2 + 64, 32)
        self.conv1_2 = ConvBlock(64 * 2 + 128, 64)
        self.conv0_3 = ConvBlock(32 * 3 + 64, 32)
        self.output = nn.Conv2d(32, num_classes, kernel_size=1)

    def upsample(self, x, reference):
        return F.interpolate(
            x, size=reference.shape[2:], mode="bilinear", align_corners=False
        )

    def forward(self, x):
        input_size = x.shape[2:]
        features = []
        for index, layer in enumerate(self.encoder):
            x = layer(x)
            if index in self.feature_indices:
                features.append(self.projections[len(features)](x))

        x0_0, x1_0, x2_0, x3_0 = features
        x0_1 = self.conv0_1(
            torch.cat([x0_0, self.upsample(x1_0, x0_0)], dim=1)
        )
        x1_1 = self.conv1_1(
            torch.cat([x1_0, self.upsample(x2_0, x1_0)], dim=1)
        )
        x2_1 = self.conv2_1(
            torch.cat([x2_0, self.upsample(x3_0, x2_0)], dim=1)
        )
        x0_2 = self.conv0_2(
            torch.cat([x0_0, x0_1, self.upsample(x1_1, x0_0)], dim=1)
        )
        x1_2 = self.conv1_2(
            torch.cat([x1_0, x1_1, self.upsample(x2_1, x1_0)], dim=1)
        )
        x0_3 = self.conv0_3(
            torch.cat([x0_0, x0_1, x0_2, self.upsample(x1_2, x0_0)], dim=1)
        )

        logits = self.output(x0_3)
        return F.interpolate(
            logits, size=input_size, mode="bilinear", align_corners=False
        )


def resolve_device(device: str | torch.device | None = None) -> torch.device:
    resolved = torch.device(
        device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
    )
    if resolved.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is false")
    return resolved


def _model_state_dict(checkpoint: object) -> Mapping[str, torch.Tensor]:
    if not isinstance(checkpoint, Mapping):
        raise TypeError("Lesion checkpoint must be a mapping")
    state_dict = checkpoint.get("model_state_dict", checkpoint)
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ValueError("Lesion checkpoint does not contain a model state dictionary")
    return state_dict


def load_lesion_model(
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
) -> tuple[LesionUNetPlusPlus, dict]:
    """Load the selected epoch-18 four-channel baseline with strict matching."""
    path = Path(checkpoint_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Lesion checkpoint not found: {path}")
    resolved_device = resolve_device(device)
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        checkpoint = torch.load(path, map_location="cpu")

    model = LesionUNetPlusPlus(
        backbone=DEFAULT_BACKBONE,
        num_classes=NUM_LESION_CLASSES,
        pretrained=False,
    )
    model.load_state_dict(_model_state_dict(checkpoint), strict=True)
    model.to(resolved_device).eval()
    metadata = {
        "checkpoint_path": str(path),
        "epoch": checkpoint.get("epoch") if isinstance(checkpoint, Mapping) else None,
        "config": checkpoint.get("config", {}) if isinstance(checkpoint, Mapping) else {},
    }
    return model, metadata
