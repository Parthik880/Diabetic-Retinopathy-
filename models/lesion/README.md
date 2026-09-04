# UNet++ lesion inference

This package preserves the trained MobileNetV3-Large UNet++ model and adds
inference-only localization metadata and visualizations. It does not alter the
architecture, preprocessing, channel order, or learned weights.

## Output channels

The channel mapping is inherited from the training dataset:

```text
0 = MA (microaneurysms)
1 = HE (hemorrhages)
2 = EX (hard exudates)
3 = SE (soft exudates)
```

Inference keeps the raw `[1, 4, 768, 768]` logits, applies sigmoid once, then
bilinearly resizes probability maps back to the original image dimensions.
Thresholding occurs in that original coordinate space. The default threshold is
`0.5` and is configurable.

## Predicted regions and coordinates

Binary masks use 8-connected components. The conservative default
`min_component_area=3` removes isolated one- and two-pixel noise while retaining
small predicted microaneurysms. `max_regions_per_class` is optional; when set,
components are ordered by area descending and then mean probability descending.

Each estimated region includes:

- inclusive pixel bounding box `[x_min, y_min, x_max, y_max]`;
- normalized bounding box and center coordinates in `[0,1]`;
- integer center, width, height, and area in original-image pixels;
- mean and maximum model probability inside the component.

These are **predicted lesion coordinates** derived from model masks. They are not
ground-truth locations, and region probabilities are not clinically validated
confidence scores.

## Grad-CAM

The target layer is the last convolution of the final UNet++ decoder block:

```text
conv0_3.layers[3]
```

For each detected lesion class, the Grad-CAM objective is the mean logit for that
class over retained predicted-lesion pixels. A class with no retained predicted
region is skipped and marked `No lesion predicted`; no heatmap is fabricated.
Grad-CAM supplements the model output and does not replace segmentation:

```text
segmentation mask -> primary lesion localization
bounding boxes / coordinates -> derived localization summary
Grad-CAM -> secondary feature-attribution visualization
```

## Generated files

The default root is `inference/outputs/lesion/`:

```text
masks/<image>_MA_mask.png ... <image>_SE_mask.png
probability_maps/<image>_MA_probability.png
probability_maps/<image>_MA_probability.npy
gradcam/<image>_MA_gradcam.png ... <image>_SE_gradcam.png
json/<image>_lesions.json
<image>_lesion_overlay.png
<image>_lesion_boxes.png
<image>_lesion_centers.png
<image>_analysis.png
```

The NPY files retain numeric probability maps; PNGs are visual heatmaps. The
combined overlay, boxes, center points, and dashboard are derived from filtered
predicted masks. All returned Python metadata is JSON-serializable.

## Usage

```powershell
python inference/lesion_inference.py `
  --image path\to\fundus.jpg `
  --threshold 0.5 `
  --min-component-area 3
```

Reusable API:

```python
from models.lesion.predict import predict_lesions

result = predict_lesions(
    "fundus.jpg",
    threshold=0.5,
    min_component_area=3,
    max_regions_per_class=None,
)
```
