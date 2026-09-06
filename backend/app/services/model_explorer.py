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
    features = service.feature_extractor[0]
    specs: list[BlockSpec] = [
        BlockSpec("quality-input", "Input", "Input", "__input__", "RGB fundus image", "The validated image after EfficientNet preprocessing."),
        BlockSpec("quality-stem", "Stem", "Feature extraction", "feature_extractor.0.0", type(features[0]).__name__, "Initial 3×3 convolution, normalization, and SiLU activation."),
    ]
    for stage_index in range(1, 8):
        stage = features[stage_index]
        internals = tuple(
            InternalSpec(
                f"quality-stage-{stage_index}--block-{block_index + 1}",
                f"MBConv block {block_index + 1}",
                f"feature_extractor.0.{stage_index}.{block_index}",
                type(module).__name__,
            )
            for block_index, module in enumerate(stage)
        )
        specs.append(BlockSpec(
            f"quality-stage-{stage_index}",
            f"Stage {stage_index}",
            "EfficientNet stages",
            f"feature_extractor.0.{stage_index}",
            f"EfficientNet MBConv stage · {len(stage)} block{'s' if len(stage) != 1 else ''}",
            "Meaningful EfficientNet-B0 stage output after its complete MBConv group.",
            internals,
        ))
    specs.extend(
        [
            BlockSpec("quality-head-conv", "Feature Head", "Feature extraction", "feature_extractor.0.8", type(features[8]).__name__, "Final EfficientNet convolution before global pooling."),
            BlockSpec("quality-pooling", "Global Pool", "Prediction", "feature_extractor.1", "AdaptiveAvgPool2d", "Compresses each feature channel to one value."),
            BlockSpec("quality-logits", "Quality Head", "Prediction", "classifier", "Calibrated MLP", "Maps the pooled representation to Good, Usable, and Reject logits.", (
                InternalSpec("quality-hidden", "128-unit hidden layer", "classifier.network.0", "Linear"),
                InternalSpec("quality-classifier", "Three-class logits", "classifier.network.3", "Linear"),
            )),
        ]
    )
    return specs


def _restoration_specs(model: nn.Module) -> list[BlockSpec]:
    specs = [
        BlockSpec("nafnet-input", "Input", "Input", "__input__", "RGB fundus image", "The selected source image before restoration."),
        BlockSpec("nafnet-intro", "Intro", "Input projection", "intro", "Conv2d", "Projects RGB input into the width-32 NAFNet feature space."),
    ]
    for level, encoder in enumerate(model.encoders, 1):
        path = f"encoders.{level - 1}"
        internals = tuple(InternalSpec(f"nafnet-encoder-{level}--block-{index}", f"NAFBlock {index}", f"{path}.{index - 1}", "NAFBlock") for index, _ in enumerate(encoder, 1))
        specs.append(BlockSpec(f"nafnet-encoder-{level}", f"Encoder Stage {level}", "Encoder", path, f"NAFNet encoder · {len(encoder)} NAFBlocks", "Complete encoder stage output before stride-2 downsampling.", internals))
    specs.append(BlockSpec("nafnet-bottleneck", "Bottleneck", "Bottleneck", "middle_blks", f"NAFNet bottleneck · {len(model.middle_blks)} NAFBlocks", "Deepest representation at the smallest spatial resolution.", tuple(InternalSpec(f"nafnet-bottleneck--block-{index}", f"NAFBlock {index}", f"middle_blks.{index - 1}", "NAFBlock") for index, _ in enumerate(model.middle_blks, 1))))
    for level, (up, decoder) in enumerate(zip(model.ups, model.decoders), 1):
        stage_number = len(model.decoders) - level + 1
        path = f"decoders.{level - 1}"
        internals = (
            InternalSpec(f"nafnet-decoder-{stage_number}--upsample", "PixelShuffle upsample", f"ups.{level - 1}", type(up).__name__),
            *(InternalSpec(f"nafnet-decoder-{stage_number}--block-{index}", f"NAFBlock {index}", f"{path}.{index - 1}", "NAFBlock") for index, _ in enumerate(decoder, 1)),
        )
        specs.append(BlockSpec(f"nafnet-decoder-{stage_number}", f"Decoder Stage {stage_number}", "Decoder", path, f"NAFNet decoder · {len(decoder)} NAFBlocks", "Complete decoder stage after its matched encoder skip addition.", internals))
    specs.extend(
        [
            BlockSpec("nafnet-ending", "Ending", "Reconstruction", "ending", "Conv2d", "Projects restored features back to three RGB channels."),
            BlockSpec("nafnet-output", "Restored Output", "Reconstruction", "__model__", "Residual reconstruction", "Adds the padded input to the predicted residual and crops to source dimensions."),
        ]
    )
    return specs


