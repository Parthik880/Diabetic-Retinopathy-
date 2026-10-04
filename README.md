# RetinaGram — Native GPU Retinal Screening

RetinaGram is a C++20 / Qt 6 desktop implementation of the retinal screening
workflow on the **PCGPU.cpp** branch. ONNX Runtime and LibTorch execute the models
with CUDA support. No Python server, FastAPI, Node.js, or Electron process is
required at runtime. Python scripts in this repository are offline development
tools only.

## Project purpose

Register a patient, import left (OS) and/or right (OD) fundus images, assess image
quality, review grading and lesion visualizations, and export reports. History
and batch analysis work locally. Cloud Sync currently presents the disconnected
integration state; this branch does not implement a configured cloud service.

This is an AI-assisted screening/research application. Local smoke tests and
parity measurements are **not clinical validation** or evidence of diagnostic
equivalence. Broader representative testing and professional review are required.

## Architecture

~~~text
Training/reference checkpoints
        | offline conversion only
        v
checkpoints/ + config/models.json
        |
Qt 6 MainWindow
        |
AnalysisController + persistent background worker
        |
ModelManager (routing, serialization boundary, mutex)
        |
ModelFactory
  +-- IQualityModel     -> ONNX Runtime IQA
  +-- IRestorationModel -> ONNX Runtime NAFNet
  +-- IGradingModel     -> LibTorch ConvNeXt grading / CAM
  +-- ILesionModel      -> LibTorch lesion UNet++
                              |
                      CPU LesionPostprocessor
                              |
           Qt visualizations / reports / local History
~~~

MainWindow owns the screens and patient/eye selection. AnalysisController owns
session persistence, import, report export, and batch orchestration. Its worker
keeps model sessions/modules alive across analyses. ModelManager serializes
initialization and analysis calls; runtime tensor types remain private to stage
adapters. LesionPostprocessor owns full masks, connected components, filtering,
merging, coordinates, region probabilities, and display artifacts.

The shared PDF renderer serves reports and Batch. ReportBundle exports deliberate
saved artifacts. Session/history metadata is written atomically with QSaveFile.

## Pipeline routing

IQA runs **once per eye**.

| Quality | Route |
| --- | --- |
| Good | Original image -> grading / grade CAM -> lesion segmentation |
| Usable | NAFNet restoration -> restored image -> grading / grade CAM -> lesion segmentation |
| Reject | Stop; recapture required; downstream models are skipped |

## Models and precision

The four production artifacts are **included as ordinary Git files** in this
branch, not LFS pointers. Their exact sizes and SHA256 values are recorded in
[checkpoints/MODEL_MANIFEST.json](checkpoints/MODEL_MANIFEST.json).

| Stage | Artifact | Precision |
| --- | --- | --- |
| IQA | iqa_int8.onnx | Partial QDQ INT8 / FP32 |
| Restoration | nafnet_fp16.onnx | FP16 internal compute / FP32 boundary |
| Lesion UNet++ | lesion_bf16_cam.pt | BF16 TorchScript |
| ConvNeXt grading | grade_bf16_cam.pt | BF16 TorchScript |

**IQA is not fully INT8.** Eighteen Conv/Gemm nodes in selected backbone stages
and the classifier were quantized; other layers remain FP32. Broader quantization
failed the local parity gate. Original lesion and grading checkpoints contained
FP32 tensors; BF16 deployment conversion was explicitly requested, without
retraining. This can affect sparse masks.

Canonical lesions are MA (Microaneurysms), HE (Hemorrhages), EX (Hard Exudates),
and SE (Soft Exudates). The current lesion input is 768x768 with independent
sigmoid threshold 0.5. Grading labels are 0 No diabetic retinopathy, 1 Mild NPDR,
2 Moderate NPDR, 3 Severe NPDR, and 4 Proliferative DR.

## Repository structure

| Path | Contents |
| --- | --- |
| src/ | Native application, UI, inference adapters, image decoding, reporting |
| include/ | Public C++ interfaces and typed results |
| config/ | Versioned model configuration |
| assets/ | Runtime logo, icons, and fonts |
| resources/ | Reserved native resources directory |
| checkpoints/ | Four production model artifacts and their manifest |
| scripts/ | Local launch/deployment, validation, benchmarks, offline conversion |
| tests/ | Isolated Qt UI, functional, inference, and bundle tests |
| specs/ | Migration history and final implementation records |
| graphify-out/ | Portable architecture graph, report, interactive HTML |
| build/ | Generated locally; ignored and never published |

