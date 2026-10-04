# Production models

The native branch includes exactly four runtime artifacts as ordinary Git blobs:
iqa_int8.onnx, nafnet_fp16.onnx, lesion_bf16_cam.pt, and grade_bf16_cam.pt.
MODEL_MANIFEST.json records their sizes, precisions and SHA256 hashes.

These files are consumed through config/models.json. No regeneration or Python
installation is required to run them. Source .pth checkpoints and experimental
conversion outputs are excluded by .gitignore; offline development scripts read
source weights from the separate reference checkout or an explicit override.

No new model license is assigned by this publication. See ../NOTICE.md and the
migration specs for conversion provenance and validation limitations.
