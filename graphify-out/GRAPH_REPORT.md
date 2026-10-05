# Graph Report - RetinaGram  (2026-10-05)

## Corpus Check
- 80 files · ~70,192 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1201 nodes · 2412 edges · 67 communities (58 shown, 4 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 260 edges (avg confidence: 0.85)
- Token cost: host semantic token usage unavailable. Tool counters are 0 input / 0 output and exclude host-agent usage; no zero-cost claim is made.

## Community Hubs (Navigation)
- Window Screen Construction
- MainWindow Public Interface
- Resource And Image Paths
- Offline Model Conversion
- Report Bundle Export
- Typed Inference Tests
- Analysis Visualization
- Serialized Pipeline Routing
- Model Configuration Validation
- ONNX Inference Sessions
- Lesion Region Postprocessing
- Controller Work Dispatch
- Torch Lesion Adapter
- Typed Pipeline Contracts
- Torch Grading Adapter
- Runtime Contract Probes
- Patient And Batch Workflow
- Controller Public Interface
- Batch Screen Controls
- Persistent Analysis Worker
- Report Data Schema
- Interactive Image Stage
- RGB Tensor Preprocessing
- Flow Layout Widgets
- Lesion Region Schema
- Torch Tensor Helpers
- Portable Build And Deployment
- Patient Eye State
- Model Adapter Factory
- Controller Header Dependencies
- UI Components And Regression
- Responsive Grid Layout
- Historical Numerical Validation
- Window And Functional Tests
- Saved Analysis Report Bundles
- Model Input Schema
- ModelManager Public Interface
- Native Command Line Modes
- Model Configuration Schema
- Widget Sizing And Geometry
- Public Header Dependencies
- Model Output Schema
- Lesion Channel Schema
- Grade Result Schema
- Page Rebuild Dispatch
- Report Image Widget
- Asset Licensing And Provenance
- Native CMake Targets
- Reference Parity Comparison
- SDK And Runtime Discovery
- Quality Result Schema
- Lesion Result Schema
- Historical Publication Preparation
- Strict Modularity Comparison
- Lesion Class Schema
- Restoration Result And History
- Segmentation Probability Planes
- Segmented Selection Widget
- Legacy Result Serialization
- Deployment Bash Entry
- Developer Bash Entry
- PDF Renderer Interface

## God Nodes (most connected - your core abstractions)
1. `MainWindow` - 136 edges
2. `AnalysisController` - 31 edges
3. `StageConfig` - 29 edges
4. `AnalysisWorker` - 27 edges
5. `RuntimeContext` - 26 edges
6. `MainWindow::buildAnalysis()` - 26 edges
7. `ReportBundleTests` - 23 edges
8. `LesionRegion` - 21 edges
9. `rebuildPage` - 21 edges
10. `stage()` - 21 edges

## Surprising Connections (you probably didn't know these)
- `Historical three-run sample: warm Good ~14% faster, Usable ~24% slower` --references--> `Usable: restoration -> restored grade/CAM -> lesions`  [EXTRACTED]
  BENCHMARK.md → README.md
- `Reserved resources; images/fonts in assets and models in src/checkpoints` --references--> `Current flat deployment artifacts under src/checkpoints`  [EXTRACTED]
  resources/README.md → specs/S6-portable-project-layout.txt
- `Historical ORT DLL selection repair from an older installed runtime` --semantically_similar_to--> `Shared scripts/dependencies.ps1 bounded SDK discovery`  [INFERRED] [semantically similar]
  specs/S5-publication-validation.txt → specs/S6-portable-project-layout.txt
- `AnalysisWorker::processBatch()` --calls--> `processBatchPlan`  [INFERRED]
  src/app/AnalysisController.cpp → src/include/app/AnalysisController.h
- `RestorationStub` --inherits--> `IRestorationModel`  [EXTRACTED]
  tests/InferenceTests.cpp → src/include/inference/ModelTypes.h

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Persistent adapters and typed-to-legacy pipeline** — specs_s2_model_modularity_modelmanager, specs_s2_model_modularity_modelfactory, specs_s2_model_modularity_iqualitymodel, specs_s2_model_modularity_irestorationmodel, specs_s2_model_modularity_igradingmodel, specs_s2_model_modularity_ilesionmodel, specs_s2_model_modularity_lesionpostprocessor, specs_s2_model_modularity_resultserialization [EXTRACTED 1.00]
- **Saved single/bilateral report export and retention** — specs_s4_report_export_bundle_reportbundle, specs_s4_report_export_bundle_bilateral_export, specs_s4_report_export_bundle_full_mask_export, specs_s4_report_export_bundle_results_json, specs_s4_report_export_bundle_shared_pdf_renderer, specs_s4_report_export_bundle_rememberreportpath [EXTRACTED 1.00]
- **Source/package portability through shared runtime discovery** — specs_s6_portable_project_layout_apppaths, specs_s6_portable_project_layout_explicit_config_selection, specs_s6_portable_project_layout_checkpoint_layout, specs_s6_portable_project_layout_run_sh, specs_s6_portable_project_layout_deploy_sh, specs_s6_portable_project_layout_package_layout [EXTRACTED 1.00]

## Communities (67 total, 4 thin omitted)

### Community 0 - "Window Screen Construction"
Cohesion: 0.06
Nodes (90): QEvent, buildEmptyState, buildPageFrame, dispatchNextEye, eyeName, eyeState, historySessionId, navigate (+82 more)

### Community 1 - "MainWindow Public Interface"
Cohesion: 0.02
Nodes (90): Page, Q_OBJECT, QMap, QPointF, QQueue, QStringList, View, MainWindow (+82 more)

### Community 2 - "Resource And Image Paths"
Cohesion: 0.06
Nodes (58): QDir, QFileInfo, batchImagePlan(), batchPatientReady(), QMap, QPair, QString, QVariantList (+50 more)

### Community 3 - "Offline Model Conversion"
Cohesion: 0.06
Nodes (45): CalibrationDataReader, Image, InferenceSession, main(), Benchmark the untouched Python pipeline with persistent CUDA models., sync(), Run the untouched Python pipeline against the native validation images. This is…, main() (+37 more)

### Community 4 - "Report Bundle Export"
Cohesion: 0.06
Nodes (49): QByteArray, BilateralReportExportResult, eyes, files, reportPaths, rootFolder, QList, QString (+41 more)

### Community 5 - "Typed Inference Tests"
Cohesion: 0.06
Nodes (29): production_, defaultPath, load, IQualityModel, infer, process, Calls, grade (+21 more)

### Community 6 - "Analysis Visualization"
Cohesion: 0.11
Nodes (37): QKeyEvent, availableLesionClasses, buildVisualization, gradeText, regionKey, resultFor, visualizationImage, box() (+29 more)

### Community 7 - "Serialized Pipeline Routing"
Cohesion: 0.09
Nodes (29): exception, ModelFactory, create, unique_ptr, ModelStages, cuda, grading, lesion (+21 more)

### Community 8 - "Model Configuration Validation"
Cohesion: 0.24
Nodes (18): QJsonValue, canonicalClasses(), array, ModelConfig, QJsonObject, QString, QStringList, TensorDtype (+10 more)

### Community 9 - "ONNX Inference Sessions"
Cohesion: 0.11
Nodes (23): ONNXTensorElementDataType, Session, QImage, QString, ScalarType, Tensor, TensorDtype, vector (+15 more)

### Community 10 - "Lesion Region Postprocessing"
Cohesion: 0.10
Nodes (26): progress, canonicalRegion(), array, ProgressCallback, QImage, QString, uchar, vector (+18 more)

### Community 11 - "Controller Work Dispatch"
Cohesion: 0.15
Nodes (22): MainWindow, AnalysisController::AnalysisController(), AnalysisController::controlBatch(), AnalysisController::enqueueAnalysis(), AnalysisController::enqueueBatch(), AnalysisController::enqueueBatchPlan(), AnalysisController::onBatchFinished(), AnalysisController::onCompleted() (+14 more)

### Community 12 - "Torch Lesion Adapter"
Cohesion: 0.10
Nodes (20): ILesionModel, infer, array, LesionPostprocessor, classes_, referenceSize_, Tensor, TorchOutputs (+12 more)

### Community 13 - "Typed Pipeline Contracts"
Cohesion: 0.17
Nodes (24): Native architectural and publication guidance, Good: original -> grade/CAM -> lesion segmentation, IQA once per eye determines Good/Usable/Reject routing, Reject: RECAPTURE_REQUIRED, downstream analysis skipped, Usable: restoration -> restored grade/CAM -> lesions, Explicit tensor/two-tensor output and optional CAM contract, Canonical quality, grade and lesion channel/class mapping, Content-addressed successful model-contract cache (+16 more)

### Community 14 - "Torch Grading Adapter"
Cohesion: 0.11
Nodes (18): Env, IGradingModel, infer, Device, RuntimeContext, cuda, env, externalContractsVerified (+10 more)

### Community 15 - "Runtime Contract Probes"
Cohesion: 0.14
Nodes (20): IValue, StageConfig, adapter, camEnabled, camEnvironment, input, model, output (+12 more)

### Community 16 - "Patient And Batch Workflow"
Cohesion: 0.16
Nodes (21): AnalysisController imports, local History, reports and Batch, Cloud Sync remains a disconnected local integration, Local session.json, retained images/masks and report references, MainWindow patient/eye selection and seven native screens, RetinaGram native C++20 / Qt 6 screening, Patient registration and OS/OD eye workflow, Persistent background model worker, CPU LesionPostprocessor full masks and original-coordinate regions (+13 more)

### Community 17 - "Controller Public Interface"
Cohesion: 0.10
Nodes (20): AnalysisController, active_, controlBatch, enqueueAnalysis, enqueueBatch, enqueueBatchPlan, initializationError_, onBatchFinished (+12 more)

### Community 18 - "Batch Screen Controls"
Cohesion: 0.15
Nodes (17): discoverBatch, setBatchStatus, action(), card(), column(), QFrame, QList, QResizeEvent (+9 more)

### Community 19 - "Persistent Analysis Worker"
Cohesion: 0.11
Nodes (18): AnalysisWorker, analyze, batchCancelled_, batchCapacity, batchFinished, batchMutex_, batchPaused_, batchProgress (+10 more)

### Community 20 - "Report Data Schema"
Cohesion: 0.11
Nodes (18): Data, confidence, device, eye, grade, lesions, metadata, original (+10 more)

### Community 21 - "Interactive Image Stage"
Cohesion: 0.18
Nodes (10): QImage, QMouseEvent, QPaintEvent, QPointF, QRectF, ImageStage, image, pointMoved (+2 more)

### Community 22 - "RGB Tensor Preprocessing"
Cohesion: 0.24
Nodes (16): pair, channel, chwPixels(), QColor, QImage, QString, span, vector (+8 more)

### Community 23 - "Flow Layout Widgets"
Cohesion: 0.18
Nodes (7): Orientations, QLayout, QLayoutItem, FlowLayout, gap_, items_, QWidget

### Community 24 - "Lesion Region Schema"
Cohesion: 0.12
Nodes (16): LesionRegion, area, centerX, centerY, centroidX, centroidY, code, maximumProbability (+8 more)

### Community 25 - "Torch Tensor Helpers"
Cohesion: 0.19
Nodes (14): QImage, ScalarType, Tensor, TensorDtype, heatmap(), imageTensor(), normalizedCam(), torchDtype() (+6 more)

### Community 26 - "Portable Build And Deployment"
Cohesion: 0.29
Nodes (15): ModelConfig version 1 and compatible model replacement, Historical root/checkpoints and RETINAGRAM_MODEL_CONFIG selection, AppPaths shared runtime root resolver, Current flat deployment artifacts under src/checkpoints, Shared scripts/dependencies.ps1 bounded SDK discovery, deploy.sh builds, packages and validates with Windows-only PATH, Legacy model-config environment ignored; explicit --model-config CLI selection, Former stale config environment selected another deployment root (+7 more)

### Community 27 - "Patient Eye State"
Cohesion: 0.14
Nodes (15): EyeState, capturedAt, error, imagePath, result, stage, QString, QVariantMap (+7 more)

### Community 28 - "Model Adapter Factory"
Cohesion: 0.18
Nodes (10): IRestorationModel, infer, ModelConfig, ModelFactory::create(), shared_ptr, unique_ptr, createOnnxQuality(), createOnnxRestoration() (+2 more)

### Community 29 - "Controller Header Dependencies"
Cohesion: 0.17
Nodes (9): atomic, condition_variable, QThread, QMap, QObject, QPair, QVariantMap, MainWindow (+1 more)

### Community 30 - "UI Components And Regression"
Cohesion: 0.35
Nodes (9): QIcon, QProgressBar, QLabel, buttonIcon(), QString, icon(), meter(), pill() (+1 more)

### Community 31 - "Responsive Grid Layout"
Cohesion: 0.17
Nodes (10): QGridLayout, QList, QResizeEvent, ResponsiveGrid, columns_, grid_, single_, stretch_ (+2 more)

### Community 32 - "Historical Numerical Validation"
Cohesion: 0.25
Nodes (11): Preserve model bytes and numerical/output contracts, Local quality/grade agreement does not establish clinical equivalence, Historical migration/modularity measurements and limits, Total-device CUDA snapshots are not isolated process peaks, Historical native parity was exact in seven of eight comparisons, Historical three-run sample: warm Good ~14% faster, Usable ~24% slower, Four unchanged production artifacts in src/checkpoints, Historical IQA quantization limited after local parity failures (+3 more)

### Community 33 - "Window And Functional Tests"
Cohesion: 0.22
Nodes (7): QMainWindow, QVector, QQueue, QComboBox, QScrollArea, QStackedWidget, PatientSelector

### Community 34 - "Saved Analysis Report Bundles"
Cohesion: 0.40
Nodes (11): Deliberate report-bundle artifacts and relative manifest, One bilateral export root with Left_OS and Right_OD, S4 historical report-bundle implementation record, Exclusive sanitized patient/time report root, Report preflight and rollback remove only the new root, rememberReportPath updates retained History using checked atomic persistence, ReportBundle exports retained complete analyses without reinference, UTF-8 results.json preserves saved analysis values (+3 more)

### Community 35 - "Model Input Schema"
Cohesion: 0.18
Nodes (11): TensorDtype, InputConfig, acceptedDtypes, dtype, dynamicSpatial, height, mean, name (+3 more)

### Community 36 - "ModelManager Public Interface"
Cohesion: 0.20
Nodes (9): Impl, unique_ptr, ModelManager, analyzeImage, impl_, initialize, isCudaAvailable, isReady (+1 more)

### Community 37 - "Native Command Line Modes"
Cohesion: 0.36
Nodes (9): initialize, processBatch, analyzeFromCommandLine(), batchFromCommandLine(), benchmarkFromCommandLine(), QJsonObject, gpuMemorySnapshot(), main() (+1 more)

### Community 38 - "Model Configuration Schema"
Cohesion: 0.20
Nodes (10): ModelConfig, applicationRoot, checkpointsDirectory, file, grading, lesion, lesionClasses, postprocessingReferenceSize (+2 more)

### Community 40 - "Public Header Dependencies"
Cohesion: 0.31
Nodes (4): QString, QImage, span, vector

### Community 41 - "Model Output Schema"
Cohesion: 0.25
Nodes (8): QStringList, OutputConfig, activationsIndex, classes, name, probabilities, scoresIndex, tuple

### Community 42 - "Lesion Channel Schema"
Cohesion: 0.22
Nodes (9): uchar, LesionChannelResult, binaryMask, camPath, code, maskPath, probabilityPath, rawRegions (+1 more)

### Community 43 - "Grade Result Schema"
Cohesion: 0.25
Nodes (8): GradeResult, camMs, camPath, confidence, forwardMs, grade, probabilities, warnings

### Community 44 - "Page Rebuild Dispatch"
Cohesion: 0.25
Nodes (8): buildAnalysis, buildBatch, buildCapture, buildCloud, buildCompare, buildHistory, buildReport, MainWindow::rebuildPage()

### Community 45 - "Report Image Widget"
Cohesion: 0.29
Nodes (3): QPaintEvent, QSize, ReportImage

### Community 46 - "Asset Licensing And Provenance"
Cohesion: 0.43
Nodes (7): Atkinson Hyperlegible Next SIL Open Font License 1.1, Manrope SIL Open Font License 1.1, Material Symbols Apache License 2.0, Google Fonts CSS origin of bundled offline UI fonts, No blanket application or supplied-model license invented, Reference/model provenance and redistribution notes, Reserved resources; images/fonts in assets and models in src/checkpoints

### Community 47 - "Native CMake Targets"
Cohesion: 0.52
Nodes (7): Native CMake build: C++20, Qt6, Torch, ORT and CUDA, QT_NO_KEYWORDS for inference translation units, RetinaGram native Windows executable, RetinaGramInference static library shared by native targets, RetinaGramPaths Qt Core static library, Optional Qt UI, functional, bundle and inference test executables, Current public headers and Qt MOC paths under src/include

### Community 48 - "Reference Parity Comparison"
Cohesion: 0.48
Nodes (6): cam_similarity(), main(), mask(), ndarray, Path, Summarize Python/C++ output parity without altering either application.

### Community 49 - "SDK And Runtime Discovery"
Cohesion: 0.48
Nodes (4): Get-RetinaGramDependencies(), Read-RetinaGramCache(), Test-RetinaGramSamePath(), Set-RetinaGramRuntimeEnvironment()

### Community 50 - "Quality Result Schema"
Cohesion: 0.29
Nodes (7): QString, Quality, QualityResult, confidence, label, probabilities, quality

### Community 51 - "Lesion Result Schema"
Cohesion: 0.29
Nodes (7): QStringList, LesionResult, channels, forwardAndTransferMs, heatmapPath, overlayPath, warnings

### Community 52 - "Historical Publication Preparation"
Cohesion: 0.33
Nodes (6): Publish portable genuine source while excluding local generated data, Historical physical cleanup rejection and ignored original files, Report tests assert the fixture actual canonical grade, Historical Graphify C++ partial parsing and unavailable host token counts, Historical ORT DLL selection repair from an older installed runtime, S5 historical native publication preparation record

### Community 53 - "Strict Modularity Comparison"
Cohesion: 0.60
Nodes (5): artifacts(), compare(), differences(), main(), normalized()

### Community 54 - "Lesion Class Schema"
Cohesion: 0.33
Nodes (6): QString, LesionClassConfig, code, mergeDistance, minimumArea, threshold

### Community 55 - "Restoration Result And History"
Cohesion: 0.40
Nodes (4): qint64, RestorationResult, forwardMs, image

### Community 56 - "Segmentation Probability Planes"
Cohesion: 0.40
Nodes (5): array, SegmentationProbabilities, channels, height, width

### Community 57 - "Segmented Selection Widget"
Cohesion: 0.50
Nodes (4): function, QObject, QStringList, segmented()

### Community 58 - "Legacy Result Serialization"
Cohesion: 0.83
Nodes (3): QVariantMap, lesionResultFields(), regionMap()

## Knowledge Gaps
- **314 isolated node(s):** `deploy.sh script`, `run.sh script`, `public`, `controlBatch`, `analyze` (+309 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 468 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `MainWindow` connect `MainWindow Public Interface` to `Window Screen Construction`, `Window And Functional Tests`, `Analysis Visualization`, `Page Rebuild Dispatch`, `Batch Screen Controls`, `Patient Eye State`, `UI Components And Regression`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `AnalysisController` connect `Controller Public Interface` to `Window And Functional Tests`, `Public Header Dependencies`, `Controller Work Dispatch`, `Persistent Analysis Worker`, `Controller Header Dependencies`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `StageConfig` connect `Runtime Contract Probes` to `Model Input Schema`, `Model Configuration Schema`, `Model Configuration Validation`, `Model Output Schema`, `ONNX Inference Sessions`, `Torch Grading Adapter`, `Lesion Class Schema`, `Torch Tensor Helpers`, `Model Adapter Factory`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `QDir` (e.g. with `.private()` and `.realBatchPauseResumeCancelAndReports()`) actually correct?**
  _`QDir` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `QFileInfo` (e.g. with `.private()` and `.realBatchPauseResumeCancelAndReports()`) actually correct?**
  _`QFileInfo` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deploy.sh script`, `run.sh script`, `public` to the rest of the system?**
  _314 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Window Screen Construction` be split into smaller, more focused modules?**
  _Cohesion score 0.056633663366336635 - nodes in this community are weakly interconnected._

## Extraction coverage and health

Generated with official graphifyy 0.9.53 AST/library analysis and host-agent semantic extraction. Source paths are relative to the repository root.

The C++ parser reported incomplete extraction in four successfully compiled files: src/include/core/AppPaths.h (line 10; no symbols), src/inference/stages/RuntimeSupport.cpp (line 93; 24 symbols), tests/FunctionalSmoke.cpp (line 24; 6 symbols), and tests/UiRegression.cpp (line 34; 9 symbols). AppPaths implementation is extracted from src/core/AppPaths.cpp. Qt macros/default arguments and parser coverage limit this map; verify relationships against source.

```text
[graphify] MultiDiGraph edge-collapse diagnostic
input: <in-memory>
input_stage: provided JSON (normal graph.json is post-build)
effective_directed: <direct-call>
nodes: 1201
unverified_code_nodes: 0
raw_edges: 2936
valid_candidate_edges: 2568
missing_endpoint_edges: 0
dangling_endpoint_edges: 368
self_loop_edges: 0
exact_duplicate_edges: 50
directed_unique_endpoint_pairs: 2394
directed_same_endpoint_collapsed_edges: 174
undirected_unique_endpoint_pairs: 2390
undirected_same_endpoint_collapsed_edges: 178
same_endpoint_group_count: 130
relation_variant_groups: 43
source_file_variant_groups: 0
source_location_variant_groups: 25
context_variant_groups: 35
post_build_graph_type: Graph
post_build_edges: 2412
producer_suppression_sites: 12
producer_suppression_examples:
  - L1204 seen_ids arity=unknown
  - L1520 seen_ids arity=unknown
  - L1522 seen_doc_refs arity=unknown
  - L1885 seen_ids arity=unknown
  - L2032 seen_ids arity=unknown
  - L2670 seen_keys arity=unknown
  - L2839 seen_keys arity=unknown
  - L4436 seen_ids arity=unknown
examples:
  - src_include_ui_mainwindow_mainwindow -> src_include_ui_mainwindow_h_qstring edges=20 relations=['references'] locations=['L127', 'L128', 'L129', 'L136', 'L139', 'L140', 'L141', 'L142', 'L143', 'L145', 'L148', 'L149', 'L150', 'L153', 'L158', 'L162', 'L163', 'L164', 'L166'] contexts=['field', 'generic_arg']
  - src_include_app_analysiscontroller_analysiscontroller -> src_include_app_analysiscontroller_h_qstring edges=4 relations=['references'] locations=['L71', 'L72', 'L75'] contexts=['field', 'generic_arg']
  - src_include_inference_modeltypes_modelstages -> src_include_inference_modeltypes_h_unique_ptr edges=4 relations=['references'] locations=['L60', 'L61', 'L62', 'L63'] contexts=['field']
  - src_ui_mainwindow_mainwindow_rememberreportpath -> src_ui_mainwindow_cpp_qstring edges=4 relations=['calls', 'references'] locations=['L555', 'L576'] contexts=['call', 'parameter_type']
  - scripts_export_models_lesioncam_forward -> scripts_export_models_py_tensor edges=3 relations=['references'] locations=['L30'] contexts=['generic_arg', 'parameter_type']
note: normal graph.json is post-build; raw producer loss must be measured earlier.
```

Graph health warning: 368 dangling-endpoint edges; 174 collapsed directed edges; 178 collapsed undirected edges. The official AST producer emits unresolved external/import references; those raw endpoints are not fabricated into verified symbols. Graphify also collapses multiple relations on the same undirected endpoints. This map is incomplete and does not retain every raw edge record.