The deployment package, test images, patient/session databases, downloaded SDKs,
logs, screenshots, and raw benchmark output are not source-controlled.

## Windows prerequisites

The tested configuration is:

- Visual Studio 2022, MSVC 14.44, x64 C++ tools and Windows SDK
- CMake 3.31 and Ninja (CMake minimum 3.26)
- Qt 6.8.3 MSVC2022 x64 (Qt minimum 6.5)
- PyTorch / LibTorch 2.8 CUDA 12.8, Release build
- NVIDIA CUDA Toolkit 12.9
- ONNX Runtime GPU 1.26, CUDA 12 / cuDNN 9 compatible runtime
- NVIDIA RTX 3060 12 GiB, a compatible NVIDIA driver
- Microsoft Visual C++ 2015–2022 x64 redistributable

These are tested versions, not a claim that only these versions can work.
Match the MSVC ABI, architecture, Release/Debug variant, Torch CUDA build, and
ONNX Runtime CUDA/cuDNN requirements when choosing alternatives. Qt image plugins
handle common formats; Windows Imaging Component handles TIFF. OpenCV is not linked.

## Clone the native branch

~~~bat
git clone --branch PCGPU.cpp --single-branch https://github.com/Parthik880/Diabetic-Retinopathy-.git
cd Diabetic-Retinopathy-
~~~

For reference comparisons, clone pc-gpu into a **separate** directory. Do not
checkout the reference implementation over the native source.

## Model setup

A normal clone contains:

~~~text
checkpoints/
  iqa_int8.onnx
  nafnet_fp16.onnx
  lesion_bf16_cam.pt
  grade_bf16_cam.pt
  MODEL_MANIFEST.json
~~~

No conversion is needed to run the application. Verify downloaded model bytes
with Get-FileHash or the manifest before investigating a model load error.
Redundant training/source .pth files and experimental ONNX candidates are excluded.
No new license is assigned to supplied model artifacts; see [NOTICE.md](NOTICE.md).

## Dependency setup and configure

Install the Qt MSVC x64 SDK and CUDA toolkit. TORCH_ROOT can be an extracted
matching Release LibTorch distribution or the torch directory in a development
PyTorch installation (the directory containing include/, lib/, and share/).

The tested ONNX Runtime SDK is the extracted Windows GPU NuGet package.
A reproducible download from NuGet is:

~~~powershell
$version = '1.26.0'
$archive = Join-Path $env:TEMP 'retinagram-onnxruntime.nupkg'
Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.ml.onnxruntime.gpu.windows/$version/microsoft.ml.onnxruntime.gpu.windows.$version.nupkg" -OutFile $archive
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive, 'D:\SDKs\onnxruntime-gpu-windows-1.26.0')
~~~

Use a new extraction directory. The package contains native headers, import
libraries, and Windows runtime DLLs; downloaded dependencies do not belong in Git.

Open **x64 Native Tools Command Prompt for VS 2022**, then substitute your SDK paths:

~~~bat
set QT_ROOT=C:\Qt\6.8.3\msvc2022_64
set TORCH_ROOT=D:\SDKs\libtorch
set ONNXRUNTIME_ROOT=D:\SDKs\onnxruntime-gpu-windows-1.26.0
cmake -S . -B build\ninja -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="%QT_ROOT%;%TORCH_ROOT%" -DONNXRUNTIME_ROOT="%ONNXRUNTIME_ROOT%" -DRETINAGRAM_BUILD_UI_TESTS=ON -DRETINAGRAM_BUILD_INFERENCE_TESTS=ON
~~~

For another SDK layout, set ONNXRUNTIME_ROOT to the directory containing include/
and lib/. CUDA_PATH normally comes from the CUDA installer. Ensure cmake and
ninja are on PATH; the Visual Studio bundled tools can also be used.

## Build

~~~bat
cmake --build build\ninja --parallel 3
~~~

Re-run this after source edits; incremental builds compile changed inputs.
The required sequence is **source edit -> build -> deploy -> package executable**.
deploy-windows.ps1 does **not** compile the application. It rejects source files
newer than the executable and verifies the copied executable hash.

## Run the development build

~~~powershell
powershell -File .\scripts\run-dev.ps1
~~~

