import torch
import torch.nn.functional as F


class GradCAM:

    def __init__(
        self,
        model,
        target_layer
    ):

        self.model = model
        self.target_layer = target_layer

        self.activations = None
        self.gradients = None

        self.forward_hook = (
            target_layer.register_forward_hook(
                self._save_activations
            )
        )

        self.backward_hook = (
            target_layer.register_full_backward_hook(
                self._save_gradients
            )
        )

    def _save_activations(
        self,
        module,
        input,
        output
    ):

        self.activations = output.detach()

    def _save_gradients(
        self,
        module,
        grad_input,
        grad_output
    ):

        self.gradients = grad_output[0].detach()

    def generate(
        self,
        image,
        class_index=None
    ):

        self.model.eval()

        # Important if backbone is frozen
        image = image.clone().requires_grad_(True)

        self.model.zero_grad(
            set_to_none=True
        )

        # Forward
        logits = self.model(image)

        probabilities = torch.softmax(
            logits,
            dim=1
        )

        # Use predicted class if one isn't specified
        if class_index is None:

            class_index = int(
                logits.argmax(dim=1).item()
            )

        # Score for selected class
        score = logits[
            0,
            class_index
        ]

        # Backward
        score.backward()

        

        gradients = self.gradients
        activations = self.activations

        # Global-average-pool gradients
        weights = gradients.mean(
            dim=(2, 3),
            keepdim=True
        )

        # Weighted combination of feature maps
        cam = (
            weights
            * activations
        ).sum(
            dim=1,
            keepdim=True
        )

        # Only positive influence
        cam = torch.relu(
            cam
        )

        # Resize Grad-CAM to input image size
        cam = F.interpolate(
            cam,
            size=image.shape[-2:],
            mode="bilinear",
            align_corners=False
        )

        # Normalize 0 -> 1
        cam = cam[
            0,
            0
        ]

        cam = cam - cam.min()

        cam = cam / (
            cam.max() + 1e-8
        )

        return (
            cam.detach().cpu(),
            probabilities.detach().cpu(),
            class_index
        )

    def remove_hooks(self):

        self.forward_hook.remove()
        self.backward_hook.remove()