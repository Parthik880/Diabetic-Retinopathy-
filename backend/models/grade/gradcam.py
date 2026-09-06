"""Grad-CAM implementation used by optional grade visualizations."""

import torch
import torch.nn.functional as F


def find_gradcam_target_layer(model):
    """Return the final ConvNeXt feature block used by the original inference code."""
    backbone = getattr(model, "model", None)
    features = getattr(backbone, "features", None)
    if features is None or len(features) == 0 or len(features[-1]) == 0:
        raise ValueError("Unable to identify the final ConvNeXt feature block")
    return features[-1][-1]


class GradCAM:
    def __init__(self, model, target_layer=None) -> None:
        self.model = model
        self.target_layer = target_layer or find_gradcam_target_layer(model)
        self.activations = None
        self.gradients = None
        self.forward_hook = self.target_layer.register_forward_hook(
            self._save_activations
        )
        self.backward_hook = self.target_layer.register_full_backward_hook(
            self._save_gradients
        )

    def _save_activations(self, module, inputs, output) -> None:
        self.activations = output.detach()

    def _save_gradients(self, module, grad_input, grad_output) -> None:
        self.gradients = grad_output[0].detach()

    def generate(self, image, class_index=None):
        self.model.eval()
        image = image.clone().requires_grad_(True)
        self.model.zero_grad(set_to_none=True)

        logits = self.model(image)
        probabilities = torch.softmax(logits, dim=1)
        if class_index is None:
            class_index = int(logits.argmax(dim=1).item())

        logits[0, class_index].backward()
        if self.activations is None or self.gradients is None:
            raise RuntimeError(
                "Grad-CAM hooks did not capture activations and gradients"
            )

        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)
        cam = torch.relu(cam)
        cam = F.interpolate(
            cam,
            size=image.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )[0, 0]
        cam = cam - cam.min()
        cam = cam / (cam.max() + 1e-8)

        return (
            cam.detach(),
            logits.detach(),
            probabilities.detach(),
            class_index,
        )

    def remove_hooks(self) -> None:
        self.forward_hook.remove()
        self.backward_hook.remove()
