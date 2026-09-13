"""Real PostgreSQL integration. Use a disposable DB via RETINA_TEST_DATABASE_URL."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select, func, text, delete
from db.models import Base, Patient, ScreeningSession, EyeResult, Report, SyncState, LegacyImport
from db.repository import HistoryRepository, identifier
from db.session import make_engine
from schemas.storage import ClearInput
from services.storage_service import StorageService
from services.sync_service import SyncService, object_key

URL = os.environ.get('RETINA_TEST_DATABASE_URL')


@unittest.skipUnless(URL, 'Set RETINA_TEST_DATABASE_URL to a disposable PostgreSQL database.')
class PostgreSQLStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'work')
        self.root = Path(self.temp.name)
        self.schema = 'test_' + uuid4().hex
        self.admin = make_engine(URL)
        with self.admin.begin() as db:
            db.execute(text(f'CREATE SCHEMA {self.schema}'))
        self.engine = make_engine(URL).execution_options(schema_translate_map={None: self.schema})
        Base.metadata.create_all(self.engine)  # Isolated tests only. Production uses Alembic.
        self.repo = HistoryRepository(self.engine, self.root, self.root / 'history.json')
        self.input = dict(id=str(uuid4()), patientIdNumber='RH-TEST', name='Test Patient', age=54,
            gender='Female', phone='+91 (98765) 43210', email='test@example.com', sessionId=str(uuid4()))

    def tearDown(self):
        # Preserve schema/tables/indexes; clean test rows only.
        with self.engine.begin() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(delete(table))
        self.engine.dispose()
        self.admin.dispose()
        self.temp.cleanup()

    def result(self, eye):
        run_id = uuid4().hex
        return dict(run_id=run_id, state='COMPLETE', eye=eye, image_url=f'/artifacts/{run_id}/input.png',
            grading={'predicted_grade': 2, 'confidence': 0.9}, quality={'quality': 'Good'}, lesions={'lesions': {}})

    def test_patient_session_bilateral_report_restart_and_counts(self):
        with patch.dict(os.environ, {'RETINA_CLOUD_SYNC_ENABLED': 'true'}):
            patient = self.repo.register_patient(self.input)
            self.repo.save_analysis(patient['sessionId'], 'OS', self.result('OS'))
            self.repo.save_analysis(patient['sessionId'], 'OD', self.result('OD'))
            report = self.root / 'reports' / 'report.pdf'
            report.parent.mkdir(); report.write_bytes(b'%PDF-test')
            self.repo.update_report_path(patient['sessionId'], 'OS', str(report))
        reopened = HistoryRepository(self.engine, self.root, self.repo.path)
        self.assertEqual(reopened.patient(patient['id'])['phone'], '+919876543210')
        self.assertEqual(reopened.patient(patient['id'])['email'], 'test@example.com')
        history = reopened.list()
        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]['left_eye']['completed'] and history[0]['right_eye']['completed'])
        self.assertEqual(history[0]['left_eye']['report_path'], str(report))
        overview = SyncService(reopened).overview(StorageService(reopened).counts())
        self.assertEqual((overview['counts']['patients'], overview['counts']['sessions'], overview['counts']['reports']), (1, 1, 1))
        self.assertEqual(overview['pending_items'], 5)
        self.assertEqual(overview['counts']['file_bytes'], len(b'%PDF-test'))
        with reopened.sessions() as db:
            rows = list(db.scalars(select(EyeResult)))
            self.assertEqual({e.session_id for e in rows}, {identifier(patient['sessionId'], 'session')})
            self.assertEqual(db.scalar(select(Report)).checksum_sha256.__len__(), 64)
            self.assertTrue(all(e.original_image_path.startswith('runs/') for e in rows))

    def test_no_cloud_is_truthful_and_settings_persist(self):
        self.repo.register_patient(self.input)
        service = SyncService(self.repo)
        with patch.dict(os.environ, {'CLOUD_DATABASE_URL': ''}):
            self.assertFalse(service.connect()['configured'])
            self.assertEqual(service.sync_now()['status'], 'Not connected')
            settings = service.settings(); settings['retinal_images'] = True
            service.save_settings(settings)
            self.assertTrue(SyncService(self.repo).settings()['retinal_images'])
            with self.assertRaises(ValueError):
                service.save_settings({**settings, 'automatic': True})
        key = object_key(uuid4(), uuid4(), 'OS', 'original.png')
        self.assertNotIn('C:', key)
        with self.assertRaises(ValueError):
            object_key(uuid4(), uuid4(), 'OS', '../secret')

    def test_migration_preserves_ids_reports_json_and_does_not_repeat(self):
        session_id = str(uuid4())
        result = self.result('OS')
        legacy = dict(session_id=session_id, patient_id='RH-OLD', patient_name='Legacy Patient',
            patient={'id': 'legacy-patient', 'age': 40, 'gender': 'Male'}, scan_datetime='2020-01-01T10:00:00Z',
            updated_at='2020-01-01T11:00:00Z', left_eye={'available': True, 'completed': True,
                'result_data': result, 'original_path': result['image_url'], 'report_path': 'reports/old.pdf'}, right_eye={})
        self.repo.path.write_text(json.dumps([legacy]), encoding='utf-8')
        self.repo.migrate_json(); self.repo.migrate_json()
        self.assertTrue(self.repo.path.exists())
        self.assertTrue(self.repo.path.with_name('history.json.pre-postgres.bak').exists())
        history = self.repo.list()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['session_id'], session_id)
        self.assertEqual(history[0]['left_eye']['result_data'], result)
        self.assertEqual(datetime.fromisoformat(history[0]['scan_datetime']), datetime.fromisoformat('2020-01-01T10:00:00+00:00'))
        self.assertEqual(history[0]['patient']['email'], None)
        with self.repo.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(LegacyImport)), 1)
        StorageService(self.repo).clear(ClearInput(categories=['history'], acknowledged=True, confirmation='DELETE'))
        self.repo.migrate_json()
        self.assertEqual(self.repo.list(), [], 'Retained JSON must not resurrect cleared history.')

    def test_failed_migration_rolls_back_all_rows_and_retains_json(self):
        self.repo.path.write_text(json.dumps([{'session_id': 'broken'}]), encoding='utf-8')
        with self.assertRaises(KeyError):
            self.repo.migrate_json()
        with self.repo.sessions() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Patient)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(LegacyImport)), 0)
        self.assertTrue(self.repo.path.exists())

    def test_clear_temporary_preserves_history_and_deletion_requires_confirmation(self):
        self.repo.register_patient(self.input)
        temp = self.root / 'tmp' / 'temporary.txt'; temp.parent.mkdir(); temp.write_text('test')
        service = StorageService(self.repo)
        with self.assertRaises(ValueError):
            service.clear(ClearInput(categories=['temporary']))
        service.clear(ClearInput(categories=['temporary'], acknowledged=True))
        self.assertFalse(temp.exists())
        self.assertEqual(len(self.repo.patients()), 1)
        with self.assertRaises(ValueError):
            service.clear(ClearInput(categories=['history'], acknowledged=True))
        service.clear(ClearInput(categories=['history'], acknowledged=True, confirmation='DELETE'))
        self.assertEqual(self.repo.patients(), [])

    def test_failed_delete_rolls_back_database_and_restores_files(self):
        patient = self.repo.register_patient(self.input)
        artifact = self.root / 'runs' / 'test' / 'overlay.png'
        artifact.parent.mkdir(parents=True); artifact.write_bytes(b'test')
        from sqlalchemy.orm import Session
        original_execute = Session.execute
        def fail_patient_delete(session, statement, *args, **kwargs):
            if getattr(statement, 'is_delete', False) and statement.table.name == 'patients':
                session.execute(text('SELECT 1 / 0'))  # Actual PostgreSQL transaction failure.
            return original_execute(session, statement, *args, **kwargs)
        with patch.object(Session, 'execute', fail_patient_delete), self.assertRaises(Exception):
            StorageService(self.repo).clear(ClearInput(categories=['artifacts', 'history'], acknowledged=True, confirmation='DELETE'))
        self.assertEqual(artifact.read_bytes(), b'test')
        self.assertEqual(self.repo.patient(patient['id'])['email'], 'test@example.com')

    def test_history_only_keeps_files_tables_and_next_registration_works(self):
        patient = self.repo.register_patient(self.input)
        self.repo.save_analysis(patient['sessionId'], 'OS', self.result('OS'))
        source = self.root / 'runs' / 'test' / 'input.png'
        source.parent.mkdir(parents=True); source.write_bytes(b'image')
        tables_before = set(Base.metadata.tables)
        StorageService(self.repo).clear(ClearInput(categories=['history'], acknowledged=True, confirmation='DELETE'))
        self.assertTrue(source.exists())
        with self.repo.sessions() as db:
            for model in (Patient, ScreeningSession, EyeResult, Report, SyncState):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 0)
        self.assertEqual(set(Base.metadata.tables), tables_before)
        self.assertEqual(self.repo.list(), [])
        self.assertEqual(self.repo.register_patient(self.input)['email'], 'test@example.com')


if __name__ == '__main__':
    unittest.main()
