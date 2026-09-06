# Analysis visualization extension

The subsequent lesion post-processing extension is documented in LESION_POSTPROCESSING.md. Its separate raw/displayed region lists and full threshold masks supersede the original 3-pixel-mask behavior described below.

The existing green clinical interface is preserved. Capture, Analysis, Compare, Report, patient selection, New Patient, Cloud Sync toggle, IQA, grading, inference run IDs, and diagnosis/review controls remain available. The Cloud Sync UI retains its original label; its tooltip states that no cloud service is connected.

## Four views inside Analysis

1. **Grade Analysis** (default): Original / Grad-CAM / Overlay, plus overlay opacity. Uses the actual predicted-class gradient from the loaded ConvNeXt Tiny, not a lesion mask or probability map.
2. **Lesion Grad-CAM**: select MA, HE, EX, or SE from the actual response. Select Grad-CAM for segmentation attribution, or Probability for the real per-pixel sigmoid map. These mechanisms have separate assets, legends, and explanations. Original, heatmap-only, and overlay modes are available.
3. **Lesion Detection**: Boxes / Coordinates. Boxes are derived from connected segmentation regions. Labels appear on hover, keyboard focus, or selection to reduce clutter. Selection shows mean pixel probability, original-pixel center, inclusive bounds, width, height, and eye. Coordinates adds numeric X/Y grid labels and a pointer readout.
4. **Lesion Annotation**: Original / Mask / Overlay, with class checkboxes and opacity. These are predicted pixel masks, not manually annotated ground truth. Transparent PNG layers preserve mask pixels and class colors.

The right diagnostic card remains beside the visualization at desktop widths and below it at narrow widths. The full region list is retained. Selecting a region in the list opens Detection. Tab navigation supports arrow keys, Home, and End.

## Actual Grad-CAM targets

**Grade:** `model.features.7.2.block.0` (Python access `model.model.features[-1][-1].block[0]`). Inspection of the deployed torchvision ConvNeXt Tiny identifies this as its final Conv2d: a 7×7 depthwise convolution with 768 channels. It retains spatial feature maps before the block's channel MLP, global pooling, and five-class classifier. This is deliberately more specific than the source helper's default entire final CNBlock. The existing GradCAM implementation is reused with this explicit inspected target. Gradients are enabled for the predicted-class **pre-softmax logit**. Spatially averaged gradients weight activations; ReLU and normalization produce a relative attention map. The map is bilinearly resized to original H×W, without axes, padding, or modifying the original image. Hooks are removed and parameter gradients cleared after each run. Weights are never updated.

**Lesions:** `conv0_3.layers[3]`, the final convolution in the last UNet++ decoder block before the output head. The existing `SegmentationGradCAM` implementation is reused unchanged. Its objective is the mean selected class-channel logit over retained predicted-lesion pixels. This is **segmentation Grad-CAM**, not standard classifier Grad-CAM. A class with no retained target pixels has no generated CAM and displays the backend's explicit unavailable explanation. A zero-valued attribution result remains zero; no artificial activation is added.

**Probability alternative:** independent sigmoid probabilities from the segmentation output, bilinearly resized before thresholding in the original source wrapper. These values are saved separately and never labeled Grad-CAM. Backend metadata records the method, target, objective, dimensions, and paths.

## Coordinate and mask alignment

`AnalysisVisualization` measures the image stage with ResizeObserver. For an original image W×H and a stage Sx×Sy, it uses `scale = min(Sx/W, Sy/H)` and centers a plane of W×scale by H×scale. The original image, attention layers, mask layers, and SVG overlay share exactly this plane. Compare panels therefore have equal outer dimensions without distorting photographs with different aspect ratios.

SVG viewBox is `0 0 W H`. Region x/y/width/height are original integer pixel values; centers and inclusive x_max/y_max are taken from the backend, not recomputed from CSS. The pointer conversion is `floor((clientX-plane.left)/plane.width*W)` (and Y equivalent), clamped to `[0,W-1]` and `[0,H-1]`. Grid labels and detail panels use these original coordinates.

The binary PNG is byte-equivalent in decoded pixels to the original 0/255 TIFF. The RGBA browser layer has class-colored RGB and alpha exactly equal to the binary mask. Its raster is original W×H, with pixelated rendering to avoid interpolating categorical masks. Heatmap rasterization uses the actual map values and a jet color lookup; continuous maps use smooth scaling. No overlay is permanently drawn onto the source image. API `image_url` points to the original decoded RGB image saved before inference overlays.

## State and Compare

Each patient's `leftEye.result` and `rightEye.result` contains that eye's IQA, grade/CAM, lesion channel maps/masks/regions, image dimensions, and run ID. `leftEye.review` and `rightEye.review` separately hold confirmation/flag state. Upload/reanalysis invalidates only that eye's old result. The frontend sends multipart `eye=OS|OD`; the backend echoes it, and the frontend rejects mismatches.

