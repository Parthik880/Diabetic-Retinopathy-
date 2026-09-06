"""Small, offline, atomic JSON persistence for completed RetinaGram sessions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStore:
    def __init__(self, default_path: Path):
        configured = os.environ.get("RETINA_HISTORY_PATH")
        self.path = Path(configured).expanduser().resolve() if configured else default_path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _read_unlocked(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return value if isinstance(value, list) else []

    def _write_unlocked(self, records: list[dict]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def list(self) -> list[dict]:
        with self._lock:
            records = self._read_unlocked()
        return sorted(records, key=lambda item: item.get("scan_datetime") or "", reverse=True)

    def upsert(self, record: dict) -> dict:
        session_id = str(record.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("A scan session identifier is required.")
        has_scan_data = any(
            bool((record.get(key) or {}).get("available"))
            or bool((record.get(key) or {}).get("result_data"))
            or bool((record.get(key) or {}).get("report_path"))
            for key in ("left_eye", "right_eye")
        )
        if not has_scan_data:
            raise ValueError("History records require at least one captured or analyzed eye.")
        saved = {**deepcopy(record), "session_id": session_id, "updated_at": _now()}
        with self._lock:
            records = self._read_unlocked()
            index = next((i for i, item in enumerate(records) if item.get("session_id") == session_id), None)
            if index is None:
                records.append(saved)
            else:
                existing = records[index]
                for key in ("left_eye", "right_eye"):
                    prior_report = (existing.get(key) or {}).get("report_path")
                    if prior_report and not (saved.get(key) or {}).get("report_path"):
                        saved.setdefault(key, {})["report_path"] = prior_report
                records[index] = saved
            self._write_unlocked(records)
        return deepcopy(saved)

    def update_report_path(self, session_id: str, eye: str, report_path: str) -> None:
        key = "left_eye" if eye == "OS" else "right_eye"
        with self._lock:
            records = self._read_unlocked()
            for record in records:
                if record.get("session_id") == session_id:
                    record.setdefault(key, {})["report_path"] = report_path
                    record["updated_at"] = _now()
                    self._write_unlocked(records)
                    return
