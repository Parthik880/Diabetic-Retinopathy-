from models.lesion.predict import IMAGE_SIZE, LESION_CLASSES, predict_lesions, preprocess_lesion_image
from models.lesion.visualization import LESION_COLORS
from utils.visualization import save_attention, save_mask_layers
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
import json
import logging
import time
from typing import Callable
from PIL import Image
from .lesion_postprocessing import load_config, process_maps
from models.lesion.visualization import create_bounding_box_image, create_center_image


def _record(timing, key, started):
    timing[key] = timing.get(key, 0.0) + (time.perf_counter_ns() - started) / 1_000_000


def predict(
    path,
    model,
    output_dir,
    on_stage: Callable[[str], None] | None = None,
    optimize_artifacts: bool = True,
    generate_gradcam: bool = False,
    precomputed_original_probabilities: np.ndarray | None = None,
):
    total_started = time.perf_counter_ns()
    timing = {}
    started = time.perf_counter_ns()
    config = load_config()
    _record(timing, 'config_load_ms', started)
    result = predict_lesions(path, model=model, output_dir=output_dir,
                            threshold=config.pixel_threshold, min_component_area=1,
                            generate_gradcam=generate_gradcam, save_analysis=False,
                            save_probability_maps=True, timing=timing,
                            stage_callback=on_stage,
                            save_probability_plot_images=not optimize_artifacts,
                            save_gradcam_overlay_images=not optimize_artifacts,
                            generate_localization_images=not optimize_artifacts,
                            defer_region_extraction=optimize_artifacts,
                            precomputed_original_probabilities=precomputed_original_probabilities)
    if on_stage is not None:
        on_stage('LESION_REGION_EXTRACTION')
    started = time.perf_counter_ns()
    maps = {code: np.load(item['probability_values_path'], allow_pickle=False) for code, item in result['lesions'].items()}
    _record(timing, 'probability_array_loading_ms', started)
    started = time.perf_counter_ns()
    processed = process_maps(maps, config, timing)
    _record(timing, 'display_region_postprocessing_ms', started)
    result.update({key: value for key, value in processed.items() if key != 'lesions'})
    result['postprocessing']['seconds'] = timing['display_region_postprocessing_ms'] / 1000
    result['mask_note'] = 'Full pixel-threshold mask; region size, merge, and score rules do not modify it.'
    result['gradcam']['target_mask'] = 'Full pixel-threshold mask before display-region processing'
    result['raw_bounding_box_image_path'] = result['bounding_box_image_path']
    result['raw_center_point_image_path'] = result['center_point_image_path']
    if on_stage is not None:
        on_stage('LESION_RESULTS_SAVING')
    for code, item in result['lesions'].items():
        item.update(processed['lesions'][code])
        destination = Path(output_dir) / 'browser' / code
        started = time.perf_counter_ns()
        item.update(save_mask_layers(item['mask_path'], LESION_COLORS[code], destination / 'mask.png'))
        _record(timing, 'browser_mask_saving_ms', started)
        values = maps[code]
        started = time.perf_counter_ns()
        item['probability_heatmap'] = {**save_attention(values, destination / 'probability.png', item['probability_values_path']),
                                       'method': 'sigmoid segmentation probability',
                                       'note': 'Independent class-channel pixel probability, not Grad-CAM.'}
        _record(timing, 'browser_probability_saving_ms', started)
        item['attention'] = None
        if item.get('gradcam_values_path'):
            started = time.perf_counter_ns()
            item['attention'] = {**save_attention(np.load(item['gradcam_values_path'], allow_pickle=False),
                                                 destination / 'gradcam.png', item['gradcam_values_path']),
                                  'method': 'Segmentation Grad-CAM',
                                  'target_layer': result['gradcam']['target_layer'],
                                  'objective': result['gradcam']['target_formulation'], 'target_channel': item['channel']}
            _record(timing, 'browser_gradcam_saving_ms', started)
        else:
            item['attention_unavailable_reason'] = 'No thresholded predicted-lesion pixels for this class; no CAM was generated.'
    started = time.perf_counter_ns()
    with Image.open(path) as image:
        image.load()
        rgb = np.array(image.convert('RGB'))
    _record(timing, 'final_original_decode_ms', started)
    boxes = Path(output_dir) / 'displayed_region_boxes.png'
    centers = Path(output_dir) / 'displayed_region_centers.png'
    started = time.perf_counter_ns()
    create_bounding_box_image(rgb, result['lesions'], boxes)
    _record(timing, 'displayed_bounding_box_saving_ms', started)
    started = time.perf_counter_ns()
    create_center_image(rgb, result['lesions'], centers)
    _record(timing, 'displayed_center_saving_ms', started)
    result['bounding_box_image_path'] = str(boxes.resolve())
    result['center_point_image_path'] = str(centers.resolve())
    result['timing_ms'] = timing
    started = time.perf_counter_ns()
    json.dumps(result, indent=2, allow_nan=False)
    _record(timing, 'final_json_serialization_ms', started)
    timing['total_lesion_stage_ms'] = (time.perf_counter_ns() - total_started) / 1_000_000
    result['timing_ms'] = timing
    serialized = json.dumps(result, indent=2, allow_nan=False)
    started = time.perf_counter_ns()
    Path(result['json_path']).write_text(serialized, encoding='utf-8')
    _record(timing, 'final_json_saving_ms', started)
    result['timing_ms'] = timing
    logging.getLogger('uvicorn.error').info('Lesion post-processing: %s; %.3fs',
                                          processed['postprocessing']['statistics'], result['postprocessing']['seconds'])
    logging.getLogger('uvicorn.error').info('[Lesion Timing] %s', json.dumps(timing, sort_keys=True))
    return result


def predict_batch(paths, model, output_dirs, on_stages=None):
    """Run one ordered UNet++ forward, then reuse the existing per-image postprocessing."""
    if len(paths) != len(output_dirs):
        raise ValueError('One lesion output directory is required per image.')
    if not paths:
        return []
    callbacks = on_stages or [None] * len(paths)
    if len(callbacks) != len(paths):
        raise ValueError('One lesion stage callback is required per image.')
    prepared = [preprocess_lesion_image(path) for path in paths]
    image_paths = [item[0] for item in prepared]
    tensors = torch.cat([item[1] for item in prepared], dim=0)
    logging.getLogger('uvicorn.error').info('Lesion tensor shape: %s', list(tensors.shape))
    sizes = []
    for path in image_paths:
        with Image.open(path) as image:
            sizes.append((image.height, image.width))
    device = next(model.parameters()).device
    for callback in callbacks:
        if callback is not None:
            callback('LESION_INFERENCE')
    model_input = tensors.to(device)
    try:
        with torch.inference_mode():
            logits = model(model_input)
            probabilities = torch.sigmoid(logits)
        expected = (len(paths), len(LESION_CLASSES), IMAGE_SIZE, IMAGE_SIZE)
        if tuple(logits.shape) != expected:
            raise RuntimeError(f'Expected batched lesion logits with shape {expected}, received {tuple(logits.shape)}')
        resized = [
            F.interpolate(probabilities[index:index + 1], size=size, mode='bilinear', align_corners=False)[0]
            .detach().float().cpu().numpy()
            for index, size in enumerate(sizes)
        ]
    finally:
        del model_input
    del logits, probabilities, tensors
    results = []
    for path, output_dir, callback, values in zip(image_paths, output_dirs, callbacks, resized, strict=True):
        results.append(predict(
            path, model, output_dir, on_stage=callback,
            precomputed_original_probabilities=values,
        ))
    return results
