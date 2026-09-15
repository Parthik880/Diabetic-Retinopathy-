"""Ordered tensor-batch orchestration used only by batch analysis."""
from __future__ import annotations

import gc
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import torch
from PIL import Image

from inference import grading, lesions, quality, restoration
from inference.pipeline import PipelineState, TERMINAL_STATES, normalize_quality_result, public_paths, utc_now


LOGGER = logging.getLogger("uvicorn.error")


def _available_ram_bytes():
    if os.name != "nt":
        return None
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    return int(status.ullAvailPhys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else None


def _postprocess_worker_count():
    by_cpu = max(1, (os.cpu_count() or 1) // 2)
    available = _available_ram_bytes()
    by_ram = max(1, available // (2 * 1024 ** 3)) if available else 1
    return min(4, by_cpu, by_ram)


def _log_stage_profile(stage, count, metrics, *, overlapping=False):
    LOGGER.info(
        "STAGE %d PROFILE\n--------------------------------\n%s",
        stage,
        "\n".join(f"{name + ':':<31} {value / 1000:.3f} s" for name, value in metrics.items()),
    )
    LOGGER.info(
        "STAGE %d PROFILE PER IMAGE\n--------------------------------\n%s",
        stage,
        "\n".join(f"{name + ':':<31} {value / count:.3f} ms" for name, value in metrics.items()),
    )
    if overlapping:
        LOGGER.info("Stage %d component totals include overlapping worker time.", stage)


def _profile_stage3(count, total_ms, grade, lesion, results, workers):
    item_timings = [result.get("timing_ms", {}) for result in results]

    def total(*keys):
        return sum(float(item.get(key, 0.0)) for item in item_timings for key in keys)

    gradcam_ms = sum(float(grade.get(key, 0.0)) for key in
                     ("gradcam_backward_ms", "gradcam_map_ms", "grade_d2h_ms"))
    cpu_ms = total("display_region_postprocessing_ms", "mask_thresholding_ms",
                   "original_image_decode_ms", "final_original_decode_ms")
    artifact_ms = total(
        "probability_array_saving_ms", "mask_saving_ms", "overlay_generation_saving_ms",
        "browser_mask_saving_ms", "browser_probability_saving_ms",
        "displayed_bounding_box_saving_ms", "displayed_center_saving_ms",
        "final_json_serialization_ms", "final_json_saving_ms",
    )
    broad = {
        "ConvNeXt forward": float(grade.get("convnext_forward_ms", 0.0)),
        "Grade Grad-CAM": gradcam_ms,
        "Grade artifacts": float(grade.get("grade_artifact_wall_ms", 0.0)),
        "UNet++ forward": float(lesion.get("unet_forward_ms", 0.0)),
        "Probability resize+D2H": float(lesion.get("probability_resize_ms", 0.0)) +
                                  float(lesion.get("d2h_transfer_ms", 0.0)),
        "Lesion CPU postprocessing": cpu_ms,
        "Lesion artifact writing": artifact_ms,
        "Total Stage 3": total_ms,
    }
    _log_stage_profile(3, count, broad, overlapping=True)
    detail = {
        "grade_preprocessing_ms": grade.get("preprocessing_ms", 0.0),
        "convnext_forward_ms": grade.get("convnext_forward_ms", 0.0),
        "gradcam_backward_ms": grade.get("gradcam_backward_ms", 0.0),
        "gradcam_map_ms": grade.get("gradcam_map_ms", 0.0),
        "gradcam_resize_ms": grade.get("gradcam_resize_ms", 0.0),
        "gradcam_png_writing_ms": grade.get("gradcam_png_writing_ms", 0.0),
        "lesion_preprocessing_ms": lesion.get("preprocessing_ms", 0.0),
        "unet_forward_ms": lesion.get("unet_forward_ms", 0.0),
        "sigmoid_ms": lesion.get("sigmoid_ms", 0.0),
        "probability_resize_ms": lesion.get("probability_resize_ms", 0.0),
        "d2h_transfer_ms": lesion.get("d2h_transfer_ms", 0.0),
        "thresholding_ms": total("mask_thresholding_ms"),
        "probability_npy_writing_ms": total("probability_array_saving_ms"),
        "mask_tiff_writing_ms": total("mask_saving_ms"),
        "process_maps_ms": total("display_region_postprocessing_ms"),
        "connected_components_ms": total("connected_components_ms"),
        "browser_mask_writing_ms": total("browser_mask_saving_ms"),
        "probability_heatmap_writing_ms": total("browser_probability_saving_ms"),
        "bounding_box_rendering_ms": total("displayed_bounding_box_saving_ms"),
        "center_rendering_ms": total("displayed_center_saving_ms"),
        "json_serialization_writing_ms": total("final_json_serialization_ms", "final_json_saving_ms"),
    }
    LOGGER.info("STAGE 3 PROFILE DETAIL (worker totals may overlap): %s", json.dumps(detail, sort_keys=True))
    LOGGER.info("Stage 3 postprocessing workers: %d", workers)


def _adaptive_map(items, limit, stage, run_chunk, user_batch_count=None):
    """Run one accepted user batch; CUDA OOM never becomes hidden sub-batches."""
    requested = len(items)
    try:
        LOGGER.info("GPU %s batch: %d images", stage, requested)
        values = run_chunk(items)
        if len(values) != requested:
            raise RuntimeError(f"{stage} returned {len(values)} results for {requested} images")
        return values, max(1, int(limit)), requested, False
    except torch.cuda.OutOfMemoryError as exc:
        peak = torch.cuda.max_memory_allocated() / 1048576 if torch.cuda.is_available() else 0.0
        LOGGER.error("CUDA OOM: requested_images=%d stage_images=%d calculated_max=%d stage=%s peak_vram_mib=%.1f",
                     user_batch_count or requested, requested, limit, stage, peak)
        gc.collect()
        torch.cuda.empty_cache()
        raise RuntimeError("This batch could not fit into GPU memory during analysis. Try a smaller batch.") from exc


def run_analysis_batch(
    *,
    items: list[dict],
    registry,
    runs_root: Path,
    target_batch_size: int,
    on_state: Callable[[int, PipelineState], None] | None = None,
    on_batch_start: Callable[[list[int]], None] | None = None,
    on_display_stage: Callable[[list[int], int], None] | None = None,
    stage1_started_ns: int | None = None,
) -> dict:
    """Run IQA, ConvNeXt, and UNet++ as ordered tensor batches.

    NAFNet remains serial because it retains each input's full resolution and
    therefore has a different, image-dependent VRAM requirement.
    """
    if len(items) > max(1, int(target_batch_size)):
        raise ValueError(
            f"Batch too large for this GPU. Maximum {target_batch_size} images; received {len(items)}."
        )
    pipeline_started = stage1_started_ns or time.perf_counter_ns()
    batch_staging_ms = max(0.0, (time.perf_counter_ns() - pipeline_started) / 1_000_000)
    input_decode_ms = 0.0
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
            started = time.perf_counter_ns()
            with Image.open(path) as source:
                context["width"], context["height"] = source.size
                context["iqa_image"] = source.convert("RGB").copy()
            input_decode_ms += (time.perf_counter_ns() - started) / 1_000_000
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

        quality_timing = {}

        def quality_chunk(chunk):
            if on_batch_start is not None:
                on_batch_start([context["index"] for context in chunk])
            for context in chunk:
                transition(context, PipelineState.IQA)
            return quality.predict_batch([context["iqa_image"] for context in chunk], registry.models["quality"],
                                         timing=quality_timing)

        quality_values, stage_limit, used, fell_back = _adaptive_map(
            valid, effective_limit, "IQA", quality_chunk, len(items)
        )
        effective_limit = min(effective_limit, stage_limit)
        largest_used = max(largest_used, used)
        oom_fallback |= fell_back
        routing_started = time.perf_counter_ns()
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

        quality_routing_ms = (time.perf_counter_ns() - routing_started) / 1_000_000
        stage1_ms = (time.perf_counter_ns() - pipeline_started) / 1_000_000
        _log_stage_profile(1, len(valid), {
            "Batch input staging": batch_staging_ms,
            "Input decode": input_decode_ms,
            "IQA preprocessing": float(quality_timing.get("preprocessing_ms", 0.0)),
            "IQA H2D transfer": float(quality_timing.get("h2d_transfer_ms", 0.0)),
            "EfficientNet feature forward": float(quality_timing.get("feature_forward_ms", 0.0)),
            "IQA classifier forward": float(quality_timing.get("classifier_forward_ms", 0.0)),
            "IQA softmax+D2H": float(quality_timing.get("softmax_d2h_ms", 0.0)),
            "IQA result routing": quality_routing_ms,
            "Total Stage 1": stage1_ms,
        })

        stage2_started = time.perf_counter_ns()
        if accepted and on_display_stage is not None:
            on_display_stage([context["index"] for context in accepted], 2)

        # Full-resolution NAFNet has image-dependent memory use and stays serial.
        restoration_timing = {}
        restoration_routing_ms = 0.0
        for context in accepted:
            if context["result"]["quality"]["normalized_quality"] != "USABLE":
                continue
            if "restoration" not in registry.models:
                raise RuntimeError("NAFNet restoration is unavailable for this usable image.")
            transition(context, PipelineState.RESTORING)
            context["invocation_counts"]["nafnet"] = 1
            restored = restoration.restore(context["path"], registry.models["restoration"],
                                           context["destination"] / "restoration", timing=restoration_timing)
            started = time.perf_counter_ns()
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
            restoration_routing_ms += (time.perf_counter_ns() - started) / 1_000_000

        if accepted:
            if "grading" not in registry.models:
                raise RuntimeError("DR grading model is unavailable.")

            stage2_ms = (time.perf_counter_ns() - stage2_started) / 1_000_000
            _log_stage_profile(2, len(accepted), {
                "Restoration validation": float(restoration_timing.get("validation_ms", 0.0)),
                "Restoration preprocessing": float(restoration_timing.get("preprocessing_ms", 0.0)),
                "Restoration H2D transfer": float(restoration_timing.get("h2d_transfer_ms", 0.0)),
                "NAFNet forward": float(restoration_timing.get("nafnet_forward_ms", 0.0)),
                "Restoration D2H": float(restoration_timing.get("d2h_transfer_ms", 0.0)),
                "Restored PNG writing": float(restoration_timing.get("png_writing_ms", 0.0)),
                "Restoration result routing": restoration_routing_ms,
                "Total Stage 2": stage2_ms,
            })
            if on_display_stage is not None:
                on_display_stage([context["index"] for context in accepted], 3)

            stage3_started = time.perf_counter_ns()
            grade_timing = {}
            lesion_timing = {}
            postprocess_workers = _postprocess_worker_count()
            with ThreadPoolExecutor(max_workers=postprocess_workers, thread_name_prefix="stage3") as executor:
                def grade_chunk(chunk):
                    for context in chunk:
                        transition(context, PipelineState.GRADING)
                    return grading.predict_batch(
                        [context["analysis_path"] for context in chunk], registry.models["grading"],
                        [context["destination"] / "grading" for context in chunk],
                        executor=executor, timing=grade_timing,
                    )

                grade_values, stage_limit, used, fell_back = _adaptive_map(
                    accepted, effective_limit, "grading", grade_chunk, len(items)
                )
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
                        executor=executor, max_workers=postprocess_workers, timing=lesion_timing,
                    )

                lesion_values, stage_limit, used, fell_back = _adaptive_map(
                    accepted, effective_limit, "lesion", lesion_chunk, len(items)
                )
            effective_limit = min(effective_limit, stage_limit)
            largest_used = max(largest_used, used)
            oom_fallback |= fell_back
            for context, lesion_result in zip(accepted, lesion_values, strict=True):
                context["invocation_counts"]["lesions"] = 1
                context["result"]["lesions"] = lesion_result
                context["result"]["warnings"].append(
                    "Lesion region scores are mean pixel probabilities, not clinical confidence or severity."
                )

            stage3_ms = (time.perf_counter_ns() - stage3_started) / 1_000_000
            _profile_stage3(len(accepted), stage3_ms, grade_timing, lesion_timing,
                            lesion_values, postprocess_workers)

            stage4_pipeline_started = time.perf_counter_ns()
            if on_display_stage is not None:
                on_display_stage([context["index"] for context in accepted], 4)
            for context in accepted:
                transition(context, PipelineState.PREPARING_RESULTS)
                transition(context, PipelineState.COMPLETE)
                context["result"]["state"] = PipelineState.COMPLETE.value

    response_writing_started = time.perf_counter_ns()
    for context in valid:
        public_result = public_paths(context["result"], runs_root)
        public_result["state_history"] = context["state_history"]
        public_result["invocation_counts"] = context["invocation_counts"]
        (context["destination"] / "response.json").write_text(
            json.dumps(public_result, indent=2, allow_nan=False), encoding="utf-8"
        )
        results[context["index"]] = public_result
    stage4_response_ms = (time.perf_counter_ns() - response_writing_started) / 1_000_000

    peak = torch.cuda.max_memory_allocated(device) / 1048576 if device.type == "cuda" else 0.0
    LOGGER.info("Effective batch size: %d", min(effective_limit, largest_used) if largest_used else 1)
    return {
        "results": results,
        "effective_batch_size": effective_limit,
        "largest_batch_used": largest_used,
        "oom_fallback": oom_fallback,
        "peak_vram_mib": peak,
        "stage4_pipeline_ms": (
            (time.perf_counter_ns() - stage4_pipeline_started) / 1_000_000 if accepted else stage4_response_ms
        ),
        "stage4_response_writing_ms": stage4_response_ms,
    }
