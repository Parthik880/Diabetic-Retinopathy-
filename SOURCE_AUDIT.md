# Source audit

The full tracked trees below were inspected before integration. Reference clones remain untouched.

## app-frontend

Native Kotlin / Jetpack Compose Android app, not a React/Vite website. `MainActivity.kt` dispatches the four ScreenTab views. `RetinaScanViewModel.updateEyeScanImage` stores image URI and fabricated quality values; `runAiAnalysis` only delays 1200 ms. `SampleDataProvider` supplies diagnostic examples. CaptureScreen.kt, AnalysisScreen.kt, CompareScreen.kt, and ReportScreen.kt implement the original flows. The native build is `./gradlew assembleDebug`.

The root package.json contains an empty dependency list and Vite build script, but no index.html or React source entry exists on this branch. `server.js` is a standalone HTML web companion with hardcoded patient predictions; its upload handler only sets a data URL and shows invented focus/illumination values. This branch is kept as `frontend-source` and is not silently replaced.

## frontend website

React/Vite/TypeScript/Tailwind website. package.json original dev command: `tsx server.ts`; build: `vite build && esbuild server.ts --bundle --platform=node --format=cjs --packages=external --sourcemap --outfile=dist/server.cjs`. React entry: src/main.tsx -> App.tsx. TabType state routes Capture/Analysis/Compare/Report without a router library. ImageUploadModal.tsx uses FileReader data URLs, preset image URLs, and getUserMedia/canvas camera capture. AddPatientModal.tsx also supports uploaded data URLs and sample patient presets.

App.handleImageSelected stores the chosen URL. CaptureScreen.handleStartAnalysis previously used four timers and never called a model. AnalysisScreen, CompareScreen, ReportScreen, and samplePatients.ts supplied static diagnoses, scores, boxes, heatmaps, and clinical text. SpecialistReferralModal is the only existing frontend fetch call (/api/referral); its old handler ignored failure and showed success. The Express server implements mock referral queues and Gemini consultation with heuristic fallback. It does not expose real PyTorch analysis. Copied frontend dependencies were retained, with TypeScript React type packages and Electron added only where needed.

## models

Deployable model classes and inference wrappers live under models/iqa, models/grade, models/lesion, models/restoration. CLIs exist under inference/. The detailed contract and checkpoint selection evidence are in resources/models/MODEL_MANIFEST.md. No TOPIQ code, ONNX model, training dataset, or actual fundus test photograph is committed in this branch. requirements.txt originally lists torch, torchvision, numpy, pandas, scipy, matplotlib, Pillow. Pandas remains a runtime requirement because the reused lesion predictor imports dataset constants from dataset.py.

Recursive checkpoint/script search is recorded below. `model.py` files are architecture implementations; `models/lesion/dataset.py` describes explicit annotation pairing. Preprocessing and class ordering were verified against inference wrappers, READMEs, checkpoint metadata, and baseline_info.txt. No architecture was replaced or training performed. Graphify's external code-only audit in work/model-audit/graphify-out indexed 33 code files into 241 nodes and 558 edges; source files and model metadata were also read directly.

## Complete tracked tree: frontend-source

Branch `app-frontend`, commit `be247609bf7b2bb29df0ea7f94e5cca35d406e26`. Git status clean.

```text
.env.example
.gitignore
README.md
app/build.gradle.kts
app/src/main/AndroidManifest.xml
app/src/main/java/com/retinascan/ai/MainActivity.kt
app/src/main/java/com/retinascan/ai/data/SampleDataProvider.kt
app/src/main/java/com/retinascan/ai/model/PatientRecord.kt
app/src/main/java/com/retinascan/ai/ui/components/AddPatientDialog.kt
app/src/main/java/com/retinascan/ai/ui/components/SpecialistReferralDialog.kt
app/src/main/java/com/retinascan/ai/ui/screens/AnalysisScreen.kt
app/src/main/java/com/retinascan/ai/ui/screens/CaptureScreen.kt
app/src/main/java/com/retinascan/ai/ui/screens/CompareScreen.kt
app/src/main/java/com/retinascan/ai/ui/screens/ReportScreen.kt
app/src/main/java/com/retinascan/ai/ui/theme/Theme.kt
app/src/main/java/com/retinascan/ai/viewmodel/RetinaScanViewModel.kt
app/src/main/res/drawable/ic_launcher_background.xml
app/src/main/res/drawable/ic_launcher_foreground.xml
app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml
app/src/main/res/values/colors.xml
app/src/main/res/values/strings.xml
app/src/main/res/values/themes.xml
build.gradle.kts
confusion_matrix_dr.npy
confusion_matrix_dr.png
grad.py
gradle.properties
gradle/libs.versions.toml
gradle/wrapper/gradle-wrapper.properties
gradlew
gradlew.bat
inference.py
metadata.json
model/__init__.py
model/convext.py
package.json
requirements.txt
server.js
settings.gradle.kts
training_history_dr.csv
tsconfig.json
vite.config.ts
```

