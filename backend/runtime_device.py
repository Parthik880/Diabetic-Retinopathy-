"""CPU-only runtime policy for the RetinaGram CPU desktop edition."""

from __future__ import annotations

import torch


DEVICE = torch.device("cpu")
DEVICE_NAME = "CPU"


def resolve_cpu_device(device: str | torch.device | None = None) -> torch.device:
    """Return the single supported device and reject accidental GPU requests."""
    if device is not None and torch.device(device).type != "cpu":
        raise ValueError("The RetinaGram CPU edition only supports device='cpu'.")
    return DEVICE


def model_parameter_device(model: torch.nn.Module, model_name: str) -> torch.device:
    """Return and validate the device used by a loaded model."""
    try:
        device = next(model.parameters()).device
    except StopIteration as exc:
        raise RuntimeError(f"{model_name} model has no parameters") from exc
    if device.type != "cpu":
        raise RuntimeError(
            f"{model_name} model is on {device}; the CPU edition requires cpu."
        )
    return device
