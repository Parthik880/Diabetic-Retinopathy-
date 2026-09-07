# NETRAGRAM — IQA Module

## 1. What is IQA?

**Image Quality Assessment (IQA)** is the first stage of NETRAGRAM.

It checks whether a fundus image is suitable for reliable downstream DR analysis.

```text
Fundus Image → IQA → Good / Usable / Reject
Good → DR Classifier
Usable → Enhancement → Re-check / DR
Reject → Recapture
```

**IQA does NOT detect or grade diabetic retinopathy.** It evaluates image quality only.

## 2. IQA Classes

| ID | Class | Action |
|---:|---|---|
| `2` | **Reject** | Ask user to recapture image |
| `1` | **Usable** | Enhance → re-check / continue |
| `0` | **Good** | Send directly to DR classifier |

### Important

**Do not change the class mapping.**

```python
0 = Good
1 = Usable
2 = Reject
```

## 3. Model

**Primary model: EfficientNet-B0**

```text
EfficientNet-B0
      ↓
1280 features
      ↓
Linear 1280 → 128
      ↓
ReLU
      ↓
Dropout 0.30
      ↓
Linear 128 → 3
      ↓
Quality Class
```

Final calibrated checkpoint:

```text
checkpoints/final_efficientnet_iqa.pth
```

## 4. Current Performance

| Metric | Validation | Unseen Test |
|---|---:|---:|
| Accuracy | 92.70% | 86.73% |
| Macro F1 | 0.8786 | 0.8476 |

Unseen-test sensitivity:

```text
Good    : 94.30%
Usable  : 73.67%
Reject  : 85.31%
```

**Main weakness:** Usable images are the hardest class to distinguish.

## 5. Backend Integration

The backend sends an image to IQA and receives:

```text
quality
confidence
class probabilities
```

Conceptual routing:

```python
result = iqa_predict(image)

if result["quality"] == "Good":
    # Send to DR classifier

elif result["quality"] == "Usable":
    # Send to enhancement / re-check

elif result["quality"] == "Reject":
    # Request image recapture
```

The backend does not need to know the internal EfficientNet architecture.

## 6. Repository Structure

```text
repository-root/
├── checkpoints/
│   ├── efficientnet_b0_rwightman-7f5810bc.pth
│   └── final_efficientnet_iqa.pth
└── models/
    └── iqa/
        └── README.md
```

The `checkpoints/` directory is local-only and is not included in Git clones.
Create it and supply both checkpoints before running inference. The pretrained
EfficientNet-B0 backbone is loaded from the local file and is never downloaded
automatically.

The retinal-image dataset is **not included in the repository**.

## 7. Important for Team Members

Do not change these without discussing with the IQA owner:

```text
Model            → EfficientNet-B0
Class mapping    → 0 Reject / 1 Usable / 2 Good
Classifier head  → 1280 → 128 → 3
Dropout          → 0.30
Final checkpoint → checkpoints/final_efficientnet_iqa.pth
```

Most importantly, **inference preprocessing must match the preprocessing used during training.**

## 8. Why IQA Exists

Without IQA:

```text
Fundus → DR Classifier → Prediction
```

With IQA:

```text
Fundus
  ↓
 IQA
  ├── Good   → DR Classifier
  ├── Usable → Enhance / Re-check
  └── Reject → Recapture
```

This makes NETRAGRAM **quality-aware** and prevents poor-quality images from being blindly passed to the DR model.

## 9. Current Status

```text
IQA Model             ✅ Complete
Training              ✅ Complete
Validation            ✅ Complete
Calibration           ✅ Complete
Unseen Test           ✅ Complete
Backend Integration   🔄 Pending integration
Enhancement Pipeline  🔄 Pending integration
```

## Team One-Liner

> **IQA checks every fundus image before DR analysis and routes it as Good → DR classifier, Usable → enhancement/re-check, or Reject → recapture.**
