# Diabetic Retinopathy Model Pipeline

This repository separates each model in the diabetic-retinopathy pipeline into
an independent package. Architecture and checkpoint loading live in `model.py`,
reusable preprocessing and prediction live in `predict.py`, and end-user command
line entry points live under `inference/`.

No training is started by this repository's inference commands. Persistent
training and evaluation artifacts live only under the top-level `Results/`
directory; per-image runtime files are written under `inference/outputs/`.

## Pipeline

```text
Fundus image
      |
      v
     IQA
      |
quality acceptable?
 +----+-----+
 |          |
YES         NO
 |          |
 |        NAFNet
 |          |
 |       IQA again
 |          |
 +----------+
      |
      v
UNet++ lesion segmentation
      |
      v
MA / HE / EX / SE
      |
      v
Grade classifier
      |
      v
DR grade + lesion output + explanation
```

- **IQA** measures input image quality with pretrained TOPIQ-NR.
- **NAFNet** restores a degraded image before quality is checked again.
- **UNet++** segments microaneurysms (MA), hemorrhages (HE), hard exudates
  (EX), and soft exudates (SE).
- **Grade model** classifies diabetic-retinopathy severity into grades 0-4 and
  can save a Grad-CAM explanation.

The IQA score is raw and no quality threshold is imposed here. TOPIQ-NR and the
generic SIDD NAFNet checkpoint are not clinically validated retinal models.

## Repository structure

```text
.
|-- models/
|   |-- grade/
|   |   |-- model.py
|   |   |-- predict.py
|   |   |-- gradcam.py
|   |   `-- weights/
|   |-- iqa/
|   |   |-- model.py
|   |   |-- predict.py
|   |   `-- weights/
|   |-- lesion/
|   |   |-- model.py
|   |   |-- predict.py
|   |   |-- dataset.py
|   |   `-- weights/epoch_018_best_dice.pth
|   `-- restoration/
|       |-- model.py
|       |-- predict.py
|       |-- nafnet/
|       |-- weights/
|       `-- README.md
|-- inference/
|   |-- grade_inference.py
|   |-- iqa_inference.py
|   |-- lesion_inference.py
|   |-- restoration_inference.py
|   `-- outputs/
|       |-- gradcam/
|       |-- lesion/
|       `-- restoration/
|-- Results/
|   |-- grade_results/
|   |-- iqa_results/
|   |-- lesion_results/
|   `-- restoration_results/
|-- requirements.txt
`-- .gitignore
```

## Setup

Python 3.10 or newer is recommended. Install a PyTorch build suitable for the
machine, then install the dependencies:

```bash
python -m pip install -r requirements.txt
```

All model wrappers automatically use CUDA when available and otherwise use CPU.
The CLIs accept `--device cpu` or `--device cuda`.

## Grade: five-class ConvNeXt

`models/grade/model.py` retains the historical `Convextnet` class: a Torchvision
ConvNeXt Tiny ImageNet-1K backbone with its final classifier replaced by five
outputs. The unchanged class order is `[0, 1, 2, 3, 4]`.

Preprocessing remains RGB conversion, resize to 224x224, tensor conversion, and
ImageNet normalization. `predict_grade` returns the five logits, five softmax
probabilities, selected grade, confidence, and optional saved Grad-CAM path.

The trained `convnext_tiny.pth` checkpoint is 111,369,899 bytes and exceeds
GitHub's normal file limit, so it is intentionally external. Download it from
the existing [checkpoint folder](https://drive.google.com/drive/folders/1WT4wW6LAY9GvKWYWWDPUh03mFhmbplzL?usp=drive_link)
and place it at:

```text
models/grade/weights/convnext_tiny.pth
```

```bash
python inference/grade_inference.py --image fundus.jpg
python inference/grade_inference.py --image fundus.jpg --no-gradcam
```

```python
from models.grade.predict import predict_grade

