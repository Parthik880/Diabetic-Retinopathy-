"""Connected-component summaries for predicted lesion segmentation masks."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


CONNECTIVITY_8 = np.ones((3, 3), dtype=np.uint8)


def _normalized(value: int, extent: int) -> float:
    """Normalize an inclusive pixel coordinate to [0, 1]."""
    return round(float(value) / max(extent - 1, 1), 6)


def extract_predicted_regions(
    binary_mask: np.ndarray,
    probability_map: np.ndarray,
    min_component_area: int = 3,
    max_regions_per_class: int | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Filter and describe 8-connected components in original-image space.

    Components are ordered by descending area, then descending mean probability.
    When ``max_regions_per_class`` is set, only the first N components are retained
    in both the returned mask and metadata.
    """
    mask = np.asarray(binary_mask, dtype=bool)
    probabilities = np.asarray(probability_map, dtype=np.float32)
    if mask.ndim != 2 or probabilities.shape != mask.shape:
        raise ValueError("binary mask and probability map must be matching 2D arrays")
    if min_component_area < 1:
        raise ValueError("min_component_area must be at least 1")
    if max_regions_per_class is not None and max_regions_per_class < 1:
        raise ValueError("max_regions_per_class must be at least 1 when provided")

    image_height, image_width = mask.shape
    labels, component_count = ndimage.label(mask, structure=CONNECTIVITY_8)
    slices = ndimage.find_objects(labels, max_label=component_count)
    components: list[tuple[int, dict]] = []

    for label_id, component_slice in enumerate(slices, start=1):
        if component_slice is None:
            continue
        y_slice, x_slice = component_slice
        local_component = labels[component_slice] == label_id
        area = int(local_component.sum())
        if area < min_component_area:
            continue

        local_y, local_x = np.nonzero(local_component)
        x_min = int(x_slice.start)
        y_min = int(y_slice.start)
        x_max = int(x_slice.stop - 1)
        y_max = int(y_slice.stop - 1)
        center_x = int(np.rint(x_min + float(local_x.mean())))
        center_y = int(np.rint(y_min + float(local_y.mean())))
        center_x = min(max(center_x, 0), image_width - 1)
        center_y = min(max(center_y, 0), image_height - 1)
        component_probabilities = probabilities[component_slice][local_component]

        region = {
            "x_min": x_min,
            "y_min": y_min,
            "x_max": x_max,
            "y_max": y_max,
            "center_x": center_x,
            "center_y": center_y,
            "width": int(x_max - x_min + 1),
            "height": int(y_max - y_min + 1),
            "bbox_pixels": [x_min, y_min, x_max, y_max],
            "bbox_normalized": [
                _normalized(x_min, image_width),
                _normalized(y_min, image_height),
                _normalized(x_max, image_width),
                _normalized(y_max, image_height),
            ],
            "center_pixels": [center_x, center_y],
            "center_normalized": [
                _normalized(center_x, image_width),
                _normalized(center_y, image_height),
            ],
            "area_pixels": area,
            "mean_probability": float(component_probabilities.mean()),
            "max_probability": float(component_probabilities.max()),
        }
        components.append((label_id, region))

    components.sort(
        key=lambda item: (
            -item[1]["area_pixels"],
            -item[1]["mean_probability"],
            item[1]["y_min"],
            item[1]["x_min"],
        )
    )
    if max_regions_per_class is not None:
        components = components[:max_regions_per_class]

    filtered_mask = np.zeros_like(mask)
    regions = []
    for region_id, (label_id, region) in enumerate(components, start=1):
        filtered_mask[labels == label_id] = True
        region["region_id"] = region_id
        regions.append(region)
    return filtered_mask, regions