This launches build/ninja/RetinaGram.exe. The script reads dependency locations
from that build's CMakeCache.txt, with optional QT_ROOT, TORCH_ROOT,
ONNXRUNTIME_ROOT, and CUDA_PATH overrides, then sets native DLL search paths and
copies the selected ORT DLLs beside the executable to prevent version ambiguity.
Pass -BuildDirectory for an alternate build tree.

## Package

~~~powershell
.\scripts\deploy-windows.ps1
.\build\package\RetinaGram.exe
~~~

Deployment uses windeployqt and dumpbin dependency scanning, including dynamically
loaded ONNX CUDA providers, cuDNN components, and NVRTC. It copies assets, config,
and exactly the model artifacts selected by config/models.json. An x64 VS tools
shell is convenient; otherwise dumpbin is resolved through vswhere.

The locally tested package is about **4.4 GiB**, chiefly LibTorch/CUDA libraries.
It has no Python or Node runtime and was tested with PATH limited to Windows system
directories. **Never commit build/package/**. Use -BuildDirectory and -Destination
for alternate locations, and deploy to a fresh folder to avoid stale files.

## CLI modes

Launch a PowerShell shell with native DLL paths initialized:

~~~powershell
. .\scripts\runtime-environment.ps1
$null = Set-RetinaGramRuntimeEnvironment -BuildDirectory .\build\ninja
.\build\ninja\RetinaGram.exe --analyze 'D:\Scans\fundus.jpg'
.\build\ninja\RetinaGram.exe --batch 'D:\Scans\Batch' 'D:\Reports\Batch'
.\build\ninja\RetinaGram.exe --benchmark 'D:\Scans\fundus.jpg' 3
.\build\ninja\RetinaGram.exe --screenshot .\build\capture.png Capture --size 1426x952
.\build\ninja\RetinaGram.exe --model-info
.\build\ninja\RetinaGram.exe --validate-models
~~~

Benchmark iterations are 1–20. Screenshot accepts Capture, Analysis, Compare,
Report, History, Batch Analysis, or Cloud Sync. An optional OS/OD selection,
--result saved-result.json, --eye OS, --patient patient.json, and --view select
retained visualizations. --batch-input selects Batch discovery state.
Saved-result and batch-input screenshot modes isolate application data.
For example, --view "Lesion Probability" selects that Analysis view.

## Environment variables

| Variable | Behavior |
| --- | --- |
| RETINAGRAM_FORCE_CPU=1 | Force Torch CPU and ONNX CPU. Presence is tested; even a value of 0 forces CPU. Unset it to restore automatic selection. |
| RETINAGRAM_ENABLE_LESION_CAM=1 | Opt in to lesion CAM through the configured environment switch; routine lesion CAM is disabled. |
| RETINAGRAM_MODEL_CONFIG | Explicit model JSON path; missing/invalid overrides fail rather than silently falling back. |
| QT_ROOT / TORCH_ROOT / ONNXRUNTIME_ROOT / CUDA_PATH | Optional dependency overrides for development scripts. |

## Data storage

Imported scans and session/history metadata use Qt's Windows
QStandardPaths::AppLocalDataLocation for the RetinaGram organization/application.
The directory contains session.json and retained run images, full masks, heatmaps,
and report references. No user-specific path is compiled in. Exported reports go
to the user's selected destination, and Batch reports go to its selected output.
Keep all patient/local data out of version control.

## Reporting

Save Left Eye Report, Save Right Eye Report, and History Download export complete
bundles under a selected **existing parent directory**:

~~~text
RetinaGram_<SanitizedPatientName>_<YYYYMMDD_HHMMSS>/
  Left_OS/                         # Right_OD/ for OD
    report.pdf
    results.json
    original_fundus.jpg
    restored_fundus.png            # Only when restoration was performed
    lesion_overlay.png            # When available
    masks/
      microaneurysm.png            # MA
      hemorrhage.png               # HE
      hard_exudate.png             # EX
      soft_exudate.png             # SE
~~~

Save Both Reports creates **one shared root** with Left_OS and Right_OD when both
eyes are complete. Windows-safe patient names and _2, _3 suffixes prevent collisions.
Saving is an export operation: it never repeats inference. The original is a real
RGB JPEG at quality 95; restored images, combined overlay, and **full** masks are
copied unchanged. CAM, probability maps, UI selections, and temporary files are
not copied.

Pretty UTF-8 results.json preserves analysis numbers and includes report/patient
metadata, quality and grading, canonical lesions, device, pipeline state, analysis
source, generation time, and portable relative artifact references. Restoration
is null when absent. Legacy unavailable detection may be null; NaN/Infinity fails
export. The PDF consumes copied bundle artifacts. GUI success displays the root
and persists the corresponding eye's PDF path in History. Fatal writes remove
only the newly allocated export root; History persistence failure is reported
separately.

Saved-result CLI export does not load models:

~~~powershell
.\build\package\RetinaGram.exe --export-report-bundle result.json 'D:\Reports' patient.json OS
.\build\package\RetinaGram.exe --export-both-bundles left-result.json right-result.json 'D:\Reports' patient.json
~~~

--export-report <result.json> <pdf-path> <patient.json> <OS|OD> remains the PDF-only
utility. Batch PDF output follows its own folder options. Details:
[specs/S4-report-export-bundle.txt](specs/S4-report-export-bundle.txt).

## Batch analysis

The GUI supports structured patient folders and flat ID_Name_OS / ID_Name_OD
filenames. Discovery reviews duplicate eye candidates and unresolved entries.
The skip-unresolved option must be explicitly selected. Patient-wise output uses
Windows-safe ID_Name/Left_OS and ID_Name/Right_OD groups. Disabling patient-wise
folders uses numbered Patient_001_ID_Name groups. The --batch CLI retains its
relative-folder behavior and rejects ambiguous/missing eye labels.

Capacity uses detected CUDA device name and total VRAM, with the reference
max(1, floor(0.006 * VRAM_MB + 41.66)) limit. Pause/Cancel apply between images;
the current image finishes, and Resume/Cancel wakes a paused worker.

## Compatible model replacement

Put a compatible artifact directly in checkpoints/, update the corresponding
stage in config/models.json, run --validate-models, and restart. No C++ compilation
is needed for an existing adapter contract. Update the checkpoint Git allowlist
deliberately if publishing a replacement.

ModelFactory creates persistent adapters implementing IQualityModel,
IRestorationModel, IGradingModel, and ILesionModel. JSON configures filenames,
supported dimensions/dtypes/normalization, explicit output contract and class/
channel ordering. ModelManager does not contain backend tensor operations.

Classification supports logits/softmax or validated probabilities/none.
Segmentation supports logits/sigmoid or probabilities/none. TorchScript supports
a scores tensor or a two-tensor scores/activations tuple at explicit indices.
CAM must be disabled for tensor-only outputs. Inputs remain RGB/NCHW; resizing
preserves the Pillow bilinear arithmetic. All four stages are required.

ONNX metadata and native shape probes validate contracts. Successful probes are
content-addressed by model bytes, contract, Torch version, and CPU/CUDA selection.
Cache misses use a short-lived native helper to keep validation warm-up separate
from patient inference; --validate-models forces fresh probes. An arbitrary new
runtime, clinical class, task, tensor contract, or CAM mechanism still requires
an adapter and potentially UI/report code. See
[specs/S2-model-modularity.txt](specs/S2-model-modularity.txt).

## Validation and development scripts

Configure both test options shown above to build the four test executables.
Inference tests use CTest. UI tests need RETINAGRAM_UI_OUTPUT (existing output
directory), RETINAGRAM_TEST_IMAGE, and RETINAGRAM_TEST_RESULT. Functional and bundle
tests additionally use RETINAGRAM_GOOD_RESULT and RETINAGRAM_USABLE_RESULT with
complete retained artifacts. Functional tests exercise real models. Test runners
use isolated application identities and are excluded from deployment.

~~~powershell
. .\scripts\runtime-environment.ps1
$null = Set-RetinaGramRuntimeEnvironment -BuildDirectory .\build\ninja
ctest --test-dir .\build\ninja --output-on-failure
# Set the fixture variables described above before these commands:
.\build\ninja\RetinaGramUiSmoke.exe
.\build\ninja\RetinaGramReportBundleTests.exe
.\build\ninja\RetinaGramFunctionalSmoke.exe
~~~

Use the Windows Qt platform for PDF typography review. The offscreen platform's
synthetic fonts are unsuitable for that check; it remains useful for isolated UI
canvas tests, including 1920x1080.

| Script | Purpose |
| --- | --- |
| create_quality_cases.py | Generate deterministic quality-routing development candidates from a local image |
| compare_reference.py | Run the read-only pc-gpu Python pipeline on copied validation inputs |
| compare_outputs.py | Compare six ordered native/reference cases, masks, restoration and grade CAM |
| benchmark_reference.py | Measure persistent reference models, stage timing and sampled memory |
| benchmark-native.ps1 | Benchmark explicit -GoodImage and -UsableImage inputs |
| compare_modularity.py | Strict before/after native JSON and decoded PNG comparison |
| test-model-replacement.ps1 | Verify config-selected renamed artifact with unchanged executable hash |
| export_models.py / export_onnx.py / tune_iqa.py / quantize_iqa_weights.py / verify_precision.py | Offline conversion experiments and checks; never needed by runtime |

Offline Python tools need the reference checkout, its development dependencies,
and source checkpoints. Set RETINAGRAM_REFERENCE_ROOT to that separate checkout.
RETINAGRAM_SOURCE_CHECKPOINTS optionally selects a source-weight directory;
the IQA backbone can also be read from the existing Torch cache.
RETINAGRAM_TEST_IMAGE selects the quality-case source. For comparison/calibration,
RETINAGRAM_VALIDATION_MANIFEST names a JSON array of **six ordered image paths**:
four Good examples, one Usable, then one Reject. Inputs and outputs remain local
under build/validation; do not publish patient scans. The reference pipeline runs
only on copies because it writes artifacts beside inputs. Offline conversion
tools can overwrite deployment models: run them deliberately in an experimental
clone and repeat validation before adopting results.

## Build troubleshooting

- **C1083: Cannot open include file: 'limits'** usually means MSVC INCLUDE/LIB
  was not initialized. Use x64 Native Tools Command Prompt, or call
  VsDevCmd.bat -arch=x64; do not rewrite source to fix an uninitialized compiler.
- **Qt platform plugin failure:** initialize the development DLL paths and match
  Qt/plugins versions; for deployment include platforms/qwindows.dll.
- **ONNX Runtime missing/wrong version:** verify ONNXRUNTIME_ROOT and selected
  native DLLs. An older ORT DLL on PATH can override the intended SDK; the launch
  script prepends the configured runtime directory.
- **CUDA/cuDNN DLL failure:** match runtime versions, use a compatible driver,
  and retain cuDNN/NVRTC components collected by deployment.
- **Models not found:** inspect --model-info, the explicit config override,
  checkpoints_directory relative to JSON, and each configured flat filename.
- **Unexpected CPU execution:** unset RETINAGRAM_FORCE_CPU entirely, then inspect
  device/provider output and CUDA initialization errors. CPU execution is much slower.
- **Package appears stale:** build after editing source, then deploy to a fresh
  destination. Deployment is not compilation.

## Validation limits and measurements

[BENCHMARK.md](BENCHMARK.md) records the small local performance sample and parity
limitations. Six local cases agreed on quality/routing; five applicable grades
agreed with the FP32 reference. Usable restoration PSNR was about 49.7 dB.
BF16 differences affected sparse lesions, including zero overlap on sparse EX
masks in two cases. These results are not clinical validation.

The modularity refactor had seven of eight strict comparisons exact. GPU Usable
varied by at most one restored uint8 intensity level, with downstream confidence/
mask differences; repeated original runs also varied. Do not claim bitwise
determinism or arbitrary-model compatibility. CUDA snapshots include other device
allocations and are not isolated process peak VRAM.

## Original reference, history, and architecture graph

[pc-gpu](https://github.com/Parthik880/Diabetic-Retinopathy-/tree/pc-gpu) is the
original Python/Electron reference used for behavioral and UI parity.
PCGPU.cpp is the native implementation. Reference checkouts remain read-only.

Start with [specs/S1-first_draft.txt](specs/S1-first_draft.txt), then the later
specs and [AGENTS.md](AGENTS.md). Both historical S2 records are retained under
their original filenames. Major future changes append specs rather than replacing
history.

[graphify-out/GRAPH_REPORT.md](graphify-out/GRAPH_REPORT.md) and
[graphify-out/graph.json](graphify-out/graph.json) describe the cleaned code/docs
corpus. Open graphify-out/graph.html locally for the interactive graph. Interpreter,
root, cache, cost, and temporary Graphify state are excluded from Git.
