from contextlib import asynccontextmanager
import json
import logging
import os
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from threading import RLock
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from typing import Literal
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from utils.model_loader import ModelRegistry, ROOT
from utils.image_processing import decode_upload, MAX_BYTES
from inference import restoration
from inference.pipeline import PipelineState, run_analysis_pipeline
from utils.reporting import create_report_root, export_report_bundle
from app.jobs import AnalysisJobManager
from db.session import make_engine, verify_local_storage
from db.repository import HistoryRepository
from services.sync_service import SyncService
from services.storage_service import StorageService
from schemas.storage import PatientInput, SyncSettingsInput, ClearInput

RUNTIME_ROOT = Path(os.environ.get('RETINA_RUNTIME_ROOT', Path(os.environ.get('APPDATA', Path.home() / '.local' / 'share')) / 'RetinaGram CPU' / 'runtime')).expanduser().resolve()
RUNS = RUNTIME_ROOT / 'runs'
RUNS.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app):
    app.state.registry = ModelRegistry()
    app.state.jobs = AnalysisJobManager(max_workers=1)
    app.state.storage_lock = RLock()
    app.state.history = None
    try:
        database()
    except HTTPException:
        logging.warning('Local patient database unavailable at startup; no JSON fallback is used.')
    try:
        yield
    finally:
        app.state.jobs.shutdown()
        if app.state.history:
            app.state.history.engine.dispose()


app = FastAPI(title='Retina desktop inference', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.mount('/artifacts', StaticFiles(directory=RUNS), name='artifacts')


def database():
    if app.state.history is None:
        engine = None
        try:
            engine = make_engine()
            with engine.connect() as connection:
                app.state.postgres_data_directory = verify_local_storage(connection)
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
                if revision != '0001_local_storage':
                    raise RuntimeError('Run Alembic upgrade head.')
            history_path = Path(os.environ.get('RETINA_HISTORY_PATH', RUNTIME_ROOT / 'history' / 'index.json'))
            repository = HistoryRepository(engine, RUNTIME_ROOT, history_path)
            repository.migrate_json()
            app.state.history = repository
            app.state.sync = SyncService(repository)
            app.state.storage = StorageService(repository)
        except Exception as exc:
            if engine is not None:
                engine.dispose()
            logging.warning('Local database initialization failed (%s).', type(exc).__name__)
            raise HTTPException(503, 'Local patient database unavailable. Check backend/.env, PostgreSQL, and Alembic migrations. Legacy JSON was retained.') from None
    return app.state.history


@app.exception_handler(SQLAlchemyError)
async def database_error(_request, error):
    logging.warning('Local database operation failed (%s).', type(error).__name__)
    message = 'This record already exists or conflicts with a saved record.' if isinstance(error, IntegrityError) else 'Local patient database unavailable.'
    return JSONResponse(status_code=409 if isinstance(error, IntegrityError) else 503, content={'detail': message})


@app.exception_handler(RequestValidationError)
async def validation_error(_request, error):
    # Pydantic's default response echoes input values (including contact details).
    return JSONResponse(status_code=422, content={'detail': '; '.join(str(item['msg']) for item in error.errors())})


@app.get('/health')
def health():
    return {**app.state.registry.health(), 'instance': os.environ.get('RETINA_INSTANCE'),
            'local_database': 'available' if app.state.history else 'unavailable'}


def analyze_image(image, eye=None):
    registry = app.state.registry
    run_id = uuid4().hex
    destination = RUNS / run_id
    destination.mkdir()
    path = destination / 'input.png'
    image.save(path)
    try:
        return run_analysis_pipeline(
            original_path=path,
            registry=registry,
            run_id=run_id,
            runs_root=RUNS,
            eye=eye,
        )
    except Exception as exc:
        raise HTTPException(
            500,
            {'state': PipelineState.FAILED.value,
             'run_id': run_id,
             'message': f'Inference failed (run {run_id}): {exc}'},
        ) from exc


@app.post('/api/analyze')
async def analyze(file: UploadFile = File(...), eye: Literal['OS', 'OD'] | None = Form(None)):
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'Image exceeds the 20 MB upload limit.')
    try:
        image = decode_upload(data)
    except TypeError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    def analyze_locked():
        with app.state.storage_lock:
            return analyze_image(image, eye)
    return await run_in_threadpool(analyze_locked)


