from pathlib import Path
import logging
import torch
import torch.nn.functional as F
from PIL import Image
from models.grade.predict import preprocess_grade_image, GRADE_CLASS_MAPPING
from models.grade.gradcam import GradCAM
from utils.visualization import save_attention


def predict_batch(paths, model, output_dirs):
    if len(paths) != len(output_dirs):
        raise ValueError('One grading output directory is required per image.')
    if not paths:
        return []
    prepared = [preprocess_grade_image(path) for path in paths]
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
            values, logits, probabilities, target_classes = cam.generate_batch(tensor.to(device))
    finally:
        cam.remove_hooks()
        model.zero_grad(set_to_none=True)
    results = []
    for index, (path, output_dir, target_class) in enumerate(zip(image_paths, output_dirs, target_classes, strict=True)):
        with Image.open(path) as original:
            width, height = original.size
        resized = F.interpolate(values[index][None, None], size=(height, width), mode='bilinear',
                                align_corners=False)[0, 0].numpy()
        artifact = save_attention(resized, Path(output_dir) / 'grade_gradcam.png')
        results.append({'image_path': str(path), 'logits': logits[index].tolist(),
                        'probabilities': probabilities[index].tolist(), 'predicted_class': target_class,
                        'predicted_grade': GRADE_CLASS_MAPPING[target_class],
                        'confidence': float(probabilities[index, target_class]), 'device': str(device),
                        'gradcam_path': artifact['heatmap_path'],
                        'gradcam': {**artifact, 'target_class': target_class, 'target_layer': target_name,
                                    'method': 'Grad-CAM', 'objective': 'predicted-class pre-softmax logit',
                                    'note': 'Relative classifier attribution, not lesion probability or clinical certainty.'}})
    return results


def predict(path, model, output_dir):
    return predict_batch([path], model, [output_dir])[0]
