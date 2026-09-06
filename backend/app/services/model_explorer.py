from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torch import nn

from backend.app.config import SESSION_ROOT
from backend.app.model_registry import INFERENCE_LOCK, MODEL_DEFINITIONS, registry
from backend.app.services.hook_manager import HookManager
from backend.app.services.image_store import media_url, read_manifest
from models.grade.gradcam import GradCAM
from models.grade.predict import preprocess_grade_image
from models.lesion.predict import preprocess_lesion_image


RESTORATION_PREVIEW_EDGE = 384


@dataclass(frozen=True)
class InternalSpec:
    id: str
    label: str
    module_path: str
    block_type: str
    channels_last: bool = False


@dataclass(frozen=True)
class BlockSpec:
    id: str
    label: str
    group: str
    module_path: str
    block_type: str
    description: str
    internals: tuple[InternalSpec, ...] = field(default_factory=tuple)


def _slug(value: str) -> str:
    return value.replace(".", "-").replace("_", "-")


def _internals(module: nn.Module, module_path: str, parent_id: str) -> tuple[InternalSpec, ...]:
    items: list[InternalSpec] = []
    candidates: list[tuple[str, nn.Module]] = []
    if module.__class__.__name__ == "NAFBlock":
        ordered = (
            ("norm1", "Layer normalization 1"),
            ("conv1", "Pointwise expansion"),
            ("conv2", "Depthwise convolution"),
            ("sg", "SimpleGate"),
            ("sca", "Simplified channel attention"),
            ("conv3", "Pointwise projection"),
            ("norm2", "Layer normalization 2"),
            ("conv4", "Feed-forward expansion"),
            ("conv5", "Feed-forward projection"),
        )
        for name, label in ordered:
            candidates.append((label, getattr(module, name)))
            path = f"{module_path}.{name}"
            items.append(InternalSpec(f"{parent_id}--{_slug(name)}", label, path, type(getattr(module, name)).__name__))
        return tuple(items)

    container = getattr(module, "block", None)
    if isinstance(container, nn.Module):
        convnext_labels = {
            0: "7×7 depthwise convolution",
            1: "Channel-last permutation",
            2: "LayerNorm",
            3: "Linear C→4C",
            4: "GELU",
            5: "Linear 4C→C",
            6: "Channel-first permutation",
        }
        for name, child in container.named_children():
            index = int(name) if name.isdigit() else -1
            label = convnext_labels[index] if module.__class__.__name__ == "CNBlock" and index in convnext_labels else f"{type(child).__name__} · operation {index + 1 if index >= 0 else name}"
            candidates.append((label, child))
            path = f"{module_path}.block.{name}"
            channels_last = module.__class__.__name__ == "CNBlock" and index in {1, 2, 3, 4, 5}
            items.append(InternalSpec(f"{parent_id}--block-{_slug(name)}", label, path, type(child).__name__, channels_last))
    elif hasattr(module, "layers") and isinstance(module.layers, nn.Module):
        for name, child in module.layers.named_children():
            label = f"{type(child).__name__} · operation {int(name) + 1 if name.isdigit() else name}"
            items.append(InternalSpec(f"{parent_id}--layers-{_slug(name)}", label, f"{module_path}.layers.{name}", type(child).__name__))
    return tuple(items)


def _quality_specs(service: Any) -> list[BlockSpec]:
    specs: list[BlockSpec] = []
    stem = service.feature_extractor[0][0]
    specs.append(BlockSpec("quality-stem", "Input stem", "Stem", "feature_extractor.0.0", type(stem).__name__, "Initial 3×3 convolution, normalization, and SiLU activation."))
    features = service.feature_extractor[0]
    for stage_index in range(1, 8):
        stage = features[stage_index]
        for block_index, module in enumerate(stage):
            block_id = f"quality-mbconv-{stage_index}-{block_index + 1}"
            path = f"feature_extractor.0.{stage_index}.{block_index}"
            specs.append(BlockSpec(block_id, f"MBConv stage {stage_index} · block {block_index + 1}", f"MBConv stage {stage_index}", path, type(module).__name__, "EfficientNet-B0 mobile inverted bottleneck block output.", _internals(module, path, block_id)))
    specs.extend(
        [
            BlockSpec("quality-head-conv", "Feature head convolution", "Feature extraction", "feature_extractor.0.8", type(features[8]).__name__, "Final EfficientNet convolution before global pooling."),
            BlockSpec("quality-pooling", "Global average pooling", "Classifier", "feature_extractor.1", "AdaptiveAvgPool2d", "Compresses each feature channel to one value."),
            BlockSpec("quality-hidden", "Calibrated MLP hidden layer", "Classifier", "classifier.network.0", "Linear", "Maps the 1,280-dimensional feature vector to 128 hidden units."),
            BlockSpec("quality-logits", "Quality logits", "Classifier", "classifier.network.3", "Linear", "Produces the three pre-temperature quality scores."),
        ]
    )
    return specs


