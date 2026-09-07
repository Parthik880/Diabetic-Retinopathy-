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
masks/<image>_MA_mask.tiff ... <image>_SE_mask.tiff
probability_maps/<image>_MA_probability.png
probability_maps/<image>_MA_probability.npy
gradcam/<image>_MA_gradcam.png ... <image>_SE_gradcam.png
json/<image>_lesions.json
<image>_lesion_overlay.png
<image>_lesion_boxes.png
<image>_lesion_centers.png
<image>_analysis.png
```

Binary masks are single-channel TIFFs with 0 background and 255 foreground.
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

## External TIFF annotations

Set DR_LESION_CSV to the external CSV before importing the dataset, or pass
csv_path explicitly. Required columns are image_path, mask_path, lesion_class,
source_dataset, and original_split. Relative paths resolve against the CSV
directory. The CSV is the authoritative mapping; row order is never used to
match files. Each image may have a separate binary annotation for MA, HE, EX,
and SE. An absent class annotation is not assumed to be a negative label.

DDR TIFFs use grayscale (L) values 0/255; IDRiD TIFFs use palette (P) indices
0/1. The reader inspects the original pixel values without RGB conversion.
Only binary 0/1 or 0/255 annotations are supported by this per-lesion adapter;
multi-class labels require an explicit mapping and are rejected instead of
being silently merged. Multi-page and unknown multichannel masks are also rejected. The inspected
IDRiD_81_EX.tif exception encodes foreground as opaque red and background as
opaque black. Only that explicit RGBA encoding is supported: red becomes the
binary target after validating green/blue are zero and alpha is 255 everywhere.
The original file is never changed.

The adapter rejects missing files, duplicate rows, conflicting image/class
assignments, unreadable TIFFs, and original image/mask dimension mismatches.
Fundus images resize bilinearly; masks resize with nearest-neighbor only.
ImageNet normalization applies exclusively to the retinal image.
The existing tuple (image, mask, lesion_class) remains the default.
return_metadata=True returns image, mask, lesion_class, image_path, mask_path.

Training/validation use the image as the network input and the corresponding
annotation as the supervision target for its lesion channel. The mask tensor is
[1,768,768]; the selected model produces four lesion channels. Annotation TIFFs
are never supplied to IQA or required for lesion prediction on new images.
No training is performed by the verification command.

```powershell
python inference/verify_lesion_annotations.py --csv C:\path\to\lesion.csv --report audit.json --overlay lesion_annotation_check.png
python -m unittest test_lesion_dataset -v
```

The verifier checks every CSV pair, prints original shapes, modes and unique
values for up to five distinct images per source dataset, and optionally saves
one side-by-side image/annotation overlay. Path/mapping errors fail at dataset
construction; per-file decoding/value/dimension failures are listed in the
audit and return a nonzero exit code. Files absent from the CSV are outside
this audit's scope.

Large images, TIFF annotations, and dataset CSVs remain external to Git.
The unchanged selected checkpoint is stored locally at
checkpoints/lesion_mobilenetv3_unetpp_epoch_018_best_dice.pth;
it is not committed to Git. --checkpoint still accepts an
explicit alternative path.
