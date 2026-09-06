from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import torch
from torch import nn


def _first_tensor(value: Any) -> torch.Tensor | None:
    if torch.is_tensor(value):
        return value
    if isinstance(value, (tuple, list)):
        for item in value:
            tensor = _first_tensor(item)
            if tensor is not None:
                return tensor
    if isinstance(value, dict):
        for item in value.values():
            tensor = _first_tensor(item)
            if tensor is not None:
                return tensor
    return None


class HookManager:
    """Short-lived forward-hook registry for one visualization request.

    Captures are immediately detached and moved to CPU. Calling ``clear`` removes
    every handle, so shared model instances never retain visualization hooks.
    """

    def __init__(self) -> None:
        self._handles: list[torch.utils.hooks.RemovableHandle] = []
        self._activations: dict[str, torch.Tensor] = {}
        self._enabled = True

    def register_block(self, name: str, module: nn.Module) -> None:
        def capture(_module: nn.Module, _inputs: tuple[Any, ...], output: Any) -> None:
            if not self._enabled:
                return
            tensor = _first_tensor(output)
            if tensor is not None:
                self._activations[name] = tensor.detach().float().cpu()

        self._handles.append(module.register_forward_hook(capture))

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def get_activation(self, name: str) -> torch.Tensor:
        try:
            return self._activations[name]
        except KeyError as exc:
            raise RuntimeError(f"Hook did not capture an activation for {name}") from exc

    def clear(self) -> None:
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._activations.clear()

    def __enter__(self) -> "HookManager":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.clear()

    def __iter__(self) -> Iterator[str]:
        return iter(self._activations)
