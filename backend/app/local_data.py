"""Local data inventory and explicitly confirmed, application-scoped cleanup."""
from pathlib import Path
import os
import re
import time
from threading import RLock
from uuid import uuid4


CATEGORIES = {
    "temporary": "Temporary inference files",
    "artifacts": "Generated analysis artifacts",
    "reports": "Locally managed reports",
    "images": "Retinal images",
    "history": "Patient/session history",
}
DEFAULT_SYNC = {"automatic": False, "patients": True, "reports": True, "images": False}


def linked(path):
    return path.is_symlink() or os.path.isjunction(path)


class LocalDataService:
    def __init__(self, root, history, busy=lambda: False):
        self.root = Path(root).resolve()
        self.history = history
        self.busy = busy
        self._lock = RLock()
        self._previews = {}

    def files(self):
        result = []
        for directory, dirs, files in os.walk(self.root, followlinks=False):
            parent = Path(directory)
            dirs[:] = [name for name in dirs if not linked(parent / name)]
            for name in files:
                path = parent / name
                if linked(path) or not path.resolve().is_relative_to(self.root):
                    continue
                relative = path.relative_to(self.root)
                parts = relative.parts
                category = None
                if parts[0] in {"temp", "tmp"}:
                    category = "temporary"
                elif parts[0] == "reports":
                    category = "reports"
                elif len(parts) >= 3 and parts[0] == "runs" and re.fullmatch(r"[0-9a-f]{32}", parts[1]):
                    if name.endswith(".tmp"):
                        category = "temporary"
                    elif name.startswith("input.") or "restoration" in parts:
                        category = "images"
                    else:
                        category = "artifacts"
                # Never classify checkpoints, schemas, DB files, or config for deletion.
                if path.suffix.lower() in {".pth", ".pt", ".onnx", ".sql", ".sqlite", ".db"}:
                    category = None
                try:
                    stat = path.stat()
                    result.append((path, category, stat.st_size, stat.st_mtime_ns))
                except FileNotFoundError:
                    continue
        return result

    def overview(self):
        with self._lock:
            files = self.files()
            records = self.history.list()
            patients = self.history.list_patients()
            reports = {str(eye["report_path"]) for record in records for eye in (record.get("left_eye") or {}, record.get("right_eye") or {}) if eye.get("report_path") and Path(eye["report_path"]).is_file()}
            reports.update(str(path) for path, category, *_ in files if category == "reports" and path.suffix.lower() == ".pdf")
            settings = {**DEFAULT_SYNC, **self.history.settings()}
            runs_root = self.root / "runs"
            analysis_runs = sum(
                path.is_dir() and not linked(path) and bool(re.fullmatch(r"[0-9a-f]{32}", path.name))
                for path in runs_root.iterdir()
            ) if runs_root.is_dir() else 0
            retinal_images = sum(category == "images" for _path, category, *_ in files)
            generated_overlays = sum(
                category == "artifacts" and "overlay" in path.name.casefold()
                for path, category, *_ in files
            )
            runtime_cache_bytes = sum(size for _path, category, size, _modified in files if category == "temporary")
            return {
                "cloud_connected": False, "cloud_status": "Not connected", "cloud_state": "not_connected",
                "cloud_message": "Cloud provider not configured", "last_sync": None,
                "storage_backend": "PostgreSQL" if self.history.database else "Local JSON (PostgreSQL not configured)",
                "database_engine": "PostgreSQL", "database_status": self.history.database_status(),
                "patient_count": len(patients), "session_count": len(records), "report_count": len(reports),
                "storage_bytes": sum(item[2] for item in files), "data_folder": str(self.root),
                "pending_items": None, "pending_reports": None, "pending_images": None, "failed_items": None,
                "analysis_runs": analysis_runs, "retinal_image_count": retinal_images,
                "generated_overlay_count": generated_overlays, "runtime_cache_bytes": runtime_cache_bytes,
                "sync_settings": settings,
                "busy": self.busy(),
                "categories": [{"id": key, "label": label,
                                "files": sum(item[1] == key for item in files),
                                "bytes": sum(item[2] for item in files if item[1] == key)} for key, label in CATEGORIES.items()],
            }

    def update_settings(self, value):
        if set(value) != set(DEFAULT_SYNC) or any(type(item) is not bool for item in value.values()):
            raise ValueError("Invalid sync preferences.")
        self.history.save_settings(value)
        return self.overview()

    def preview(self, categories):
        with self._lock:
            if self.busy():
                raise ValueError("Finish or cancel active analysis before clearing local data.")
            if not isinstance(categories, list) or not categories or any(not isinstance(item, str) or item not in CATEGORIES for item in categories):
                raise ValueError("Select at least one valid category.")
            categories = sorted(set(categories))
            files = [item for item in self.files() if item[1] in categories]
            token = uuid4().hex
            self._previews = {key: value for key, value in self._previews.items() if value["expires"] > time.monotonic()}
            self._previews[token] = {"categories": categories, "files": files, "expires": time.monotonic() + 600}
            return {"token": token, "categories": categories, "file_count": len(files), "bytes": sum(item[2] for item in files),
                    "patient_count": len(self.history.list_patients()) if "history" in categories else 0,
                    "session_count": len(self.history.list()) if "history" in categories else 0}

    def clear(self, token, confirmed, typed):
        with self._lock:
            if not isinstance(token, str):
                raise ValueError("A valid preview is required.")
            preview = self._previews.get(token)
            if not preview or preview["expires"] < time.monotonic():
                raise ValueError("This preview expired. Review the selected data again.")
            if confirmed is not True or ("history" in preview["categories"] and typed != "DELETE"):
                raise ValueError("Confirm deletion; type DELETE to remove patient/session history.")
            if self.busy():
                raise ValueError("Finish or cancel active analysis before clearing local data.")
            self._previews.pop(token)
            deleted, skipped = 0, 0
            # Re-enumerate our allowlist; never trust request paths or follow links.
            current = {str(p): (category, size, modified) for p, category, size, modified in self.files()}
            for path, category, size, modified in preview["files"]:
                if current.get(str(path)) != (category, size, modified):
                    skipped += 1
                    continue
                try:
                    if linked(path) or any(linked(p) for p in path.parents if p != self.root and p.is_relative_to(self.root)):
                        skipped += 1
                        continue
                    path.unlink()
                    deleted += 1
                except OSError:
                    skipped += 1
            if "history" in preview["categories"]:
                self.history.clear_history()
            return {"deleted_files": deleted, "skipped_files": skipped, "history_cleared": "history" in preview["categories"]}
