from pathlib import Path
import torch
import torch.nn.functional as F
from PIL import Image
from models.grade.predict import preprocess_grade_image, GRADE_CLASS_MAPPING
from models.grade.gradcam import GradCAM
from utils.visualization import save_attention


def predict(path, model, output_dir):
    path, tensor = preprocess_grade_image(path)
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
            values, logits, probabilities, target_class = cam.generate(tensor.to(device))
        with Image.open(path) as original:
            width, height = original.size
        values = F.interpolate(values[None, None], size=(height, width), mode='bilinear',
                               align_corners=False)[0, 0].numpy()
        artifact = save_attention(values, Path(output_dir) / 'grade_gradcam.png')
    finally:
        cam.remove_hooks()
        model.zero_grad(set_to_none=True)
    return {'image_path': str(path), 'logits': logits[0].tolist(),
            'probabilities': probabilities[0].tolist(), 'predicted_class': target_class,
            'predicted_grade': GRADE_CLASS_MAPPING[target_class],
            'confidence': float(probabilities[0, target_class]), 'device': str(device),
            'gradcam_path': artifact['heatmap_path'],
            'gradcam': {**artifact, 'target_class': target_class, 'target_layer': target_name,
                        'method': 'Grad-CAM', 'objective': 'predicted-class pre-softmax logit',
                        'note': 'Relative classifier attribution, not lesion probability or clinical certainty.'}}
