from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.app.config import SESSION_ROOT, ensure_runtime_directories
from backend.app.model_registry import registry
from backend.app.schemas import (
    AnalyzeResponse,
    BlockVisualization,
    ExplorerArchitecture,
    FeatureStage,
    GradeGradCAMResponse,
    ModelStatus,
    PipelineStage,
)
from backend.app.services.analysis import pipeline_stages, run_analysis
from backend.app.services.image_store import read_manifest, save_upload
from backend.app.services.model_explorer import architecture, capture_block, capture_stages, grade_gradcam


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_runtime_directories()
    yield


app = FastAPI(
    title="RetinaGram AI Model Visualizer API",
    version="1.0.0",
    description="Local-only API over the repository's existing retinal models.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "device": str(registry.device)}


@app.get("/api/stages", response_model=list[PipelineStage])
def stages() -> list[dict]:
    return pipeline_stages()


@app.get("/api/models", response_model=list[ModelStatus])
def models() -> list[dict]:
    return registry.status()


@app.get("/api/explorer/{model_id}", response_model=ExplorerArchitecture)
def explorer_architecture(model_id: str) -> dict:
    if model_id not in {"quality", "restoration", "grade", "lesion"}:
        raise HTTPException(status_code=404, detail="Model explorer not found.")
    try:
        return architecture(model_id)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get(
    "/api/explorer/{model_id}/blocks/{block_id}",
    response_model=BlockVisualization,
)
async def explorer_block(
    model_id: str,
    block_id: str,
    session_id: str = Query(..., min_length=32, max_length=32),
    channel: int | None = Query(default=None, ge=0),
) -> dict:
    if model_id not in {"quality", "restoration", "grade", "lesion"}:
        raise HTTPException(status_code=404, detail="Model explorer not found.")
    try:
        return await run_in_threadpool(capture_block, session_id, model_id, block_id, channel)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get(
    "/api/explorer/{model_id}/visualizations",
    response_model=list[BlockVisualization],
)
async def explorer_visualizations(
    model_id: str,
    session_id: str = Query(..., min_length=32, max_length=32),
) -> list[dict]:
    if model_id not in {"quality", "restoration", "grade", "lesion"}:
        raise HTTPException(status_code=404, detail="Model explorer not found.")
    try:
        return await run_in_threadpool(capture_stages, session_id, model_id)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/explorer/grade/gradcam/{target_class}", response_model=GradeGradCAMResponse)
async def explorer_grade_gradcam(
    target_class: int,
    session_id: str = Query(..., min_length=32, max_length=32),
) -> dict:
    try:
        return await run_in_threadpool(grade_gradcam, session_id, target_class)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> dict:
    try:
        session_id, session_dir, image_path = await save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await run_in_threadpool(run_analysis, session_id, session_dir, image_path)


@app.get("/api/analysis/{session_id}", response_model=AnalyzeResponse)
def analysis_session(session_id: str) -> dict:
    if len(session_id) != 32 or any(char not in "0123456789abcdef" for char in session_id):
        raise HTTPException(status_code=404, detail="Analysis session not found.")
    try:
        return read_manifest(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/lesions/{session_id}/regions")
def lesion_regions(
    session_id: str,
    limit: int = Query(default=25, ge=1, le=25),
    lesion_class: str | None = Query(default=None),
) -> dict:
    try:
        manifest = read_manifest(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lesions = manifest.get("lesions")
    if not lesions:
        raise HTTPException(status_code=404, detail="Lesion segmentation result not found.")
    regions = lesions.get("regions", [])
    if lesion_class and lesion_class.upper() != "ALL":
        code = lesion_class.upper()
        if code not in lesions.get("channel_order", []):
            raise HTTPException(status_code=422, detail="Unknown lesion class filter.")
        regions = [region for region in regions if region["class_code"] == code]
    retained = regions[:limit]
    return {
        "regions": retained,
        "count": len(retained),
        "available_count": len(regions),
        "limit": limit,
        "confidence_method": lesions.get("confidence_method"),
    }


@app.get("/api/lesions/{session_id}/regions/{rank}/crop")
def lesion_region_crop(session_id: str, rank: int) -> FileResponse:
    try:
        manifest = read_manifest(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    region = next((item for item in manifest.get("lesions", {}).get("regions", []) if item.get("rank") == rank), None)
    if region is None:
        raise HTTPException(status_code=404, detail="Lesion region not found.")
    prefix = f"/media/{session_id}/"
    crop_url = region["crop_url"]
    root = (SESSION_ROOT / session_id).resolve()
    crop_path = (root / crop_url.removeprefix(prefix)).resolve()
    try:
        crop_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Lesion crop not found.") from exc
    return FileResponse(crop_path, filename=region["download_name"])


@app.get("/api/nafnet/features/{stage}", response_model=FeatureStage)
def nafnet_features(
    stage: str,
    session_id: str = Query(..., min_length=32, max_length=32),
) -> dict:
    try:
        manifest = read_manifest(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    feature = manifest.get("features", {}).get(stage)
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature stage not found.")
    return feature


@app.get("/media/{session_id}/{asset_path:path}")
def media(session_id: str, asset_path: str) -> FileResponse:
    if len(session_id) != 32 or any(char not in "0123456789abcdef" for char in session_id):
        raise HTTPException(status_code=404, detail="Media not found.")
    session_root = (SESSION_ROOT / session_id).resolve()
    candidate = (session_root / asset_path).resolve()
    try:
        candidate.relative_to(session_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media not found.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    return FileResponse(candidate)
