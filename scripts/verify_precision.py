"""Compare original FP32 checkpoints with BF16 TorchScript on local fundus images."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.nn import functional as F
from torchvision import transforms

from export_models import CHECKPOINTS, ROOT, SOURCE_BACKEND, GradeCam, load_model


SOURCE = SOURCE_BACKEND.parent
from dev_paths import validation_images
IMAGES = validation_images()[:4]
IMAGES = [path for path in IMAGES if path.is_file()]
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
GRADE_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
    ]
)


def lesion_input(image: Image.Image) -> torch.Tensor:
    resized = image.resize((768, 768), Image.Resampling.BILINEAR)
    tensor = torch.from_numpy(np.array(resized)).permute(2, 0, 1).float() / 255.0
    return ((tensor - MEAN) / STD).unsqueeze(0)


def normalized_cam(logits: torch.Tensor, activation: torch.Tensor, class_index: int) -> torch.Tensor:
    gradient = torch.autograd.grad(logits[:, class_index].float().sum(), activation)[0]
    weights = gradient.float().mean(dim=(2, 3), keepdim=True)
    cam = torch.relu((weights * activation.float()).sum(dim=1, keepdim=True))
    cam = F.interpolate(cam, size=(224, 224), mode="bilinear", align_corners=False)[:, 0]
    return (cam - cam.amin(dim=(1, 2), keepdim=True)) / (
        cam.amax(dim=(1, 2), keepdim=True) - cam.amin(dim=(1, 2), keepdim=True) + 1e-8
    )


def main() -> None:
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 CUDA is required")
    device = torch.device("cuda:0")
    lesion = load_model("lesion", device)
    grade = load_model("grade", device)
    lesion_script = torch.jit.load(str(CHECKPOINTS / "lesion_bf16_cam.pt"), map_location=device).eval()
    grade_script = torch.jit.load(str(CHECKPOINTS / "grade_bf16_cam.pt"), map_location=device).eval()
    records = []
    for path in IMAGES:
        with Image.open(path) as original:
            rgb = original.convert("RGB")
            grade_tensor = GRADE_TRANSFORM(rgb).unsqueeze(0).to(device)
            lesion_tensor = lesion_input(rgb).to(device)
        with torch.inference_mode():
            grade_fp32 = grade(grade_tensor).float()
            grade_bf16, _ = grade_script(grade_tensor.bfloat16())
            grade_prob_fp32 = torch.softmax(grade_fp32, dim=1)
            grade_prob_bf16 = torch.softmax(grade_bf16.float(), dim=1)
            lesion_fp32 = lesion(lesion_tensor).float()
            lesion_bf16, _ = lesion_script(lesion_tensor.bfloat16())
            lesion_prob_fp32 = torch.sigmoid(lesion_fp32)
            lesion_prob_bf16 = torch.sigmoid(lesion_bf16.float())
            mask_fp32 = lesion_prob_fp32 >= 0.5
            mask_bf16 = lesion_prob_bf16 >= 0.5
            intersections = (mask_fp32 & mask_bf16).sum(dim=(0, 2, 3)).cpu().tolist()
            unions = (mask_fp32 | mask_bf16).sum(dim=(0, 2, 3)).cpu().tolist()
            iou = [1.0 if union == 0 else intersection / union for intersection, union in zip(intersections, unions)]
            grade_difference = (grade_prob_fp32 - grade_prob_bf16).abs()
            lesion_difference = (lesion_prob_fp32 - lesion_prob_bf16).abs()
            record = {
                "image": str(path),
                "grade_reference": int(grade_prob_fp32.argmax(dim=1).item()),
                "grade_bf16": int(grade_prob_bf16.argmax(dim=1).item()),
                "grade_reference_confidence": float(grade_prob_fp32.max().item()),
                "grade_bf16_confidence": float(grade_prob_bf16.max().item()),
                "grade_max_probability_difference": float(grade_difference.max().item()),
                "grade_mean_probability_difference": float(grade_difference.mean().item()),
                "lesion_max_probability_difference": float(lesion_difference.max().item()),
                "lesion_mean_probability_difference": float(lesion_difference.mean().item()),
                "lesion_mask_iou_ma_he_ex_se": iou,
                "lesion_reference_pixels_ma_he_ex_se": mask_fp32.sum(dim=(0, 2, 3)).cpu().tolist(),
                "lesion_bf16_pixels_ma_he_ex_se": mask_bf16.sum(dim=(0, 2, 3)).cpu().tolist(),
            }
        # The output activation must stay connected to the selected class logit.
        index = record["grade_reference"]
        fp_logits, fp_activation = GradeCam(grade)(grade_tensor.requires_grad_(True))
        bf_logits, bf_activation = grade_script(grade_tensor.bfloat16().requires_grad_(True))
        fp_cam = normalized_cam(fp_logits, fp_activation, index)
        bf_cam = normalized_cam(bf_logits, bf_activation, index)
        record["grade_cam_mean_abs_difference"] = float((fp_cam - bf_cam).abs().mean().item())
        record["grade_cam_max_abs_difference"] = float((fp_cam - bf_cam).abs().max().item())
        records.append(record)
        print(json.dumps(record), flush=True)
    result = {
        "images": records,
        "grade_agreement": sum(item["grade_reference"] == item["grade_bf16"] for item in records),
        "image_count": len(records),
        "model_input": "RGB, original source resize/normalization; lesion 768x768, grade 224x224",
        "notes": "FP32 original checkpoints vs BF16 TorchScript CUDA. Lesion IoU uses 0.5 sigmoid threshold at 768x768; no connected-component postprocessing in this check.",
    }
    (ROOT / "scripts" / "precision_parity_report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "images"}, indent=2))


if __name__ == "__main__":
    main()