Compare always places OS left and OD right on desktop, stacked OS then OD at narrow widths. One view setting drives both panels: Grade Grad-CAM, Lesion Heatmap, Lesion Detection, or Lesion Annotation. Class, mechanism, image mode, opacity, and mask toggles are synchronized. Selection of an individual region is independent per panel. Each panel displays its own grade, confidence, IQA, lesion counts, and run ID. The bilateral summary compares numeric predicted grades only; missing grades remain unavailable, equal grades are reported as equal, and no progression or treatment inference is made. Report remains a separate page.

## API and performance

`POST /api/analyze` still accepts multipart `file`, now with optional `eye` limited to OS/OD. It adds `eye`, `image_url`, `grading.gradcam`, and per-class `lesions.lesions[code].attention`, `probability_heatmap`, `mask_png_path`, and `mask_layer_path`. Existing prediction/region fields remain. Artifacts are served by the existing `/artifacts` route.

All visualizations are generated once during that inference run and cached as artifacts and per-eye React state. Switching tabs, classes, modes, opacity, or Compare never invokes another model. The model registry still loads once and serializes requests to protect shared hooks and memory. Attribution/export makes analyze slower and increases disk use compared with prediction-only inference. No retraining or restoration is inserted into analysis.

## Verification

- Backend real-image inference passed with external network access blocked and all four models loaded.
- `scripts/test-visual-artifacts.py` verifies unchanged original RGB pixels, correct grade target/class, distinct grade CAM/lesion CAM/probability arrays, original raster dimensions, TIFF-to-PNG mask equality, alpha alignment, and inclusive box dimensions.
- `desktop/visual-smoke.cjs` runs two different actual retinal photographs through the existing Capture UI, checks all four Analysis views for both eyes, verifies original-pixel selected-region and pointer values, cycles annotation modes, and tests independent confirmation state.
- Compare checks cover all synchronized views, actual per-eye grade ownership, equal desktop panel dimensions, and 390px stacked/narrow layouts. Exactly two analyze requests were observed for two eyes; view changes caused none. No renderer runtime errors were recorded.
- TypeScript checking and production build pass. The Impeccable mechanical detector returned no findings for the three changed view components.

Evidence: `work/visual-artifact-test.json`, `work/visual-smoke.json`, `work/visual-analysis-*.png`, and `work/visual-compare-*.png`.

## Current limitations

No requested visualization is a placeholder: grade Grad-CAM, segmentation Grad-CAM for classes with retained regions, probability maps, derived boxes, and masks all use real model outputs. Absent-class CAMs and pre-extension runs without new assets show unavailable states. No independent object-detector output, manual annotation editor, or ground-truth annotation is claimed. CUDA, packaged distribution, and clinical validity remain outside the tested scope.

## Files changed for this extension

- `backend/app/main.py`: eye metadata and visualization-aware grading call.
- `backend/inference/grading.py`: explicit final-convolution Grad-CAM and full-resolution artifact metadata.
- `backend/inference/lesions.py`: source segmentation CAM/probability generation and browser mask layers.
- `backend/models/lesion/predict.py`: retain normalized CAM NPY values alongside original exports.
- `backend/utils/visualization.py`: new pixel-aligned map and mask exporters.
- `frontend/src/api.ts`, `types.ts`, `App.tsx`: extended response types, eye echo validation, eye-specific reviews and result ownership.
- `frontend/src/components/AnalysisScreen.tsx`: four in-page views with preserved diagnostic card and list.
- `frontend/src/components/AnalysisVisualization.tsx`: shared controls, overlay plane, coordinates, and selection details.
- `frontend/src/components/CompareScreen.tsx`: synchronized bilateral comparison and summary.
- `frontend/src/components/TopAppBar.tsx`: retain Cloud Sync UI label with truthful local-only tooltip.
- `desktop/main.cjs`, `desktop/visual-smoke.cjs`: selectable visualization integration harness.
- `scripts/test-visual-artifacts.py`: model artifact integrity checks.
- Documentation: this file, README.md, INTEGRATION_STATUS.md, MODEL_MANIFEST.md, FILES_CREATED.md.

Launch:

```powershell
cd C:\Users\ADMIN\Music\retina-desktop\desktop-app
.\scripts\start-desktop.ps1
```

Run the visualization harness:

```powershell
$env:RETINA_SMOKE='1'
$env:RETINA_VISUAL_SMOKE='1'
.\scripts\start-desktop.ps1
Remove-Item Env:RETINA_SMOKE, Env:RETINA_VISUAL_SMOKE
```
