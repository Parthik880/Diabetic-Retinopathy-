"""Smoke-test the real IQA checkpoint: python test_iqa.py --image fundus.jpg."""

import argparse

import torch
from PIL import Image

from models.iqa import EfficientNetIQAService, IQA_CLASS_NAMES, predict_iqa
from models.iqa.model import DEFAULT_CHECKPOINT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    service = EfficientNetIQAService(args.checkpoint, args.device)
    assert not service.feature_extractor.training
    assert not service.classifier.training
    assert all(not p.requires_grad for p in service.feature_extractor.parameters())
    with Image.open(args.image) as image, torch.inference_mode():
        inputs = service.transform(image.convert("RGB")).unsqueeze(0).to(service.device)
        features = service.feature_extractor(inputs).flatten(start_dim=1)
        logits = service.classifier(features)
        probabilities = torch.softmax(logits / service.temperature, dim=1)
        result = service.predict(image)
        # Upload/camera modes must also be accepted via RGB conversion.
        for mode in ("L", "RGBA"):
            assert service.predict(image.convert(mode))["quality"] in IQA_CLASS_NAMES
    assert list(inputs.shape) == [1, 3, 224, 224]
    assert list(features.shape) == [1, 1280]
    assert list(logits.shape) == [1, 3]
    assert list(probabilities.shape) == [1, 3]
    assert torch.isfinite(probabilities).all()
    assert torch.allclose(probabilities.sum(1), torch.ones(1, device=service.device))
    assert result["class_id"] == probabilities.argmax(1).item()
    assert result["quality"] == IQA_CLASS_NAMES[result["class_id"]]
    assert result["confidence"] == max(result["probabilities"].values())
    torch.testing.assert_close(
        torch.tensor(list(result["probabilities"].values())),
        probabilities[0].cpu(),
    )
    assert predict_iqa(args.image, model=service)["probabilities"] == result["probabilities"]
    print("Checkpoint loaded strict=True: YES")
    print(f"Temperature: {service.temperature}")
    print(f"Input tensor: {list(inputs.shape)}")
    print(f"EfficientNet feature shape: {list(features.shape)}")
    print(f"Classifier logits: {list(logits.shape)}")
    print(f"Probabilities shape: {list(probabilities.shape)}")
    print(f"Predicted quality: {result['quality']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Probabilities: {result['probabilities']}")


if __name__ == "__main__":
    main()
