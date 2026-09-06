# RetinaGram CPU desktop edition

This directory is the Windows CPU-only RetinaGram desktop application. It runs IQA, diabetic-retinopathy grading, lesion segmentation, optional NAFNet restoration, and local PDF reporting through a persistent FastAPI model registry. It must not install or select CUDA.

## Install and launch

Requires Windows, Python 3.12, and Node.js/npm. No NVIDIA driver, CUDA Toolkit, or cuDNN installation is required.

```powershell
cd "C:\Users\ADMIN\Music\retina-desktop\desktop-app1 - Cpu"
.\scripts\setup.ps1
.\scripts\start-desktop.ps1
```

The explicit Python dependency flow is:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe scripts\verify_cpu.py
```

`scripts/install_cpu.ps1` performs those steps, removes any leftover NVIDIA-only Python packages, and fails unless `torch.version.cuda` is `None`, `torch.cuda.is_available()` is `False`, and every loaded application model is on `cpu`.

If PowerShell blocks local scripts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\ADMIN\Music\retina-desktop\desktop-app1 - Cpu\scripts\start-desktop.ps1"
```

## Runtime and optional dependencies

- `requirements-runtime.txt`: FastAPI/uvicorn, multipart uploads, Pillow, NumPy, SciPy lesion post-processing, Matplotlib artifact rendering, and ReportLab PDF generation.
- CPU-only `torch==2.14.0` and `torchvision==0.29.0`: installed separately from the official CPU wheel index. Torchvision is required by the deployed EfficientNet-B0, ConvNeXt, MobileNetV3, and image transforms.
- `requirements-dev.txt`: integration-test and PyInstaller tooling; not part of the runtime install.
- `requirements-training.txt`: pandas for the optional lesion CSV dataset/training utilities; not part of the desktop runtime install.

The model registry loads each checkpoint once at backend startup and reuses it across images. All model architectures and weights remain unchanged. Startup logs include the torch version, CUDA build metadata/availability, and each loaded model's parameter device.

## Use

In Capture, register a patient, select an OS and/or OD image, choose **Apply Scan**, then choose **Analyze Retinal Images**. The pipeline is:

`Capture → IQA → optional NAFNet for Usable images → Grade → Lesion → Report`

Analysis is eye-scoped. History is persisted as atomic JSON in the CPU edition's isolated local application-data directory. The separate GPU/standard project uses a different project directory and is not modified by CPU reset or setup scripts.

## Reset local patient data

Close RetinaGram CPU, then run:

```powershell
.\.venv\Scripts\python.exe scripts\reset_local_data.py
```

The reset removes CPU-edition patient/history/session JSON, inference runs, referral drafts, reports and caches under the project runtime directories, and the isolated `RetinaGram CPU` user-data directory. It preserves `resources/models`, model source, migrations/schema code, branding, frontend assets, and application source.

## Development and validation

```powershell
# Terminal 1
.\scripts\start-backend.ps1
# Terminal 2
.\scripts\start-frontend.ps1

.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\verify_cpu.py
.\.venv\Scripts\python.exe scripts\test-integration.py
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run test:workflow
npm.cmd --prefix frontend run test:history
```

The integration test blocks external network access, loads real checkpoints, analyzes the bundled fundus image, exercises report generation and invalid-input handling, and verifies model reuse. Test evidence is written under `work/` and can be removed with the reset script.

## Build

Build the frontend:

```powershell
npm.cmd run build
```

Build the CPU backend onedir bundle after installing development dependencies:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm RetinaGramBackend.spec
```

`RetinaGramBackend.spec` packages one copy of the deployed checkpoints, built frontend, logo, and runtime configuration. It explicitly excludes training/test/notebook packages. The CPU PyTorch environment prevents CUDA/NVIDIA binaries from entering the bundle.

Build the Windows installer (frontend build + NSIS packaging):

```powershell
npm.cmd run package:win
```

Packaging outputs (all generated and excluded from Git):

- `dist\RetinaGramBackend\` — PyInstaller onedir backend bundle
- `dist\win-unpacked\` — unpacked Electron app
- `dist\RetinaGram Setup 0.1.0.exe` — NSIS installer

The installed application bundles its own backend and frontend and does not require Python or Node.js.

## API

- `GET /health`: readiness, torch/CPU device metadata, model devices, and startup errors.
- `POST /api/analysis-jobs`: queued real IQA, grading, lesion metadata, and local artifacts.
- `POST /api/reports/export`: patient/report-specific offline PDF bundle.
- `POST /api/restore`: explicit NAFNet restoration; it never replaces the original analysis automatically.
- `POST /api/history/sessions`, `GET /api/history`: local atomic JSON session history.
- `POST /api/referral`, `GET /api/referrals`: local referral drafts only; nothing is transmitted.

Runtime inference, report generation, weights, fonts, logo, and the bundled test image are local. Preserve `resources/models/`; setup does not replace the trained application checkpoints.

Patient/history/session JSON, inference runs, reports, and caches under `work/` and the isolated `RetinaGram CPU` user-data directory are local-only and excluded from Git. Test fixtures, schema/config code, and model weights stay tracked.

## Disclaimer

RetinaGram is an AI-assisted retinal screening tool and is not a substitute for professional medical diagnosis.
