"""Central checkpoint paths for every trained model."""

from __future__ import annotations

import os
from pathlib import Path


CHECKPOINT_ENV_VAR = "DR_CHECKPOINT_DIR"
MODELS_DIR = Path(__file__).resolve().parent
CHECKPOINT_DIR = MODELS_DIR / "checkpoints"


def checkpoint_root() -> Path:
    """Return the shared checkpoint directory without creating it."""
    configured = os.environ.get(CHECKPOINT_ENV_VAR)
    root = Path(configured).expanduser() if configured else CHECKPOINT_DIR
    return root.resolve()


def checkpoint_path(filename: str) -> Path:
    """Return a checkpoint file inside the shared flat directory."""
    return checkpoint_root() / filename


GRADE_CHECKPOINT = checkpoint_path("convnext_tiny.pth")
NAFNET_CHECKPOINT = checkpoint_path("NAFNet-SIDD-width32.pth")
LESION_CHECKPOINT = checkpoint_path(
    "lesion_mobilenetv3_unetpp_epoch_018_best_dice.pth"
)
IQA_CHECKPOINT = checkpoint_path("final_efficientnet_iqa.pth")
