# Retinal AI Model Pipeline

Implementation and inference flow for retinal image quality assessment, lesion segmentation, restoration, and diabetic retinopathy analysis.

## Pipeline overview

```text
Fundus image
    |
Image quality assessment -> Good / Usable / Reject
    |
Optional restoration -> reassess quality
    |
Selected original or restored retinal image
    |-----------------------|
Lesion segmentation    DR grade classification
    |-----------------------|
Final application output
```

Each model has a separate PyTorch module and reusable prediction wrapper.
An application can combine their results using the flow above; this branch
provides individual Python APIs and CLIs, with no combined runner or frontend.
The application decides when to restore, continue, or request another image.
Lesion segmentation and grading both receive the selected retinal image;
the grade classifier does not consume segmentation masks.

## IQA: EfficientNet-B0 + MLP

**Code:** `models/iqa/model.py` defines `EfficientNetIQA`;
`models/iqa/inference.py` defines `EfficientNetIQAService`;
`models/iqa/predict.py` exposes `predict_iqa` for image paths.

**Input:** an RGB retinal image. The service accepts a PIL image and converts
it to RGB. Preprocessing resizes to **224 x 224**, converts to a tensor, and
applies ImageNet normalization: mean `[0.485, 0.456, 0.406]`,
std `[0.229, 0.224, 0.225]`. The batched input is `[B, 3, 224, 224]`.

**Implementation:** a frozen ImageNet-pretrained torchvision EfficientNet-B0
runs its feature layers and average pooling. Flattening produces **1280
features per image**. Those features, rather than image pixels, enter this head:

```python
class EfficientNetIQA(nn.Module):
    def __init__(self, num_classes=3):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(1280, 128),
            nn.ReLU(),
            nn.Dropout(0.30),
            nn.Linear(128, num_classes)
        )

    def forward(self, x):
        return self.network(x)
```

The classifier directly produces three logits. In evaluation mode, dropout
is disabled. The service loads the head strictly from
`model/checkpoints/final_efficientnet_iqa.pth`, whose saved fields include
`model_state_dict` and `temperature`.

```text
1280 features -> Linear(1280,128) -> ReLU -> Dropout(0.30) -> Linear(128,3)
3 logits -> divide by saved temperature -> softmax -> class probabilities
         -> argmax -> 0: Good / 1: Usable / 2: Reject
```

**Output:** `class_id`, `quality`, `confidence`, and a `probabilities`
dictionary keyed by Good, Usable, Reject. Confidence is the largest
temperature-calibrated probability. Path-based predictions also include
image, model, checkpoint, and device metadata.

Construct the service once at application startup and reuse it:

```python
from models.iqa import EfficientNetIQAService, predict_iqa

iqa = EfficientNetIQAService()
quality = predict_iqa("fundus.jpg", model=iqa)
# For a PIL upload/camera image: quality = iqa.predict(image)
```

Calls to `predict_iqa` without an explicit service cache it by checkpoint/device.

## Lesion segmentation: MobileNetV3-Large UNet++

**Code:** `models/lesion/model.py` implements `LesionUNetPlusPlus`;
`models/lesion/predict.py` exposes `predict_lesions`.
`postprocess.py` extracts regions and `visualization.py` saves artifacts.

**Input:** a retinal image path. RGB conversion, bilinear resize to
**768 x 768**, tensor conversion, and ImageNet normalization produce
`[1, 3, 768, 768]`.

**Implementation:** MobileNetV3-Large encoder features feed a four-level
nested UNet++ decoder. The selected checkpoint,
`model/checkpoints/epoch_018_best_dice.pth`, produces logits shaped
`[1, 4, 768, 768]`, with channels:

| Channel | Lesion |
| --- | --- |
| 0 | MA: microaneurysms |
| 1 | HE: hemorrhages |
| 2 | EX: hard exudates |
| 3 | SE: soft exudates |

Sigmoid converts logits to independent per-lesion probabilities. Probability
maps are resized to the original image dimensions before thresholding
(default `0.5`). Connected regions smaller than three pixels are removed
by default; both settings are configurable.

**Output:** a dictionary and JSON file containing per-class detections,
region counts, area, bounding boxes, centers, probability statistics, and
artifact paths. Coordinates refer to the original image. Grad-CAM is optional
and is skipped for a class with no retained lesion.

```python
from models.lesion.predict import predict_lesions

lesions = predict_lesions("fundus.jpg")
ma_regions = lesions["lesions"]["MA"]["regions"]
```