def _grade_specs(model: nn.Module) -> list[BlockSpec]:
    features = model.model.features
    specs = [
        BlockSpec("grade-input", "Input", "Input", "__input__", "RGB fundus image", "The selected 224×224 classifier input."),
        BlockSpec("grade-stem", "Stem", "Feature extraction", "model.features.0", type(features[0]).__name__, "4×4 stride-4 convolution followed by channel-first layer normalization."),
    ]
    stage_slots = (1, 3, 5, 7)
    for stage_number, slot in enumerate(stage_slots, 1):
        stage = features[slot]
        path = f"model.features.{slot}"
        internals = tuple(InternalSpec(f"grade-stage-{stage_number}--block-{index}", f"ConvNeXt block {index}", f"{path}.{index - 1}", type(block).__name__) for index, block in enumerate(stage, 1))
        specs.append(BlockSpec(f"grade-stage-{stage_number}", f"Stage {stage_number}", "ConvNeXt stages", path, f"ConvNeXt stage · {len(stage)} blocks", "Complete residual ConvNeXt stage output.", internals))
    specs.extend(
        [
            BlockSpec("grade-pooling", "Global Pool", "Prediction", "model.avgpool", "AdaptiveAvgPool2d", "Reduces the final spatial grid to one value per channel."),
            BlockSpec("grade-logits", "Classifier", "Prediction", "model.classifier", "Five-class classifier", "Normalizes the pooled representation and produces logits for DR grades 0 through 4.", (
                InternalSpec("grade-layernorm", "Classifier LayerNorm", "model.classifier.0", type(model.model.classifier[0]).__name__, True),
                InternalSpec("grade-linear", "Five-class linear head", "model.classifier.2", "Linear"),
            )),
        ]
    )
    return specs


def _lesion_specs(model: nn.Module) -> list[BlockSpec]:
    feature_indices = tuple(model.feature_indices)
    specs: list[BlockSpec] = [
        BlockSpec("lesion-input", "Input", "Input", "__input__", "RGB fundus image", "The selected 768×768 segmentation input."),
        BlockSpec("lesion-stem", "Stem", "MobileNetV3 encoder", "encoder.0", type(model.encoder[0]).__name__, "MobileNetV3-Large input convolution."),
    ]
    previous = 1
    for stage_number, feature_index in enumerate(feature_indices, 1):
        internals = tuple(InternalSpec(f"lesion-encoder-{stage_number}--block-{index}", f"Inverted residual block {index}", f"encoder.{index}", type(model.encoder[index]).__name__) for index in range(previous, feature_index + 1))
        specs.append(BlockSpec(f"lesion-encoder-{stage_number}", f"Encoder Stage {stage_number}", "MobileNetV3 encoder", f"encoder.{feature_index}", f"MobileNetV3 stage · through block {feature_index}", "Actual encoder feature selected by the UNet++ decoder.", internals))
        previous = feature_index + 1
    specs.extend([
        BlockSpec("lesion-bottleneck", "Bottleneck", "UNet++ bridge", "projections.3", "1×1 encoder projection", "Projects the deepest 960-channel MobileNetV3 feature to the decoder width."),
        BlockSpec("lesion-decoder-1", "UNet++ Decoder Stage 1", "UNet++ decoder", "conv2_1", type(model.conv2_1).__name__, "Deep decoder fusion of encoder stages 3 and 4.", tuple(InternalSpec(f"lesion-decoder-1--{name}", f"Nested node {name.replace('_', ',')}", name, type(getattr(model, name)).__name__) for name in ("conv0_1", "conv1_1", "conv2_1"))),
        BlockSpec("lesion-decoder-2", "Decoder Stage 2", "UNet++ decoder", "conv1_2", type(model.conv1_2).__name__, "Second nested fusion combining prior decoder and encoder features.", tuple(InternalSpec(f"lesion-decoder-2--{name}", f"Nested node {name.replace('_', ',')}", name, type(getattr(model, name)).__name__) for name in ("conv0_2", "conv1_2"))),
        BlockSpec("lesion-decoder-3", "Decoder Stage 3", "UNet++ decoder", "conv0_3", type(model.conv0_3).__name__, "Final full-resolution nested decoder feature before segmentation logits."),
        BlockSpec("lesion-output-head", "Segmentation Head", "Segmentation output", "__model__", "Four-channel bilinear output", "Produces resized logits for the verified MA, HE, EX, and SE channels."),
    ])
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
        if "." not in module_path:
            return getattr(model, module_path)
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


