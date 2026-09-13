"""Transactional repository with the existing flat frontend history contract."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
import json
import os
import shutil
import base64

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from db.models import Patient, ScreeningSession, EyeResult, Report, SyncState, AppSetting, LegacyImport, now
from db.session import session_factory
from schemas.storage import PatientInput

CLINICAL_KEYS = ('dob', 'diabeticHistoryYears', 'hba1c', 'bloodPressure')
GRADE_LABELS = ('No diabetic retinopathy', 'Mild NPDR', 'Moderate NPDR', 'Severe NPDR', 'Proliferative DR')


def identifier(value, kind):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return uuid5(NAMESPACE_URL, f'retinagram/{kind}/{value}') if value else uuid4()


def timestamp(value, fallback=None):
    if isinstance(value, datetime):
        return value
    try:
        # Legacy intake sometimes wrote a fixed EST suffix.
        parsed = datetime.fromisoformat(str(value).replace(' EST', '-05:00').replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return fallback or now()


def mark_pending(db, entity_type, entity_id):
    enabled = os.environ.get('RETINA_CLOUD_SYNC_ENABLED', 'false').lower() == 'true'
    values = dict(entity_type=entity_type, entity_id=entity_id,
                  sync_status='PENDING' if enabled else 'LOCAL_ONLY', updated_at=now())
    db.execute(insert(SyncState).values(**values).on_conflict_do_update(
        index_elements=['entity_type', 'entity_id'], set_={'sync_status': values['sync_status'], 'updated_at': values['updated_at']}))


class HistoryRepository:
    def __init__(self, engine, runtime_root, history_path):
        self.engine = engine
        self.sessions = session_factory(engine)
        self.runtime_root = Path(runtime_root).resolve()
        self.path = Path(history_path).resolve()  # Legacy source only, never the active store.

    def local_path(self, value):
        if not value or str(value).startswith(('data:', 'blob:')):
            return None
        value = str(value)
        if value.startswith('/artifacts/'):
            return 'runs/' + value[len('/artifacts/'):]
        path = Path(value)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(self.runtime_root).as_posix()
            except ValueError:
                return str(path)  # Existing user-selected export, not a cloud object key.
        return value

    def browser_path(self, value):
        return '/artifacts/' + value[5:] if value and value.startswith('runs/') else value

    def patient_dict(self, row, session_id=None):
        return dict(id=str(row.id), name=row.name, patientIdNumber=row.patient_code, age=row.age,
                    gender=row.gender, phone=row.phone or '', email=row.email or '', **row.clinical_metadata,
                    sessionId=str(session_id) if session_id else None, studyDate=now().isoformat(), activeEye='OS',
                    leftEye={'eye': 'OS', 'eyeLabel': 'Left Eye (OS)'}, rightEye={'eye': 'OD', 'eyeLabel': 'Right Eye (OD)'},
                    clinicalNotes='', isConfirmed=False, isFlagged=False)

    def patients(self):
        with self.sessions() as db:
            return [self.patient_dict(row) for row in db.scalars(select(Patient).order_by(Patient.created_at.desc()))]

    def patient(self, patient_id):
        with self.sessions() as db:
            row = db.get(Patient, identifier(patient_id, 'patient'))
            if not row:
                raise ValueError('Patient not found.')
            return self.patient_dict(row)

    def _patient(self, db, data, *, registering=False, legacy=False):
        row = db.scalar(select(Patient).where(Patient.patient_code == data['patientIdNumber']))
        if row:
            if registering:
                raise ValueError('This patient ID is already registered. Select that patient or use a different ID.')
            if not legacy and identifier(data.get('id'), 'patient') != row.id:
                raise ValueError('Patient identity does not match the registered patient.')
            if legacy:
                # Registration metadata wins; fill contacts absent from older entries.
                for field in ('phone', 'email'):
                    if not getattr(row, field) and data.get(field):
                        value = PatientInput.model_validate({**data, 'age': data.get('age') or 0, 'gender': data.get('gender') or 'Other'})
                        setattr(row, field, getattr(value, field))
                        mark_pending(db, 'patient', row.id)
            return row  # Database demographics are the source of truth, not stale history snapshots.
        valid = PatientInput.model_validate(data)
        row = Patient(id=identifier(valid.id, 'patient'), legacy_id=valid.id if legacy else None,
                      patient_code=valid.patientIdNumber, name=valid.name, age=valid.age, gender=valid.gender,
                      phone=valid.phone, email=valid.email,
                      clinical_metadata={key: data.get(key) for key in CLINICAL_KEYS})
        db.add(row); db.flush(); mark_pending(db, 'patient', row.id)
        return row

    def register_patient(self, data):
        with self.sessions.begin() as db:
            row = self._patient(db, data, registering=True)
            session_id = identifier(data.get('sessionId'), 'session')
            self._session(db, row, session_id, data.get('sessionStartedAt'), data.get('clinicalNotes', ''))
            return self.patient_dict(row, session_id)

    def _session(self, db, patient, session_id, started_at=None, notes='', legacy=False):
        key = identifier(session_id, 'session')
        row = db.get(ScreeningSession, key)
        if row and row.patient_id != patient.id:
            raise ValueError('The session belongs to a different patient.')
        if not row:
            row = ScreeningSession(id=key, legacy_id=str(session_id) if legacy else None,
                                   patient_id=patient.id, started_at=timestamp(started_at), notes=notes or '', status='WAITING')
            db.add(row); db.flush(); mark_pending(db, 'session', row.id)
        return row

    def start_session(self, data):
        with self.sessions.begin() as db:
            patient = db.get(Patient, identifier(data['id'], 'patient'))
            if not patient:
                raise ValueError('Register the patient before starting a session.')
            row = self._session(db, patient, data.get('sessionId'), data.get('sessionStartedAt'), data.get('clinicalNotes', ''))
            return {'session_id': str(row.id)}

    def save_analysis(self, session_id, eye, result):
        with self.sessions.begin() as db:
            session = db.get(ScreeningSession, identifier(session_id, 'session'))
            if not session:
                raise ValueError('Screening session not found.')
            patient = db.get(Patient, session.patient_id)
            record = dict(session_id=str(session.id), patient_id=patient.patient_code, patient_name=patient.name,
                          patient=self.patient_dict(patient), scan_datetime=session.started_at.isoformat())
            record['left_eye' if eye == 'OS' else 'right_eye'] = dict(available=True,
                result_data=result, captured_at=now().isoformat(), original_path=result.get('image_url'),
                restored_path=result.get('restored_image_url'), overlay_path=(result.get('lesions') or {}).get('combined_overlay_path'))
            self._upsert(db, record)

    def report_patient(self, session_id, eye, run_id):
        with self.sessions() as db:
            session = db.get(ScreeningSession, identifier(session_id, 'session'))
            row = db.scalar(select(EyeResult).where(EyeResult.session_id == identifier(session_id, 'session'), EyeResult.eye == eye, EyeResult.run_id == run_id))
            if not session or not row:
                raise ValueError('The report does not match this saved screening session and eye.')
            patient = db.get(Patient, session.patient_id)
            return dict(name=patient.name, id=patient.patient_code, age=patient.age, gender=patient.gender,
                        eye=eye, scan_datetime=row.scan_datetime.isoformat() if row.scan_datetime else None)

    def _upsert(self, db, record, legacy=False):
        details = record.get('patient') or {}
        patient = self._patient(db, {**details, 'id': details.get('id') or record['patient_id'],
            'name': record['patient_name'], 'patientIdNumber': record['patient_id'],
            'age': details.get('age') or 0, 'gender': details.get('gender') or 'Other'}, legacy=legacy)
        session = self._session(db, patient, record['session_id'], record.get('scan_datetime'), record.get('notes', ''), legacy=legacy)
        for eye, key in [('OS', 'left_eye'), ('OD', 'right_eye')]:
            data = record.get(key) or {}
            if not any(data.get(field) for field in ('available', 'result_data', 'report_path')):
                continue
            row = db.scalar(select(EyeResult).where(EyeResult.session_id == session.id, EyeResult.eye == eye))
            if not row:
                row = EyeResult(session_id=session.id, eye=eye)
                db.add(row)
            result = data.get('result_data') or {}
            # Do not let a stale or partial client overwrite a completed result.
            if row.result_json and not result:
                continue
            row.run_id = result.get('run_id')
            row.scan_datetime = timestamp(data.get('captured_at'), session.started_at)
            row.status = result.get('state') or data.get('state') or 'WAITING'
            row.result_json = deepcopy(result) or None
            row.image_quality = (result.get('quality') or {}).get('quality')
            grade = result.get('grading') or {}
            row.dr_grade = grade.get('predicted_grade')
            row.grade_label = GRADE_LABELS[row.dr_grade] if row.dr_grade in range(5) else None
            row.confidence = grade.get('confidence')
            original = data.get('original_path') or result.get('image_url')
            if isinstance(original, str) and original.startswith('data:image/'):
                # Legacy/unsaved captures belong on disk, never inside JSONB.
                from utils.image_processing import decode_upload, MAX_BYTES
                header, encoded = original.split(',', 1)
                if ';base64' not in header or len(encoded) > MAX_BYTES * 4 // 3 + 4:
                    raise ValueError('Invalid or oversized captured image.')
                image = decode_upload(base64.b64decode(encoded, validate=True))
                capture_dir = self.runtime_root / 'runs' / (row.run_id or uuid4().hex)
                capture_dir.mkdir(parents=True, exist_ok=True)
                image.save(capture_dir / 'input.png')
                original = str(capture_dir / 'input.png')
            row.original_image_path = self.local_path(original)
            row.restored_image_path = self.local_path(data.get('restored_path'))
            row.lesion_overlay_path = self.local_path(data.get('overlay_path'))
            row.gradcam_path = self.local_path((grade.get('gradcam') or {}).get('heatmap_path'))
            db.flush(); mark_pending(db, 'eye_result', row.id)
            if data.get('report_path'):
                self._report(db, session, row, data['report_path'], record.get('updated_at'))
        db.flush()
        eyes = list(db.scalars(select(EyeResult).where(EyeResult.session_id == session.id)))
        completed = sum(eye.status == 'COMPLETE' for eye in eyes)
        session.status = 'COMPLETE' if completed == 2 else 'PARTIAL' if completed else 'WAITING'
        session.completed_at = max((eye.scan_datetime for eye in eyes), default=None) if completed else None
        if legacy:
            session.created_at = session.started_at
            session.updated_at = timestamp(record.get('updated_at'), session.started_at)
        mark_pending(db, 'session', session.id)
        return session.id

    def upsert(self, record):
        if not record.get('session_id'):
            raise ValueError('A scan session identifier is required.')
        with self.sessions.begin() as db:
            session_id = self._upsert(db, record)
        return next(item for item in self.list() if item['session_id'] == str(session_id))

    def _report(self, db, session, eye, path, generated_at=None):
        stored = self.local_path(path)
        row = db.scalar(select(Report).where(Report.session_id == session.id, Report.report_path == stored))
        if not row:
            actual = Path(stored) if Path(stored).is_absolute() else self.runtime_root / stored
            row = Report(session_id=session.id, eye_result_id=eye.id, report_path=stored,
                         generated_at=timestamp(generated_at), checksum_sha256=sha256(actual.read_bytes()).hexdigest() if actual.is_file() else None)
            db.add(row); db.flush(); mark_pending(db, 'report', row.id)

    def update_report_path(self, session_id, eye, report_path):
        with self.sessions.begin() as db:
            session = db.get(ScreeningSession, identifier(session_id, 'session'))
            result = db.scalar(select(EyeResult).where(EyeResult.session_id == identifier(session_id, 'session'), EyeResult.eye == eye))
            if not session or not result:
                raise ValueError('Save this screening session before exporting its report.')
            self._report(db, session, result, report_path)

    def list(self):
        with self.sessions() as db:
            patients = {p.id: p for p in db.scalars(select(Patient))}
            eyes = {}
            for row in db.scalars(select(EyeResult)):
                eyes.setdefault(row.session_id, []).append(row)
            reports = {}
            for row in db.scalars(select(Report).order_by(Report.generated_at)):
                reports[row.eye_result_id] = row
            records = []
            for session in db.scalars(select(ScreeningSession).order_by(ScreeningSession.started_at.desc())):
                if session.id not in eyes:
                    continue  # Fresh registrations do not clutter scan history.
                p = patients[session.patient_id]
                metadata = {key: getattr(p, key) for key in ('age', 'gender', 'phone', 'email')}
                record = dict(session_id=str(session.id), patient_id=p.patient_code, patient_name=p.name,
                    patient={'id': str(p.id), **metadata, **p.clinical_metadata}, scan_datetime=session.started_at.isoformat(),
                    updated_at=session.updated_at.isoformat(), notes=session.notes)
                for side, key in [('OS', 'left_eye'), ('OD', 'right_eye')]:
                    row = next((e for e in eyes[session.id] if e.eye == side), None)
                    report = reports.get(row.id) if row else None
                    report_path = report.report_path if report else None
                    if report_path and not Path(report_path).is_absolute():
                        report_path = str(self.runtime_root / report_path)
                    record[key] = dict(available=bool(row and row.original_image_path), completed=bool(row and row.status == 'COMPLETE'),
                        state=row.status if row else 'WAITING', result_data=row.result_json if row else None,
                        original_path=self.browser_path(row.original_image_path) if row else None,
                        restored_path=self.browser_path(row.restored_image_path) if row else None,
                        overlay_path=self.browser_path(row.lesion_overlay_path) if row else None,
                        report_path=report_path, captured_at=row.scan_datetime.isoformat() if row and row.scan_datetime else None)
                records.append(record)
            return records

    def migrate_json(self):
        sources = [self.path.with_name(self.path.stem + '-patients.json'), self.path]
        with self.sessions.begin() as db:
            # A DB advisory lock makes two simultaneous startup migrations safe.
            db.execute(select(func.pg_advisory_xact_lock(72419831)))
            for source in sources:
                if not source.is_file() or db.get(LegacyImport, str(source)):
                    continue
                raw = source.read_bytes()
                rows = json.loads(raw)
                if not isinstance(rows, list):
                    raise ValueError('Legacy history is not a list. Original JSON was retained.')
                backup = source.with_name(source.name + '.pre-postgres.bak')
                if not backup.exists():
                    shutil.copy2(source, backup)
                if source == self.path:
                    for record in sorted(rows, key=lambda item: item.get('scan_datetime') or ''):
                        self._upsert(db, record, legacy=True)
                else:
                    for record in rows:
                        self._patient(db, record, legacy=True)
                db.add(LegacyImport(source=str(source), checksum_sha256=sha256(raw).hexdigest()))
            # Marker and imported rows commit together; originals and backups remain untouched.
