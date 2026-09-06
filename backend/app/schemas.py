from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


StageState = Literal["pending", "running", "complete", "error"]


class PipelineStage(BaseModel):
    id: str
    number: int
    label: str
    description: str
    state: StageState = "pending"
    error: str | None = None


class FeatureStage(BaseModel):
    id: str
    label: str
    layer: str
    tensor_shape: list[int]
    channels_total: int
    channels_shown: int
    images: list[str]
    explanation: str


class AnalyzeResponse(BaseModel):
    session_id: str
    device: str
    input_image_url: str
    stages: list[PipelineStage]
    quality: dict[str, Any] | None = None
    restoration: dict[str, Any] | None = None
    grade: dict[str, Any] | None = None
    lesions: dict[str, Any] | None = None
    features: dict[str, FeatureStage] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ModelStatus(BaseModel):
    id: str
    label: str
    architecture: str
    checkpoint: str
    checkpoint_present: bool


class ExplorerInternal(BaseModel):
    id: str
    label: str
    block_type: str


class ExplorerBlock(BaseModel):
    id: str
    label: str
    group: str
    block_type: str
    description: str
    internals: list[ExplorerInternal] = Field(default_factory=list)


class ExplorerArchitecture(BaseModel):
    id: str
    label: str
    model_name: str
    device: str
    input: str
    parameter_count: int
    block_count: int
    blocks: list[ExplorerBlock]


class BlockVisualization(BaseModel):
    id: str
    parent_id: str
    label: str
    block_type: str
    tensor_shape: list[int]
    channels: int
    height: int
    width: int
    spatial: bool
    feature_map_url: str
    activation_heatmap_url: str
    feature_thumbnail_url: str
    activation_thumbnail_url: str
    feature_download_name: str
    activation_download_name: str
    channel_index: int | None = None
    feature_method: str
    heatmap_method: str
    input_shape: list[int]


class GradeGradCAMResponse(BaseModel):
    target_class: int
    probabilities: list[float]
    gradcam_url: str
    method: str
