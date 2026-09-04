"""TOPIQ image-quality model and reusable prediction API."""

from .model import METRIC_ID, MODEL_LABEL, IQAModel
from .predict import predict_iqa

__all__ = ["METRIC_ID", "MODEL_LABEL", "IQAModel", "predict_iqa"]
