# Diabetic Retinopathy Grading with ConvNeXt and Grad-CAM
#Checkpoints link:
https://drive.google.com/drive/folders/1WT4wW6LAY9GvKWYWWDPUh03mFhmbplzL?usp=drive_link


#checkp

This project grades diabetic retinopathy (DR) from retinal fundus images. It uses a pretrained ConvNeXt image classifier with a five-output classification head and includes Grad-CAM visualization to help explain which retinal regions influenced a prediction.

## Model architecture

`model/convext.py` defines `Convextnet`, a thin PyTorch wrapper around Torchvision's ConvNeXt models:

- ConvNeXt Tiny is used by default.
- ConvNeXt Small can be selected with `type="Small"`.
- Any other `type` value selects ConvNeXt Base.
- Each backbone starts with ImageNet-1K V1 pretrained weights.
- The final classifier layer is replaced with a linear layer containing five outputs.

The five output indices (`0` through `4`) represent the five DR grades used by the training dataset. Confirm the dataset's label mapping before attaching clinical severity names to these indices.

## Repository structure

```text
.
|-- model/
|   |-- __init__.py          # Exposes Convextnet
|   `-- convext.py           # ConvNeXt-based five-class classifier
|-- grad.py                  # Grad-CAM implementation
|-- inference.py             # Single-image prediction and heatmap example
|-- training_history_dr.csv  # Per-epoch training and validation metrics
|-- confusion_matrix_dr.npy  # NumPy confusion matrix (grades 0-4)
|-- confusion_matrix_dr.csv  # Labeled, human-readable confusion matrix
|-- requirements.txt         # Project-specific Python dependencies
`-- README.md
```

Model checkpoints, datasets, virtual environments, and cache files are intentionally not included.

## Requirements

- Python 3.9 or newer
- PyTorch
- Torchvision
- NumPy
- Matplotlib
- Pillow

Install the Python dependencies with:

```bash
python -m pip install -r requirements.txt
```

For NVIDIA GPU acceleration, install a CUDA-enabled PyTorch build that matches your driver and CUDA environment. The inference script automatically selects CUDA when `torch.cuda.is_available()` is true and otherwise runs on the CPU.

## Model weights

The repository does not include a checkpoint. By default, `inference.py` expects one at:

```text
checkpoint/grade-classifier/convnext_tiny.pth
```

After loading a checkpoint, apply it to the model before calling `model.eval()`. For a checkpoint saved as a raw state dictionary:

```python
checkpoint = torch.load(
    "checkpoint/grade-classifier/convnext_tiny.pth",
    map_location=device,
)
model.load_state_dict(checkpoint)
model.eval()
```

If training saved a dictionary containing the weights, select the appropriate entry instead, for example:

```python
model.load_state_dict(checkpoint["model_state_dict"])
```

The architecture used to load a checkpoint must match the architecture used during training. The provided inference example constructs `Convextnet(numclasses=5)`, which selects ConvNeXt Tiny.

## Running inference

1. Place the compatible model checkpoint at the path above, or update the checkpoint path in `inference.py`.
2. Set `image_path` in `inference.py` to a retinal fundus image.
3. Add the appropriate `model.load_state_dict(...)` call after `torch.load(...)`, as shown above.
4. Run:

```bash
python inference.py
```

For example, the image setting can be changed to:

```python
image_path = r"data/example_fundus.jpg"
```

The script resizes the image to `224 x 224`, converts it to a tensor, and applies ImageNet normalization. It prints the predicted grade index and the five class probabilities, then displays the original image with a Grad-CAM heatmap overlay.

## Grad-CAM interpretability

`grad.py` implements Gradient-weighted Class Activation Mapping (Grad-CAM). It registers forward and backward hooks on a selected convolutional feature layer, pools the class-specific gradients, combines them with the saved activations, and normalizes the resulting heatmap.

`inference.py` targets the final ConvNeXt feature block (`model.model.features[-1][-1]`). The heatmap is resized to the input image and overlaid with Matplotlib. This visualization is intended for model interpretability: it can help inspect which areas influenced a DR grade, but it is not an independent diagnosis or a substitute for clinical review.

Hooks can be released after use with:

```python
gradcam.remove_hooks()
```

## Training history

`training_history_dr.csv` contains metrics for 20 training epochs. It records training and validation loss and accuracy, quadratic weighted kappa (QWK), referable-DR sensitivity, specificity and AUROC, confusion counts, macro and weighted multiclass metrics, per-class precision/recall/F1/AUC/support, and the learning rate.

The CSV is provided as training evidence and for plotting or comparing model behavior; it is not required to run inference.

## DR Grading Confusion Matrix

| True \ Pred | Grade 0 | Grade 1 | Grade 2 | Grade 3 | Grade 4 |
| ----------- | ------- | ------- | ------- | ------- | ------- |
| Grade 0     | 1416    | 53      | 47      | 1       | 3       |
| Grade 1     | 130     | 1062    | 99      | 4       | 10      |
| Grade 2     | 115     | 134     | 1040    | 73      | 37      |
| Grade 3     | 0       | 9       | 39      | 1200    | 30      |
| Grade 4     | 4       | 8       | 49      | 33      | 1200    |

Rows are the true DR grades and columns are the predicted DR grades, using class order 0 through 4. Values on the diagonal are correct predictions. Grade 2 shows more confusion with its neighboring grades than Grades 0, 3, and 4.

The raw matrix is available in two formats:

- `confusion_matrix_dr.npy` for direct loading with NumPy
- `confusion_matrix_dr.csv` for labeled tabular analysis

## Notes

- The model outputs logits. Softmax probabilities are computed during Grad-CAM generation.
- CPU inference is supported through PyTorch's `map_location` handling.
- CUDA is used automatically when available.
- Verify preprocessing, grade definitions, and checkpoint provenance before evaluating or deploying the model.
