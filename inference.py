import torch
import torch.nn as nn
from torchvision.models import convnext_tiny, ConvNeXt_Tiny_Weights
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from model import Convextnet
from grad import GradCAM
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
device = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

model = Convextnet(
    numclasses=5
).to(device)

checkpoint = torch.load(
    "checkpoint/grade-classifier/convnext_tiny.pth",
    map_location=device
)



model.eval()
target_layer = (
    model
    .model
    .features[-1][-1]
)

print(target_layer)


gradcam = GradCAM(
    model,
    target_layer
)

transform = transforms.Compose([

    transforms.Resize(
        (224, 224)
    ),

    transforms.ToTensor(),

    transforms.Normalize(
        mean=[
            0.485,
            0.456,
            0.406
        ],
        std=[
            0.229,
            0.224,
            0.225
        ]
    )
])


image_path = r"" #path of image

original_image = Image.open(
    image_path
).convert("RGB")

image_tensor = transform(
    original_image
)

image_tensor = (
    image_tensor
    .unsqueeze(0)
    .to(device)
)

original_resized = original_image.resize(
    (224, 224)
)

original_array = np.array(
    original_resized
)
cam, probabilities, predicted_class = (
    gradcam.generate(
        image_tensor
    )
)

print(
    "Predicted grade:",
    predicted_class
)

print(
    "Probabilities:",
    probabilities[0]
)


plt.figure(
    figsize=(6, 6)
)

plt.imshow(
    original_array
)

plt.imshow(
    cam.numpy(),
    alpha=0.4,
    cmap="jet"
)

plt.title(
    f"Predicted DR Grade: {predicted_class}"
)

plt.axis("off")

plt.show()