The dataset adapter in `models/lesion/dataset.py` uses explicit CSV image/mask
pairs for training or validation. Each TIFF is a supervision target for one
lesion channel; it is not an inference input. The adapter preserves categorical
values, validates original dimensions, and resizes masks with nearest-neighbor
interpolation. TIFF annotations never enter IQA.

## Optional restoration: NAFNet

**Code:** `models/restoration/model.py` constructs the vendored network under
`models/restoration/nafnet/`; `predict.py` exposes `restore_image`.

**Input:** a retinal image path, converted to RGB float values in `[0,1]`.
The tensor is `[1, 3, H, W]`: no fixed-size resize or ImageNet normalization.

**Implementation:** width-32 NAFNet uses encoder blocks `[2,2,4,8]`,
12 middle blocks, and decoder blocks `[2,2,2,2]`. Internal padding supports
the network's spatial requirements, and output is cropped to the original size.
The default checkpoint is `checkpoint/restoration/NAFNet-SIDD-width32.pth`.

**Output:** a restored RGB array, a saved PNG path, dimensions, and
device/checkpoint metadata. The application can pass that PNG back to IQA
and, if it chooses to proceed, to lesion segmentation and grading.

```python
from models.restoration.predict import restore_image

restoration = restore_image("fundus.jpg")
restored_quality = predict_iqa(restoration["output_path"], model=iqa)
```

## DR grade classification: ConvNeXt Tiny

**Code:** `models/grade/model.py` retains the `Convextnet` class;
`models/grade/predict.py` exposes `predict_grade`.

**Input:** a retinal image path, converted to RGB, resized to **224 x 224**,
converted to a tensor, and ImageNet-normalized: `[1, 3, 224, 224]`.

**Implementation:** torchvision ConvNeXt Tiny has its final linear classifier
replaced with five outputs. The loader strictly loads
`checkpoint/grade/convnext_tiny.pth`. Softmax converts the five logits to
probabilities; argmax selects grade **0, 1, 2, 3, or 4**.

**Output:** five logits, five probabilities, `predicted_class`,
`predicted_grade`, `confidence`, and an optional `gradcam_path`.
Grade Grad-CAM is saved by default and can be disabled.

```python
from models.grade.predict import predict_grade

grade = predict_grade("fundus.jpg", save_gradcam=True)
```

All wrappers support CPU and CUDA. Grade, lesion, and restoration accept a
loaded `model` for reuse across images. Grade/restoration checkpoint roots
can be set with `DR_CHECKPOINT_DIR`; IQA and lesion default to the committed
files under `model/checkpoints/`.

## What the application receives and displays

The application combines the returned dictionaries and artifact paths:

| Result | What can be displayed |
| --- | --- |
| IQA | Good / Usable / Reject, confidence, three probabilities |
| Restoration, when used | Restored image and its reassessed quality |
| Lesions | Colored overlay, per-class regions, boxes, centers, and optional Grad-CAM |
| DR grade | Grade 0-4, confidence, five probabilities, and optional Grad-CAM |

Lesion outputs default to `inference/outputs/lesion/`:

```text
masks/<image>_MA_mask.tiff ... <image>_SE_mask.tiff
probability_maps/<image>_MA_probability.png ... <image>_SE_probability.png
probability_maps/<image>_MA_probability.npy ... <image>_SE_probability.npy
gradcam/<image>_MA_gradcam.png ... <image>_SE_gradcam.png
json/<image>_lesions.json
<image>_lesion_overlay.png
<image>_lesion_boxes.png
<image>_lesion_centers.png
<image>_analysis.png
```

Masks are lossless, single-channel TIFFs at the original image dimensions,
with **0 = background** and **255 = predicted lesion**. Probability NPY files
retain numeric arrays; probability PNGs and overlays are display images.
The JSON provides the actual paths, including suffixes added on repeated runs.

Restoration PNGs default to `inference/outputs/restoration/`; grade Grad-CAM
PNGs default to `inference/outputs/gradcam/`. CLIs under `inference/` expose
each model separately:

```bash
python inference/iqa_inference.py --image fundus.jpg
python inference/restoration_inference.py --image fundus.jpg
python inference/lesion_inference.py --image fundus.jpg
python inference/grade_inference.py --image fundus.jpg
```

## RetinaGram AI Model Visualizer (localhost)

The visualizer is a separate React/FastAPI application. It does not modify or
replace an existing desktop executable. It calls the reusable model loaders and
prediction functions documented above and keeps uploaded/generated files under
`inference/outputs/visualizer/`.

