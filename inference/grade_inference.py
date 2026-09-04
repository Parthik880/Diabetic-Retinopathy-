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
        "--gradcam-output-dir",
        type=Path,
        help="Grad-CAM directory (default: inference/outputs/gradcam)",
    )
    parser.add_argument(
        "--no-gradcam",
        action="store_true",
        help="skip Grad-CAM generation and saving",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = predict_grade(
            args.image,
            checkpoint_path=args.checkpoint,
            device=args.device,
            save_gradcam=not args.no_gradcam,
            gradcam_output_dir=args.gradcam_output_dir,
        )
        print(f"Image: {result['image_path']}")
        print("\nClassifier logits:")
        print(result["logits"])
        print("\nClassifier probabilities:")
        print(result["probabilities"])
        print(f"\nPredicted grade: {result['predicted_grade']}")
        print(f"Confidence: {result['confidence']:.6f}")
        print(f"Device: {result['device']}")
        print(f"\nGrad-CAM: {result['gradcam_path'] or 'disabled'}")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
