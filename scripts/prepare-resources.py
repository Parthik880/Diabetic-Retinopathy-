"""Setup-only official backbone download; inference never downloads weights."""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
os.environ['TORCH_HOME'] = str(ROOT / 'resources/models/torch')
from torchvision.models import EfficientNet_B0_Weights
EfficientNet_B0_Weights.IMAGENET1K_V1.get_state_dict(progress=True, check_hash=True)
required = ['final_efficientnet_iqa.pth', 'epoch_018_best_dice.pth', 'grade/convnext_tiny.pth']
for name in required:
    if not (ROOT / 'resources/models' / name).is_file():
        raise FileNotFoundError(f'Missing trained checkpoint: {name}. See MODEL_MANIFEST.md.')