def _restoration_specs(model: nn.Module) -> list[BlockSpec]:
    specs = [BlockSpec("nafnet-intro", "Intro convolution", "Input projection", "intro", "Conv2d", "Projects RGB input into the width-32 NAFNet feature space.")]
    for level, encoder in enumerate(model.encoders, 1):
        for index, block in enumerate(encoder, 1):
            block_id = f"nafnet-encoder-{level}-block-{index}"
            path = f"encoders.{level - 1}.{index - 1}"
            specs.append(BlockSpec(block_id, f"Encoder level {level} · NAFBlock {index}", f"Encoder level {level}", path, "NAFBlock", "Residual NAFBlock at the current encoder resolution.", _internals(block, path, block_id)))
        specs.append(BlockSpec(f"nafnet-down-{level}", f"Downsample {level}", f"Encoder level {level}", f"downs.{level - 1}", "Stride-2 Conv2d", "Halves spatial resolution and doubles channel width."))
    for index, block in enumerate(model.middle_blks, 1):
        block_id = f"nafnet-middle-block-{index}"
        path = f"middle_blks.{index - 1}"
        specs.append(BlockSpec(block_id, f"Bottleneck · NAFBlock {index}", "Middle / bottleneck", path, "NAFBlock", "Deepest NAFBlock at the smallest feature resolution.", _internals(block, path, block_id)))
    for level, (up, decoder) in enumerate(zip(model.ups, model.decoders), 1):
        specs.append(BlockSpec(f"nafnet-up-{level}", f"Upsample {level}", f"Decoder level {level}", f"ups.{level - 1}", type(up).__name__, "Pointwise convolution followed by PixelShuffle upsampling."))
        for index, block in enumerate(decoder, 1):
            block_id = f"nafnet-decoder-{level}-block-{index}"
            path = f"decoders.{level - 1}.{index - 1}"
            specs.append(BlockSpec(block_id, f"Decoder level {level} · NAFBlock {index}", f"Decoder level {level}", path, "NAFBlock", "NAFBlock after the matching encoder skip addition.", _internals(block, path, block_id)))
    specs.extend(
        [
            BlockSpec("nafnet-ending", "Ending convolution", "Reconstruction", "ending", "Conv2d", "Projects restored features back to three RGB channels."),
            BlockSpec("nafnet-output", "Residual reconstruction / final output", "Reconstruction", "__model__", "Residual output", "Adds the padded input to the predicted residual and crops to source dimensions."),
        ]
    )
    return specs


def _grade_specs(model: nn.Module) -> list[BlockSpec]:
    features = model.model.features
    specs = [BlockSpec("grade-stem", "ConvNeXt stem", "Stem", "model.features.0", type(features[0]).__name__, "4×4 stride-4 convolution followed by channel-first layer normalization.")]
    stage_slots = (1, 3, 5, 7)
    for stage_number, slot in enumerate(stage_slots, 1):
        stage = features[slot]
        for index, block in enumerate(stage, 1):
            block_id = f"grade-stage-{stage_number}-block-{index}"
            path = f"model.features.{slot}.{index - 1}"
            specs.append(BlockSpec(block_id, f"ConvNeXt stage {stage_number} · block {index}", f"ConvNeXt stage {stage_number}", path, type(block).__name__, "Residual ConvNeXt block with depthwise convolution and channel MLP.", _internals(block, path, block_id)))
        if stage_number < 4:
            down_slot = slot + 1
            specs.append(BlockSpec(f"grade-downsample-{stage_number}", f"Downsample after stage {stage_number}", f"ConvNeXt stage {stage_number}", f"model.features.{down_slot}", type(features[down_slot]).__name__, "Layer normalization and stride-2 convolution."))
    specs.extend(
        [
            BlockSpec("grade-pooling", "Global pooling", "Classifier", "model.avgpool", "AdaptiveAvgPool2d", "Reduces the final spatial grid to one value per channel."),
            BlockSpec("grade-layernorm", "Classifier LayerNorm", "Classifier", "model.classifier.0", type(model.model.classifier[0]).__name__, "Normalizes the pooled 768-channel representation."),
            BlockSpec("grade-logits", "Five-class classifier", "Classifier", "model.classifier.2", "Linear", "Produces logits for DR grades 0 through 4."),
        ]
    )
    return specs


