# Deployed model manifest

Visualization update: grade Grad-CAM is enabled on model.features.7.2.block.0; lesion segmentation Grad-CAM is enabled on conv0_3.layers[3], with separate probability maps and pixel-aligned PNG mask layers. See ../../ANALYSIS_VIEWS.md. These supersede the initial optional-export-disabled notes below; weights and preprocessing are unchanged.

Code source: `models` branch at `7e1a99d9d044041baa972c0f12b38632d951b409`.
All paths below are relative to this `resources/models` directory unless explicitly identified as original paths. Checkpoints were copied byte-for-byte, without renaming or reserialization. Full SHA-256 inventory: `MODEL_HASHES.json`.

## Quality

- Original: `models-source/model/checkpoints/final_efficientnet_iqa.pth`.
- Deployed: `final_efficientnet_iqa.pth` (660,659 bytes).
- SHA-256: `c9e6798682916e55dd327901854dfb9521dcf17408956b4238a9d3f922d1e426`.
- Identical to the user-supplied `C:\Users\ADMIN\Desktop\models\checkpoint\iqa\final_efficientnet_iqa.pth`.
- Architecture: copied `models/iqa/model.py` `EfficientNetIQA`, 1280→128→3 MLP with ReLU and dropout 0.30; frozen torchvision EfficientNet-B0 features and global pooling.
- Input: RGB, torchvision Resize((224,224)) using its original bilinear/antialias defaults, ToTensor CHW [0,1], normalization mean [0.485,0.456,0.406], std [0.229,0.224,0.225], batch [1,3,224,224]. No crop/augmentation.
- Output: three logits divided by saved temperature `1.0064263343811035`, softmax, argmax. 0 Good / 1 Usable / 2 Reject. Confidence and all calibrated probabilities are returned.
- Evidence: branch README, `models/iqa/inference.py`, `models/iqa/predict.py`, actual checkpoint metadata/class mapping.
- Required backbone: `torch/hub/checkpoints/efficientnet_b0_rwightman-7f5810bc.pth`, torchvision EfficientNet_B0_Weights.IMAGENET1K_V1. Downloaded from the official PyTorch model host during setup; exact bytes are local for runtime. This head checkpoint does **not** contain the frozen backbone. Copied service now loads it strictly with weights=None initialization; architecture/preprocessing are unchanged.

## DR grading

- Original: `C:\Users\ADMIN\Desktop\models\checkpoint\grade\convnext_tiny.pth`.
- Deployed: `grade/convnext_tiny.pth` (111,369,899 bytes).
- SHA-256: `3e1106ea74c6f54153e3d553dff0c9ba5e7f91af4d65d45509b32d9532498a47`, matching the supplied manifest.
- Architecture: copied `models/grade/model.py` `Convextnet`, torchvision ConvNeXt Tiny with final classifier replaced by five outputs. Complete trained state is strictly loaded; no pretrained backbone download.
- Input: RGB, Resize((224,224)), ToTensor, same documented ImageNet mean/std as above, batch [1,3,224,224]. No crop/augmentation.
- Output: five logits, softmax probabilities, argmax `predicted_class` and `predicted_grade`, confidence. Mapping is explicitly `{0:0,1:1,2:2,3:3,4:4}`. Named diagnostic labels are not inferred from the inconsistent example UI.
- Evidence: branch `models/grade/model.py`, `predict.py`, original frontend `inference.py`, supplied bundle README/manifest, successful strict CPU loading.
- Optional Grad-CAM is disabled in this initial pipeline; no heatmap is fabricated.

## Lesion segmentation

- Original: `models-source/model/checkpoints/epoch_018_best_dice.pth`, identical to the supplied bundle's lesion checkpoint.
- Deployed: `epoch_018_best_dice.pth` (51,997,113 bytes).
- SHA-256: `5af3ed1059b6bba3d2a4f666ff6d8c0dce3cf29da466c28de8bc4be21ec57d05`.
- Architecture: unchanged `LesionUNetPlusPlus`, MobileNetV3-Large encoder, four-level nested decoder, four output channels. Strict state loading with pretrained=False.
- Selection evidence: `Results/lesion_results/baseline_info.txt` selects epoch 18 for best Dice/IoU/F1/AUPRC in the completed 20-epoch run; matching hash and checkpoint metadata. README and inference loader select the same file.
- Input: RGB, PIL bilinear resize 768×768, uint8→float/255 CHW, documented ImageNet mean/std, batch [1,3,768,768]. No crop/augmentation.
- Output: logits [1,4,768,768], sigmoid once, bilinear probabilities resized to original H×W with align_corners=False, threshold >=0.5, eight-connected regions with minimum 3 original-image pixels. No top-N truncation.
- Channel order: 0 MA microaneurysms, 1 HE hemorrhages, 2 EX hard exudates, 3 SE soft exudates. Coordinates are inclusive original-image pixel boxes; counts/centers/area and mean/max pixel probabilities come from masks. They are not clinical severity or calibrated region confidence.
- Original source prediction wrapper is reused. Optional Grad-CAM, dashboard, and probability-map exports are disabled; masks, combined overlay, boxes, centers, and JSON are retained.
- `dataset.py` uses explicit external CSV image/TIFF pairs. Masks are supervision targets, not inference inputs. No annotations/datasets are modified or loaded by analyze.

## Optional restoration

- Original: `C:\Users\ADMIN\Desktop\models\checkpoint\restoration\NAFNet-SIDD-width32.pth`.
- Deployed: `restoration/NAFNet-SIDD-width32.pth` (116,861,841 bytes).
- SHA-256: `89c70e808d1783b6c07911306e106aaf0d4f7f3da8c61078b99ff7f8929a26f4`, matching supplied manifest.
- Architecture: copied official NAFNet files, width32, encoder [2,2,4,8], middle12, decoder [2,2,2,2], img_channel3. Vendored code/licensing is retained unchanged.
- Input: RGB float [0,1], [1,3,H,W], no fixed resize, no ImageNet normalization. Network pads internally and crops to original dimensions.
- Output: same-resolution restored RGB, clamp [0,1], round to uint8 PNG. Optional API re-runs IQA on the saved result.
- Policy: explicit `/api/restore` only; never automatically applied during analyze. Current endpoint maximum is one megapixel to bound CPU memory, and rejects rather than silently resizes larger images.
- Generic SIDD denoising checkpoint, not retinal fine-tuned. Source README supports optional restoration followed by IQA reassessment; it does not justify restoring every image.

## Historical TOPIQ mismatch

The supplied checkpoint README/MANIFEST describes `iqa/cfanet_nr_koniq_res50-9a73138b.pth`, but that file is absent. The actual supplied IQA file is the EfficientNet head, matching current Git code. No pyiqa/TOPIQ model or fabricated score was substituted. The historical manifest is not used as a runtime loader configuration.
