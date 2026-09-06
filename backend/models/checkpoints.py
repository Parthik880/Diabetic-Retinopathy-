"""Portable resolution of the centralized offline checkpoint bundle."""

from __future__ import annotations

import os
from pathlib import Path


CHECKPOINT_ENV_VAR = "DR_CHECKPOINT_DIR"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def checkpoint_root() -> Path:
    """Return the configured bundle root or the repository-local fallback."""
    configured = os.environ.get(CHECKPOINT_ENV_VAR)
    root = Path(configured).expanduser() if configured else PROJECT_ROOT / "checkpoint"
    return root.resolve()


def checkpoint_path(model_name: str, filename: str) -> Path:
    """Resolve one model asset inside the centralized checkpoint bundle."""
    return checkpoint_root() / model_name / filename