def _lesion_specs(model: nn.Module) -> list[BlockSpec]:
    specs: list[BlockSpec] = []
    for index, module in enumerate(model.encoder):
        if index == 0:
            label, group = "MobileNet stem", "Encoder stem"
        elif index == 16:
            label, group = "MobileNet final feature convolution", "Encoder head"
        else:
            label, group = f"Inverted residual block {index}", "MobileNetV3 encoder"
        block_id = f"lesion-encoder-{index}"
        path = f"encoder.{index}"
        specs.append(BlockSpec(block_id, label, group, path, type(module).__name__, "Real MobileNetV3-Large encoder output; SE is listed only where present.", _internals(module, path, block_id)))
    for index, module in enumerate(model.projections):
        specs.append(BlockSpec(f"lesion-projection-{index + 1}", f"Encoder projection {index + 1}", "Encoder projections", f"projections.{index}", "1×1 Conv2d", "Maps a selected encoder feature into the UNet++ decoder width."))
    for name in ("conv0_1", "conv1_1", "conv2_1", "conv0_2", "conv1_2", "conv0_3"):
        module = getattr(model, name)
        block_id = f"lesion-{name.replace('_', '-')}"
        specs.append(BlockSpec(block_id, f"UNet++ decoder node {name.replace('_', ',')}", "UNet++ nested decoder", name, type(module).__name__, "Nested decoder feature built from projected encoder and earlier decoder nodes.", _internals(module, name, block_id)))
    specs.extend(
        [
            BlockSpec("lesion-output-head", "Four-channel segmentation head", "Segmentation output", "output", "1×1 Conv2d", "Produces logits for MA, HE, EX, and SE channels."),
            BlockSpec("lesion-logits", "Resized segmentation logits", "Segmentation output", "__model__", "Bilinear output", "Four-channel logits resized to the 768×768 model input space."),
        ]
    )
    return specs


def _model_and_specs(model_id: str) -> tuple[Any, list[BlockSpec]]:
    model = registry.get(model_id)
    if model_id == "quality":
        return model, _quality_specs(model)
    if model_id == "restoration":
        return model, _restoration_specs(model)
    if model_id == "grade":
        return model, _grade_specs(model)
    if model_id == "lesion":
        return model, _lesion_specs(model)
    raise KeyError(model_id)


def _parameter_count(model_id: str, model: Any) -> int:
    if model_id == "quality":
        modules = (model.feature_extractor, model.classifier)
        return sum(parameter.numel() for module in modules for parameter in module.parameters())
    return sum(parameter.numel() for parameter in model.parameters())


def architecture(model_id: str) -> dict[str, Any]:
    model, specs = _model_and_specs(model_id)
    input_labels = {
        "quality": "3 × 224 × 224",
        "restoration": f"3 × H × W · visualization preview ≤ {RESTORATION_PREVIEW_EDGE}px",
        "grade": "3 × 224 × 224",
        "lesion": "3 × 768 × 768",
    }
    return {
        "id": model_id,
        "label": MODEL_DEFINITIONS[model_id]["label"],
        "model_name": MODEL_DEFINITIONS[model_id]["architecture"],
        "device": str(registry.device),
        "input": input_labels[model_id],
        "parameter_count": _parameter_count(model_id, model),
        "block_count": len(specs),
        "blocks": [
            {
                "id": spec.id,
                "label": spec.label,
                "group": spec.group,
                "block_type": spec.block_type,
                "description": spec.description,
                "internals": [
                    {"id": item.id, "label": item.label, "block_type": item.block_type}
                    for item in spec.internals
                ],
            }
            for spec in specs
        ],
    }


