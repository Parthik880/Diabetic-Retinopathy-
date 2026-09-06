from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from backend.app.config import (
    MAX_IMAGE_EDGE,
    MAX_UPLOAD_BYTES,
    SESSION_ROOT,
    SUPPORTED_IMAGE_EXTENSIONS,
    ensure_runtime_directories,
)


def _safe_filename(filename: str | None) -> str:
    source = Path(filename or "retina.png")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", source.stem).strip("-") or "retina"
    extension = source.suffix.lower() or ".png"
    return f"{stem[:80]}{extension}"


async def save_upload(upload: UploadFile) -> tuple[str, Path, Path]:
    ensure_runtime_directories()
    filename = _safe_filename(upload.filename)
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise ValueError(f"Unsupported image type. Choose one of: {allowed}")

    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ValueError("The uploaded image is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("The image is larger than the 20 MB upload limit.")

    session_id = uuid.uuid4().hex
    session_dir = SESSION_ROOT / session_id
    session_dir.mkdir(parents=True)
    destination = session_dir / filename
    destination.write_bytes(data)

    try:
        with Image.open(destination) as image:
            image.verify()
        with Image.open(destination) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        destination.unlink(missing_ok=True)
        session_dir.rmdir()
        raise ValueError("The uploaded file is not a readable image.") from exc

    if max(width, height) > MAX_IMAGE_EDGE:
        destination.unlink(missing_ok=True)
        session_dir.rmdir()
        raise ValueError(
            f"Image dimensions exceed {MAX_IMAGE_EDGE}px on one edge. "
            "Use a smaller export to keep localhost inference responsive."
        )
    return session_id, session_dir, destination


def media_url(path: str | Path, session_id: str) -> str:
    resolved = Path(path).resolve()
    root = (SESSION_ROOT / session_id).resolve()
    relative = resolved.relative_to(root)
    return f"/media/{session_id}/{relative.as_posix()}"


def write_manifest(session_dir: Path, payload: dict[str, Any]) -> None:
    (session_dir / "analysis.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def read_manifest(session_id: str) -> dict[str, Any]:
    path = SESSION_ROOT / session_id / "analysis.json"
    if not path.is_file():
        raise FileNotFoundError("Analysis session not found.")
    return json.loads(path.read_text(encoding="utf-8"))
