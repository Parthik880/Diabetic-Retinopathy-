from pathlib import Path
import logging
import time
import torch
import torch.nn.functional as F
from PIL import Image
from models.grade.predict import preprocess_grade_image, GRADE_CLASS_MAPPING
from models.grade.gradcam import GradCAM
from utils.visualization import save_attention


def _finish_prediction(index, path, output_dir, target_class, values, logits, probabilities, device, target_name):
    timing = {}
    started = time.perf_counter_ns()
    with Image.open(path) as original:
        width, height = original.size
    resized = F.interpolate(values[None, None], size=(height, width), mode='bilinear',
                            align_corners=False)[0, 0].numpy()
    timing['gradcam_resize_ms'] = (time.perf_counter_ns() - started) / 1_000_000
    started = time.perf_counter_ns()
    artifact = save_attention(resized, Path(output_dir) / 'grade_gradcam.png')
    timing['gradcam_png_writing_ms'] = (time.perf_counter_ns() - started) / 1_000_000
    return index, {'image_path': str(path), 'logits': logits.tolist(),
                   'probabilities': probabilities.tolist(), 'predicted_class': target_class,
                   'predicted_grade': GRADE_CLASS_MAPPING[target_class],
                   'confidence': float(probabilities[target_class]), 'device': str(device),
                   'gradcam_path': artifact['heatmap_path'],
                   'gradcam': {**artifact, 'target_class': target_class, 'target_layer': target_name,
                               'method': 'Grad-CAM', 'objective': 'predicted-class pre-softmax logit',
                               'note': 'Relative classifier attribution, not lesion probability or clinical certainty.'}}, timing


def predict_batch(paths, model, output_dirs, *, executor=None, timing=None):
    if len(paths) != len(output_dirs):
        raise ValueError('One grading output directory is required per image.')
    if not paths:
        return []
    timing = timing if timing is not None else {}
    started = time.perf_counter_ns()
    prepared = [preprocess_grade_image(path) for path in paths]
    timing['preprocessing_ms'] = (time.perf_counter_ns() - started) / 1_000_000
    image_paths = [item[0] for item in prepared]
    tensor = torch.cat([item[1] for item in prepared], dim=0)
    logging.getLogger('uvicorn.error').info('Grade tensor shape: %s', list(tensor.shape))
    device = next(model.parameters()).device
    # Verified final Conv2d in the deployed ConvNeXt Tiny. The feature tensor
    # retains spatial dimensions before channel MLP / pooling / classification.
    layer = model.model.features[-1][-1].block[0]
    if not isinstance(layer, torch.nn.Conv2d):
        raise RuntimeError('The inspected ConvNeXt Grad-CAM layer is no longer a convolution.')
    target_name = next(name for name, module in model.named_modules() if module is layer)
    cam = GradCAM(model, target_layer=layer)
    try:
        with torch.enable_grad():
            values, logits, probabilities, target_classes = cam.generate_batch(tensor.to(device), timing=timing)
    finally:
        cam.remove_hooks()
        model.zero_grad(set_to_none=True)
    started = time.perf_counter_ns()
    args = [(index, path, output_dir, target_class, values[index], logits[index], probabilities[index], device, target_name)
            for index, (path, output_dir, target_class) in enumerate(
                zip(image_paths, output_dirs, target_classes, strict=True))]
    completed = ([future.result() for future in [executor.submit(_finish_prediction, *item) for item in args]]
                 if executor else [_finish_prediction(*item) for item in args])
    completed.sort(key=lambda item: item[0])
    results = [item[1] for item in completed]
    artifact_timings = [item[2] for item in completed]
    timing['grade_artifact_wall_ms'] = (time.perf_counter_ns() - started) / 1_000_000
    for key in ('gradcam_resize_ms', 'gradcam_png_writing_ms'):
        timing[key] = sum(item[key] for item in artifact_timings)
    return results


def predict(path, model, output_dir):
    return predict_batch([path], model, [output_dir])[0]
