"""Offline IQA INT8 and NAFNet FP16 ONNX exports with local parity checks."""

from __future__ import annotations

import argparse
import json
import sys
sys.dont_write_bytecode = True
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision import models, transforms


from dev_paths import ROOT, SOURCE, CHECKPOINTS, source_checkpoint, validation_images
sys.path.insert(0, str(SOURCE / "backend"))

import onnx  # noqa: E402
import onnxruntime as ort  # noqa: E402


IMAGES = validation_images()
IMAGES = [path for path in IMAGES if path.is_file()]


class IQA(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        from models.iqa.model import EfficientNetIQA

        from numpy._core.multiarray import scalar

        with torch.serialization.safe_globals([scalar, np.dtype, np.dtypes.Float64DType]):
            saved = torch.load(
                source_checkpoint("final_efficientnet_iqa.pth"),
                map_location="cpu",
                weights_only=True,
            )
        self.temperature = float(saved["temperature"])
        self.backbone = models.efficientnet_b0(weights=None)
        self.backbone.load_state_dict(
            torch.load(
                source_checkpoint("efficientnet_b0_rwightman-7f5810bc.pth"),
                map_location="cpu",
                weights_only=True,
            ),
            strict=True,
        )
        self.head = EfficientNetIQA()
        self.head.load_state_dict(saved["model_state_dict"], strict=True)
        self.eval()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone.avgpool(self.backbone.features(x)).flatten(1)
        return self.head(features) / self.temperature


def iqa_inputs() -> list[np.ndarray]:
    transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
        ]
    )
    inputs = []
    for path in IMAGES:
        with Image.open(path) as image:
            inputs.append(transform(image.convert("RGB")).unsqueeze(0).numpy())
    if not inputs:
        raise RuntimeError("No reference fundus images found")
    return inputs


def _session(path: Path) -> ort.InferenceSession:
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _stats(reference: np.ndarray, candidate: np.ndarray) -> dict:
    difference = np.abs(reference.astype(np.float32) - candidate.astype(np.float32))
    return {
        "max_abs": float(difference.max()),
        "mean_abs": float(difference.mean()),
    }


