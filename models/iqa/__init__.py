"""EfficientNet image-quality model and reusable prediction API."""

from .inference import EfficientNetIQAService
from .model import IQA_CLASS_NAMES, METRIC_ID, MODEL_LABEL, EfficientNetIQA
from .predict import predict_iqa

IQAModel = EfficientNetIQAService

__all__ = [
    "EfficientNetIQA", "EfficientNetIQAService", "IQA_CLASS_NAMES",
    "IQAModel", "METRIC_ID", "MODEL_LABEL", "predict_iqa",
]
