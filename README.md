# RetinaGram desktop integration

RetinaGram is a Windows desktop application that runs the existing IQA, diabetic-retinopathy grading, lesion-segmentation, and optional restoration models through a local FastAPI backend. Electron starts and stops Python automatically. Inference and report generation work offline after setup.

The standard screening report contains the original fundus image, lesion overlay, actual DR grade and confidence, actual IQA state, detected/not-detected lesion findings, a screening-oriented recommendation, and the required AI-assistance disclaimer. Grad-CAM remains available in Analysis but is intentionally excluded from the standard PDF.

## Launch on this PC

```powershell
cd C:\Users\ADMIN\Music\retina-desktop\desktop-app1
.\scripts\start-desktop.ps1
```

If PowerShell blocks local scripts:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\ADMIN\Music\retina-desktop\desktop-app1\scripts\start-desktop.ps1"
```

In Capture, replace an eye image, choose **Apply Scan**, then choose **Analyze Retinal Images**. Analysis is stored independently for OS and OD. Open Report and choose **Save Report** to select a native Windows destination folder. RetinaGram creates a timestamped patient-specific subfolder containing only artifacts that exist.

## CUDA setup / reinstall

Requires Windows, Python 3.12, Node.js/npm, an NVIDIA GPU, and a working NVIDIA driver. The detected driver on the tested PC is 591.86 and reports CUDA 13.1 capability. NVIDIA's CUDA 13.0 release notes require a Windows driver in the 580 family or newer for CUDA 13.x minor-version compatibility. PyTorch 2.14.0 publishes Windows CUDA 13.0 wheels, so this project installs the compatible `cu130` build. The PyTorch wheel contains the CUDA, cuDNN, and cuBLAS runtime libraries required by the packaged backend; end users need a compatible NVIDIA driver, not a separate Python installation or the full CUDA Toolkit.

```powershell
.\scripts\install_windows_gpu.ps1
```

Equivalent dependency commands:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv\Scripts\python.exe -m pip install --upgrade --force-reinstall torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cu130
.\.venv\Scripts\python.exe scripts\verify_gpu.py
```

The original CPU-only installation came from `scripts/setup.ps1` installing plain `torch==2.14.0` and `torchvision==0.29.0` from the default PyPI index. On Windows those resolved to `2.14.0+cpu` and `0.29.0+cpu`. Runtime dependencies now live in `requirements-runtime.txt`; CUDA PyTorch is installed explicitly from the official PyTorch index.

For a complete setup including frontend dependencies and build:

```powershell
.\scripts\setup.ps1
```

Setup needs internet for dependency downloads. Runtime inference, report generation, weights, fonts, logo, and sample images are local. Preserve `resources/models/` when moving the workspace; setup does not download the trained application checkpoints.

## Development

```powershell
# Terminal 1
.\scripts\start-backend.ps1
# Terminal 2
.\scripts\start-frontend.ps1
```

Frontend: `http://127.0.0.1:5173`; API: `http://127.0.0.1:8765`. Vite proxies `/api`, `/health`, and `/artifacts`. Electron uses a free loopback port and serves the built UI from the same origin as the API.

## API

- `GET /health`: loaded models, selected device and GPU name, readiness, and startup errors.
- `POST /api/analyze`: real IQA, grading, lesion metadata, and local artifacts.
- `POST /api/reports/export`: creates a patient/report-specific offline PDF bundle in the native folder selected by Electron.
- `POST /api/restore`: optional explicit NAFNet restoration and IQA reassessment; it never replaces the original analysis automatically.
- `POST /api/referral`, `GET /api/referrals`: local referral drafts only; nothing is transmitted.
- `/artifacts/...`: local run images, masks, overlays, and JSON.

## Validation

```powershell
.\.venv\Scripts\python.exe scripts\verify_gpu.py
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\test-integration.py
npm.cmd --prefix frontend run lint
$env:RETINA_SMOKE = '1'
.\scripts\start-desktop.ps1
Remove-Item Env:RETINA_SMOKE
```

The integration test loads real checkpoints with external network access blocked, analyzes the bundled 2592 x 1728 sample, exports a report bundle, checks input failures, and verifies model reuse. The Electron smoke test uploads the same file through the real UI, checks displayed results, verifies the standard report contains no Grad-CAM, saves the report bundle, checks eye isolation and error states, then closes the app.

Evidence is written under `work/`: `integration-test.json`, `desktop-smoke.json`, `desktop-analysis.png`, `runs/`, and test report directories. Patient UI state remains session-only. No automatic retention deletion is enabled.

## GPU desktop packaging

Build the Windows x64 NSIS package from the already-verified GPU virtual environment:

```powershell
npm.cmd run package:win
```

This runs the Vite build first, creates the CUDA-enabled onedir backend with `RetinaGramBackendGPU.spec`, and packages Electron. The final artifact is `dist/RetinaGram GPU Setup 0.1.0.exe`; `dist/win-unpacked/RetinaGram GPU.exe` can be tested before installation.

The GPU edition is intentionally independent of the CPU edition: app ID `com.retinagram.desktop.gpu`, product/executable/shortcut name `RetinaGram GPU`, package/install folder name `retinagram-gpu`, and user-data folder `%APPDATA%/RetinaGram GPU`. Electron chooses a free loopback port at each launch, so CPU and GPU editions can run simultaneously. Uninstall does not delete the edition's user-data folder.

The PyInstaller configuration bundles only runtime code, one copy of each required checkpoint, the frontend distribution, fonts, branding, and the CUDA-enabled PyTorch runtime. Training data, notebooks, optimizer state, caches, `__pycache__`, test outputs, and duplicate checkpoints remain outside the package. Runtime imports such as SciPy, pandas, Matplotlib, and ReportLab must not be removed merely for size reduction. When CUDA is unavailable the existing device-selection logic falls back to CPU, although the GPU package is much larger because it retains the CUDA runtime libraries.
