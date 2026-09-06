# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite with TypeScript for the frontend and FastAPI + PyTorch for a localhost-only backend, as specified in the implementation brief.

## Users

Primary users are developers, researchers, and clinical project reviewers inspecting how RetinaGram's retinal-screening pipeline transforms an uploaded fundus image. The visualizer supports technical understanding and demonstration; it is not a replacement for clinical judgment.

## Product Purpose

RetinaGram's AI Model Visualizer makes every meaningful architectural block inspectable across image quality assessment, NAFNet restoration, DR grade classification, and lesion segmentation. Success means that an uploaded image is processed by the repository's real checkpoints while block outputs, activation-energy maps, valid classifier Grad-CAM, tensor shapes, and final predictions are rendered honestly and efficiently.

## Positioning

The product exposes the actual existing RetinaGram pipeline and selected model activations without changing model predictions or fabricating pathology interpretations.

## Operating Context

The application runs locally with the API on `127.0.0.1:8000` and the web interface on `127.0.0.1:5173`. A user uploads one supported retinal image, follows the ordered pipeline, and may revisit completed stages. Model execution may use CUDA when safely available and must fall back to CPU.

## Capabilities and Constraints

- Reuse the repository's EfficientNet-B0 IQA service, width-32 NAFNet, ConvNeXt Tiny grade classifier, and MobileNetV3-Large UNet++ lesion model.
- Load existing checkpoints without retraining or modifying them.
- Use inference mode or no-grad where gradients are not required.
- Capture explainability data with short-lived, on-demand forward hooks and never perturb predictions to produce a visualization.
- Convert selected feature channels to independently normalized RGB renderings on the server; keep activation-energy views black-and-white and never send large raw tensors to the browser.
- Distinguish representative feature channels, mean-absolute activation heatmaps, class-conditioned Grad-CAM, and segmentation masks in both implementation and copy.
- Generate the architecture tree and parameter/block counts from the actual loaded module structure wherever practical.
- Do not claim that an activation channel maps to a specific pathology without evidence.
- Continue to start and explain missing-checkpoint errors sensibly when an optional model asset is unavailable.
- Use the full desktop width for the pipeline and model explorer; do not render a left sidebar.

## Brand Commitments

Use the name RetinaGram and the subtitle “AI Retinal Screening.” Preserve the supplied green retina-and-landscape image as the application logo. The visual language is a light clinical interface with white or very light cream backgrounds, dark RetinaGram green, pale mint surfaces, rounded cards, restrained borders and shadows, and no dark theme.

## Evidence on Hand

- `WhatsApp Image 2026-09-05 at 19.35.33.jpeg` is the confirmed logo asset.
- `checkpoint/` and `model/checkpoints/` contain the current model weights.
- `models/` and `inference/` contain the real model definitions, preprocessing, inference wrappers, and existing Grad-CAM utilities.
- No clinical performance claims or diagnostic guarantees were supplied and none may be invented.

## Product Principles

- Show real computation, not illustrative predictions.
- Make pipeline state and provenance easy to inspect.
- Explain activations conservatively and clearly.
- Preserve reusable model code and checkpoint compatibility.
- Keep the local workflow dependable on both CPU and CUDA.

## Accessibility & Inclusion

Use semantic controls, visible keyboard focus, descriptive alternative text, readable contrast, and layouts optimized for desktop/PC widths. Mobile is explicitly outside the current product scope.
