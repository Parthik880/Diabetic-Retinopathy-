"""Official NAFNet width-32 construction and checkpoint loading."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import torch

from models.checkpoints import checkpoint_path

from .nafnet import NAFNet


DEFAULT_CHECKPOINT_PATH = checkpoint_path(
    "restoration", "NAFNet-SIDD-width32.pth"
)
NAFNET_CONFIG = {
    "img_channel": 3,
    "width": 32,
    "enc_blk_nums": [2, 2, 4, 8],
    "middle_blk_num": 12,
    "dec_blk_nums": [2, 2, 2, 2],
}


def resolve_device(device: str | torch.device | None = None) -> torch.device:
    resolved = torch.device(
        device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
    )
    if resolved.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is false")
    return resolved


def build_restoration_model() -> NAFNet:
    """Construct the unchanged official NAFNet-width32 network."""
    return NAFNet(**NAFNET_CONFIG)


def _select_state_dict(checkpoint: object) -> tuple[Mapping[str, torch.Tensor], str]:
    if not isinstance(checkpoint, Mapping):
        raise TypeError("NAFNet checkpoint must be a mapping")
    for key in ("params_ema", "params", "state_dict", "net_g", "model"):
        value = checkpoint.get(key)
        if isinstance(value, Mapping) and value:
            return value, key
    if checkpoint and all(torch.is_tensor(value) for value in checkpoint.values()):
        return checkpoint, "plain state dict"
    raise ValueError(
        "Could not find NAFNet weights; expected params, params_ema, "
        "state_dict, net_g, model, or a plain state dictionary"
    )


def load_restoration_model(
    checkpoint_path: str | Path = DEFAULT_CHECKPOINT_PATH,
    device: str | torch.device | None = None,
) -> tuple[NAFNet, dict]:
    """Load a compatible BasicSR NAFNet checkpoint with strict key matching."""
    path = Path(checkpoint_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"NAFNet checkpoint not found: {path}. See models/restoration/README.md."
        )
    try:
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:
        checkpoint = torch.load(path, map_location="cpu")
    state_dict, source_key = _select_state_dict(checkpoint)
    cleaned = {
        name.removeprefix("module."): tensor for name, tensor in state_dict.items()
    }
    model = build_restoration_model()
    model.load_state_dict(cleaned, strict=True)
    resolved_device = resolve_device(device)
    model.to(resolved_device).eval()
    generic = any(
        marker in path.name.casefold() for marker in ("sidd", "gopro")
    )
    return model, {
        "checkpoint_path": str(path),
        "weights_key": source_key,
        "generic_pretrained": generic,
        "retinal_trained": not generic,
    }
