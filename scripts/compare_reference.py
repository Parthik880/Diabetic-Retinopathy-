"""Run the untouched Python pipeline against the native validation images.

This is a development-only comparison. It writes exclusively under build/validation.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
sys.dont_write_bytecode = True
import threading
from pathlib import Path
from types import SimpleNamespace

import torch

from dev_paths import ROOT, SOURCE, SOURCE_CHECKPOINTS, validation_images
sys.path.insert(0, str(SOURCE / "backend"))
os.environ["TORCH_HOME"] = str(Path.home() / ".cache" / "torch")

from inference.pipeline import run_analysis_pipeline  # noqa: E402
from models.grade.model import load_grade_model  # noqa: E402
from models.iqa.inference import EfficientNetIQAService  # noqa: E402
from models.lesion.model import load_lesion_model  # noqa: E402
from models.restoration.model import load_restoration_model  # noqa: E402

IMAGES = validation_images()


def main() -> None:
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    checkpoints = SOURCE_CHECKPOINTS
    registry = SimpleNamespace(
        models={
            "quality": EfficientNetIQAService(checkpoints / "final_efficientnet_iqa.pth", device),
            "restoration": load_restoration_model(checkpoints / "NAFNet-SIDD-width32.pth", device)[0],
            "grading": load_grade_model(checkpoints / "convnext_tiny.pth", device),
            "lesion": load_lesion_model(checkpoints / "epoch_018_best_dice.pth", device)[0],
        },
        lock=threading.Lock(),
        device=device,
        device_name=torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU",
    )
    destination = ROOT / "build/validation/reference"
    destination.mkdir(parents=True, exist_ok=True)
    summaries = []
    for index, path in enumerate(IMAGES):
        if len(sys.argv) > 1 and str(index) not in sys.argv[1:]:
            continue
        if not path.is_file():
            continue
        run_id = f"reference_{index}"
        folder = destination / run_id
        folder.mkdir(parents=True, exist_ok=True)
        copied = folder / path.name
        shutil.copy2(path, copied)
        result = run_analysis_pipeline(
            original_path=copied, registry=registry, run_id=run_id,
            runs_root=destination, eye="OS",
        )
        summary = {
            "image": str(path),
            "state": result["state"],
            "quality": result["quality"],
            "analysis_source": result["analysis_source"],
            "grading": result["grading"],
            "lesion_summary": result["lesions"].get("summary") if result["lesions"] else None,
            "invocation_counts": result["invocation_counts"],
        }
        summaries.append(summary)
        print(json.dumps({"image": str(path), "state": result["state"],
                          "quality": result["quality"]["quality"],
                          "grade": (result["grading"] or {}).get("predicted_grade")}), flush=True)
    (destination / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
