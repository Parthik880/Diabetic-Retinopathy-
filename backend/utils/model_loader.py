"""One registry per backend process; no request-time checkpoint loading."""
import logging
import os
from pathlib import Path
import sys
from threading import Lock

ROOT = (
    Path(getattr(sys, "_MEIPASS")).resolve()
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[2]
)
RESOURCES = ROOT / 'resources' / 'models'
os.environ.setdefault('TORCH_HOME', str(RESOURCES / 'torch'))
os.environ.setdefault('DR_CHECKPOINT_DIR', str(RESOURCES))
os.environ.setdefault('MPLBACKEND', 'Agg')

import torch
from runtime_device import DEVICE, DEVICE_NAME, model_parameter_device
from models.iqa.inference import EfficientNetIQAService
from models.lesion.model import load_lesion_model
from models.grade.model import load_grade_model
from models.restoration.model import load_restoration_model


class ModelRegistry:
    def __init__(self):
        self.device = DEVICE
        self.device_name = DEVICE_NAME
        self.model_devices = {}
        logger = logging.getLogger('uvicorn.error')
        logger.info('RetinaGram inference device: CPU')
        logger.info('torch.__version__: %s', torch.__version__)
        logger.info('torch.version.cuda: %s', torch.version.cuda)
        logger.info('torch.cuda.is_available(): %s', torch.cuda.is_available())
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.models = {}
        self.errors = {}
        self.lock = Lock()
        loaders = {
            'quality': lambda: EfficientNetIQAService(RESOURCES / 'final_efficientnet_iqa.pth', self.device),
            'lesion': lambda: load_lesion_model(RESOURCES / 'epoch_018_best_dice.pth', self.device)[0],
            'grading': lambda: load_grade_model(RESOURCES / 'grade' / 'convnext_tiny.pth', self.device),
            'restoration': lambda: load_restoration_model(RESOURCES / 'restoration' / 'NAFNet-SIDD-width32.pth', self.device)[0],
        }
        for name, loader in loaders.items():
            try:
                loaded = loader()
                self.models[name] = loaded
                if name == 'quality':
                    classifier_device = model_parameter_device(loaded.classifier, 'IQA classifier')
                    feature_device = model_parameter_device(loaded.feature_extractor, 'IQA feature extractor')
                    if classifier_device != feature_device:
                        raise RuntimeError('IQA components are on different devices.')
                    self.model_devices[name] = str(classifier_device)
                else:
                    self.model_devices[name] = str(model_parameter_device(loaded, name))
                logger.info('%s next(model.parameters()).device: %s', name, self.model_devices[name])
            except Exception as exc:
                self.errors[name] = str(exc)
                logging.exception('Model unavailable: %s', name)

    def health(self):
        return {'status': 'ok', 'app': 'retina-desktop', 'device': str(self.device),
                'device_name': self.device_name,
                'ready': any(k in self.models for k in ('quality', 'grading', 'lesion')),
                'models': list(self.models), 'unavailable': self.errors,
                'model_devices': self.model_devices,
                'torch_version': torch.__version__,
                'torch_version_cuda': torch.version.cuda,
                'torch_cuda_available': torch.cuda.is_available(),
                'restoration_policy': 'Explicit request only; generic SIDD denoiser, not retinal fine-tuned.'}
