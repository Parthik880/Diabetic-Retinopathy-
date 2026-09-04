# Diabetic Retinopathy Models

This repository provides separate, reusable model packages for diabetic-retinopathy
grading and no-reference image-quality assessment (IQA). Model construction and
weight loading live in each model's `model.py`, preprocessing and reusable Python
prediction functions live in `predict.py`, and user-facing command-line entry points
live in `inference/`.

## Repository structure

```text
.
|-- models/
|   |-- grade/
|   |   |-- model.py          # ConvNeXt architecture and trained checkpoint loading
|   |   |-- predict.py        # prediction vectors and saved Grad-CAM overlays
|   |   |-- gradcam.py        # ConvNeXt Grad-CAM implementation
|   |   |-- weights/          # place the external grade checkpoint here
|   |   `-- results/          # persistent grade training/evaluation artifacts
|   `-- iqa/
|       |-- model.py          # pyiqa TOPIQ-NR initialization
|       |-- predict.py        # reusable raw IQA-score prediction
|       `-- weights/          # reserved; TOPIQ downloads to the torch cache
|-- inference/
|   |-- grade_inference.py    # grade CLI
|   |-- iqa_inference.py      # IQA CLI
|   `-- outputs/gradcam/      # generated per-image overlays (ignored by Git)
|-- requirements.txt
`-- README.md
```

## Setup

Python 3.10 or newer is recommended. Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

Install a PyTorch build appropriate for the machine's CPU or CUDA runtime when the
default pip selection is not suitable. Both entry points automatically use CUDA when
available and otherwise use CPU; `--device cpu` or `--device cuda` overrides that
selection.

## Grade model

`models/grade/model.py` retains the original `Convextnet` architecture and historical
class name: a Torchvision ConvNeXt Tiny ImageNet-1K V1 backbone whose final classifier
is replaced with five outputs. The five output indices (`0` through `4`) remain the
dataset grade mapping; no new clinical labels or class reordering has been introduced.
ConvNeXt Small remains selectable with `type="Small"`, and other `type` values retain
the original ConvNeXt Base fallback.

`models/grade/predict.py` preserves the original preprocessing exactly:

1. convert the image to RGB;
2. resize to `224 x 224`;
3. convert to a `[0,1]` tensor;
4. normalize with ImageNet mean `[0.485, 0.456, 0.406]` and standard deviation
   `[0.229, 0.224, 0.225]`.

The trained checkpoint is not committed. Download it from the existing
[checkpoint folder](https://drive.google.com/drive/folders/1WT4wW6LAY9GvKWYWWDPUh03mFhmbplzL?usp=drive_link)
and place it at:

```text
models/grade/weights/convnext_tiny.pth
```

Alternatively, pass its location explicitly:

```bash
python inference/grade_inference.py \
  --image path/to/fundus.jpg \
  --checkpoint path/to/convnext_tiny.pth
```

The reusable API is:

```python
from models.grade.predict import predict_grade

result = predict_grade("path/to/fundus.jpg")
```

The result contains separate five-value `logits` and `probabilities` lists, the
argmax-derived `predicted_class`/`predicted_grade`, confidence, and a saved Grad-CAM
path. Every value is JSON-serializable. Grad-CAM is enabled by default and is saved
under `inference/outputs/gradcam/`. Use `--gradcam-output-dir` to select another
directory or `--no-gradcam` to skip it.

### Grad-CAM interpretability

`models/grade/gradcam.py` retains the original Gradient-weighted Class Activation
Mapping implementation. It registers forward and backward hooks on the final ConvNeXt
feature block (`model.model.features[-1][-1]`), pools class-specific gradients,
combines them with saved activations, and normalizes the heatmap. The visualization
can help inspect which areas influenced a grade, but it is not an independent
diagnosis or a substitute for clinical review.

## IQA model: pretrained TOPIQ-NR

The IQA module uses the maintained [IQA-PyTorch (`pyiqa`)](https://github.com/chaofengc/IQA-PyTorch)
implementation rather than recreating TOPIQ.

- pyiqa metric identifier: `topiq_nr`
- architecture/variant: `cfanet_nr_koniq_res50`
- semantic backbone: ResNet-50
- training dataset: KonIQ-10k natural images
- checkpoint filename: `cfanet_nr_koniq_res50-9a73138b.pth`
- returned value: raw TOPIQ-NR score; no quality threshold or label is applied

Run one image from the repository root:

```bash
python inference/iqa_inference.py --image path/to/fundus.jpg
```

Or reuse one loaded model across calls:

```python
from models.iqa.model import IQAModel
from models.iqa.predict import predict_iqa

model = IQAModel()
first = predict_iqa("first.jpg", model=model)
second = predict_iqa("second.jpg", model=model)
```

### IQA preprocessing and pretrained weights

The image path is passed directly to pyiqa. With pyiqa 0.1.16, its path pipeline
opens the image with Pillow, converts it to RGB, and converts it to a batched float
tensor in `[0,1]`. The default `topiq_nr` configuration preserves the input spatial
resolution (no wrapper resize or crop). CFANet then applies the ImageNet normalization
expected by its ResNet-50 semantic backbone. Do not add a second normalization step.

On first use, pyiqa downloads the pretrained checkpoint automatically and normally
caches it outside the repository under `~/.cache/torch/hub/pyiqa/`. The roughly
173 MiB checkpoint is intentionally not duplicated in Git or in `models/iqa/weights/`.

TOPIQ-NR was trained on natural images, not clinically validated fundus gradability
data. Its raw score must be calibrated and validated before anyone derives a retinal
quality decision or clinical workflow threshold from it.

## Grade training artifacts

Persistent grade evaluation artifacts are stored together under
`models/grade/results/`. This includes `grade_training.csv`, `confusion_matrix.npy`,
`confusion_matrix.png`, and the existing metric plots. These artifacts are not
required for inference, and their contents were not altered during relocation.

The training history records 20 epochs of training/validation loss and accuracy,
quadratic weighted kappa, referable-DR sensitivity/specificity/AUROC, confusion counts,
multiclass metrics, per-class metrics, and learning rate.

| True / Predicted | Grade 0 | Grade 1 | Grade 2 | Grade 3 | Grade 4 |
| ---------------- | ------- | ------- | ------- | ------- | ------- |
| Grade 0          | 1416    | 53      | 47      | 1       | 3       |
| Grade 1          | 130     | 1062    | 99      | 4       | 10      |
| Grade 2          | 115     | 134     | 1040    | 73      | 37      |
| Grade 3          | 0       | 9       | 39      | 1200    | 30      |
| Grade 4          | 4       | 8       | 49      | 33      | 1200    |

Rows are true DR grades and columns are predicted grades, in unchanged class order
0 through 4. The model outputs logits; the reusable prediction API returns softmax
probabilities alongside the selected grade index.
