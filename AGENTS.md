# RetinaGram native development guidance

## Project identity and mandatory first reads

PCGPU.cpp is the native C++20 / Qt 6 branch. pc-gpu is the original Python/Electron reference. Before changes, read README.md, this file, specs/S1-first_draft.txt, BENCHMARK.md, and the relevant later specs completely. Inspect graphify-out/GRAPH_REPORT.md and graphify-out/graph.json for architectural context; verify graph facts against current source. Historical S2 files intentionally share a number and must retain their original names.

## Reference and frontend authority

Keep the separate pc-gpu checkout read-only. Its path is supplied by RETINAGRAM_REFERENCE_ROOT for offline tools; do not assume a specific Windows account or sibling directory. Safe Git fetch/worktree metadata operations are allowed when explicitly requested. Do not edit reference files or run its artifact-producing pipeline directly on reference input files; use local copies.

For frontend parity inspect frontend/src/components/TopAppBar.tsx, CaptureScreen.tsx, AnalysisScreen.tsx, AnalysisVisualization.tsx, CompareScreen.tsx, ReportScreen.tsx, HistoryScreen.tsx, BatchAnalysisScreen.tsx, CloudSyncScreen.tsx, and frontend/src/index.css on pc-gpu. Match viewport dimensions before comparing proportions. MainWindow, the controller, and the persistent worker implement native workflow; use the page files rather than recreating a web runtime.

## Scope and regression baseline

This project is a native C++20 / Qt 6 application. The sibling Diabetic-Retinopathy- checkout is read-only. Read specs/S1-first_draft.txt and the relevant later spec before changing behavior. The current native production artifacts and their outputs are the regression baseline for architecture work; do not re-export, quantize, retrain or change numerical behavior as part of a refactor.

## Inference architecture

ModelManager is the serialized pipeline orchestrator and UI/controller QVariantMap boundary. Its mutex protects initialization and the complete analysis call. Persistent adapters are created once by ModelFactory from config/models.json. Public stage contracts in include/inference/ModelTypes.h are IQualityModel, IRestorationModel, IGradingModel and ILesionModel, with typed canonical results. Do not expose ONNX/Torch tensors through these interfaces.

DO NOT add hard-coded model filenames, input resolutions, precision details, output tuple indices, class/channel ordering or backend session/module calls back into ModelManager.

The current adapters are OnnxQualityModel and OnnxRestorationModel in stages/OnnxModels.cpp, TorchScriptGradingModel, and TorchScriptLesionModel. Runtime headers and helpers stay private under src/inference/stages/. Reusable RGB/NCHW preprocessing remains in Preprocessing.cpp; preserve the existing Pillow-compatible bilinear arithmetic and rounding.

LesionPostprocessor consumes borrowed canonical CPU FP32 probability planes. It owns full threshold masks, 8-connected components, minimum-area filtering, proximity merging, bounding boxes, centroids, region probabilities and display artifacts. Keep full masks independent of filtered display regions and UI Top-K. Model input resolution and postprocessing reference size are separate concepts. The current canonical clinical/display classes are MA, HE, EX and SE.

ResultSerialization is the legacy UI map boundary. Preserve all existing result keys, warning strings, canonical probability order and artifact basenames. Actual run UUID directories and timing values vary and are normalized only in validation comparisons.

## Configuration and model replacement

config/models.json version 1 is the deployment source of truth. It resolves checkpoints_directory relative to the JSON file and requires flat model filenames. RETINAGRAM_MODEL_CONFIG overrides the JSON path; missing or invalid explicit overrides must fail clearly. Required fields and supported values are validated rather than silently defaulted. All four pipeline stages remain required.

Compatible replacements require only a new artifact in checkpoints/, configuration changes and restarting the app. Do not claim arbitrary runtime/tasks/tensor contracts or new clinical classes work through JSON alone. See README Replacing models and specs/S2-model-modularity.txt for the implemented schema and limits.

Startup validates model contracts before patient work. Metadata covers ONNX and Torch schemas; a native CLI helper performs shape probes on cache misses so validation does not alter the patient process's kernel initialization order. The content-addressed contract cache includes model bytes, contract settings, Torch version and CPU/CUDA device. --validate-models forces validation; --model-info prints configuration. Changing validation assumptions requires updating the cache version/key and tests. Never cache failed validation.