def _activation_map(tensor: torch.Tensor, *, energy: bool, channels_last: bool = False, channel: int | None = None) -> tuple[np.ndarray, bool, int, int | None]:
    value = tensor.detach().float().cpu()
    if value.ndim >= 4:
        value = value[0]
    if value.ndim == 3:
        if channels_last:
            value = value.permute(2, 0, 1)
        channels = int(value.shape[0])
        if energy:
            plane = value.abs().mean(dim=0)
            selected_channel = None
        else:
            scores = value.flatten(1).abs().mean(dim=1)
            selected_channel = int(scores.argmax().item()) if channel is None else channel
            if selected_channel < 0 or selected_channel >= channels:
                raise ValueError(f"channel must be between 0 and {channels - 1}")
            plane = value[selected_channel]
        return plane.numpy(), True, channels, selected_channel
    flat = value.flatten()
    return (flat.abs() if energy else flat).numpy()[None, :], False, int(flat.numel()), None


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


def _save_feature_rgb(array: np.ndarray, path: Path) -> None:
    """Render one deterministic feature channel with RetinaGram's RGB ramp."""
    Image.fromarray(_colorize(array), mode="RGB").save(path)


def _save_thumbnail(source: Path, destination: Path, edge: int = 320) -> None:
    with Image.open(source) as image:
        thumbnail = image.copy()
        thumbnail.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        thumbnail.save(destination, optimize=True)


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


