"""Patient/session persistence: configured PostgreSQL or atomic offline JSON."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import RLock
import re


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryStore:
    def __init__(self, default_path: Path):
        configured = os.environ.get("RETINA_HISTORY_PATH")
        self.path = Path(configured).expanduser().resolve() if configured else default_path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.database = None
        database_url = os.environ.get("RETINA_DATABASE_URL")
        if database_url:
            if not database_url.startswith("postgresql+psycopg://"):
                raise ValueError("RETINA_DATABASE_URL must use postgresql+psycopg://")
            from app.database import DatabaseStore
            database = DatabaseStore(database_url)
            database.import_legacy(self._read_unlocked(), self.list_patients())
            self.database = database

    def _read_unlocked(self) -> list[dict]:
        if self.database:
            return self.database.list_records()
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
            patients = {p["patientIdNumber"]: p for p in self.list_patients()}
            for record in records:
                patient = patients.get(record.get("patient_id"))
                if patient:
                    record.setdefault("patient", {}).update({key: patient.get(key, "") for key in ("phone", "email")})
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
            if self.database:
                if not any(p["patientIdNumber"] == saved["patient_id"] for p in self.database.list_patients()):
                    details = saved.get("patient") or {}
                    self.database.save_patient({**details, "patientIdNumber": saved["patient_id"],
                                                "name": saved.get("patient_name", ""),
                                                "age": details.get("age") or 0, "gender": details.get("gender") or "Other"})
                self.database.save_record(saved)
            else:
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
                    if self.database:
                        self.database.save_record(record)
                    else:
                        self._write_unlocked(records)
                    return

    def _read_json(self, name, default):
        path = self.path.with_name(name)
        if not path.is_file():
            return deepcopy(default)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_json(self, name, value):
        path = self.path.with_name(name)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)

    def list_patients(self):
        with self._lock:
            patients = self.database.list_patients() if self.database else self._read_json("patients.json", [])
            known = {p["patientIdNumber"] for p in patients}
            # Older histories predate the patient table and contact fields.
            for record in self._read_unlocked():
                patient_id = record.get("patient_id")
                if patient_id and patient_id not in known:
                    patients.append({**(record.get("patient") or {}), "patientIdNumber": patient_id,
                                     "name": record.get("patient_name", ""), "age": (record.get("patient") or {}).get("age", 0),
                                     "gender": (record.get("patient") or {}).get("gender", "Other")})
                    known.add(patient_id)
            return patients

    def register_patient(self, value):
        keys = ("id", "patientIdNumber", "name", "age", "gender", "phone", "email", "dob", "diabeticHistoryYears", "hba1c", "bloodPressure")
        patient = {key: deepcopy(value[key]) for key in keys if key in value}
        for key in ("patientIdNumber", "name", "phone", "email"):
            patient[key] = str(patient.get(key) or "").strip()
        if not patient["patientIdNumber"] or not patient["name"] or len(patient["patientIdNumber"]) > 100 or len(patient["name"]) > 200:
            raise ValueError("A patient ID and name are required (maximum 100 and 200 characters).")
        if patient["email"] and (len(patient["email"]) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", patient["email"])):
            raise ValueError("Enter a valid email address.")
        if patient["phone"] and not re.fullmatch(r"\+?[0-9 ()\-.]{3,40}", patient["phone"]):
            raise ValueError("Enter a valid phone number.")
        if not isinstance(patient.get("age"), int) or isinstance(patient["age"], bool) or not 0 <= patient["age"] <= 120:
            raise ValueError("Age must be between 0 and 120.")
        if patient.get("gender") not in {"Female", "Male", "Other"}:
            raise ValueError("Select a valid gender.")
        with self._lock:
            patients = self.list_patients()
            if any(p["patientIdNumber"].casefold() == patient["patientIdNumber"].casefold() for p in patients):
                raise ValueError("This patient ID already exists. Select the existing patient to start a new session.")
            if self.database:
                self.database.save_patient(patient)
            else:
                self._save_json("patients.json", patients + [patient])
        return patient

    def settings(self):
        with self._lock:
            return self.database.settings() if self.database else self._read_json("sync-settings.json", {})

    def database_status(self):
        return "Ready" if self.database and self.database.health() else "Unavailable"

    def save_settings(self, value):
        with self._lock:
            if self.database:
                self.database.save_settings(value)
            else:
                self._save_json("sync-settings.json", value)

    def clear_history(self):
        with self._lock:
            if self.database:
                self.database.clear_history()
            # Clear the legacy copy too so switching offline cannot resurrect it.
            self._write_unlocked([])
            self._save_json("patients.json", [])
