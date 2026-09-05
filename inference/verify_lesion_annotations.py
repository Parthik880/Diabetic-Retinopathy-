"""Verify external CSV/TIFF pairs without training or modifying source files."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.lesion.dataset import DDRLesionDataset, read_annotation


def inspect_pair(sample):
    image_path, mask_path = sample["image_path"], sample["mask_path"]
    record = {"image": image_path, "mask": mask_path, "lesion": sample["lesion"]}
    try:
        with Image.open(image_path) as image:
            size = image.size
            image.verify()
        array, metadata = read_annotation(mask_path, size)
        record.update(metadata)
        record.update(image_shape=[size[1], size[0], 3], mask_shape=list(array.shape))
    except (OSError, ValueError) as exc:
        record["error"] = str(exc)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="optional JSON audit path")
    parser.add_argument("--overlay", type=Path, help="optional single annotation overlay")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    dataset = DDRLesionDataset(args.csv)
    rows = dataset.samples.to_dict("records")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(inspect_pair, rows))
    good = [r for r in records if "error" not in r]
    errors = [r for r in records if "error" in r]
    # Include examples from each source; prefer different images.
    examples = []
    for source in dataset.samples.source_dataset.unique():
        candidates = set(dataset.samples.loc[
            dataset.samples.source_dataset == source, "mask_path"
        ])
        seen = set()
        for record in good:
            if record["mask"] in candidates and record["image"] not in seen:
                examples.append(record)
                seen.add(record["image"])
                if len(seen) == 5:
                    break
    summary = {
        "csv": str(args.csv.resolve()),
        "retinal_images": dataset.samples.image_path.nunique(),
        "tiff_masks": dataset.samples.mask_path.nunique(),
        "annotation_bytes": sum(Path(p).stat().st_size for p in dataset.samples.mask_path.unique()),
        "successfully_matched_pairs": len(good),
        "errors": errors,
        "missing_masks": 0, "duplicate_masks": 0, "ambiguous_masks": 0,
        "modes": sorted({r["mode"] for r in good}),
        "unique_value_sets": sorted({tuple(r["values"]) for r in good}),
        "image_directories": sorted({str(Path(r["image_path"]).parent) for r in rows}),
        "annotation_directories": sorted({str(Path(r["mask_path"]).parent) for r in rows}),
        "examples": examples,
    }
    # Missing/duplicate/ambiguous CSV paths fail during dataset construction.
    print(json.dumps(summary, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.overlay and good:
        selected = next((r for r in good if max(r["values"]) > 0), good[0])
        with Image.open(selected["image"]) as image:
            original = image.convert("RGB")
        array, _ = read_annotation(selected["mask"], original.size)
        overlay = np.array(original).copy()
        foreground = array > 0
        overlay[foreground] = (
            0.5 * overlay[foreground] + 0.5 * np.array([255, 0, 0])
        ).astype(np.uint8)
        annotated = Image.fromarray(overlay)
        original.thumbnail((800, 600))
        annotated.thumbnail((800, 600))
        panel = Image.new("RGB", (original.width * 2, original.height))
        panel.paste(original)
        panel.paste(annotated, (original.width, 0))
        args.overlay.parent.mkdir(parents=True, exist_ok=True)
        panel.save(args.overlay)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
