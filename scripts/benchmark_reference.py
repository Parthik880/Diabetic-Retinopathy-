"""Benchmark the untouched Python pipeline with persistent CUDA models."""
from __future__ import annotations

import json
import os
import shutil
import sys
sys.dont_write_bytecode = True
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psutil
import torch

from dev_paths import ROOT, SOURCE, SOURCE_CHECKPOINTS, validation_images
sys.path.insert(0, str(SOURCE / "backend"))
os.environ["TORCH_HOME"] = str(Path.home() / ".cache/torch")

from inference import pipeline  # noqa: E402
from models.grade.model import load_grade_model  # noqa: E402
from models.iqa.inference import EfficientNetIQAService  # noqa: E402
from models.lesion.model import load_lesion_model  # noqa: E402
from models.restoration.model import load_restoration_model  # noqa: E402


def sync() -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def main() -> None:
    process = psutil.Process()
    cases = validation_images()
    original, usable = cases[0], cases[4]
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    checkpoint = SOURCE_CHECKPOINTS
    start = time.perf_counter()
    registry = SimpleNamespace(
        models={
            "quality": EfficientNetIQAService(checkpoint / "final_efficientnet_iqa.pth", device),
            "restoration": load_restoration_model(checkpoint / "NAFNet-SIDD-width32.pth", device)[0],
            "grading": load_grade_model(checkpoint / "convnext_tiny.pth", device),
            "lesion": load_lesion_model(checkpoint / "epoch_018_best_dice.pth", device)[0],
        },
        lock=threading.Lock(), device=device,
        device_name=torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU",
    )
    sync()
    init_ms = (time.perf_counter() - start) * 1000
    idle_ram = process.memory_info().rss
    folder = ROOT / "build/validation/benchmark_reference"
    folder.mkdir(parents=True, exist_ok=True)
    results = {"model_initialization_ms": init_ms, "idle_ram_bytes": idle_ram, "runs": []}
    functions = [(pipeline.quality, "predict", "iqa"),
                 (pipeline.restoration, "restore", "nafnet"),
                 (pipeline.grading, "predict", "grading_and_cam"),
                 (pipeline.lesions, "predict", "lesions_and_visualization")]
    for kind, path in (("good", original), ("usable", usable)):
        for iteration in range(3):
            record = {"kind": kind, "iteration": iteration, "stages_ms": {},
                      "peak_sampled_ram_bytes": idle_ram}
            originals = []
            for module, name, stage in functions:
                function = getattr(module, name)
                originals.append((module, name, function))
                target = function
                if stage == "grading_and_cam":
                    def target(path, model, output_dir, _module=module):
                        detail = record.setdefault("grading_detail_ms", {})
                        return _module.predict_batch([path], model, [output_dir], timing=detail)[0]

                def timed(*args, _function=target, _stage=stage, **kwargs):
                    sync()
                    started = time.perf_counter()
                    output = _function(*args, **kwargs)
                    sync()
                    record["stages_ms"][_stage] = (time.perf_counter() - started) * 1000
                    record["peak_sampled_ram_bytes"] = max(
                        record["peak_sampled_ram_bytes"], process.memory_info().rss)
                    return output

                setattr(module, name, timed)
            try:
                name = f"{kind}_{iteration}"
                destination = folder / name
                destination.mkdir(parents=True, exist_ok=True)
                copied = destination / path.name
                shutil.copy2(path, copied)
                if device.type == "cuda":
                    torch.cuda.reset_peak_memory_stats()
                sync()
                started = time.perf_counter()
                outcome = pipeline.run_analysis_pipeline(
                    original_path=copied, registry=registry, run_id=name,
                    runs_root=folder, eye="OS")
                sync()
                record["analysis_ms"] = (time.perf_counter() - started) * 1000
                record["state"] = outcome["state"]
                record["peak_torch_vram_bytes"] = torch.cuda.max_memory_allocated() if device.type == "cuda" else None
                results["runs"].append(record)
                print(kind, iteration, round(record["analysis_ms"]), record["stages_ms"], flush=True)
            finally:
                for module, name, function in originals:
                    setattr(module, name, function)
    (folder / "benchmark.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
