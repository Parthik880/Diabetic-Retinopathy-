from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.history import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_completed_session_is_atomic_and_upserts_same_session(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = HistoryStore(path)
            record = {
                "session_id": "session-1", "patient_id": "RH-1", "patient_name": "Patient",
                "scan_datetime": "2026-09-05T10:00:00+00:00",
                "left_eye": {"available": True, "completed": True, "report_path": None},
                "right_eye": {"available": False, "completed": False, "report_path": None},
            }
            store.upsert(record)
            record["right_eye"]["completed"] = True
            store.upsert(record)
            self.assertEqual(len(store.list()), 1)
            self.assertTrue(store.list()[0]["right_eye"]["completed"])
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), list)

    def test_partial_without_completed_eye_is_rejected(self):
        with TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / "history.json")
            with self.assertRaisesRegex(ValueError, "captured or analyzed eye"):
                store.upsert({"session_id": "x", "left_eye": {}, "right_eye": {}})

    def test_same_patient_keeps_multiple_sessions_newest_first(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = HistoryStore(path)
            for session_id, timestamp in (("session-old", "2026-09-05T10:00:00+00:00"), ("session-new", "2026-09-05T11:00:00+00:00")):
                store.upsert({
                    "session_id": session_id, "patient_id": "RH-9344", "patient_name": "Kate",
                    "scan_datetime": timestamp,
                    "left_eye": {"available": True, "completed": True},
                    "right_eye": {"available": False, "completed": False},
                })
            reopened = HistoryStore(path)
            self.assertEqual([item["session_id"] for item in reopened.list()], ["session-new", "session-old"])


if __name__ == "__main__":
    unittest.main()