## Pipeline invariants

Production artifacts are iqa_int8.onnx (partial QDQ INT8/FP32, not fully INT8), nafnet_fp16.onnx (FP16 internals, FP32 boundary), lesion_bf16_cam.pt and grade_bf16_cam.pt (BF16 TorchScript). Verify hashes in checkpoints/MODEL_MANIFEST.json. Do not regenerate weights or change precision, preprocessing, thresholds, or numerical behavior during unrelated UI/documentation work. Original FP32 source checkpoints are kept outside this native branch.

Default lesions use 768x768 input and independent sigmoid threshold 0.5, original-pixel coordinates, 8-connected components, the canonical minimum-area/proximity settings, full masks and Top-K display filtering. Grade labels are 0 No diabetic retinopathy, 1 Mild NPDR, 2 Moderate NPDR, 3 Severe NPDR, and 4 Proliferative DR.

IQA is invoked exactly once per eye. Good uses the original image for grading/CAM then lesions. Usable invokes restoration, saves restored.png and uses the restored image for grading/CAM and lesions. Reject returns RECAPTURE_REQUIRED without invoking downstream stage interfaces. Grade CAM defaults on; lesion CAM defaults off with RETINAGRAM_ENABLE_LESION_CAM=1 opt-in. Preserve RETINAGRAM_FORCE_CPU behavior and paired ONNX CUDA-to-CPU fallback. Do not add concurrent calls to shared runtime sessions/modules.

## Adding an adapter

1. Define an explicit supported image/tensor/output contract with clear validation errors.
2. Implement the matching typed stage interface and keep runtime types private.
3. Add validated adapter selection/schema support in ModelConfig and ModelFactory; avoid dynamic tensor guessing.
4. Reuse preprocessing and the canonical lesion postprocessor where appropriate.
5. Add sources to RetinaGramInference in CMake and add configuration, contract, routing and output-adaptation tests.
6. Verify renamed compatible artifacts, cache invalidation, CUDA and CPU, default-model output parity, startup/inference/memory and packaged deployment.
7. Document any new runtime, task, CAM or clinical/UI requirements. Update README and the architecture spec after implementation and validation.

## Build and validation

From x64 Native Tools Command Prompt for VS 2022:

```bat
set QT_ROOT=C:\Qt\6.8.3\msvc2022_64
set TORCH_ROOT=D:\SDKs\libtorch
set ONNXRUNTIME_ROOT=D:\SDKs\onnxruntime-gpu-windows-1.26.0
cmake -S . -B build\ninja -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="%QT_ROOT%;%TORCH_ROOT%" -DONNXRUNTIME_ROOT="%ONNXRUNTIME_ROOT%" -DRETINAGRAM_BUILD_UI_TESTS=ON -DRETINAGRAM_BUILD_INFERENCE_TESTS=ON
cmake --build build\ninja --parallel 3
```

Normal PowerShell may lack MSVC INCLUDE/LIB variables. C1083 missing <limits> normally means the compiler environment is uninitialized: use the tools prompt or VsDevCmd.bat -arch=x64. Do not change source to compensate.

UI loop: edit -> build -> powershell -File scripts/run-dev.ps1. Packaging loop: edit -> build -> scripts/deploy-windows.ps1 -> build/package/RetinaGram.exe. Deployment does not imply compilation. scripts/runtime-environment.ps1 reads dependency paths from the selected CMake cache or environment overrides; do not add developer-specific absolute paths. Keep Qt, Torch, ORT and CUDA versions coherent.

Use --screenshot for Capture, Analysis, Compare, Report, History, Batch Analysis and Cloud Sync. Historical desktop comparisons use 1426x952 / 1440x960; also verify 1920x1080 in the isolated UI runner. Compare identical viewport dimensions. Use --result or --batch-input and test fixture identities to avoid altering production sessions. Cloud Sync is currently local/disconnected; do not claim a working cloud backend.

Use the VS2022 x64 environment. RetinaGramInference is a static library shared by the application and functional/inference tests; Qt keyword macros are disabled for its sources. Native source changes must be rebuilt before deployment.

