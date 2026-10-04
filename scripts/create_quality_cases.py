"""Make deterministic development images that exercise IQA routing."""
from __future__ import annotations

import os
import sys
sys.dont_write_bytecode = True
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from dev_paths import ROOT, SOURCE, source_checkpoint
sys.path.insert(0, str(SOURCE / "backend"))
os.environ["TORCH_HOME"] = str(Path.home() / ".cache/torch")
from models.iqa.inference import EfficientNetIQAService  # noqa: E402


def main() -> None:
    image = Image.open(os.environ.get("RETINAGRAM_TEST_IMAGE", str(SOURCE / "resources/test-images/20170629163635747.jpg"))).convert("RGB")
    folder = ROOT / "build/validation/quality_cases"
    folder.mkdir(parents=True, exist_ok=True)
    candidates = {}
    for sigma in (2, 4, 6, 9, 12, 16, 24):
        candidates[f"blur_{sigma}"] = image.filter(ImageFilter.GaussianBlur(sigma))
    for factor in (0.2, 0.35, 0.5, 0.7, 1.3, 1.7, 2.2):
        candidates[f"brightness_{factor}"] = ImageEnhance.Brightness(image).enhance(factor)
    for factor in (0.2, 0.4, 0.6, 1.5, 2.0):
        candidates[f"contrast_{factor}"] = ImageEnhance.Contrast(image).enhance(factor)
    model = EfficientNetIQAService(source_checkpoint("final_efficientnet_iqa.pth"), "cuda")
    for name, candidate in candidates.items():
        outcome = model.predict(candidate)
        print(name, outcome["quality"], round(outcome["confidence"], 4), flush=True)
        if outcome["quality"] != "Good":
            candidate.save(folder / f"{name}.png")
    for width in (512, 768):
        height = round(width * image.height / image.width)
        candidate = candidates["brightness_0.35"].resize((width, height), Image.Resampling.BILINEAR)
        candidate.save(folder / f"usable_{width}.png")
        outcome = model.predict(candidate)
        print(f"usable_{width}", outcome["quality"], round(outcome["confidence"], 4), flush=True)


if __name__ == "__main__":
    main()
