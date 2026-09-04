"""Command-line grade prediction with optional Grad-CAM visualization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.grade.model import DEFAULT_CHECKPOINT_PATH
from models.grade.predict import predict_grade


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict a diabetic-retinopathy grade."
    )
    parser.add_argument(
        "--image", required=True, type=Path, help="path to one retinal image"
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_PATH,
        help=f"trained ConvNeXt checkpoint (default: {DEFAULT_CHECKPOINT_PATH})",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        help="inference device (default: CUDA when available, otherwise CPU)",
    )
    parser.add_argument(
        "--gradcam-output", type=Path, help="optional heatmap output image"
    )
    parser.add_argument(
        "--show-gradcam", action="store_true", help="display the heatmap"
    )
    return parser.parse_args()


def render_gradcam(image_path: Path, cam, output_path: Path | None, show: bool) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    with Image.open(image_path) as image:
        original_array = np.array(image.convert("RGB").resize((224, 224)))

    plt.figure(figsize=(6, 6))
    plt.imshow(original_array)
    plt.imshow(cam.numpy(), alpha=0.4, cmap="jet")
    plt.axis("off")
    if output_path is not None:
        resolved_output = output_path.expanduser().resolve()
        resolved_output.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(resolved_output, bbox_inches="tight", pad_inches=0)
        print(f"Grad-CAM: {resolved_output}")
    if show:
        plt.show()
    plt.close()


def main() -> int:
    args = parse_args()
    include_gradcam = args.gradcam_output is not None or args.show_gradcam
    try:
        result = predict_grade(
            args.image,
            checkpoint_path=args.checkpoint,
            device=args.device,
            return_gradcam=include_gradcam,
        )
        print(f"Image: {result['image']}")
        print(f"Predicted grade: {result['grade']}")
        print(
            "Probabilities: "
            + ", ".join(f"{value:.8f}" for value in result["probabilities"])
        )
        print(f"Device: {result['device']}")
        if include_gradcam:
            render_gradcam(
                Path(result["image"]),
                result["gradcam"],
                args.gradcam_output,
                args.show_gradcam,
            )
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
