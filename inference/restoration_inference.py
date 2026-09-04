"""Command-line NAFNet image restoration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.restoration.model import DEFAULT_CHECKPOINT_PATH
from models.restoration.predict import DEFAULT_OUTPUT_DIR, restore_image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore one image with NAFNet")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = restore_image(
            args.image,
            checkpoint=args.checkpoint,
            device=args.device,
            output_dir=args.output_dir,
        )
        print(f"Input: {result['image_path']}")
        print(f"Restored image: {result['output_path']}")
        print(f"Output dimensions: {result['width']}x{result['height']}")
        print(f"Device: {result['device']}")
        if result["checkpoint"].get("generic_pretrained"):
            print("Checkpoint: generic pretrained NAFNet; NOT retinal fine-tuned")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