@app.post('/api/analysis-jobs', status_code=202)
async def create_analysis_job(file: UploadFile = File(...), eye: Literal['OS', 'OD'] | None = Form(None), session_id: str | None = Form(None)):
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'Image exceeds the 20 MB upload limit.')
    try:
        image = decode_upload(data)
    except TypeError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    jobs = app.state.jobs
    if session_id:
        database()
    with app.state.storage_lock:
        run_id = uuid4().hex
        destination = RUNS / run_id
        destination.mkdir()
        path = destination / 'input.png'
        image.save(path)
        jobs.create(run_id, eye)
    def analyze_and_save():
        result = run_analysis_pipeline(
            original_path=path, registry=app.state.registry, run_id=run_id,
            runs_root=RUNS, eye=eye, on_state=lambda state: jobs.transition(run_id, state))
        if session_id and eye:
            database().save_analysis(session_id, eye, result)
        return result
    jobs.submit(
        run_id,
        analyze_and_save,
    )
    return {'job_id': run_id, 'state': PipelineState.WAITING.value}


@app.get('/api/analysis-jobs/{job_id}')
def get_analysis_job(job_id: str):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise HTTPException(404, 'Analysis job not found.')
    job = app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, 'Analysis job not found.')
    return job


def restore_image(image):
    registry = app.state.registry
    if 'restoration' not in registry.models:
        raise HTTPException(503, 'Restoration model is unavailable.')
    # Full-resolution NAFNet is memory intensive on CPU; do not silently resize.
    if image.width * image.height > 1_000_000:
        raise HTTPException(413, 'Optional full-resolution restoration currently supports up to 1 megapixel.')
    with registry.lock:
        run_id = uuid4().hex
        destination = RUNS / run_id
        destination.mkdir()
        source = destination / 'input.png'
        image.save(source)
        try:
            output = restoration.restore(source, registry.models['restoration'], destination)
            return {'run_id': run_id, 'output_path': '/artifacts/' + Path(output['output_path']).relative_to(RUNS).as_posix(),
                    'quality': None, 'width': image.width, 'height': image.height,
                    'warnings': ['Restoration-only endpoint: IQA is not run or re-run. Generic SIDD denoising weights are not retinal fine-tuned.']}
        except Exception as exc:
            logging.exception('Restoration failed for %s', run_id)
            raise HTTPException(500, f'Restoration failed (run {run_id}). Check backend logs.') from exc