def _session_path(session_id: str, url: str) -> Path:
    prefix = f"/media/{session_id}/"
    if not url.startswith(prefix):
        raise ValueError("Session manifest contains an invalid media path")
    root = (SESSION_ROOT / session_id).resolve()
    path = (root / url.removeprefix(prefix)).resolve()
    path.relative_to(root)
    if not path.is_file():
        raise FileNotFoundError("Analysis image is no longer available")
    return path


def _selected_image(session_id: str, model_id: str, manifest: dict[str, Any]) -> Path:
    if model_id in {"grade", "lesion"} and manifest.get("restoration"):
        return _session_path(session_id, manifest["restoration"]["output_image_url"])
    return _session_path(session_id, manifest["input_image_url"])


def _resolve_module(model_id: str, model: Any, module_path: str) -> nn.Module:
    if module_path == "__model__":
        if model_id == "quality":
            raise ValueError("Quality service has no root module hook")
        return model
    if model_id == "quality":
        root_name, relative = module_path.split(".", 1)
        root = getattr(model, root_name)
        return root.get_submodule(relative)
    return model.get_submodule(module_path)


def _prepare_input(model_id: str, path: Path, model: Any) -> torch.Tensor:
    if model_id == "quality":
        with Image.open(path) as image:
            return model.transform(image.convert("RGB")).unsqueeze(0).to(model.device)
    if model_id == "restoration":
        with Image.open(path) as image:
            image = image.convert("RGB")
            if max(image.size) > RESTORATION_PREVIEW_EDGE:
                image.thumbnail((RESTORATION_PREVIEW_EDGE, RESTORATION_PREVIEW_EDGE), Image.Resampling.LANCZOS)
            pixels = np.asarray(image, dtype=np.float32) / 255.0
        return torch.from_numpy(np.ascontiguousarray(pixels.transpose(2, 0, 1))).unsqueeze(0).to(next(model.parameters()).device)
    if model_id == "grade":
        _, tensor = preprocess_grade_image(path)
        return tensor.to(next(model.parameters()).device)
    if model_id == "lesion":
        _, tensor = preprocess_lesion_image(path)
        return tensor.to(next(model.parameters()).device)
    raise KeyError(model_id)


def _forward(model_id: str, model: Any, tensor: torch.Tensor) -> torch.Tensor:
    if model_id == "quality":
        features = model.feature_extractor(tensor).flatten(start_dim=1)
        return model.classifier(features)
    return model(tensor)


def _activation_map(tensor: torch.Tensor, *, energy: bool, channels_last: bool = False) -> tuple[np.ndarray, bool, int]:
    value = tensor.detach().float().cpu()
    if value.ndim >= 4:
        value = value[0]
    if value.ndim == 3:
        if channels_last:
            value = value.permute(2, 0, 1)
        channels = int(value.shape[0])
        if energy:
            plane = value.abs().mean(dim=0)
        else:
            scores = value.flatten(1).abs().mean(dim=1)
            plane = value[int(scores.argmax().item())]
        return plane.numpy(), True, channels
    flat = value.flatten()
    return (flat.abs() if energy else flat).numpy()[None, :], False, int(flat.numel())


def _normalize(array: np.ndarray) -> np.ndarray:
    values = np.nan_to_num(array.astype(np.float32), nan=0.0, posinf=0.0, neginf=0.0)
    low, high = np.percentile(values, (1, 99))
    if high - low <= 1e-12:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _save_grayscale(array: np.ndarray, path: Path) -> None:
    pixels = np.rint(_normalize(array) * 255).astype(np.uint8)
    image = Image.fromarray(pixels, mode="L")
    if image.height == 1:
        image = image.resize((max(320, image.width), 72), Image.Resampling.NEAREST)
    image.save(path)


def _colorize(array: np.ndarray) -> np.ndarray:
    normalized = _normalize(array)
    stops = np.array([0.0, 0.35, 0.72, 1.0])
    colors = np.array([[7, 26, 22], [20, 91, 74], [213, 118, 32], [255, 239, 181]], dtype=np.float32)
    rgb = np.empty((*normalized.shape, 3), dtype=np.uint8)
    for channel in range(3):
        rgb[..., channel] = np.interp(normalized, stops, colors[:, channel]).astype(np.uint8)
    return rgb


def _save_heatmap(array: np.ndarray, path: Path) -> None:
    image = Image.fromarray(_colorize(array), mode="RGB")
    if image.height == 1:
        image = image.resize((max(320, image.width), 72), Image.Resampling.NEAREST)
    image.save(path)


