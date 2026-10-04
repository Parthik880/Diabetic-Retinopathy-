"""Portable paths for offline tools; never imported by the native runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("RETINAGRAM_REFERENCE_ROOT", ROOT.parent / "Diabetic-Retinopathy-"))
SOURCE_BACKEND = SOURCE / "backend"
CHECKPOINTS = ROOT / "checkpoints"
SOURCE_CHECKPOINTS = Path(os.environ.get("RETINAGRAM_SOURCE_CHECKPOINTS", SOURCE / "checkpoints"))


def source_checkpoint(name: str) -> Path:
    path = SOURCE_CHECKPOINTS / name
    if not path.is_file() and name == "efficientnet_b0_rwightman-7f5810bc.pth":
        path = Path(os.environ.get("TORCH_HOME", Path.home() / ".cache/torch")) / "hub/checkpoints" / name
    if not path.is_file():
        raise FileNotFoundError(f"Source checkpoint unavailable: {path}. Set RETINAGRAM_SOURCE_CHECKPOINTS.")
    return path


def validation_images() -> list[Path]:
    manifest = os.environ.get("RETINAGRAM_VALIDATION_MANIFEST")
    if manifest:
        manifest_path = Path(manifest).resolve()
        paths = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(paths, list) or len(paths) != 6 or not all(isinstance(p, str) for p in paths):
            raise ValueError("Validation manifest must contain six image paths: four Good, Usable, Reject.")
        return [(manifest_path.parent / path).resolve() for path in paths]
    return [
        SOURCE / "resources/test-images/20170629163635747.jpg",
        SOURCE / "frontend/public/samples/retina-b.jpg",
        ROOT / "build/validation/good_2.png",
        ROOT / "build/validation/good_3.png",
        ROOT / "build/validation/quality_cases/usable_768.png",
        ROOT / "build/validation/quality_cases/blur_12.png",
    ]
