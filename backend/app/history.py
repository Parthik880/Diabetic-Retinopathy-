"""Small, offline, atomic JSON persistence for completed RetinaGram sessions."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
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

    def _read_unlocked(self, path: Path | None = None) -> list[dict]:
        path = path or self.path
        if not path.is_file():
            return []
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if path == self.patients_path:
                raise ValueError('Patient storage could not be read. Restore the local JSON file before registering patients.')
            return []
        if path == self.patients_path and (not isinstance(value, list) or any(not isinstance(item, dict) for item in value)):
            raise ValueError('Patient storage has an invalid format. Restore the local JSON file before registering patients.')
        return value if isinstance(value, list) else []

    def _write_unlocked(self, records: list[dict], path: Path | None = None) -> None:
        path = path or self.path
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(records, indent=2, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(path)

    @property
    def patients_path(self) -> Path:
        return self.path.with_name(self.path.stem + '-patients.json')

    def patients(self) -> list[dict]:
        with self._lock:
            return self._read_unlocked(self.patients_path)

    def register_patient(self, patient: dict) -> dict:
        # Reuse PatientRecord, but accept registration only (no scan artifacts).
        saved = deepcopy(patient)
        for key in ('id', 'name', 'patientIdNumber'):
            if not isinstance(saved.get(key), str) or not saved[key].strip():
                raise ValueError('Patient name and identifiers are required.')
            saved[key] = saved[key].strip()
        for key in ('leftEye', 'rightEye'):
            scan = saved.get(key)
            if not isinstance(scan, dict) or scan.get('imageUrl') or scan.get('result'):
                raise ValueError('Registration must contain empty eye records; save scans in history.')
        email = str(saved.get('email') or '').strip()
        phone = re.sub(r'[\s().-]', '', str(saved.get('phone') or '').strip())
        if email and (len(email) > 254 or not re.fullmatch(r'[^\s@?&#%]+@[^\s@?&#%]+\.[^\s@?&#%]+', email)):
            raise ValueError('Enter a valid email address.')
        if phone and not re.fullmatch(r'\+?[0-9]{7,15}', phone):
            raise ValueError('Phone must contain 7–15 digits and an optional leading +.')
        saved.update(email=email, phone=phone)
        with self._lock:
            records = self._read_unlocked(self.patients_path)
            # Never overwrite an existing registration accidentally.
            if any(item.get('id') == saved['id'] or item.get('patientIdNumber') == saved['patientIdNumber'] for item in records):
                raise ValueError('This patient ID is already registered. Select that patient or use a different ID.')
            records.insert(0, saved)
            self._write_unlocked(records, self.patients_path)
        return deepcopy(saved)

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