### 1. Setup

Run these commands from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
cd frontend
npm install
cd ..
```

Python 3.10–3.12 is recommended. The frontend uses a locally bundled Manrope
font package and does not depend on a hosted font at runtime.

### 2. Start the backend

From the repository root:

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

The API and interactive OpenAPI documentation are available at:

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`

Implemented endpoints:

- `POST /api/analyze` — validates one upload and runs the real local pipeline.
- `GET /api/analysis/{session_id}` — reloads an existing local analysis, which
  also makes refreshable `?session=...` visualizer URLs possible.
- `GET /api/stages` — returns the ordered visualizer stage definitions.
- `GET /api/models` — reports model architecture, resolved checkpoint path, and
  whether each checkpoint exists.
- `GET /api/explorer/{model_id}` — returns the architecture tree, dynamically
  calculated parameter count, and meaningful block list for a loaded model.
- `GET /api/explorer/{model_id}/blocks/{block_id}?session_id=...` — runs one
  short-lived hook and returns rendered feature/activation image URLs plus the
  exact captured tensor shape. Raw tensors are never serialized to the browser.
- `GET /api/explorer/grade/gradcam/{target_class}?session_id=...` — recomputes
  class-conditioned ConvNeXt Grad-CAM for grades 0–4.
- `GET /api/nafnet/features/{stage}?session_id=...` — legacy session endpoint for
  analyses created by the earlier five-stage feature-map implementation.

### 3. Start the frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/media` to the backend.
Set `VITE_API_URL` only when running the two processes on different origins.
The current visualizer is designed and validated for desktop/PC use; mobile is
not an acceptance target for this version.

### 4. Model and checkpoint detection

The application uses the existing repository defaults:

| Stage | Architecture | Default checkpoint |
| --- | --- | --- |
| Quality | EfficientNet-B0 + calibrated MLP | `model/checkpoints/final_efficientnet_iqa.pth` |
| Restoration | NAFNet width-32 | `checkpoint/restoration/NAFNet-SIDD-width32.pth` |
| Grade | ConvNeXt Tiny, 5 classes | `checkpoint/grade/convnext_tiny.pth` |
| Lesions | MobileNetV3-Large UNet++, 4 channels | `model/checkpoints/epoch_018_best_dice.pth` |

Grade and restoration also honor `DR_CHECKPOINT_DIR` through
`models/checkpoints.py`. Models load lazily on the first analysis so the API can
start and report missing checkpoints without crashing at import time. A failed
optional stage returns an explicit stage error and the rest of the pipeline uses
the last valid image where possible.

### 5. GPU and CPU behavior

`backend/app/model_registry.py` selects CUDA only when
`torch.cuda.is_available()` is true; otherwise all stages use CPU. Checkpoints
are mapped safely and existing loaders place models in evaluation mode. Inference
uses `torch.inference_mode()` except existing Grad-CAM paths, which enable only
the gradients needed for attribution. The UI warns that CPU analysis can take
several minutes for larger images. Uploads are capped at 20 MB and 2048 pixels on
the longest edge to keep local inference bounded.

### 6. Layer explorer and hook lifecycle

The reusable `HookManager` in `backend/app/services/hook_manager.py` registers
only the selected block, detaches the captured tensor, moves it to CPU, and
removes every hook at the end of the request. Initial analysis no longer renders
feature maps eagerly. `backend/app/services/model_explorer.py` derives the
available blocks from the real model modules and reruns one bounded inference
only when a card is expanded. Renders are cached under the current session.

Default block units are EfficientNet MBConv blocks, every NAFBlock plus real
down/up modules, every ConvNeXt block and downsampler, MobileNetV3 inverted
residual blocks, actual encoder projections, UNet++ nested decoder nodes, and
the real output heads. Advanced mode exposes child operations that genuinely
exist inside those repository modules.

The grayscale feature image is the strongest representative channel by mean
absolute response. The distinct heatmap is channel mean absolute activation
energy. Both use safe percentile normalization for display, and neither is
called Grad-CAM. NAFNet visualization reruns on a documented preview capped at
384 pixels on its longest edge; prediction still uses the full validated image.

Existing grade Grad-CAM remains in `models/grade/gradcam.py` and is exposed with
a real target-class selector. Lesion output uses the model's actual thresholded
masks, probability maps, and combined overlay. Feature maps, activation energy,
Grad-CAM, and segmentation masks are labeled as separate evidence types.

### Verification

```powershell
python -m pytest backend/tests -q
cd frontend
npm run build
```
