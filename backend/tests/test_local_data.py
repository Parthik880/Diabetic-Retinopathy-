from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.history import HistoryStore
from app.local_data import LocalDataService
from app.database import Base, DatabaseStore
from sqlalchemy import inspect, text


PATIENT = {"id": "p1", "patientIdNumber": "RH-1", "name": "Test Patient", "age": 50, "gender": "Other", "phone": "+1 202 555 0146", "email": "fixture@example.test"}
RECORD = {"session_id": "s1", "patient_id": "RH-1", "patient_name": "Test Patient", "patient": {"id": "p1"}, "left_eye": {"available": True}, "right_eye": {}}


class DataTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ)
        self.environment.start()
        os.environ.pop("RETINA_DATABASE_URL", None)
        os.environ.pop("RETINA_HISTORY_PATH", None)
        self.store = HistoryStore(self.root / "runtime" / "history" / "index.json")
        self.service = LocalDataService(self.root / "runtime", self.store)

    def tearDown(self):
        if self.store.database:
            self.store.database.engine.dispose()
        self.environment.stop()
        self.temp.cleanup()

    def test_contacts_survive_restart_without_any_scan_and_legacy_loads(self):
        self.store.register_patient(PATIENT)
        restarted = HistoryStore(self.store.path)
        self.assertEqual(restarted.list_patients()[0]["email"], PATIENT["email"])
        self.assertEqual(restarted.list_patients()[0]["phone"], PATIENT["phone"])
        self.store.upsert(RECORD)
        self.assertEqual(restarted.list()[0]["patient"]["email"], PATIENT["email"])
        self.assertEqual(self.service.overview()["patient_count"], 1)
        self.assertEqual(self.service.overview()["session_count"], 1)
        self.assertIsNone(self.service.overview()["pending_items"])
        with self.assertRaises(ValueError):
            self.store.register_patient(PATIENT)

    def test_no_contacts_and_invalid_contacts(self):
        self.store.register_patient({k: v for k, v in PATIENT.items() if k not in {"email", "phone"}})
        self.assertEqual(self.store.list_patients()[0]["phone"], "")
        for contact in ({"email": "bad\r\nBcc: hidden@example.test"}, {"phone": "file:///C:/windows"}, {"age": -1}):
            with self.subTest(contact=contact), self.assertRaises(ValueError):
                self.store.register_patient({**PATIENT, "patientIdNumber": "RH-2", **contact})

    def test_clear_preview_confirmation_scoping_and_changed_files(self):
        self.store.register_patient(PATIENT)
        self.store.upsert(RECORD)
        runtime = self.service.root
        run = runtime / "runs" / ("a" * 32)
        run.mkdir(parents=True)
        source, artifact, weights = run / "input.jpg", run / "response.json", run / "model.pth"
        for path in (source, artifact, weights):
            path.write_text("keep", encoding="utf-8")
        external = self.root / "external.pdf"
        external.write_text("external report", encoding="utf-8")
        self.store.update_report_path("s1", "OS", str(external))
        preview = self.service.preview(["artifacts", "history"])
        self.assertEqual(preview["file_count"], 1)
        for confirmed, typed in ((False, "DELETE"), (True, ""), (True, "delete")):
            with self.assertRaises(ValueError):
                self.service.clear(preview["token"], confirmed, typed)
        self.assertTrue(artifact.exists())
        result = self.service.clear(preview["token"], True, "DELETE")
        self.assertEqual(result["deleted_files"], 1)
        self.assertFalse(artifact.exists())
        self.assertTrue(source.exists() and weights.exists() and external.exists())
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.store.list_patients(), [])
        with self.assertRaises(ValueError):
            self.service.clear(preview["token"], True, "DELETE")
        preview = self.service.preview(["images"])
        source.write_text("modified since preview", encoding="utf-8")
        self.assertEqual(self.service.clear(preview["token"], True, "")["skipped_files"], 1)
        self.assertTrue(source.exists())

    def test_busy_and_empty_selection_cannot_clear(self):
        for categories in ([], None, ["other"], [{}]):
            with self.assertRaises(ValueError):
                self.service.preview(categories)
        preview = self.service.preview(["images"])
        self.service.busy = lambda: True
        with self.assertRaises(ValueError):
            self.service.preview(["images"])
        with self.assertRaises(ValueError):
            self.service.clear(preview["token"], True, "")

    def test_junctions_do_not_expand_cleanup_scope(self):
        import subprocess
        outside = self.root / "external"
        outside.mkdir()
        original = outside / "important.pdf"
        original.write_text("preserve", encoding="utf-8")
        link = self.service.root / "reports"
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
        else:
            link.symlink_to(outside, target_is_directory=True)
        try:
            preview = self.service.preview(["reports"])
            self.assertEqual(preview["file_count"], 0)
            self.service.clear(preview["token"], True, "")
            self.assertTrue(original.exists())
        finally:
            if os.name == "nt":
                link.rmdir()
            else:
                link.unlink()

    def test_sqlalchemy_persistence_and_clear_preserve_schema_and_other_tables(self):
        self.store.database = DatabaseStore(f"sqlite:///{self.root / 'test.sqlite'}")
        self.store.register_patient(PATIENT)
        self.store.upsert(RECORD)
        database = self.store.database
        with database.engine.begin() as connection:
            connection.execute(text("CREATE TABLE unrelated (value INTEGER)"))
            connection.execute(text("INSERT INTO unrelated VALUES (7)"))
        self.assertEqual(database.list_patients()[0]["email"], PATIENT["email"])
        preview = self.service.preview(["history"])
        self.service.clear(preview["token"], True, "DELETE")
        self.assertEqual(database.list_records(), [])
        self.assertEqual(database.list_patients(), [])
        self.assertTrue(set(Base.metadata.tables).issubset(inspect(database.engine).get_table_names()))
        with database.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT value FROM unrelated")).scalar(), 7)

    def test_sync_preferences_persist_without_claiming_sync(self):
        value = {"automatic": True, "patients": True, "reports": True, "images": False}
        self.service.update_settings(value)
        reopened = LocalDataService(self.service.root, HistoryStore(self.store.path)).overview()
        self.assertEqual(reopened["sync_settings"], value)
        self.assertFalse(reopened["cloud_connected"])
        self.assertIsNone(reopened["last_sync"])


if __name__ == '__main__':
    unittest.main()
