# Lesion post-processing audit (before changes)

The deployed MobileNetV3-Large UNet++ returns logits [1,4,768,768], ordered MA, HE, EX, SE. The inference wrapper applies independent sigmoid channels, bilinearly resizes probabilities to original H×W (align_corners=False), and thresholds each channel at 0.50. This pixel threshold is retained.

The source extract_predicted_regions uses SciPy 8-connected labeling, removes components below 3 **original-image** pixels, and optionally caps the number (the integration does not enable the cap). It computes inclusive original-pixel bounds, rounded pixel centroid, component area, mean and maximum probabilities from component pixels only. Regions are ordered by area, then mean probability. No score filter or proximity merging exists. The returned filtered mask is used for TIFF/PNG exports and segmentation CAM targets.

Before this change the reference image 20170629163635747.jpg (2592×1728) yielded 114 regions **after** the existing 3-pixel filter, not necessarily the count of all raw connected components. Cached probabilities permit an exact before/after comparison without modifying weights or rerunning a different model.

Analysis and Compare receive the same per-eye regions via projectPatient. Boxes and Coordinates share that list and an SVG in original-image coordinates; CSS affects display only. Annotation uses separate full-resolution mask layers. Report renders every projected region in its main table and headlines the full count. The new post-processor will preserve raw probabilities and full threshold masks, replace only displayed region lists, and retain an explicit raw audit list.

## Implemented pipeline

`backend/inference/lesion_postprocessing.py` is separate from the unchanged neural network, training, and validation code. It labels the full threshold mask with SciPy 8-connectivity, measures every raw component, filters by area, optionally joins same-class fragments, calculates pixel-area-weighted group scores, and applies the independent display-score threshold. No top-N cap limits detection or coordinate views. The raw and displayed lists are returned alongside count-conservation statistics and effective settings.

The adapter calls the source inference wrapper with minimum area 1 so the exported TIFF, binary PNG, RGBA masks, and segmentation CAM target use the **full threshold mask**, before display-region processing. The model's sigmoid probabilities are bit-identical to the cached pre-change run. This intentionally restores the tiny pixels previously removed by the old 3-pixel wrapper; filtering boxes never removes mask pixels. Separate raw and displayed box/center image exports are available. Neither source photographs nor probability arrays are mutated.

Each region includes stable component ID, class, source component IDs, inclusive bounds, width/height, integer rounded centroid, exact floating centroid, original-pixel area, model-equivalent area, mean and maximum pixel probability. Merged scores use only original component member pixels, weighted by area. Empty gaps inside union bounding boxes never contribute. Each class is processed independently, so overlapping channels cannot merge.

## Configuration and evidence

Configuration: `backend/config/lesion_postprocessing.json`. An optional `RETINA_LESION_POSTPROCESS_CONFIG` path can select another JSON file. Invalid thresholds, unsupported classes, negative sizes, and nonfinite values fail explicitly. Settings are recorded in every result; changing them affects subsequent runs, never cached results silently.

- Pixel threshold: **0.50**, unchanged from the source inference default.
- Region display threshold: **0.50**, independently configurable. The equal initial numbers do not conflate their purposes. Because every thresholded pixel is at least 0.50, this conservative default adds no score-based removals. Higher candidate thresholds are evaluated below, not selected merely to reduce counts.
- Geometry reference: **768×768-equivalent pixels**. Minimum original area is `max(1, ceil(configured_area × original_width × original_height / 768²))`. Distances use anisotropic sampling `(768/H, 768/W)` on original-pixel centers, consistent with the model's square resize.

| Class | Minimum area at model scale | Minimum original pixels for 2592×1728 | Merge distance at model scale |
| --- | ---: | ---: | ---: |
| MA | 0.4 | 4 | 0 (disabled) |
| HE | 2.0 | 16 | 1.0 |
| EX | 0.4 | 4 | 0 (disabled) |
| SE | 4.0 | 31 | 1.0 |

