"""Try complete IQA INT8 weight storage without activation quantization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import torch
from onnx import helper, numpy_helper

from export_onnx import CHECKPOINTS, ROOT, IQA, IMAGES, _session, _stats, iqa_inputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combine-hybrid", action="store_true")
    args = parser.parse_args()
    model = IQA()
    inputs = iqa_inputs()
    fp32_path = CHECKPOINTS / "iqa_fp32_weight_reference.onnx"
    output_path = CHECKPOINTS / (
        "iqa_int8_combined_candidate.onnx" if args.combine_hybrid else "iqa_int8_weight_only.onnx"
    )
    if args.combine_hybrid:
        input_path = CHECKPOINTS / "iqa_int8.onnx"
    else:
        with torch.inference_mode():
            torch.onnx.export(
                model,
                torch.from_numpy(inputs[0]),
                str(fp32_path),
                input_names=["input"],
                output_names=["logits"],
                opset_version=17,
                dynamo=False,
            )
        input_path = fp32_path
    graph = onnx.load(str(input_path))
    initializers = {item.name: item for item in graph.graph.initializer}
    replacements = {}
    new_initializers = []
    new_nodes = []
    original_weight_bytes = 0
    quantized_weight_bytes = 0
    for node in graph.graph.node:
        if node.op_type not in ("Conv", "Gemm") or node.input[1] not in initializers:
            continue
        name = node.input[1]
        if name not in replacements:
            weight = numpy_helper.to_array(initializers[name])
            if weight.dtype != np.float32:
                raise TypeError(f"Expected FP32 weight: {name} {weight.dtype}")
            if node.op_type == "Conv":
                axis = 0
            else:
                transposed = next(
                    (attribute.i for attribute in node.attribute if attribute.name == "transB"), 0
                )
                axis = 0 if transposed else 1
            axes = tuple(index for index in range(weight.ndim) if index != axis)
            scale = np.maximum(np.max(np.abs(weight), axis=axes) / 127.0, 1e-8).astype(np.float32)
            shape = [1] * weight.ndim
            shape[axis] = -1
            quantized = np.clip(np.rint(weight / scale.reshape(shape)), -127, 127).astype(np.int8)
            q_name, scale_name, zero_name, dq_name = (
                f"{name}.int8", f"{name}.scale", f"{name}.zero", f"{name}.dequant"
            )
            new_initializers.extend(
                [
                    numpy_helper.from_array(quantized, q_name),
                    numpy_helper.from_array(scale, scale_name),
                    numpy_helper.from_array(np.zeros_like(scale, dtype=np.int8), zero_name),
                ]
            )
            new_nodes.append(
                helper.make_node(
                    "DequantizeLinear", [q_name, scale_name, zero_name], [dq_name],
                    name=f"DQ_{name}", axis=axis,
                )
            )
            replacements[name] = dq_name
            original_weight_bytes += weight.nbytes
            quantized_weight_bytes += quantized.nbytes
        node.input[1] = replacements[name]
    remaining = [item for name, item in initializers.items() if name not in replacements]
    graph.graph.ClearField("initializer")
    graph.graph.initializer.extend(remaining + new_initializers)
    existing_nodes = list(graph.graph.node)
    graph.graph.ClearField("node")
    graph.graph.node.extend(new_nodes + existing_nodes)
    onnx.save(graph, str(output_path))
    onnx.checker.check_model(str(output_path))
    checked = onnx.load(str(output_path), load_external_data=False)
    checked_initializers = {item.name: item for item in checked.graph.initializer}
    producers = {name: node for node in checked.graph.node for name in node.output}
    covered_weights = 0
    for node in checked.graph.node:
        if node.op_type not in ("Conv", "Gemm"):
            continue
        weight = node.input[1]
        producer = producers.get(weight)
        if producer is None or producer.op_type != "DequantizeLinear":
            raise RuntimeError(f"IQA weight is not INT8-dequantized: {node.name}")
        source = checked_initializers.get(producer.input[0])
        if source is None or source.data_type != onnx.TensorProto.INT8:
            raise RuntimeError(f"IQA weight is not stored INT8: {node.name}")
        covered_weights += 1

    session = _session(output_path)
    comparisons = []
    for path, image in zip(IMAGES, inputs, strict=True):
        with torch.inference_mode():
            expected = model(torch.from_numpy(image)).numpy()[0]
        candidate = session.run(["logits"], {"input": image})[0][0]
        ref_prob = torch.softmax(torch.from_numpy(expected), dim=0).numpy()
        cand_prob = torch.softmax(torch.from_numpy(candidate), dim=0).numpy()
        comparisons.append(
            {
                "image": str(path),
                "reference_class": int(ref_prob.argmax()),
                "weight_int8_class": int(cand_prob.argmax()),
                "reference_confidence": float(ref_prob.max()),
                "weight_int8_confidence": float(cand_prob.max()),
                "probability_difference": _stats(ref_prob, cand_prob),
            }
        )
    agreement = sum(
        item["reference_class"] == item["weight_int8_class"] for item in comparisons
    )
    max_error = max(item["probability_difference"]["max_abs"] for item in comparisons)
    if args.combine_hybrid and (agreement != len(comparisons) or max_error > 0.05):
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Combined IQA quantization failed parity: {agreement}/{len(comparisons)}, {max_error:.4f}")
    if args.combine_hybrid:
        output_path.replace(CHECKPOINTS / "iqa_int8.onnx")
        output_path = CHECKPOINTS / "iqa_int8.onnx"
    result = {
        "artifact": str(output_path),
        "bytes": output_path.stat().st_size,
        "quantized_conv_gemm_weight_count": len(replacements),
        "all_conv_gemm_int8_coverage": covered_weights,
        "original_conv_gemm_weight_bytes": original_weight_bytes,
        "quantized_conv_gemm_weight_bytes": quantized_weight_bytes,
        "input": "input FLOAT [1,3,224,224]",
        "output": "logits FLOAT [1,3], temperature calibrated",
        "execution": (
            "all Conv/Gemm weights INT8; stages 5-8 and head use QDQ INT8/UINT8 activation quantization; earlier stages dequantize weights to FP32 compute"
            if args.combine_hybrid else
            "all Conv/Gemm weights stored INT8 then dequantized to FP32; activations/computation FP32"
        ),
        "comparisons": comparisons,
        "max_probability_difference": max_error,
        "classification_agreement": agreement,
    }
    report_name = "iqa_combined_report.json" if args.combine_hybrid else "iqa_weight_only_report.json"
    (ROOT / "scripts" / report_name).write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    if not args.combine_hybrid:
        fp32_path.unlink()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
