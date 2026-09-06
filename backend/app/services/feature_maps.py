from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

from models.restoration.model import NAFNet
from models.restoration.predict import restore_image


FEATURE_TARGETS: tuple[tuple[str, str, str, Callable[[NAFNet], torch.nn.Module]], ...] = (
    (
        "encoder_1",
        "Encoder 1",
        "encoders[0]",
        lambda model: model.encoders[0],
    ),
    (
        "encoder_2",
        "Encoder 2",
        "encoders[1]",
        lambda model: model.encoders[1],
    ),
    (
        "bottleneck",
        "Bottleneck",
        "middle_blks",
        lambda model: model.middle_blks,
    ),
    (
        "decoder_1",
        "Decoder 1",
        "decoders[0]",
        lambda model: model.decoders[0],
    ),
    (
        "decoder_2",
        "Decoder 2",
        "decoders[2]",
        lambda model: model.decoders[2],
    ),
)


def _representative_channels(total: int, count: int = 8) -> list[int]:
    if total <= count:
        return list(range(total))
    return sorted({int(value) for value in np.linspace(0, total - 1, count)})


def _save_feature_stage(
    stage_id: str,
    label: str,
    layer_name: str,
    output: torch.Tensor,
    feature_root: Path,
) -> dict[str, Any]:
    if not torch.is_tensor(output) or output.ndim != 4:
        raise RuntimeError(f"{layer_name} did not return a 4D activation tensor")

    # The display pipeline is intentionally separate from model execution:
    # detach -> CPU -> representative channels -> per-channel normalization.
    activation = output.detach().float().cpu()
    indices = _representative_channels(int(activation.shape[1]))
    selected = activation[0, indices]
    stage_dir = feature_root / stage_id
    stage_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for index, channel in zip(indices, selected):
        minimum = channel.min()
        maximum = channel.max()
        if float(maximum - minimum) > 1e-12:
            normalized = (channel - minimum) / (maximum - minimum)
        else:
            normalized = torch.zeros_like(channel)
        pixels = np.rint(normalized.numpy() * 255.0).astype(np.uint8)
        path = stage_dir / f"channel_{index:03d}.png"
        Image.fromarray(pixels, mode="L").save(path, optimize=True)
        paths.append(str(path.resolve()))

    shape = [int(value) for value in activation.shape]
    return {
        "id": stage_id,
        "label": label,
        "layer": layer_name,
        "tensor_shape": shape,
        "channels_total": shape[1],
        "channels_shown": len(paths),
        "images": paths,
        "explanation": (
            "These grayscale images show normalized activation strength for "
            "representative channels. They are internal model responses, not "
            "direct maps of a specific lesion or diagnosis."
        ),
    }


def restore_with_feature_maps(
    image_path: Path,
    model: NAFNet,
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    feature_root = output_dir / "features"
    features: dict[str, dict[str, Any]] = {}
    handles: list[torch.utils.hooks.RemovableHandle] = []

    for stage_id, label, layer_name, selector in FEATURE_TARGETS:
        module = selector(model)

        def capture(
            _module: torch.nn.Module,
            _inputs: tuple[torch.Tensor, ...],
            output: torch.Tensor,
            *,
            current_id: str = stage_id,
            current_label: str = label,
            current_layer: str = layer_name,
        ) -> None:
            features[current_id] = _save_feature_stage(
                current_id,
                current_label,
                current_layer,
                output,
                feature_root,
            )

        handles.append(module.register_forward_hook(capture))

    try:
        result = restore_image(image_path, model=model, output_dir=output_dir)
    finally:
        for handle in handles:
            handle.remove()

    if set(features) != {target[0] for target in FEATURE_TARGETS}:
        missing = sorted({target[0] for target in FEATURE_TARGETS} - set(features))
        raise RuntimeError(f"NAFNet hooks did not capture: {', '.join(missing)}")
    result.pop("restored_image", None)
    return result, features