@app.post('/api/restore')
async def restore(file: UploadFile = File(...)):
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, 'Image exceeds the 20 MB upload limit.')
    try:
        image = decode_upload(data)
    except TypeError as exc:
        raise HTTPException(415, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    def restore_locked():
        with app.state.storage_lock:
            return restore_image(image)
    return await run_in_threadpool(restore_locked)


def create_report_bundle(payload):
    repository = database()
    run_id = str(payload.get('run_id') or '')
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise HTTPException(400, 'A valid completed inference run is required.')
    destination = Path(str(payload.get('destination') or '')).expanduser()
    run_dir = RUNS / run_id
    try:
        session_id = str(payload.get('session_id') or '')
        eye = str((payload.get('patient') or {}).get('eye') or '')
        patient = repository.report_patient(session_id, eye, run_id)
        exported = export_report_bundle(
            destination,
            run_dir=run_dir,
            patient=patient,
            logo_path=ROOT / 'frontend' / 'public' / 'logo.png.jpeg',
        )
        session_id = str(payload.get('session_id') or '')
        eye = str((payload.get('patient') or {}).get('eye') or '')
        if session_id and eye in {'OS', 'OD'}:
            repository.update_report_path(session_id, eye, exported['report'])
        return exported
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logging.exception('Report export failed for %s', run_id)
        raise HTTPException(500, f'Report export failed (run {run_id}). Check backend logs.') from exc


@app.post('/api/reports/export')
async def export_report(payload: dict):
    def export_locked():
        with app.state.storage_lock:
            return create_report_bundle(payload)
    return await run_in_threadpool(export_locked)


def create_bilateral_report_bundle(payload):
    repository = database()
    destination = Path(str(payload.get('destination') or '')).expanduser()
    patient = payload.get('patient') or {}
    reports = payload.get('reports') or []
    if not isinstance(reports, list) or not reports:
        raise HTTPException(400, 'At least one completed eye report is required.')
    try:
        report_root = create_report_root(destination, str(patient.get('name') or ''))
        exported = []
        for item in reports:
            run_id = str(item.get('run_id') or '')
            eye = str(item.get('eye') or '')
            if not re.fullmatch(r'[0-9a-f]{32}', run_id) or eye not in {'OS', 'OD'}:
                raise ValueError('Each report requires a valid run and eye.')
            exported.append(export_report_bundle(
                destination,
                run_dir=RUNS / run_id,
                patient=repository.report_patient(payload.get('session_id'), eye, run_id),
                logo_path=ROOT / 'frontend' / 'public' / 'logo.png.jpeg',
                report_root=report_root,
            ))
            repository.update_report_path(payload.get('session_id'), eye, exported[-1]['report'])
        return {
            'folder': str(report_root),
            'report': exported[0]['report'],
            'reports': [item['report'] for item in exported],
            'files': sorted(str(path.relative_to(report_root)).replace('\\', '/') for path in report_root.rglob('*') if path.is_file()),
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logging.exception('Bilateral report export failed')
        raise HTTPException(500, 'Report export failed. Check backend logs.') from exc


@app.post('/api/reports/export-both')
async def export_both_reports(payload: dict):
    def export_locked():
        with app.state.storage_lock:
            return create_bilateral_report_bundle(payload)
    return await run_in_threadpool(export_locked)


@app.get('/api/history')
def history_records():
    return {'records': database().list(), 'storage': 'PostgreSQL'}


@app.get('/api/patients')
def registered_patients():
    try:
        return {'patients': database().patients()}
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.post('/api/patients')
def register_patient(payload: PatientInput):
    try:
        with app.state.storage_lock:
            return {'patient': database().register_patient(payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post('/api/history/sessions')
def save_history_session(payload: dict):
    try:
        with app.state.storage_lock:
            return {'record': database().upsert(payload)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get('/api/patients/{patient_id}')
def patient_details(patient_id: str):
    try:
        return {'patient': database().patient(patient_id)}
    except ValueError:
        raise HTTPException(404, 'Patient not found.') from None


@app.post('/api/sessions')
def start_session(payload: PatientInput):
    try:
        with app.state.storage_lock:
            return database().start_session(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.get('/api/sync')
def sync_overview():
    database()
    return app.state.sync.overview(app.state.storage.counts())


@app.post('/api/sync/settings')
def sync_settings(payload: SyncSettingsInput):
    database()
    try:
        return app.state.sync.save_settings(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.post('/api/sync/connect')
def sync_connect():
    database()
    return app.state.sync.connect()


@app.post('/api/sync/now')
def sync_now():
    database()
    return app.state.sync.sync_now()


@app.post('/api/storage/preview')
def clear_preview(payload: ClearInput):
    database()
    return app.state.storage.preview(payload.categories)


@app.post('/api/storage/clear')
def clear_storage(payload: ClearInput):
    database()
    with app.state.storage_lock:
        if app.state.jobs.has_active_jobs():
            raise HTTPException(409, 'Wait for the active analysis to finish before clearing local data.')
        try:
            return app.state.storage.clear(payload)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except OSError:
            raise HTTPException(500, 'Local cleanup failed. Database changes were rolled back; check the data folder for recovery files.') from None


@app.post('/api/referral')
def referral(payload: dict):
    # Preserve the existing queue feature as an honest local draft. No remote
    # specialist connection is configured and no message is transmitted.
    identifier = uuid4().hex
    record = {**payload, 'id': identifier, 'submittedAt': datetime.now(timezone.utc).isoformat(),
              'status': 'Local draft', 'transmitted': False}
    directory = RUNTIME_ROOT / 'referrals'
    directory.mkdir(exist_ok=True)
    (directory / f'{identifier}.json').write_text(json.dumps(record, indent=2))
    return {'success': True, 'referral': record, 'transmitted': False}


@app.get('/api/referrals')
def referrals():
    directory = RUNTIME_ROOT / 'referrals'
    return {'referrals': [json.loads(path.read_text()) for path in directory.glob('*.json')]}


# The built React application and model artifacts share this loopback origin.
DIST = ROOT / 'frontend' / 'dist'
if DIST.is_dir():
    app.mount('/', StaticFiles(directory=DIST, html=True), name='frontend')
