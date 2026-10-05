"""Offline exports from the untouched RetinaGram PyTorch checkpoints.

Run with the CUDA-enabled development Python. Outputs are written to src/checkpoints in the repository.
"""

from __future__ import annotations

import argparse
import json
import sys
sys.dont_write_bytecode = True
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


from dev_paths import ROOT, SOURCE_BACKEND, CHECKPOINTS, source_checkpoint
sys.path.insert(0, str(SOURCE_BACKEND))


class LesionCam(nn.Module):
    """Original lesion forward with the existing CAM target made an output."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, image: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        model = self.model
        input_size = image.shape[2:]
        features = []
        x = image
        for index, layer in enumerate(model.encoder):
            x = layer(x)
            if index in model.feature_indices:
                features.append(model.projections[len(features)](x))
        x0_0, x1_0, x2_0, x3_0 = features
        x0_1 = model.conv0_1(torch.cat([x0_0, model.upsample(x1_0, x0_0)], dim=1))
        x1_1 = model.conv1_1(torch.cat([x1_0, model.upsample(x2_0, x1_0)], dim=1))
        x2_1 = model.conv2_1(torch.cat([x2_0, model.upsample(x3_0, x2_0)], dim=1))
        x0_2 = model.conv0_2(torch.cat([x0_0, x0_1, model.upsample(x1_1, x0_0)], dim=1))
        x1_2 = model.conv1_2(torch.cat([x1_0, x1_1, model.upsample(x2_1, x1_0)], dim=1))
        final_input = torch.cat([x0_0, x0_1, x0_2, model.upsample(x1_2, x0_0)], dim=1)
        block = model.conv0_3.layers
        activation = block[3](block[2](block[1](block[0](final_input))))
        x = block[5](block[4](activation))
        logits = model.output(x)
        return F.interpolate(logits, size=input_size, mode="bilinear", align_corners=False), activation


class GradeCam(nn.Module):
    """Original ConvNeXt forward with features.7.2.block.0 exposed."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model

    def forward(self, image: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        backbone = self.model.model
        x = image
        for stage in backbone.features[:7]:
            x = stage(x)
        stage = backbone.features[7]
        x = stage[1](stage[0](x))
        residual = x
        final_block = stage[2]
        activation = final_block.block[0](x)
        tail = final_block.block[1:](activation)
        x = residual + final_block.stochastic_depth(final_block.layer_scale * tail)
        logits = backbone.classifier(backbone.avgpool(x))
        return logits, activation


def load_model(name: str, device: torch.device) -> nn.Module:
    if name == "lesion":
        from models.lesion.model import load_lesion_model

        model, _ = load_lesion_model(source_checkpoint("epoch_018_best_dice.pth"), device)
    elif name == "grade":
        from models.grade.model import load_grade_model

        model = load_grade_model(source_checkpoint("convnext_tiny.pth"), device)
    else:
        raise ValueError(name)
    return model.eval()


def export_cam(name: str) -> dict:
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 CUDA support is required for this export and verification")
    device = torch.device("cuda:0")
    model = load_model(name, device)
    size = 768 if name == "lesion" else 224
    wrapper_type = LesionCam if name == "lesion" else GradeCam
    original = torch.rand(1, 3, size, size, device=device)
    with torch.inference_mode():
        fp32_logits = model(original).float()
        fp32_wrapper_logits, _ = wrapper_type(model)(original)
        wrapper_error = (fp32_logits - fp32_wrapper_logits.float()).abs().max().item()
    if wrapper_error > 1e-4:
        raise RuntimeError(f"{name} CAM wrapper changes FP32 logits: {wrapper_error}")

    wrapper = wrapper_type(model.to(dtype=torch.bfloat16)).eval()
    sample = original.to(dtype=torch.bfloat16)
    output = CHECKPOINTS / f"{name}_bf16_cam.pt"
    traced = torch.jit.trace(wrapper, sample, strict=False, check_trace=False)
    traced.save(str(output))
    del traced
    scripted = torch.jit.load(str(output), map_location=device).eval()
    with torch.enable_grad():
        logits, activation = scripted(sample)
        gradient = torch.autograd.grad(logits.float().sum(), activation)[0]
    if not torch.isfinite(logits).all() or not torch.isfinite(gradient).all():
        raise RuntimeError(f"{name} TorchScript produced non-finite logits or CAM gradient")
    with torch.inference_mode():
        reference_bf16 = model(sample).float()
        script_error = (reference_bf16 - logits.float()).abs().max().item()
        fp32_error = (fp32_logits - logits.float()).abs()
        result = {
            "artifact": str(output),
            "bytes": output.stat().st_size,
            "input_shape": list(sample.shape),
            "input_dtype": str(sample.dtype),
            "logits_shape": list(logits.shape),
            "activation_shape": list(activation.shape),
            "wrapper_fp32_max_abs_error": wrapper_error,
            "torchscript_vs_bf16_max_abs_error": script_error,
            "bf16_vs_fp32_max_abs_error": fp32_error.max().item(),
            "bf16_vs_fp32_mean_abs_error": fp32_error.mean().item(),
            "cam_gradient_finite": bool(torch.isfinite(gradient).all().item()),
            "cam_gradient_nonzero": bool((gradient != 0).any().item()),
        }
    if script_error > 0.01:
        raise RuntimeError(f"{name} TorchScript mismatch: {script_error}")
    print(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=("lesion", "grade"))
    args = parser.parse_args()
    export_cam(args.model)


if __name__ == "__main__":
    main()
