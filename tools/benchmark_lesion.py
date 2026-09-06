#!/usr/bin/env python
"""Reproducible benchmark for RetinaGram's deployed lesion model path.

Examples:
  python tools/benchmark_lesion.py --image scan.jpg
  python tools/benchmark_lesion.py --image left.jpg --second-image right.jpg --compare-fp16
  python tools/benchmark_lesion.py --image scan.jpg --device cpu --warm-runs 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from inference.lesion_postprocessing import load_config, process_maps  # noqa: E402
from models.lesion.dataset import LESION_CLASSES  # noqa: E402
from models.lesion.model import load_lesion_model  # noqa: E402
from models.lesion.predict import preprocess_lesion_image  # noqa: E402


def sync(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def milliseconds(started: int, device: torch.device | None = None) -> float:
    if device is not None:
        sync(device)
    return (time.perf_counter_ns() - started) / 1_000_000


def original_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.height, image.width


def percentile(values: list[float], value: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), value))


def summarize(records: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    keys = ("preprocessing_ms", "h2d_ms", "gpu_forward_ms", "postprocessing_ms", "total_ms", "peak_vram_mib")
    return {
        key: {
            "mean": statistics.fmean(row[key] for row in records),
            "median": statistics.median(row[key] for row in records),
            "min": min(row[key] for row in records),
            "max": max(row[key] for row in records),
            "p95": percentile([row[key] for row in records], 95),
        }
        for key in keys
    }


def forward_probabilities(
    model: torch.nn.Module,
    tensor: torch.Tensor,
    size: tuple[int, int],
    device: torch.device,
    precision: str,
) -> tuple[np.ndarray, float, float]:
    started = time.perf_counter_ns()
    with torch.inference_mode(), torch.autocast(
        device_type=device.type,
        dtype=torch.float16,
        enabled=precision == "fp16",
    ):
        logits = model(tensor)
    forward_ms = milliseconds(started, device)
    started = time.perf_counter_ns()
    probabilities = F.interpolate(
        torch.sigmoid(logits), size=size, mode="bilinear", align_corners=False
    ).float().cpu().numpy()
    transfer_and_resize_ms = milliseconds(started, device)
    return probabilities, forward_ms, transfer_and_resize_ms


def run_once(
    model: torch.nn.Module,
    image: Path,
    device: torch.device,
    precision: str,
    config,
) -> tuple[dict[str, float], np.ndarray, dict]:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    total_started = time.perf_counter_ns()
    started = time.perf_counter_ns()
    resolved, cpu_tensor = preprocess_lesion_image(image)
    preprocessing_ms = milliseconds(started)
    size = original_size(resolved)
    started = time.perf_counter_ns()
    tensor = cpu_tensor.to(device)
    h2d_ms = milliseconds(started, device)
    probabilities, forward_ms, resize_transfer_ms = forward_probabilities(
        model, tensor, size, device, precision
    )
    maps = {code: probabilities[0, channel] for code, channel in LESION_CLASSES.items()}
    started = time.perf_counter_ns()
    processed = process_maps(maps, config)
    region_ms = milliseconds(started)
    postprocessing_ms = resize_transfer_ms + region_ms
    total_ms = milliseconds(total_started, device)
    peak = torch.cuda.max_memory_allocated(device) / 1048576 if device.type == "cuda" else 0.0
    return ({
        "preprocessing_ms": preprocessing_ms,
        "h2d_ms": h2d_ms,
        "gpu_forward_ms": forward_ms,
        "resize_d2h_ms": resize_transfer_ms,
        "region_postprocessing_ms": region_ms,
        "postprocessing_ms": postprocessing_ms,
        "total_ms": total_ms,
        "peak_vram_mib": peak,
    }, probabilities, processed)


def compare_fp16(model, image: Path, device: torch.device, config) -> dict:
    if device.type != "cuda":
        return {"skipped": "FP16 autocast comparison requires CUDA."}
    resolved, cpu_tensor = preprocess_lesion_image(image)
    tensor = cpu_tensor.to(device)
    size = original_size(resolved)
    fp32, fp32_ms, _ = forward_probabilities(model, tensor, size, device, "fp32")
    fp16, fp16_ms, _ = forward_probabilities(model, tensor, size, device, "fp16")
    details = {}
    for code, channel in LESION_CLASSES.items():
        reference = fp32[0, channel]
        candidate = fp16[0, channel]
        mask_a = reference >= config.pixel_threshold
        mask_b = candidate >= config.pixel_threshold
        intersection = int(np.logical_and(mask_a, mask_b).sum())
        union = int(np.logical_or(mask_a, mask_b).sum())
        denominator = int(mask_a.sum() + mask_b.sum())
        details[code] = {
            "max_probability_abs_error": float(np.max(np.abs(reference - candidate))),
            "mean_probability_abs_error": float(np.mean(np.abs(reference - candidate))),
            "fp32_positive_pixels": int(mask_a.sum()),
            "fp16_positive_pixels": int(mask_b.sum()),
            "mask_iou": intersection / union if union else 1.0,
            "mask_dice": 2 * intersection / denominator if denominator else 1.0,
        }
    fp32_regions = process_maps(
        {code: fp32[0, channel] for code, channel in LESION_CLASSES.items()}, config
    )["lesions"]
    fp16_regions = process_maps(
        {code: fp16[0, channel] for code, channel in LESION_CLASSES.items()}, config
    )["lesions"]
    return {
        "fp32_forward_ms": fp32_ms,
        "fp16_forward_ms": fp16_ms,
        "speedup": fp32_ms / fp16_ms,
        "exact_probability_match": bool(np.array_equal(fp32, fp16)),
        "exact_threshold_mask_match": bool(np.array_equal(fp32 >= config.pixel_threshold, fp16 >= config.pixel_threshold)),
        "displayed_region_counts": {
            code: {"fp32": fp32_regions[code]["num_regions"], "fp16": fp16_regions[code]["num_regions"]}
            for code in LESION_CLASSES
        },
        "classes": details,
    }


def compare_batch_two(model, first: Path, second: Path, device: torch.device, precision: str, runs: int) -> dict:
    tensors = [preprocess_lesion_image(path)[1].to(device) for path in (first, second)]
    batch = torch.cat(tensors, dim=0)

    def measure(value: torch.Tensor) -> float:
        sync(device)
        started = time.perf_counter_ns()
        with torch.inference_mode(), torch.autocast(
            device_type=device.type, dtype=torch.float16, enabled=precision == "fp16"
        ):
            model(value)
        return milliseconds(started, device)

    # Untimed warmup keeps compilation/cache effects out of this focused comparison.
    measure(tensors[0])
    sequential = [sum(measure(item) for item in tensors) for _ in range(runs)]
    batched = [measure(batch) for _ in range(runs)]
    return {
        "runs": runs,
        "sequential_two_images_ms": summarize_scalar(sequential),
        "batch_size_2_ms": summarize_scalar(batched),
        "throughput_speedup": statistics.fmean(sequential) / statistics.fmean(batched),
    }


def summarize_scalar(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values), "median": statistics.median(values),
        "min": min(values), "max": max(values), "p95": percentile(values, 95),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument(
        "--checkpoint", type=Path,
        default=ROOT / "resources" / "models" / "epoch_018_best_dice.pth",
    )
    parser.add_argument("--second-image", type=Path)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--precision", choices=("fp32", "fp16"), default="fp32")
    parser.add_argument("--warm-runs", type=int, default=10)
    parser.add_argument("--compare-fp16", action="store_true")
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.warm_runs < 1:
        raise ValueError("--warm-runs must be at least 1")
    device_name = "cuda" if args.device == "auto" and torch.cuda.is_available() else args.device
    if device_name == "auto":
        device_name = "cpu"
    device = torch.device(device_name)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
    if args.precision == "fp16" and device.type != "cuda":
        raise ValueError("FP16 mode requires CUDA")
    started = time.perf_counter_ns()
    model, metadata = load_lesion_model(args.checkpoint, device=device)
    sync(device)
    model_load_ms = milliseconds(started)
    config = load_config()
    cold, _, cold_processed = run_once(model, args.image, device, args.precision, config)
    warm = [run_once(model, args.image, device, args.precision, config)[0] for _ in range(args.warm_runs)]
    report = {
        "environment": {
            "torch": torch.__version__, "cuda_runtime": torch.version.cuda,
            "device": str(device),
            "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
            "precision": args.precision,
        },
        "model": {"load_ms": model_load_ms, **metadata},
        "image": str(args.image.resolve()),
        "cold_run": cold,
        "cold_displayed_region_counts": {
            code: value["num_regions"] for code, value in cold_processed["lesions"].items()
        },
        "warm_runs": {"count": len(warm), "summary": summarize(warm), "records": warm},
    }
    if args.compare_fp16:
        report["fp16_equivalence"] = compare_fp16(model, args.image, device, config)
    if args.second_image:
        report["batch_size_two"] = compare_batch_two(
            model, args.image, args.second_image, device, args.precision, args.warm_runs
        )
    rendered = json.dumps(report, indent=2, allow_nan=False)
    print(rendered)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
