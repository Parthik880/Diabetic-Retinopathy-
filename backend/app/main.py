from contextlib import asynccontextmanager
import json
import logging
import os
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

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
from app.history import HistoryStore

RUNTIME_ROOT = Path(os.environ.get('RETINA_RUNTIME_ROOT', ROOT / 'work')).expanduser().resolve()
RUNS = RUNTIME_ROOT / 'runs'
RUNS.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app):
    app.state.registry = ModelRegistry()
    app.state.jobs = AnalysisJobManager(max_workers=1)
    app.state.history = HistoryStore(RUNTIME_ROOT / 'history' / 'index.json')
    try:
        yield
    finally:
        app.state.jobs.shutdown()


app = FastAPI(title='Retina desktop inference', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.mount('/artifacts', StaticFiles(directory=RUNS), name='artifacts')


@app.get('/health')
def health():
    return {**app.state.registry.health(), 'instance': os.environ.get('RETINA_INSTANCE')}


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
    return await run_in_threadpool(analyze_image, image, eye)


@app.post('/api/analysis-jobs', status_code=202)
async def create_analysis_job(file: UploadFile = File(...), eye: Literal['OS', 'OD'] | None = Form(None)):
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

    run_id = uuid4().hex
    destination = RUNS / run_id
    destination.mkdir()
    path = destination / 'input.png'
    image.save(path)
    jobs = app.state.jobs
    jobs.create(run_id, eye)
    jobs.submit(
        run_id,
        lambda: run_analysis_pipeline(
            original_path=path,
            registry=app.state.registry,
            run_id=run_id,
            runs_root=RUNS,
            eye=eye,
            on_state=lambda state: jobs.transition(run_id, state),
        ),
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
    return await run_in_threadpool(restore_image, image)


def create_report_bundle(payload):
    run_id = str(payload.get('run_id') or '')
    if not re.fullmatch(r'[0-9a-f]{32}', run_id):
        raise HTTPException(400, 'A valid completed inference run is required.')
    destination = Path(str(payload.get('destination') or '')).expanduser()
    run_dir = RUNS / run_id
    try:
        exported = export_report_bundle(
            destination,
            run_dir=run_dir,
            patient=payload.get('patient') or {},
            logo_path=ROOT / 'frontend' / 'public' / 'logo.png.jpeg',
        )
        session_id = str(payload.get('session_id') or '')
        eye = str((payload.get('patient') or {}).get('eye') or '')
        if session_id and eye in {'OS', 'OD'}:
            app.state.history.update_report_path(session_id, eye, exported['report'])
        return exported
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        logging.exception('Report export failed for %s', run_id)
        raise HTTPException(500, f'Report export failed (run {run_id}). Check backend logs.') from exc


@app.post('/api/reports/export')
async def export_report(payload: dict):
    return await run_in_threadpool(create_report_bundle, payload)


def create_bilateral_report_bundle(payload):
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
                patient={**patient, 'eye': eye, 'scan_datetime': item.get('scan_datetime')},
                logo_path=ROOT / 'frontend' / 'public' / 'logo.png.jpeg',
                report_root=report_root,
            ))
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
    return await run_in_threadpool(create_bilateral_report_bundle, payload)


@app.get('/api/history')
def history_records():
    return {'records': app.state.history.list(), 'storage_path': str(app.state.history.path)}


@app.post('/api/history/sessions')
def save_history_session(payload: dict):
    try:
        return {'record': app.state.history.upsert(payload)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


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