Enable RETINAGRAM_BUILD_INFERENCE_TESTS for configuration/routing/postprocessing tests and RETINAGRAM_BUILD_UI_TESTS for existing UI/functional gates. Validation fixtures use isolated app identities. scripts/compare_modularity.py compares archived before/after native results and PNG pixels. Exclude only variable run directories and timings; investigate any numerical, coordinate, mask, restoration, CAM or warning differences.

scripts/deploy-windows.ps1 packages config/models.json and only the artifacts named in that config into one flat checkpoints/ directory. Test packaged --validate-models, visible launch and inference with PATH limited to Windows system folders. Keep Python and offline export tooling out of production runtime.

Do not overwrite specs/S1-first_draft.txt. Write specs after code and validation; report measured results and limitations rather than an aspirational architecture.

## Report bundles

Save Report exports a BUNDLE, not just a PDF. The pc-gpu reference is backend/utils/reporting.py export_report_bundle and the single/bilateral endpoints and frontend save actions. ReportBundle.cpp validates saved complete results and artifacts, allocates one exclusive collision-safe RetinaGram patient/time root, writes Left_OS/Right_OD subfolders, and rolls back that new root on fatal failure. Never recursively copy the inference run directory and never rerun inference for export.

Preserve original_fundus.jpg as an actual RGB JPEG at quality 95; copy actual restored_fundus.png only when present; reuse lesion_overlay.png and full masks under masks/microaneurysm.png, hemorrhage.png, hard_exudate.png, soft_exudate.png. Do not export Top-K/selected regions, probability maps or CAM files. Keep portable relative references and the original analysis probabilities in UTF-8 results.json. Reject non-finite JSON values.

Save Both must dispatch one bilateral export rather than two single exports. UI notices show the report root. After success rememberReportPath updates the appropriate eye result.report_path in current/persisted History data and checks atomic session persistence; do not change session identifiers or saved scan times. A failed History update must not be advertised as successful persistence. The PDF renderer is shared with Batch; bundle export adapts its image paths without changing its layout.

Read specs/S4-report-export-bundle.txt before changing export semantics. Run ReportBundleTests and the report/History functional cases. Verify packaged exports with the Windows Qt platform and inspect rendered Good/Usable PDFs; offscreen synthetic fonts are unsuitable for typography verification. CLI bundle export must succeed without any model initialization. Batch folder semantics and the inference configuration are independent of this exporter.

## Repository hygiene and Git safety

Publish genuine source, config, runtime assets, four production artifacts, scripts, tests, documentation, specs and portable Graphify output only. Never commit build/, package/, downloaded toolchains, DLLs/EXEs/compiler objects, reference-ui copies, node_modules, environments, caches, raw validation screenshots/JSON, patient images, local sessions/databases, credentials or machine-specific Graphify state. Source .pth and experimental exports are ignored; do not delete the only surviving model copy.

Before every push inspect git status, git diff --stat, git diff, staged paths, large-file sizes and secrets. Graphify publication is explicitly limited to graph.json, GRAPH_REPORT.md, graph.html (or graphify.html), and its portable README. Exclude .graphify_root, .graphify_python, cache, cost.json, analysis/temp files and absolute filesystem paths. Regenerate through the official Graphify tool/library; never invent graph edges or pretend an extraction failure succeeded.

Never force-push main or pc-gpu, delete reference branches, or replace their contents. PCGPU.cpp is the native publication branch. Preserve existing ancestry through a publishing worktree based on origin/pc-gpu; replace implementation files only inside that isolated worktree. Build the publishable source successfully before pushing. No default branch change is part of this project.

## Known validation limits

The local quality/grade sample is small and not clinical validation. BF16 differences can change sparse masks, including zero EX overlap in two FP32/reference comparisons. Modularity checks had seven of eight comparisons exact; GPU Usable differed by at most one restored uint8 level and downstream confidence/masks. The original executable also varied across repeated GPU Usable runs. Preserve this evidence rather than claiming bitwise determinism or clinical equivalence. Native CUDA memory snapshots include other allocations and are not isolated process peaks. Read BENCHMARK.md and S2-model-modularity.txt before interpreting performance.