def _input_activation(model_id: str, image_path: Path, tensor: torch.Tensor) -> torch.Tensor:
    """Return a spatial CPU tensor for the validated model input."""
    if model_id == "restoration":
        return tensor.detach().float().cpu()
    with Image.open(image_path) as image:
        size = (int(tensor.shape[-1]), int(tensor.shape[-2]))
        pixels = np.asarray(image.convert("RGB").resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 255.0
    return torch.from_numpy(np.ascontiguousarray(pixels.transpose(2, 0, 1))).unsqueeze(0)


def _render_visualization(
    session_id: str,
    model_id: str,
    spec: BlockSpec,
    activation: torch.Tensor,
    input_shape: list[int],
    *,
    channels_last: bool = False,
    channel: int | None = None,
) -> dict[str, Any]:
    suffix = "auto" if channel is None else f"ch-{channel}"
    output_dir = SESSION_ROOT / session_id / "explorer" / model_id / spec.id / suffix
    metadata_path = output_dir / "metadata.json"
    if metadata_path.is_file():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    feature, spatial, channels, channel_index = _activation_map(activation, energy=False, channels_last=channels_last, channel=channel)
    energy, _energy_spatial, _, _ = _activation_map(activation, energy=True, channels_last=channels_last)
    feature_path = output_dir / "feature.png"
    activation_path = output_dir / "activation.png"
    feature_thumb = output_dir / "feature-thumb.png"
    activation_thumb = output_dir / "activation-thumb.png"
    _save_feature_rgb(feature, feature_path)
    _save_grayscale(energy, activation_path)
    _save_thumbnail(feature_path, feature_thumb)
    _save_thumbnail(activation_path, activation_thumb)
    shape = [int(value) for value in activation.shape]
    if channels_last and len(shape) == 4:
        height, width = int(shape[1]), int(shape[2])
    else:
        height = int(shape[-2]) if len(shape) >= 3 else 1
        width = int(shape[-1]) if len(shape) >= 2 else shape[0]
    stem = spec.id.replace("-", "_")
    response = {
        "id": spec.id,
        "parent_id": spec.id,
        "label": spec.label,
        "block_type": spec.block_type,
        "tensor_shape": shape,
        "channels": channels,
        "height": height,
        "width": width,
        "spatial": spatial,
        "feature_map_url": media_url(feature_path, session_id),
        "activation_heatmap_url": media_url(activation_path, session_id),
        "feature_thumbnail_url": media_url(feature_thumb, session_id),
        "activation_thumbnail_url": media_url(activation_thumb, session_id),
        "feature_download_name": f"{stem}_feature_ch{channel_index}.png" if channel_index is not None else f"{stem}_feature.png",
        "activation_download_name": f"{stem}_activation.png",
        "channel_index": channel_index,
        "feature_method": "Deterministic strongest channel by mean absolute response, percentile-normalized and rendered with a fixed RetinaGram RGB ramp." if channel is None else f"Channel {channel}, percentile-normalized and rendered with a fixed RetinaGram RGB ramp.",
        "heatmap_method": "Channel mean absolute activation, percentile-normalized to grayscale. This is activation energy, not Grad-CAM.",
        "input_shape": input_shape,
    }
    metadata_path.write_text(json.dumps(response, indent=2), encoding="utf-8")
    return response


def capture_stages(session_id: str, model_id: str) -> list[dict[str, Any]]:
    """Capture every meaningful architectural stage in one inference pass."""
    manifest = read_manifest(session_id)
    model, specs = _model_and_specs(model_id)
    cached: list[dict[str, Any]] = []
    cache_complete = True
    for spec in specs:
        metadata = SESSION_ROOT / session_id / "explorer" / model_id / spec.id / "auto" / "metadata.json"
        if not metadata.is_file():
            cache_complete = False
            break
        cached.append(json.loads(metadata.read_text(encoding="utf-8")))
    if cache_complete:
        return cached

    image_path = _selected_image(session_id, model_id, manifest)
    tensor = _prepare_input(model_id, image_path, model)
    activations: dict[str, torch.Tensor] = {specs[0].id: _input_activation(model_id, image_path, tensor)}
    with INFERENCE_LOCK, HookManager() as hooks:
        for spec in specs:
            if spec.module_path == "__input__":
                continue
            hooks.register_stage(spec.id, _resolve_module(model_id, model, spec.module_path))
        with torch.inference_mode():
            _forward(model_id, model, tensor)
        for spec in specs:
            if spec.module_path != "__input__":
                activations[spec.id] = hooks.get_activation(spec.id)
    input_shape = [int(value) for value in tensor.shape]
    return [_render_visualization(session_id, model_id, spec, activations[spec.id], input_shape) for spec in specs]


def capture_block(session_id: str, model_id: str, block_id: str, channel: int | None = None) -> dict[str, Any]:
    manifest = read_manifest(session_id)
    model, _ = _model_and_specs(model_id)
    parent, module_path, label, block_type, channels_last = _lookup_spec(model_id, model, block_id)
    image_path = _selected_image(session_id, model_id, manifest)
    tensor = _prepare_input(model_id, image_path, model)
    if module_path == "__input__":
        activation = _input_activation(model_id, image_path, tensor)
    else:
        module = _resolve_module(model_id, model, module_path)
        with INFERENCE_LOCK, HookManager() as hooks:
            hooks.register_stage("selected", module)
            with torch.inference_mode():
                _forward(model_id, model, tensor)
            activation = hooks.get_activation("selected")
    render_spec = BlockSpec(block_id, label, parent.group, module_path, block_type, parent.description)
    return _render_visualization(session_id, model_id, render_spec, activation, [int(value) for value in tensor.shape], channels_last=channels_last, channel=channel)


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
