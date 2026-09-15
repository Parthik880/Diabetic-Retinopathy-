"""Grad-CAM implementation used by optional grade visualizations."""

import time

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
        cams, logits, probabilities, classes = self.generate_batch(
            image, None if class_index is None else [class_index]
        )
        return cams[0], logits, probabilities, classes[0]

    def generate_batch(self, images, class_indices=None, timing=None):
        """Generate ordered per-image CAMs with one forward and one backward."""
        self.model.eval()
        images = images.clone().requires_grad_(True)
        self.model.zero_grad(set_to_none=True)

        timing = timing if timing is not None else {}
        device = images.device
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        started = time.perf_counter_ns()
        logits = self.model(images)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        timing["convnext_forward_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        probabilities = torch.softmax(logits, dim=1)
        if class_indices is None:
            targets = logits.argmax(dim=1)
        else:
            targets = torch.as_tensor(class_indices, device=logits.device, dtype=torch.long)
            if targets.shape != (images.shape[0],):
                raise ValueError("One Grad-CAM class index is required per image")

        if device.type == "cuda":
            torch.cuda.synchronize(device)
        started = time.perf_counter_ns()
        logits.gather(1, targets[:, None]).sum().backward()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        timing["gradcam_backward_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        if self.activations is None or self.gradients is None:
            raise RuntimeError(
                "Grad-CAM hooks did not capture activations and gradients"
            )

        started = time.perf_counter_ns()
        weights = self.gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * self.activations).sum(dim=1, keepdim=True)
        cam = torch.relu(cam)
        cam = F.interpolate(
            cam,
            size=images.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )[:, 0]
        minimum = cam.amin(dim=(1, 2), keepdim=True)
        maximum = cam.amax(dim=(1, 2), keepdim=True)
        cam = (cam - minimum) / (maximum - minimum + 1e-8)
        if device.type == "cuda":
            torch.cuda.synchronize(device)

        timing["gradcam_map_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        started = time.perf_counter_ns()
        result = (
            cam.detach().cpu(), logits.detach().cpu(), probabilities.detach().cpu(),
            [int(value) for value in targets.detach().cpu().tolist()],
        )
        timing["grade_d2h_ms"] = (time.perf_counter_ns() - started) / 1_000_000
        return result

    def remove_hooks(self) -> None:
        self.forward_hook.remove()
        self.backward_hook.remove()
