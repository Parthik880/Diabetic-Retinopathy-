from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "inference" / "outputs" / "visualizer"
SESSION_ROOT = RUNTIME_ROOT / "sessions"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_EDGE = 2048
SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
}


def ensure_runtime_directories() -> None:
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
