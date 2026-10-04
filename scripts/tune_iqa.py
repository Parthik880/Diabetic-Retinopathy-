"""Choose the widest IQA QDQ INT8 coverage that preserves local class probabilities."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnx
import torch
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static

from export_onnx import CHECKPOINTS, ROOT, IQA, IMAGES, _session, iqa_inputs


class Reader(CalibrationDataReader):
    def __init__(self, tensors: list[np.ndarray]):
        self.iterator = iter({"input": tensor} for tensor in tensors)

    def get_next(self):
        return next(self.iterator, None)


def main() -> None:
    reference = CHECKPOINTS / "iqa_fp32_reference.onnx"
    model = IQA()
    if not reference.is_file():
        inputs = iqa_inputs()
        with torch.inference_mode():
            torch.onnx.export(model, torch.from_numpy(inputs[0]), str(reference),
                              input_names=["input"], output_names=["logits"],
                              opset_version=17, dynamo=False)
    graph = onnx.load(str(reference))
    quantizable = [node for node in graph.graph.node if node.op_type in ("Conv", "Gemm")]
    inputs = iqa_inputs()
    with torch.inference_mode():
        probabilities = [torch.softmax(model(torch.from_numpy(image))[0], dim=0).numpy() for image in inputs]
    options = [
        ("head", []),
        ("stage8", [8]),
        *[(f"stage{stage}_8", [stage, 8]) for stage in range(0, 8)],
        ("stages0_4_8", [0, 1, 2, 3, 4, 8]),
        ("stages0_5_8", [0, 1, 2, 3, 4, 5, 8]),
        ("stages6to8", [6, 7, 8]),
        ("stages5to8", [5, 6, 7, 8]),
    ]
    output = CHECKPOINTS / "iqa_int8.onnx"
    candidates = []
    best = None
    for label, stages in options:
        names = [node.name for node in quantizable if node.op_type == "Gemm"
                 or any(f"features.{stage}/" in node.name for stage in stages)]
        quantize_static(
            str(reference), str(output), Reader(inputs),
            quant_format=QuantFormat.QDQ,
            activation_type=QuantType.QUInt8,
            weight_type=QuantType.QInt8,
            per_channel=True,
            nodes_to_quantize=names,
        )
        session = _session(output)
        rows = []
        for path, image, expected in zip(IMAGES, inputs, probabilities, strict=True):
            logits = session.run(["logits"], {"input": image})[0][0]
            actual = torch.softmax(torch.from_numpy(logits), dim=0).numpy()
            rows.append({"image": Path(path).name,
                         "reference_class": int(expected.argmax()),
                         "candidate_class": int(actual.argmax()),
                         "reference_confidence": float(expected.max()),
                         "candidate_confidence": float(actual.max()),
                         "max_abs_probability_error": float(np.max(np.abs(expected - actual)))})
        max_error = max(row["max_abs_probability_error"] for row in rows)
        agreement = sum(row["reference_class"] == row["candidate_class"] for row in rows)
        report = {"name": label, "quantized_nodes": len(names), "bytes": output.stat().st_size,
                  "class_agreement": agreement, "max_probability_error": max_error, "images": rows}
        candidates.append(report)
        print(label, len(names), agreement, round(max_error, 5), flush=True)
        if agreement == len(inputs) and max_error <= 0.05 and (best is None or len(names) > best[0]):
            best = (len(names), label, output.read_bytes())
    if best is None:
        raise RuntimeError("No INT8 calibration met the 0.05 probability-error gate")
    output.write_bytes(best[2])
    result = {"selected": best[1], "quantized_nodes": best[0], "candidates": candidates,
              "calibration_images": len(inputs), "quality_classes_in_calibration": ["Good", "Usable", "Reject"]}
    (ROOT / "scripts/iqa_tuning_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    chosen = next(item for item in candidates if item["name"] == best[1])
    (ROOT / "scripts/iqa_export_report.json").write_text(json.dumps({
        "artifact": str(output), "bytes": output.stat().st_size,
        "precision": "partial QDQ INT8: selected EfficientNet stage and classifier; remaining layers FP32",
        "quantized_nodes": best[0], "calibration_images": len(inputs),
        "class_agreement": chosen["class_agreement"],
        "max_probability_error": chosen["max_probability_error"],
        "selection": best[1]}, indent=2), encoding="utf-8")
    reference.unlink(missing_ok=True)
    print("selected", best[1])


if __name__ == "__main__":
    main()
