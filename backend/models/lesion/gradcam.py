"""Per-lesion Grad-CAM for the UNet++ segmentation decoder."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from .model import LesionUNetPlusPlus


GRADCAM_TARGET_LAYER = "conv0_3.layers[3]"
GRADCAM_TARGET_FORMULATION = (
    "mean class-channel logit over retained predicted-lesion pixels"
)


class SegmentationGradCAM:
    """Capture the final decoder convolution and explain one output channel."""

    def __init__(self, model: LesionUNetPlusPlus) -> None:
        self.model = model
        self.activations: torch.Tensor | None = None
        target_layer = model.conv0_3.layers[3]
        self._hook = target_layer.register_forward_hook(self._capture_activations)

    def _capture_activations(self, _module, _inputs, output) -> None:
        self.activations = output
        output.retain_grad()

    def generate(
        self,
        logits: torch.Tensor,
        channel: int,
        predicted_region_mask: np.ndarray,
    ) -> np.ndarray | None:
        """Return a normalized original-resolution CAM, or None when absent."""
        mask = np.asarray(predicted_region_mask, dtype=bool)
        if mask.ndim != 2 or not mask.any():
            return None
        if self.activations is None:
            raise RuntimeError("Grad-CAM target activations were not captured")

        target_mask = torch.from_numpy(mask.astype(np.float32)).to(logits.device)
        target_mask = F.interpolate(
            target_mask[None, None],
            size=logits.shape[-2:],
            mode="nearest",
        )[0, 0]
        if not torch.any(target_mask):
            return None

        self.model.zero_grad(set_to_none=True)
        self.activations.grad = None
        objective = (logits[0, channel] * target_mask).sum() / target_mask.sum()
        objective.backward(retain_graph=True)
        gradients = self.activations.grad
        if gradients is None:
            raise RuntimeError("Grad-CAM target gradients were not captured")

        weights = gradients[0].mean(dim=(1, 2), keepdim=True)
        cam = torch.relu((weights * self.activations[0]).sum(dim=0, keepdim=True))
        cam = F.interpolate(
            cam[None], size=mask.shape, mode="bilinear", align_corners=False
        )[0, 0]
        cam = cam.detach().float().cpu()
        minimum = cam.min()
        maximum = cam.max()
        if float(maximum - minimum) > 1e-12:
            cam = (cam - minimum) / (maximum - minimum)
        else:
            cam = torch.zeros_like(cam)
        return cam.numpy()

    def close(self) -> None:
        self.model.zero_grad(set_to_none=True)
        self._hook.remove()
