# Integration status — 2026-09-05

## Latest: Top-K display selection

Implemented in Analysis Detection, synchronized Compare, and Report. Default Top 25; options 5/10/20/25/50/All filtered. Exact mean pixel probability ranks cached retained regions after optional class filtering. Stable IDs, full masks, raw counts, backend filtering, and the full report appendix are preserved. Raw inspection explicitly bypasses Top-K. The reference image has 116 raw, 110 retained, and 25 displayed; the lowest displayed mean probability is 0.874125415210221. See TOP_K_REGIONS.md for files and verification. This supersedes the previous six-row report-highlights default.

## Latest: separate lesion post-processing

Implemented and tested. See LESION_POSTPROCESSING.md for the before-change audit, annotation evidence, threshold candidates, exact settings, files, and commands. Pixel threshold 0.50; independent region threshold 0.50 (conservative, no score removals by default). Minimum areas MA/HE/EX/SE: 0.4/2.0/0.4/4.0 model-equivalent square pixels, or 4/16/4/31 original pixels on the 2592×1728 reference. HE and SE allow same-class member-pixel distance merging within one model-equivalent pixel; MA/EX merging is disabled. Scores are area-weighted means over member pixels only.

The former 114 displayed-region example contains 116 raw components. New processing removes 5 by area, reduces count by 1 through merging, removes 0 by score, and displays **110**. Higher score thresholds reduced annotation-component recall, so count was not forced down. Full masks and raw components remain available. Analysis/Compare distinguish raw/displayed counts, and Report uses six highlights plus a full retained-region appendix. New inference probabilities match the pre-change run bit for bit. No weights, architecture, training, or validation model code changed. This section supersedes earlier descriptions of a 3-pixel-filtered annotation mask.

## Latest extension: four Analysis views and bilateral Compare

Completed and tested using real model outputs. See ANALYSIS_VIEWS.md for the implementation, exact Grad-CAM layers, coordinate conversion, mask format, per-eye state, API fields, modified files, and validation evidence. The initial-integration notes below are retained as history; the extension supersedes their Grad-CAM-disabled and single-eye Compare descriptions.

Workspace: `C:\Users\ADMIN\Music\retina-desktop`.
Application: `C:\Users\ADMIN\Music\retina-desktop\desktop-app`.

## Source branches

Remote heads found: `app-frontend`, `frontend`, `models`. No `main` replacement or branch merge was used.

| Reference clone | Branch | Commit |
| --- | --- | --- |
| frontend-source | app-frontend | be247609bf7b2bb29df0ea7f94e5cca35d406e26 |
| website-source | frontend | edc12fa90b3f014bf1398994e9bf92d01d349c69 |
| models-source | models | 7e1a99d9d044041baa972c0f12b38632d951b409 |

`app-frontend` is actually the native Android/Kotlin app plus an HTML web companion, despite the initial request calling it the website. Its README points to `frontend` for React/Vite. After reporting the discrepancy and receiving “continue,” a separate `website-source` clone was added. The requested clone names and branches were preserved. All three reference clones remain clean, and no existing repository copies or original datasets/checkpoints were modified. Nothing was pushed.

## Frontend architecture and changes

React 19, TypeScript, Vite 6, Tailwind 4. Entries: `index.html`, `src/main.tsx`, `src/App.tsx`. Navigation uses the `TabType` state, not a URL router. Capture, Analysis, Compare, Report, patient management, camera/file input, and referral UI are retained with the existing design.

The old Analyze button only advanced timers. It now sends multipart images to FastAPI. `src/api.ts` maps actual outputs into existing fields, including per-eye bounding boxes in original image coordinates. Every new/replaced scan clears old predictions, confirmation flags, and fabricated quality/focus values. Failed retries do not retain stale results. Numeric grade classes 0–4 are displayed as supplied by the source code rather than inheriting the website's inconsistent named grade labels.

Hardcoded lesion pills, risk findings, diagnostic report text, ICD code, clinical recommendations, progression metrics, and pretend export success were replaced with real results or explicit unavailable states. Compare displays the actual lesion mask overlay, with its channel legend. JSON export and print/report UI work from the current result. The referral workflow stores a local draft and reports that no remote transmission occurs. The legacy Express/Gemini server remains copied but is not launched. Original fonts and two actual local retinal sample images are bundled for offline use.

## Models and checkpoints