def export_iqa() -> dict:
    from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static

    class Reader(CalibrationDataReader):
        def __init__(self, tensors: list[np.ndarray]):
            self._iterator = iter({"input": tensor} for tensor in tensors)

        def get_next(self):
            return next(self._iterator, None)

    model = IQA()
    inputs = iqa_inputs()
    reference_path = CHECKPOINTS / "iqa_fp32_reference.onnx"
    output_path = CHECKPOINTS / "iqa_int8.onnx"
    with torch.inference_mode():
        torch.onnx.export(
            model,
            torch.from_numpy(inputs[0]),
            str(reference_path),
            input_names=["input"],
            output_names=["logits"],
            opset_version=17,
            dynamo=False,
        )
    onnx.checker.check_model(str(reference_path))
    reference_session = _session(reference_path)
    reference_errors = []
    for image in inputs:
        with torch.inference_mode():
            expected = model(torch.from_numpy(image)).numpy()
        actual = reference_session.run(["logits"], {"input": image})[0]
        reference_errors.append(_stats(expected, actual))
    reference_graph = onnx.load(str(reference_path), load_external_data=False)
    # Full-model activation quantization flipped Good to Reject on every local
    # fundus image. Later backbone stages and the head retain class/confidence.
    quantized_nodes = [
        node.name
        for node in reference_graph.graph.node
        if node.op_type == "Gemm"
        or (
            node.op_type == "Conv"
            and any(f"features.{stage}/" in node.name for stage in range(5, 9))
        )
    ]
    if len(quantized_nodes) != 43:
        raise RuntimeError(f"Unexpected IQA graph: {len(quantized_nodes)} quantizable nodes")
    quantize_static(
        str(reference_path),
        str(output_path),
        Reader(inputs),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        nodes_to_quantize=quantized_nodes,
    )
    onnx.checker.check_model(str(output_path))
    session = _session(output_path)
    comparisons = []
    times_ms = []
    for path, image in zip(IMAGES, inputs, strict=True):
        with torch.inference_mode():
            expected = model(torch.from_numpy(image)).numpy()[0]
        started = time.perf_counter()
        actual = session.run(["logits"], {"input": image})[0][0]
        times_ms.append((time.perf_counter() - started) * 1000)
        expected_prob = torch.softmax(torch.from_numpy(expected), dim=0).numpy()
        actual_prob = torch.softmax(torch.from_numpy(actual), dim=0).numpy()
        comparisons.append(
            {
                "image": str(path),
                "calibrated_logit_difference": _stats(expected, actual),
                "probability_difference": _stats(expected_prob, actual_prob),
                "reference_class": int(expected_prob.argmax()),
                "int8_class": int(actual_prob.argmax()),
                "reference_confidence": float(expected_prob.max()),
                "int8_confidence": float(actual_prob.max()),
            }
        )
    graph = onnx.load(str(output_path), load_external_data=False)
    from collections import Counter

    types = dict(Counter(onnx.TensorProto.DataType.Name(item.data_type) for item in graph.graph.initializer))
    agreement = sum(item["reference_class"] == item["int8_class"] for item in comparisons)
    max_probability_error = max(
        item["probability_difference"]["max_abs"] for item in comparisons
    )
    if agreement != len(comparisons) or max_probability_error > 0.05:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"IQA INT8 parity failed: {agreement}/{len(comparisons)} classes agree; "
            f"max probability difference {max_probability_error:.4f}"
        )
    result = {
        "artifact": str(output_path),
        "bytes": output_path.stat().st_size,
        "input": "input float32 NCHW [1,3,224,224]",
        "output": "logits float32 [1,3], already divided by checkpoint temperature",
        "temperature": model.temperature,
        "calibration_images": len(inputs),
        "initializer_types": types,
        "quantization": "QDQ INT8 weights / UINT8 activations in backbone stages 5-8 and head; earlier stages FP32",
        "quantized_node_count": len(quantized_nodes),
        "classification_agreement": f"{agreement}/{len(comparisons)}",
        "max_probability_difference": max_probability_error,
        "reference_onnx_vs_pytorch": reference_errors,
        "comparisons": comparisons,
        "average_ort_inference_ms": sum(times_ms) / len(times_ms),
    }
    reference_path.unlink()
    return result


def export_nafnet() -> dict:
    from models.restoration.model import load_restoration_model
    from onnxconverter_common import float16

    model, _ = load_restoration_model(source_checkpoint("NAFNet-SIDD-width32.pth"), "cpu")
    reference_path = CHECKPOINTS / "nafnet_fp32_reference.onnx"
    output_path = CHECKPOINTS / "nafnet_fp16.onnx"
    sample = torch.rand(1, 3, 256, 256)
    with torch.inference_mode():
        torch.onnx.export(
            model,
            sample,
            str(reference_path),
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={
                "input": {0: "batch", 2: "height", 3: "width"},
                "output": {0: "batch", 2: "height", 3: "width"},
            },
            opset_version=17,
            dynamo=False,
        )
    onnx.checker.check_model(str(reference_path))
    with torch.inference_mode():
        expected = model(sample).numpy()
    actual = _session(reference_path).run(["output"], {"input": sample.numpy()})[0]
    model_fp16 = float16.convert_float_to_float16(
        onnx.load(str(reference_path)), keep_io_types=True
    )
    onnx.save(model_fp16, str(output_path))
    onnx.checker.check_model(str(output_path))
    result = {
        "artifact": str(output_path),
        "bytes": output_path.stat().st_size,
        "input": "input float32 NCHW; dynamic batch/height/width",
        "output": "output float32 NCHW; raw restoration before clamp/round",
        "fp32_onnx_vs_pytorch": _stats(expected, actual),
        "fp16_cpu_ort": "not tested",
    }
    try:
        candidate = _session(output_path).run(["output"], {"input": sample.numpy()})[0]
        result["fp16_cpu_ort"] = _stats(expected, candidate)
    except Exception as exc:
        result["fp16_cpu_ort"] = f"unavailable: {type(exc).__name__}: {str(exc)[:300]}"
    reference_path.unlink()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=("iqa", "nafnet"))
    args = parser.parse_args()
    if args.model == "iqa":
        from tune_iqa import main as tune_iqa
        tune_iqa()
        return
    result = export_nafnet()
    (ROOT / "scripts" / f"{args.model}_export_report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