Read-only audit of all 149 DDR valid TIFFs per class found 2,556 MA, 1,342 HE, 1,920 EX, and 349 SE annotation components. Fifth-percentile areas at model scale were respectively 1.05, 3.31, 0.53, and 6.80. The conservative minima lie below these lower-tail values; MA and EX receive subpixel-equivalent minima because both annotations contain very small components. These are exploratory display settings, not a clinically validated operating point. `work/region-size-audit.json` contains the complete size audit.

Merging uses actual minimum component-pixel distance, never bounding-box overlap alone. A local SciPy distance transform finds same-class neighbors; deterministic union-find joins qualifying connected groups. Distance zero disables merging. MA and EX stay separate by default to preserve discrete small lesions. HE/SE permit only a one-model-pixel distance. Transitive groups are possible; their original member IDs remain inspectable. No dilation, gap filling, or merged-box reconstruction alters the mask.

## Same-image results and threshold evaluation

Reference: `resources/test-images/20170629163635747.jpg`, the original 114-region example.

| Step | Count |
| --- | ---: |
| Raw connected components at pixel threshold 0.50 | 116 |
| Previous displayed count after legacy 3-pixel filter | 114 |
| Removed by new class-specific area filter | 5 |
| Component-count reduction from merging (two HE components into one) | 1 |
| Removed by region-score threshold | 0 |
| Final displayed regions | **110** |

Per-class raw → displayed: MA 47 → 44, HE 63 → 61, EX 3 → 3, SE 3 → 2. Count conservation: 116 − 5 − 1 − 0 = 110. New post-processing took approximately **0.19 seconds**, compared with approximately 18 seconds for the complete integration verification including model startup, attribution, image exports, input checks, and restoration.

| Region threshold (pixel threshold fixed at 0.50) | Displayed regions | MA component-proxy recall | HE component-proxy recall |
| --- | ---: | ---: | ---: |
| 0.40 | 110 | 0.47 | 0.70 |
| 0.50 | 110 | 0.47 | 0.70 |
| 0.60 | 99 | 0.41 | 0.70 |
| 0.70 | 77 | 0.31 | 0.63 |
| 0.80 | 57 | 0.22 | 0.59 |
| 0.90 | 12 | 0.00 | 0.19 |

This image does **not** support aggressively reducing the display to 18 regions while preserving small-lesion sensitivity. The current choice prioritizes retention. Counts remain substantial because many predicted regions are larger than the conservative size minima. Further operating-point selection needs representative held-out evaluation; the result is not described as 110 confirmed lesions.

The evaluation script accepts cached response JSON and explicit optional `--ground-truth CLASS=path.tif` pairs. It measures raw pixel Dice/IoU/recall/precision and the union of retained member pixels. Raw pixel metrics remain constant across region thresholds. For region metrics it uses one-to-one maximum bipartite matching of predicted member masks to 8-connected annotation masks at configurable IoU (default 0.10), and reports component-proxy precision/recall and unmatched predicted regions per image. These are **annotation-component proxies**, not verified lesion-instance metrics. EX/SE annotations for this sample are empty; undefined recall is JSON null. Missing annotations remain unmeasured and are never treated as negatives. Dataset membership/independence from checkpoint training is not established, so these are exploratory same-image measurements. Full metrics and exact GT paths are in `work/postprocessing-evaluation.json`.

## UI and report

Analysis shows displayed count first and raw connected count second, with mean-probability wording and clinician-interpretation text. Detection defaults to retained regions. “View all raw model regions” explicitly switches to Raw Model Output; Boxes and Coordinates use the exact same IDs/list in either mode. Selected-region details include original-pixel area, maximum probability, and source IDs. Compare uses the same settings for both eyes and shows each eye's separate raw/display count. The annotation legend explicitly states that region filters do not affect the full mask.