| Model | Status | Checkpoint |
| --- | --- | --- |
| EfficientNet-B0 frozen features + calibrated MLP IQA | Integrated in API and UI; real CPU test | final_efficientnet_iqa.pth + efficientnet_b0_rwightman-7f5810bc.pth |
| ConvNeXt Tiny DR classifier | Integrated in API and UI; real CPU test | grade/convnext_tiny.pth |
| MobileNetV3-Large UNet++ four-channel lesions | Integrated in API, overlays, report; real CPU test | epoch_018_best_dice.pth |
| NAFNet width32 generic SIDD restoration | Loaded once; optional `/api/restore` tested, followed by IQA | restoration/NAFNet-SIDD-width32.pth |
| TOPIQ / TOPIQ-NR | Not present in current models branch or supplied folder | Supplied README/manifest references an absent historical checkpoint |

The Git branch commits only IQA and lesion weights. The user supplied `C:\Users\ADMIN\Desktop\models\checkpoint`; its grade and restoration weights were copied to this application, and their hashes match the supplied manifest. Its IQA file is identical to the Git IQA head. The selected lesion checkpoint is corroborated by `Results/lesion_results/baseline_info.txt`, the README, loader defaults, epoch/config metadata, and SHA-256—not chosen merely from its filename.

Architectures, checkpoints, source preprocessing, sigmoid/softmax, temperature, and mappings are preserved. The only change inside copied model inference code is loading the identical IQA pretrained backbone from a local resource rather than permitting torchvision to fetch it at startup. The original IQA checkpoint loader's `weights_only=False` is retained because the supplied metadata contains NumPy scalar objects. See the model manifest for complete file hashes and contracts.

## API and Electron

FastAPI exposes `/health`, `/api/analyze`, `/api/restore`, `/api/referral`, `/api/referrals`, `/artifacts`, and `/docs`. Startup owns a single model registry; requests reuse it under an inference lock. CPU fallback and automatic CUDA selection are implemented. The tested environment is CPU PyTorch, not CUDA.

Electron 44.2.0 starts the Python environment with no visible helper terminal, waits for its own instance's health response, opens the built React UI, and terminates its Python child when the application exits. Renderer Node integration is disabled; context isolation and sandboxing are enabled. No installer or final executable has been packaged.

## Verified results

Test image: `resources/test-images/20170629163635747.jpg`, copied unchanged from the user's DDR validation image folder (2592×1728). No actual fundus photograph was committed in either requested branch; their image files were metric plots. Two local photographs were copied for test/demo use without altering datasets.

The backend real-image test returned:

- IQA: Good, confidence 0.9975466132.
- DR grade: 3, confidence 0.9216770530; all five probabilities returned.
- Lesion regions: MA 46, HE 62, EX 3, SE 3; raw output shape `[1,4,768,768]`.
- Original-image mask files and overlay retrieved successfully through the API.

This verifies integration, not clinical accuracy. These are measured outputs from the supplied models, not sample predictions.

Backend checks passed for external-network-blocked startup/inference, model reuse, invalid input 400, unsupported format 415, missing file 422, oversized request 413, inference failure 500, and CORS. Explicit NAFNet restoration plus IQA was separately checked on a 128×128 test derivative; restoration was not inserted into the original-image analysis.

Electron uploaded the actual retinal image through Chromium's file input and displayed IQA, grade, confidence, and lesion data. Report values and per-eye isolation passed. Invalid/unsupported UI tests used real backend responses; network failure and 500 UI handling used isolated fault injection. The successful path used actual models throughout. The Python PID was absent after Electron exited. TypeScript checking and the Vite production build passed.

Evidence is retained under `work/`: integration-test.json, desktop-smoke.json, desktop-analysis.png, and logs/backend.log. Complete checkpoint hashes: `resources/models/MODEL_HASHES.json`. Full application file inventory: `FILES_CREATED.md`.

## Pending work / limits

- No blocker remains for frontend → API → IQA + DR grading + lesion results → frontend.
- Optional restoration UI selection/reassessment workflow remains pending. Its API works, has a one-megapixel initial limit, and uses generic SIDD—not retinal fine-tuned—weights.
- Grad-CAM implementations are preserved; this initial desktop path disables optional Grad-CAM and displays segmentation overlays instead.
- TOPIQ checkpoint/code is absent in the current audited sources; the supplied bundle's older documentation is inconsistent with its actual files.
- Named clinical grade labels require an authoritative class-name mapping; numeric grade ordering is preserved.
- CUDA, packaged runtime paths, clean-machine deployment, patient persistence, remote specialist service, and clinical validation remain untested/unimplemented. Patient UI state is session-only; local inference artifacts persist.
- Existing frontend dependency ranges were preserved and locked. Its npm audit reports three moderate advisories in inherited packages; no broad dependency upgrade was performed. The newly selected Electron dependency reports zero advisories at installation.

## Exact launch command

```powershell
cd C:\Users\ADMIN\Music\retina-desktop\desktop-app
.\scripts\start-desktop.ps1
```

For separate frontend/backend development and all validation commands, see `README.md`.
