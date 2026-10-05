# Provenance and redistribution notes

RetinaGram's native branch was developed against the pc-gpu branch of
Parthik880/Diabetic-Retinopathy-. The repository currently has no blanket license
declaration. This publication does not invent or assign a new license to the
application or to user-supplied model artifacts.

The four deployment models are derivatives of supplied reference checkpoints,
converted offline as documented in the migration specs. Their bytes and hashes
are preserved in src/checkpoints/MODEL_MANIFEST.json. No source training checkpoint,
patient scan, calibration image, or session database is published here.

Bundled fonts retain their upstream licenses in assets/fonts/:

- Atkinson Hyperlegible Next: SIL Open Font License 1.1.
- Manrope: SIL Open Font License 1.1.
- Material Symbols: Apache License 2.0.

Source URLs are in assets/fonts/SOURCE.txt. The logo and XPM icons are retained
application assets. Qt, PyTorch/LibTorch, ONNX Runtime, CUDA and cuDNN are external
dependencies; their binaries are not committed. Preserve applicable upstream
license/redistribution obligations when distributing a locally generated package.
