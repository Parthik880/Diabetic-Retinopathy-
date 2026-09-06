"""Verify the CPU wheel and every persistent RetinaGram model device."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import torch

from utils.model_loader import ModelRegistry


print(f"torch.__version__: {torch.__version__}")
print(f"torch.version.cuda: {torch.version.cuda}")
print(f"torch.cuda.is_available(): {torch.cuda.is_available()}")
if torch.version.cuda is not None or torch.cuda.is_available():
    raise SystemExit("Expected the official CPU-only PyTorch wheel.")

registry = ModelRegistry()
if registry.errors:
    raise SystemExit(f"Model loading failed: {registry.errors}")
for name, device in registry.model_devices.items():
    print(f"{name} next(model.parameters()).device: {device}")
    if device != "cpu":
        raise SystemExit(f"{name} loaded on {device}; expected cpu.")
print("RetinaGram inference device: CPU")
