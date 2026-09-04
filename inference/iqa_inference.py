"""Command-line inference for raw pretrained TOPIQ-NR scores."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.iqa.model import DEFAULT_CHECKPOINT_PATH
from models.iqa.predict import predict_iqa


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict a raw TOPIQ-NR image-quality score."
    )
    parser.add_argument("--image", required=True, type=Path, help="path to one image")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT_PATH,
        help=f"local TOPIQ checkpoint (default: {DEFAULT_CHECKPOINT_PATH})",
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        help="inference device (default: CUDA when available, otherwise CPU)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = predict_iqa(
            args.image,
            checkpoint_path=args.checkpoint,
            device=args.device,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Image: {result['image']}")
    print(f"Model: {result['metric']}")
    print(f"Metric ID: {result['metric_id']}")
    print(f"Checkpoint: {result['checkpoint_path']}")
    print(f"IQA Score: {result['score']:.6f}")
    print(f"Device: {result['device']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
