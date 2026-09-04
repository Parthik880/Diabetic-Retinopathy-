"""Command-line UNet++ lesion prediction and mask export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.lesion.model import DEFAULT_CHECKPOINT_PATH
from models.lesion.predict import DEFAULT_THRESHOLD, predict_lesions


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "outputs" / "lesion"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict four retinal lesion masks")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = predict_lesions(
            args.image,
            checkpoint_path=args.checkpoint,
            device=args.device,
            threshold=args.threshold,
        )
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Image: {result['image_path']}")
        print(f"Device: {result['device']}")
        print(f"Threshold: {result['threshold']}")
        for lesion, prediction in result["lesions"].items():
            output_path = output_dir / f"{Path(args.image).stem}_{lesion}_mask.png"
            pixels = prediction["mask"].astype(np.uint8) * 255
            Image.fromarray(pixels, mode="L").save(output_path)
            print(f"{lesion} (channel {prediction['channel']}): {output_path}")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
