from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.history import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def test_registration_survives_restart_without_a_scan(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'history.json'
            patient = {'id': 'test', 'patientIdNumber': 'RH-TEST', 'name': 'Test Patient',
                       'phone': '+91 (98765) 43210', 'email': ' test@example.com ',
                       'leftEye': {}, 'rightEye': {}}
            HistoryStore(path).register_patient(patient)
            reopened = HistoryStore(path)
            self.assertEqual(reopened.patients()[0]['phone'], '+919876543210')
            self.assertEqual(reopened.patients()[0]['email'], 'test@example.com')
            self.assertEqual(reopened.list(), [])
            with self.assertRaisesRegex(ValueError, 'already registered'):
                reopened.register_patient(patient)

    def test_contacts_optional_invalid_and_old_history(self):
        with TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / 'history.json')
            patient = {'id': 'legacy', 'patientIdNumber': 'RH-OLD', 'name': 'Old Patient', 'leftEye': {}, 'rightEye': {}}
            saved = store.register_patient(patient)
            self.assertEqual((saved['email'], saved['phone']), ('', ''))
            for key, value in [('phone', '123'), ('email', 'not an email')]:
                with self.assertRaises(ValueError):
                    store.register_patient({**patient, 'id': 'bad', 'patientIdNumber': 'BAD', key: value})
            old = {'session_id': 'old', 'patient': {'id': 'legacy'}, 'left_eye': {'available': True}}
            store.upsert(old)
            self.assertNotIn('email', store.list()[0]['patient'])
            old['patient'].update(phone='+919876543210', email='test@example.com')
            store.upsert(old)
            self.assertEqual(store.list()[0]['patient']['email'], 'test@example.com')

    def test_corrupt_registry_is_not_overwritten(self):
        with TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory) / 'history.json')
            store.patients_path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(ValueError):
                store.patients()
            self.assertEqual(store.patients_path.read_text(encoding='utf-8'), '{broken')

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
