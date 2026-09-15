"""Ordered tensor-batch orchestration used only by batch analysis."""
from __future__ import annotations

import gc
import json
import logging
from pathlib import Path
from typing import Callable

import torch
from PIL import Image

from inference import grading, lesions, quality, restoration
from inference.pipeline import PipelineState, TERMINAL_STATES, normalize_quality_result, public_paths, utc_now


LOGGER = logging.getLogger("uvicorn.error")


def _adaptive_map(items, limit, stage, run_chunk):
    """Map ordered chunks, halving and retrying only the failed CUDA OOM chunk."""
    outputs = []
    offset = 0
    effective = max(1, int(limit))
    mini_batch = 0
    oom_fallback = False
    largest_used = 0
    while offset < len(items):
        chunk = items[offset:offset + effective]
        try:
            mini_batch += 1
            LOGGER.info("GPU %s mini-batch %d: %d images", stage, mini_batch, len(chunk))
            values = run_chunk(chunk)
            if len(values) != len(chunk):
                raise RuntimeError(f"{stage} returned {len(values)} results for {len(chunk)} images")
            outputs.extend(values)
            largest_used = max(largest_used, len(chunk))
            offset += len(chunk)
        except torch.cuda.OutOfMemoryError:
            if len(chunk) <= 1:
                raise
            oom_fallback = True
            effective = max(1, len(chunk) // 2)
            LOGGER.warning("CUDA OOM during %s; retrying the same images with batch size %d", stage, effective)
            gc.collect()
            torch.cuda.empty_cache()
    return outputs, effective, largest_used, oom_fallback


def run_analysis_batch(
    *,
    items: list[dict],
    registry,
    runs_root: Path,
    target_batch_size: int,
    on_state: Callable[[int, PipelineState], None] | None = None,
    on_batch_start: Callable[[list[int]], None] | None = None,
) -> dict:
    """Run IQA, ConvNeXt, and UNet++ as ordered tensor batches.

    NAFNet remains serial because it retains each input's full resolution and
    therefore has a different, image-dependent VRAM requirement.
    """
    contexts = []
    results: list[dict | Exception | None] = [None] * len(items)
    effective_limit = max(1, int(target_batch_size))
    largest_used = 0
    oom_fallback = False
    device = torch.device(registry.device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    def transition(context, state):
        history = context["state_history"]
        if history[-1]["state"] != state.value:
            history.append({"state": state.value, "at": utc_now()})
        LOGGER.info("[BATCH PIPELINE] image=%s run=%s state=%s", context["path"].name, context["run_id"], state.value)
        if on_state is not None and state not in TERMINAL_STATES:
            on_state(context["index"], state)

    for index, item in enumerate(items):
        path = Path(item["original_path"])
        context = {
            "index": index, "path": path, "run_id": item["run_id"], "eye": item.get("eye"),
            "destination": path.parent, "state_history": [{"state": PipelineState.WAITING.value, "at": utc_now()}],
            "invocation_counts": {"iqa": 0, "nafnet": 0, "grading": 0, "lesions": 0},
        }
        try:
            with Image.open(path) as source:
                context["width"], context["height"] = source.size
                context["iqa_image"] = source.convert("RGB").copy()
        except Exception as exc:
            transition(context, PipelineState.FAILED)
            results[index] = exc
            (path.parent / "failure.json").write_text(json.dumps({
                "run_id": item["run_id"], "state": PipelineState.FAILED.value,
                "state_history": context["state_history"], "invocation_counts": context["invocation_counts"],
            }, indent=2), encoding="utf-8")
        contexts.append(context)

    valid = [context for context in contexts if results[context["index"]] is None]
    if not valid:
        return {"results": results, "effective_batch_size": 1, "largest_batch_used": 0,
                "oom_fallback": False, "peak_vram_mib": 0.0}

    with registry.lock:
        if "quality" not in registry.models:
            raise RuntimeError("IQA model is unavailable; analysis cannot be routed safely.")

        def quality_chunk(chunk):
            if on_batch_start is not None:
                on_batch_start([context["index"] for context in chunk])
            for context in chunk:
                transition(context, PipelineState.IQA)
            return quality.predict_batch([context["iqa_image"] for context in chunk], registry.models["quality"])

        quality_values, stage_limit, used, fell_back = _adaptive_map(valid, effective_limit, "IQA", quality_chunk)
        effective_limit = min(effective_limit, stage_limit)
        largest_used = max(largest_used, used)
        oom_fallback |= fell_back
        accepted = []
        for context, quality_result in zip(valid, quality_values, strict=True):
            context.pop("iqa_image", None)
            context["invocation_counts"]["iqa"] = 1
            normalized = normalize_quality_result(quality_result)
            quality_result = {**quality_result, "normalized_quality": normalized}
            transition(context, {"GOOD": PipelineState.IQA_GOOD, "USABLE": PipelineState.IQA_USABLE,
                                 "RECAPTURE": PipelineState.IQA_REJECTED}[normalized])
            result = {
                "run_id": context["run_id"], "eye": context["eye"], "state": None,
                "state_history": context["state_history"], "quality": quality_result,
                "grading": None, "lesions": None, "warnings": [], "device": str(registry.device),
                "device_name": registry.device_name, "image_width": context["width"], "image_height": context["height"],
                "image_url": str(context["path"].resolve()), "original_image_url": str(context["path"].resolve()),
                "restored_image_url": None, "analysis_image_url": str(context["path"].resolve()),
                "analysis_source": "original", "invocation_counts": context["invocation_counts"],
            }
            context["result"] = result
            context["analysis_path"] = context["path"]
            if normalized == "RECAPTURE":
                result["warnings"].append(
                    "IQA rejected this image. Recapture is required; restoration, grading, and lesion analysis were not run."
                )
                transition(context, PipelineState.RECAPTURE_REQUIRED)
                result["state"] = PipelineState.RECAPTURE_REQUIRED.value
            else:
                accepted.append(context)

        # Full-resolution NAFNet has image-dependent memory use and stays serial.
        for context in accepted:
            if context["result"]["quality"]["normalized_quality"] != "USABLE":
                continue
            if "restoration" not in registry.models:
                raise RuntimeError("NAFNet restoration is unavailable for this usable image.")
            transition(context, PipelineState.RESTORING)
            context["invocation_counts"]["nafnet"] = 1
            restored = restoration.restore(context["path"], registry.models["restoration"], context["destination"] / "restoration")
            analysis_path = Path(restored["output_path"]).resolve()
            if not analysis_path.is_file():
                raise RuntimeError("NAFNet completed without producing a restored image.")
            context["analysis_path"] = analysis_path
            context["result"].update({
                "restored_image_url": str(analysis_path), "analysis_image_url": str(analysis_path),
                "analysis_source": "restored",
                "restoration": {key: value for key, value in restored.items() if key != "restored_image"},
            })
            context["result"]["warnings"].append(
                "IQA marked the image usable; downstream models ran on the NAFNet-restored image."
            )
            transition(context, PipelineState.RESTORATION_COMPLETE)

        if accepted:
            if "grading" not in registry.models:
                raise RuntimeError("DR grading model is unavailable.")

            def grade_chunk(chunk):
                for context in chunk:
                    transition(context, PipelineState.GRADING)
                return grading.predict_batch(
                    [context["analysis_path"] for context in chunk], registry.models["grading"],
                    [context["destination"] / "grading" for context in chunk],
                )

            grade_values, stage_limit, used, fell_back = _adaptive_map(accepted, effective_limit, "grading", grade_chunk)
            effective_limit = min(effective_limit, stage_limit)
            largest_used = max(largest_used, used)
            oom_fallback |= fell_back
            for context, grade_result in zip(accepted, grade_values, strict=True):
                context["invocation_counts"]["grading"] = 1
                context["result"]["grading"] = grade_result

            if "lesion" not in registry.models:
                raise RuntimeError("Lesion analysis model is unavailable.")

            def lesion_chunk(chunk):
                callbacks = []
                for context in chunk:
                    transition(context, PipelineState.LESION_ANALYSIS)
                    callbacks.append(lambda state, current=context: transition(current, PipelineState(state)))
                return lesions.predict_batch(
                    [context["analysis_path"] for context in chunk], registry.models["lesion"],
                    [context["destination"] / "lesions" for context in chunk], callbacks,
                )

            lesion_values, stage_limit, used, fell_back = _adaptive_map(accepted, effective_limit, "lesion", lesion_chunk)
            effective_limit = min(effective_limit, stage_limit)
            largest_used = max(largest_used, used)
            oom_fallback |= fell_back
            for context, lesion_result in zip(accepted, lesion_values, strict=True):
                context["invocation_counts"]["lesions"] = 1
                context["result"]["lesions"] = lesion_result
                context["result"]["warnings"].append(
                    "Lesion region scores are mean pixel probabilities, not clinical confidence or severity."
                )
                transition(context, PipelineState.PREPARING_RESULTS)
                transition(context, PipelineState.COMPLETE)
                context["result"]["state"] = PipelineState.COMPLETE.value

    for context in valid:
        public_result = public_paths(context["result"], runs_root)
        public_result["state_history"] = context["state_history"]
        public_result["invocation_counts"] = context["invocation_counts"]
        (context["destination"] / "response.json").write_text(
            json.dumps(public_result, indent=2, allow_nan=False), encoding="utf-8"
        )
        results[context["index"]] = public_result

    peak = torch.cuda.max_memory_allocated(device) / 1048576 if device.type == "cuda" else 0.0
    LOGGER.info("Effective batch size: %d", min(effective_limit, largest_used) if largest_used else 1)
    return {
        "results": results,
        "effective_batch_size": effective_limit,
        "largest_batch_used": largest_used,
        "oom_fallback": oom_fallback,
        "peak_vram_mib": peak,
    }
