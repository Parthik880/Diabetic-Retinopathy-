"""Command-line UNet++ lesion localization and visualization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.lesion.model import DEFAULT_CHECKPOINT_PATH
from models.lesion.predict import (
    DEFAULT_MIN_COMPONENT_AREA,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_THRESHOLD,
    predict_lesions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict and visualize four retinal lesion channels"
    )
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--min-component-area",
        type=int,
        default=DEFAULT_MIN_COMPONENT_AREA,
        help="minimum retained component area in original-image pixels (default: 3)",
    )
    parser.add_argument(
        "--max-regions-per-class",
        type=int,
        help="optional largest-component limit for each lesion class",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--no-gradcam", action="store_true", help="skip per-lesion Grad-CAM"
    )
    parser.add_argument(
        "--no-probability-maps",
        action="store_true",
        help="skip probability PNG and numeric NPY files",
    )
    parser.add_argument(
        "--no-analysis", action="store_true", help="skip the dashboard image"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = predict_lesions(
            args.image,
            checkpoint_path=args.checkpoint,
            device=args.device,
            threshold=args.threshold,
            min_component_area=args.min_component_area,
            max_regions_per_class=args.max_regions_per_class,
            output_dir=args.output_dir,
            save_probability_maps=not args.no_probability_maps,
            generate_gradcam=not args.no_gradcam,
            save_analysis=not args.no_analysis,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Image: {Path(result['image']).name}")
    print(f"Dimensions: {result['image_width']}x{result['image_height']}")
    print(f"Logits: {result['logits_shape']}")
    print(f"Threshold: {result['threshold']:.2f}")
    print(f"Minimum component area: {args.min_component_area} pixels")
    for lesion, metadata in result["lesions"].items():
        print(f"\n{lesion}:")
        print(f"Regions: {metadata['num_regions']}")
        print(f"Total area: {metadata['total_area_pixels']} pixels")

    print(f"\nOverlay: {result['combined_overlay_path']}")
    print(f"Bounding boxes: {result['bounding_box_image_path']}")
    print(f"Centers: {result['center_point_image_path']}")
    print(f"Analysis: {result['analysis_image_path'] or 'disabled'}")
    print(f"JSON: {result['json_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