def _lookup_spec(model_id: str, model: Any, block_id: str) -> tuple[BlockSpec, str, str, str, bool]:
    _, specs = _model_and_specs(model_id)
    for spec in specs:
        if spec.id == block_id:
            return spec, spec.module_path, spec.label, spec.block_type, False
        for internal in spec.internals:
            if internal.id == block_id:
                return spec, internal.module_path, internal.label, internal.block_type, internal.channels_last
    raise KeyError(block_id)


def capture_block(session_id: str, model_id: str, block_id: str) -> dict[str, Any]:
    manifest = read_manifest(session_id)
    model, _ = _model_and_specs(model_id)
    parent, module_path, label, block_type, channels_last = _lookup_spec(model_id, model, block_id)
    output_dir = SESSION_ROOT / session_id / "explorer" / model_id / block_id
    metadata_path = output_dir / "metadata.json"
    if metadata_path.is_file():
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = _selected_image(session_id, model_id, manifest)
    tensor = _prepare_input(model_id, image_path, model)
    module = _resolve_module(model_id, model, module_path)
    with INFERENCE_LOCK, HookManager() as hooks:
        hooks.register_block("selected", module)
        with torch.inference_mode():
            _forward(model_id, model, tensor)
        activation = hooks.get_activation("selected")

    feature, spatial, channels = _activation_map(activation, energy=False, channels_last=channels_last)
    energy, _energy_spatial, _ = _activation_map(activation, energy=True, channels_last=channels_last)
    feature_path = output_dir / "feature.png"
    heatmap_path = output_dir / "activation-energy.png"
    _save_grayscale(feature, feature_path)
    _save_heatmap(energy, heatmap_path)
    shape = [int(value) for value in activation.shape]
    if channels_last and len(shape) == 4:
        height, width = int(shape[1]), int(shape[2])
    else:
        height = int(shape[-2]) if len(shape) >= 3 else 1
        width = int(shape[-1]) if len(shape) >= 2 else shape[0]
    response = {
        "id": block_id,
        "parent_id": parent.id,
        "label": label,
        "block_type": block_type,
        "tensor_shape": shape,
        "channels": channels,
        "height": height,
        "width": width,
        "spatial": spatial,
        "feature_map_url": media_url(feature_path, session_id),
        "activation_heatmap_url": media_url(heatmap_path, session_id),
        "feature_method": "Strongest representative channel by mean absolute response, percentile-normalized to grayscale.",
        "heatmap_method": "Channel mean absolute activation, percentile-normalized. This is activation energy, not Grad-CAM.",
        "input_shape": [int(value) for value in tensor.shape],
    }
    metadata_path.write_text(json.dumps(response, indent=2), encoding="utf-8")
    return response


def grade_gradcam(session_id: str, target_class: int) -> dict[str, Any]:
    if target_class not in range(5):
        raise ValueError("target_class must be between 0 and 4")
    manifest = read_manifest(session_id)
    model = registry.get("grade")
    image_path = _selected_image(session_id, "grade", manifest)
    output_dir = SESSION_ROOT / session_id / "explorer" / "grade" / "gradcam"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"class-{target_class}.png"
    metadata_path = output_dir / f"class-{target_class}.json"
    if metadata_path.is_file() and output_path.is_file():
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    _, tensor = preprocess_grade_image(image_path)
    tensor = tensor.to(next(model.parameters()).device)
    cam_engine = GradCAM(model)
    try:
        with INFERENCE_LOCK, torch.enable_grad():
            cam, _logits, probabilities, actual_target = cam_engine.generate(tensor, target_class)
    finally:
        cam_engine.remove_hooks()
    with Image.open(image_path) as image:
        source = np.asarray(image.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR), dtype=np.float32)
    heat = _colorize(cam.numpy()).astype(np.float32)
    overlay = np.clip(source * 0.56 + heat * 0.44, 0, 255).astype(np.uint8)
    Image.fromarray(overlay, mode="RGB").save(output_path)
    response = {
        "target_class": int(actual_target),
        "probabilities": [float(value) for value in probabilities[0].tolist()],
        "gradcam_url": media_url(output_path, session_id),
        "method": "Class-conditioned Grad-CAM from the final ConvNeXt feature block.",
    }
    metadata_path.write_text(json.dumps(response, indent=2), encoding="utf-8")
    return response
