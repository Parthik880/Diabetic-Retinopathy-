from models.lesion.predict import predict_lesions
from models.lesion.visualization import LESION_COLORS
from utils.visualization import save_attention, save_mask_layers
from pathlib import Path
import numpy as np
import json
import logging
import time
from PIL import Image
from .lesion_postprocessing import load_config, process_maps
from models.lesion.visualization import create_bounding_box_image, create_center_image


def predict(path, model, output_dir):
    config = load_config()
    result = predict_lesions(path, model=model, output_dir=output_dir,
                            threshold=config.pixel_threshold, min_component_area=1,
                            generate_gradcam=True, save_analysis=False,
                            save_probability_maps=True)
    started = time.perf_counter()
    maps = {code: np.load(item['probability_values_path'], allow_pickle=False) for code, item in result['lesions'].items()}
    processed = process_maps(maps, config)
    result.update({key: value for key, value in processed.items() if key != 'lesions'})
    result['postprocessing']['seconds'] = time.perf_counter() - started
    result['mask_note'] = 'Full pixel-threshold mask; region size, merge, and score rules do not modify it.'
    result['gradcam']['target_mask'] = 'Full pixel-threshold mask before display-region processing'
    result['raw_bounding_box_image_path'] = result['bounding_box_image_path']
    result['raw_center_point_image_path'] = result['center_point_image_path']
    for code, item in result['lesions'].items():
        item.update(processed['lesions'][code])
        destination = Path(output_dir) / 'browser' / code
        item.update(save_mask_layers(item['mask_path'], LESION_COLORS[code], destination / 'mask.png'))
        values = maps[code]
        item['probability_heatmap'] = {**save_attention(values, destination / 'probability.png'),
                                       'method': 'sigmoid segmentation probability',
                                       'note': 'Independent class-channel pixel probability, not Grad-CAM.'}
        item['attention'] = None
        if item.get('gradcam_values_path'):
            item['attention'] = {**save_attention(np.load(item['gradcam_values_path'], allow_pickle=False),
                                                 destination / 'gradcam.png'),
                                  'method': 'Segmentation Grad-CAM',
                                  'target_layer': result['gradcam']['target_layer'],
                                  'objective': result['gradcam']['target_formulation'], 'target_channel': item['channel']}
        else:
            item['attention_unavailable_reason'] = 'No thresholded predicted-lesion pixels for this class; no CAM was generated.'
    with Image.open(path) as image:
        rgb = np.array(image.convert('RGB'))
    boxes = Path(output_dir) / 'displayed_region_boxes.png'
    centers = Path(output_dir) / 'displayed_region_centers.png'
    create_bounding_box_image(rgb, result['lesions'], boxes)
    create_center_image(rgb, result['lesions'], centers)
    result['bounding_box_image_path'] = str(boxes.resolve())
    result['center_point_image_path'] = str(centers.resolve())
    Path(result['json_path']).write_text(json.dumps(result, indent=2, allow_nan=False))
    logging.getLogger('uvicorn.error').info('Lesion post-processing: %s; %.3fs',
                                          processed['postprocessing']['statistics'], result['postprocessing']['seconds'])
    return result