Report shows up to six retained regions ranked by mean probability, not clinical importance, followed by a full retained-region coordinate appendix starting on a new printed page. No report row is described as clinically confirmed. Raw components remain available in Analysis and exported JSON. Print styling hides fixed app navigation so it cannot obscure table rows, repeats table headers, and avoids splitting rows.

## Validation and modified files

- Seven synthetic tests: tiny removal, area/score retention, exact coordinates, member-pixel weighted merge score, class isolation, distance exclusion, resolution scaling, conservative MA behavior, threshold independence, empty inputs, invalid values, and probability preservation.
- Full real CPU/offline API integration passed; strict checkpoint loading, invalid inputs, failure handling, and model reuse remain intact.
- `test-postprocessing-regression.py` compares the exact original cached run to a new inference: bit-identical segmentation probabilities, unchanged predicted grade, and count conservation.
- Artifact test verifies full `probability >= pixel_threshold` mask equality, TIFF/PNG/alpha equality, and original-photo preservation.
- Electron smoke checks both eyes, retained and raw box counts, identical Boxes/Coordinates IDs, report highlights/appendix, synchronized Compare, narrow layouts, and exactly two inference requests for two images. TypeScript checking and production build pass.
- All eight pages of the exported OD demonstration PDF were rendered and inspected: six highlights in the main report, full 125-row retained appendix, repeated table headers, and no fixed navigation over the content. The main report occupies two pages including its sign-off; the appendix begins on page three. No renderer runtime errors were recorded.

New files: `backend/config/lesion_postprocessing.json`, `backend/inference/lesion_postprocessing.py`, `backend/scripts/evaluate_lesion_postprocessing.py`, `backend/tests/test_lesion_postprocessing.py`, `scripts/test-postprocessing-regression.py`, `frontend/src/components/RegionCounts.tsx`, `frontend/src/components/RegionTable.tsx`, and this document.

Modified: `backend/inference/lesions.py`; `frontend/src/api.ts`, `types.ts`, `index.css`; `AnalysisScreen.tsx`, `AnalysisVisualization.tsx`, `CompareScreen.tsx`, `ReportScreen.tsx`, `TopAppBar.tsx`, `BottomNavBar.tsx`; `desktop/main.cjs`, `desktop/visual-smoke.cjs`; `scripts/test-visual-artifacts.py`; status/readme/inventory documentation. No neural architecture, model weights, training code, or validation model code changed. No Git push.

Commands actually used from `C:\Users\ADMIN\Music\retina-desktop\desktop-app`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\python.exe scripts/test-integration.py
.\.venv\Scripts\python.exe scripts/test-visual-artifacts.py
.\.venv\Scripts\python.exe scripts/test-postprocessing-regression.py

$labelRoot = 'C:\Users\ADMIN\Desktop\models\DDR-dataset\lesion_segmentation\valid\segmentation label'
.\.venv\Scripts\python.exe backend/scripts/evaluate_lesion_postprocessing.py --result work/runs/f8d8bd0cf8c44399b4ceeee0afabfeab/response.json --ground-truth "MA=$labelRoot\MA\20170629163635747.tif" --ground-truth "HE=$labelRoot\HE\20170629163635747.tif" --ground-truth "EX=$labelRoot\EX\20170629163635747.tif" --ground-truth "SE=$labelRoot\SE\20170629163635747.tif" --output work/postprocessing-evaluation.json

npm.cmd --prefix frontend run lint
npm.cmd run build
$env:RETINA_SMOKE='1'
$env:RETINA_VISUAL_SMOKE='1'
npm.cmd run desktop
Remove-Item Env:RETINA_SMOKE, Env:RETINA_VISUAL_SMOKE
```

The first evaluation used `work/integration-test.json` while it still referenced the same pre-change run; the explicit cached response above preserves that input for repeatability. For normal use, close an already running older app and run `scripts/start-desktop.ps1` to load the updated build/backend. Smoke tests use a separate Electron profile so they do not interrupt that existing app.