Checkpoint and requested script matches:

```text
inference.py
requirements.txt
```

## Complete tracked tree: website-source

Branch `frontend`, commit `edc12fa90b3f014bf1398994e9bf92d01d349c69`. Git status clean.

```text
.env.example
.gitignore
README.md
confusion_matrix_dr.npy
confusion_matrix_dr.png
grad.py
index.html
inference.py
metadata.json
model/__init__.py
model/convext.py
package.json
requirements.txt
server.ts
src/App.tsx
src/components/AddPatientModal.tsx
src/components/AnalysisScreen.tsx
src/components/BottomNavBar.tsx
src/components/CaptureScreen.tsx
src/components/CompareScreen.tsx
src/components/ImageUploadModal.tsx
src/components/ReportScreen.tsx
src/components/SpecialistReferralModal.tsx
src/components/TopAppBar.tsx
src/data/samplePatients.ts
src/index.css
src/main.tsx
src/types.ts
training_history_dr.csv
tsconfig.json
vite.config.ts
```

Checkpoint and requested script matches:

```text
inference.py
requirements.txt
```

## Complete tracked tree: models-source

Branch `models`, commit `7e1a99d9d044041baa972c0f12b38632d951b409`. Git status clean.

```text
.gitignore
README.md
Results/grade_results/00_dashboard.png
Results/grade_results/01_loss_curve.png
Results/grade_results/02_accuracy_curve.png
Results/grade_results/03_qwk_curve.png
Results/grade_results/04_referable_dr_metrics.png
Results/grade_results/05_per_class_auc.png
Results/grade_results/06_macro_prf1.png
Results/grade_results/07_per_class_f1.png
Results/grade_results/08_learning_rate.png
Results/grade_results/09_multiclass_auc.png
Results/grade_results/10_referable_confusion_components.png
Results/grade_results/confusion_matrix.npy
Results/grade_results/confusion_matrix.png
Results/grade_results/grade_training.csv
Results/iqa_results/.gitkeep
Results/lesion_results/baseline_info.txt
Results/lesion_results/best_confusion_matrix.npy
Results/lesion_results/evaluation_metrics.json
Results/lesion_results/training_metrics.csv
Results/restoration_results/.gitkeep
inference/__init__.py
inference/grade_inference.py
inference/iqa_inference.py
inference/lesion_inference.py
inference/outputs/gradcam/.gitkeep
inference/outputs/lesion/.gitkeep
inference/outputs/restoration/.gitkeep
inference/restoration_inference.py
inference/verify_lesion_annotations.py
model/checkpoints/epoch_018_best_dice.pth
model/checkpoints/final_efficientnet_iqa.pth
models/__init__.py
models/checkpoints.py
models/grade/__init__.py
models/grade/gradcam.py
models/grade/model.py
models/grade/predict.py
models/grade/weights/.gitkeep
models/iqa/__init__.py
models/iqa/inference.py
models/iqa/model.py
models/iqa/predict.py
models/lesion/README.md
models/lesion/__init__.py
models/lesion/dataset.py
models/lesion/gradcam.py
models/lesion/model.py
models/lesion/postprocess.py
models/lesion/predict.py
models/lesion/visualization.py
models/restoration/README.md
models/restoration/__init__.py
models/restoration/model.py
models/restoration/nafnet/LICENSE
models/restoration/nafnet/NAFNet_arch.py
models/restoration/nafnet/__init__.py
models/restoration/nafnet/arch_util.py
models/restoration/nafnet/local_arch.py
models/restoration/predict.py
models/restoration/weights/.gitkeep
requirements.txt
test_iqa.py
test_lesion_dataset.py
```

Checkpoint and requested script matches:

```text
model/checkpoints/epoch_018_best_dice.pth
model/checkpoints/final_efficientnet_iqa.pth
models/grade/model.py
models/iqa/inference.py
models/iqa/model.py
models/lesion/dataset.py
models/lesion/model.py
models/restoration/model.py
requirements.txt
```
