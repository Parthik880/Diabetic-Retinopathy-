"""One registry per backend process; no request-time checkpoint loading."""
import logging
import os
from pathlib import Path
import sys
from threading import Lock
import time

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
from models.iqa.inference import EfficientNetIQAService
from models.lesion.model import load_lesion_model
from models.grade.model import load_grade_model
from models.restoration.model import load_restoration_model


class ModelRegistry:
    def __init__(self):
        self.device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        self.device_name = torch.cuda.get_device_name(0) if self.device.type == 'cuda' else 'CPU'
        self.model_devices = {}
        logger = logging.getLogger('uvicorn.error')
        if self.device.type == 'cuda':
            logger.info('RetinaGram inference device: CUDA (%s)', self.device_name)
        else:
            logger.info('RetinaGram inference device: CPU fallback')
        logger.info('torch.__version__: %s', torch.__version__)
        logger.info('torch.version.cuda: %s', torch.version.cuda)
        logger.info('torch.cuda.is_available(): %s', torch.cuda.is_available())
        if self.device.type == 'cuda':
            properties = torch.cuda.get_device_properties(self.device)
            logger.info('GPU total VRAM: %.0f MiB', properties.total_memory / 1048576)
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.models = {}
        self.errors = {}
        self.load_times_ms = {}
        self.warmup_times_ms = {}
        self.lock = Lock()
        loaders = {
            'quality': lambda: EfficientNetIQAService(RESOURCES / 'final_efficientnet_iqa.pth', self.device),
            'lesion': lambda: load_lesion_model(RESOURCES / 'epoch_018_best_dice.pth', self.device)[0],
            'grading': lambda: load_grade_model(RESOURCES / 'grade' / 'convnext_tiny.pth', self.device),
            'restoration': lambda: load_restoration_model(RESOURCES / 'restoration' / 'NAFNet-SIDD-width32.pth', self.device)[0],
        }
        for name, loader in loaders.items():
            try:
                started = time.perf_counter_ns()
                loaded = loader()
                self.models[name] = loaded
                if name == 'quality':
                    classifier_device = next(loaded.classifier.parameters()).device
                    feature_device = next(loaded.feature_extractor.parameters()).device
                    if classifier_device != feature_device:
                        raise RuntimeError('IQA components are on different devices.')
                    model_device = classifier_device
                else:
                    model_device = next(loaded.parameters()).device
                self.model_devices[name] = str(model_device)
                if self.device.type == 'cuda':
                    torch.cuda.synchronize(self.device)
                self.load_times_ms[name] = (time.perf_counter_ns() - started) / 1_000_000
                if name == 'lesion' and self.device.type == 'cuda':
                    try:
                        started = time.perf_counter_ns()
                        with torch.inference_mode():
                            loaded(torch.zeros((1, 3, 768, 768), device=self.device))
                        torch.cuda.synchronize(self.device)
                        self.warmup_times_ms[name] = (time.perf_counter_ns() - started) / 1_000_000
                    except RuntimeError:
                        logging.getLogger('uvicorn.error').warning('Lesion CUDA warmup was skipped.', exc_info=True)
                logger.info('%s next(model.parameters()).device: %s', name, model_device)
                logger.info(
                    '[MODEL] %s loaded in %.1f ms%s', name, self.load_times_ms[name],
                    f'; CUDA warmup {self.warmup_times_ms[name]:.1f} ms' if name in self.warmup_times_ms else '',
                )
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
                'gpu_total_vram_bytes': (
                    torch.cuda.get_device_properties(self.device).total_memory
                    if self.device.type == 'cuda' else None
                ),
                'model_load_ms': self.load_times_ms, 'model_warmup_ms': self.warmup_times_ms,
                'restoration_policy': 'Explicit request only; generic SIDD denoiser, not retinal fine-tuned.'}