result = predict_grade("fundus.jpg")
```

Grad-CAM overlays are generated under `inference/outputs/gradcam/` by default.

## IQA: TOPIQ-NR

The IQA package delegates to IQA-PyTorch (`pyiqa==0.1.16`) using metric ID
`topiq_nr` and pretrained variant `cfanet_nr_koniq_res50`. The image path is
passed directly to pyiqa; the wrapper does not add a resize, crop, normalization,
threshold, or quality label.

The roughly 173 MiB TOPIQ checkpoint is downloaded and cached by pyiqa outside
the repository rather than duplicated in `models/iqa/weights/`.

```bash
python inference/iqa_inference.py --image fundus.jpg
```

```python
from models.iqa.predict import predict_iqa

result = predict_iqa("fundus.jpg")
```

## Lesion segmentation: UNet++ baseline

The selected lesion baseline is `models/lesion/weights/epoch_018_best_dice.pth`.
It is copied unchanged from `C:\Users\ADMIN\Desktop\u_net_baseline\baseline` and
has SHA-256:

```text
5af3ed1059b6bba3d2a4f666ff6d8c0dce3cf29da466c28de8bc4be21ec57d05
```

The preserved architecture uses a MobileNetV3-Large encoder, four-level nested
UNet++ decoder, and four output channels. Channel order is exactly:

```text
0 = MA, 1 = HE, 2 = EX, 3 = SE
```

Preprocessing remains RGB conversion, bilinear resize to 768x768, conversion to
`[0,1]`, and ImageNet normalization. The default inference threshold remains
0.5. The checkpoint was saved at epoch 18 and loads with strict state-dict
matching.

Checkpoint-recorded validation metrics at threshold 0.5 are Dice 0.601242, IoU
0.429840, AUPRC 0.662660, AUROC 0.992029, sensitivity 0.738866, specificity
0.998657, and precision 0.506837. Best-threshold Dice is 0.634498 at threshold
0.9. The full copied history and metadata are in `Results/lesion_results/`.

```bash
python inference/lesion_inference.py --image fundus.jpg
```

```python
from models.lesion.predict import predict_lesions

result = predict_lesions("fundus.jpg")
ma_probability = result["lesions"]["MA"]["probability"]
```

`models/lesion/dataset.py` preserves the external DDR/IDRiD dataset adapter, but
the dataset index, images, and masks are not committed.

## Restoration: NAFNet width-32

The required official NAFNet architecture is vendored under
`models/restoration/nafnet/` from `megvii-research/NAFNet` commit
`2b4af71ebe098a92a75910c233a3965a3e93ede4`. Attribution headers and the upstream
Apache 2.0 license are retained.

The wrapper uses width 32, encoder blocks `[2, 2, 4, 8]`, 12 middle blocks, and
decoder blocks `[2, 2, 2, 2]`. Inference uses full-resolution RGB `[0,1]` input,
no ImageNet normalization, internal padding to a multiple of 16, and exact
cropping back to the input size.

Place a retinal-trained checkpoint at:

```text
models/restoration/weights/nafnet_retina_width32.pth
```

The official generic `NAFNet-SIDD-width32.pth` is 116,861,841 bytes and is not
committed. It may be passed explicitly for architecture/inference testing, but
it is a SIDD denoising checkpoint and must not be described as retinal-trained.
See `models/restoration/README.md` for checkpoint details.

```bash
python inference/restoration_inference.py \
  --image degraded.jpg \
  --checkpoint path/to/NAFNet-SIDD-width32.pth
```

```python
from models.restoration.predict import restore_image

result = restore_image("degraded.jpg", checkpoint="path/to/checkpoint.pth")
```

Restored images are written under `inference/outputs/restoration/`; persistent
PSNR/SSIM summaries and comparison artifacts belong under
`Results/restoration_results/`.

## Persistent results

```text
Results/
|-- grade_results/
|   |-- grade_training.csv
|   |-- confusion_matrix.npy
|   |-- confusion_matrix.png
|   `-- 00_dashboard.png ... 10_referable_confusion_components.png
|-- iqa_results/
|-- lesion_results/
|   |-- training_metrics.csv
|   |-- evaluation_metrics.json
|   |-- best_confusion_matrix.npy
|   `-- baseline_info.txt
`-- restoration_results/
```

No model package contains a results directory. Persistent results go in
`Results/<model>_results/`; outputs created by a prediction go in
`inference/outputs/<model>/`.
