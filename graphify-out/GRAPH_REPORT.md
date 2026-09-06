# Graph Report - Diabetic-Retinopathy-  (2026-09-06)

## Corpus Check
- Corpus is ~13,807 words - fits in a single context window. You may not need a graph.

## Summary
- 279 nodes · 454 edges · 13 communities (10 shown, 3 thin omitted)
- Extraction: 96% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Lesion Output Pipeline
- NAFNet Restoration
- Image Quality Assessment
- DR Grade Classification
- Pipeline Concepts and Assets
- UNet++ Segmentation Model
- NAFNet Building Blocks
- Lesion Concepts and Evidence
- Lesion Dataset Validation
- Grade Grad-CAM
- Inference Package
- Model Package
- IQA Performance Notes

## God Nodes (most connected - your core abstractions)
1. `predict_lesions()` - 21 edges
2. `predict_grade()` - 12 edges
3. `LesionUNetPlusPlus` - 12 edges
4. `load_restoration_model()` - 11 edges
5. `restore_image()` - 11 edges
6. `load_grade_model()` - 10 edges
7. `EfficientNetIQAService` - 10 edges
8. `predict_iqa()` - 10 edges
9. `load_lesion_model()` - 10 edges
10. `NAFNet` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Stylized Eye Motif` --conceptually_related_to--> `Retinal AI Model Pipeline`  [INFERRED]
  WhatsApp Image 2026-09-05 at 19.35.33.jpeg → README.md
- `Lesion Localization Outputs` --semantically_similar_to--> `Lesion Masks Probability Maps and Visualizations`  [INFERRED] [semantically similar]
  README.md → models/lesion/README.md
- `Image Quality Assessment` --semantically_similar_to--> `Fundus Image Quality Assessment`  [INFERRED] [semantically similar]
  README.md → models/iqa/README.md
- `EfficientNet-B0 IQA Classifier` --semantically_similar_to--> `EfficientNet-B0 IQA Model`  [INFERRED] [semantically similar]
  README.md → models/iqa/README.md
- `Width-32 NAFNet Restoration` --semantically_similar_to--> `NAFNet Width-32 Configuration`  [INFERRED] [semantically similar]
  README.md → models/restoration/README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Retinal Inference Pipeline Flow** — readme_fundus_image, readme_image_quality_assessment, readme_optional_restoration, readme_selected_retinal_image, readme_lesion_segmentation, readme_dr_grade_classification, readme_final_application_output [EXTRACTED 1.00]
- **Lesion Localization Output System** — models_lesion_readme_original_coordinate_thresholding, models_lesion_readme_connected_component_filtering, models_lesion_readme_predicted_region_metadata, models_lesion_readme_grad_cam, models_lesion_readme_lesion_artifacts [EXTRACTED 1.00]
- **Retinal Pipeline Runtime Stack** — requirements_torch, requirements_torchvision, requirements_numpy, requirements_pandas, requirements_scipy, requirements_matplotlib, requirements_pillow [EXTRACTED 1.00]

## Communities (13 total, 3 thin omitted)

### Community 0 - "Lesion Output Pipeline"
Cohesion: 0.10
Nodes (37): main(), parse_args(), Namespace, Command-line UNet++ lesion localization and visualization., UNet++ MA/HE/EX/SE lesion segmentation package., extract_predicted_regions(), _normalized(), ndarray (+29 more)

### Community 1 - "NAFNet Restoration"
Cohesion: 0.10
Nodes (29): main(), parse_args(), Namespace, Command-line NAFNet image restoration., checkpoint_path(), checkpoint_root(), Path, Portable resolution of the centralized offline checkpoint bundle. (+21 more)

### Community 2 - "Image Quality Assessment"
Cohesion: 0.10
Nodes (23): Image, main(), parse_args(), Namespace, Command-line inference for calibrated EfficientNet image quality., inference_mode, IQAModel, EfficientNetIQAService (+15 more)

### Community 3 - "DR Grade Classification"
Cohesion: 0.12
Nodes (26): main(), parse_args(), Namespace, Command-line grade prediction with optional Grad-CAM visualization., Diabetic-retinopathy grade model and reusable prediction API., Convextnet, _load_checkpoint(), load_grade_model() (+18 more)

### Community 4 - "Pipeline Concepts and Assets"
Cohesion: 0.09
Nodes (30): Final Calibrated IQA Checkpoint, IQA Mapping 0 Good 1 Usable 2 Reject, Conflicting Team Note Mapping 0 Reject 1 Usable 2 Good, EfficientNet-B0 IQA Model, Fundus Image Quality Assessment, NETRAGRAM IQA Module, Training-Inference Preprocessing Consistency, Good Usable Reject Routing (+22 more)

### Community 5 - "UNet++ Segmentation Model"
Cohesion: 0.10
Nodes (17): ndarray, Tensor, Per-lesion Grad-CAM for the UNet++ segmentation decoder., Capture the final decoder convolution and explain one output channel., Return a normalized original-resolution CAM, or None when absent., SegmentationGradCAM, ConvBlock, LesionUNetPlusPlus (+9 more)

### Community 6 - "NAFNet Building Blocks"
Cohesion: 0.12
Nodes (9): LayerNorm2d, LayerNormFunction, Vendored NAFNet architecture from megvii-research/NAFNet., AvgPool2d, Local_Base, replace_layers(), NAFBlock, NAFNetLocal (+1 more)

### Community 7 - "Lesion Concepts and Evidence"
Cohesion: 0.10
Nodes (22): Lesion Annotation Validation, Authoritative Lesion CSV Mapping, Epoch 18 Best-Dice Lesion Checkpoint, MA HE EX SE Output Channel Mapping, Eight-Connected Component Filtering, External Per-Lesion TIFF Annotations, Lesion Grad-CAM, Lesion Masks Probability Maps and Visualizations (+14 more)

### Community 8 - "Lesion Dataset Validation"
Cohesion: 0.21
Nodes (9): Dataset, inspect_pair(), main(), Verify external CSV/TIFF pairs without training or modifying source files., DDRLesionDataset, Explicit CSV image/TIFF pairs for DDR/IDRiD lesion supervision., Read categorical pixels unchanged; reject unsupported encodings., One image/mask/lesion row from an external combined DDR + IDRiD CSV. (+1 more)

### Community 9 - "Grade Grad-CAM"
Cohesion: 0.22
Nodes (4): find_gradcam_target_layer(), GradCAM, Grad-CAM implementation used by optional grade visualizations., Return the final ConvNeXt feature block used by the original inference code.

## Ambiguous Edges - Review These
- `IQA Mapping 0 Good 1 Usable 2 Reject` → `Conflicting Team Note Mapping 0 Reject 1 Usable 2 Good`  [AMBIGUOUS]
  models/iqa/README.md · relation: conceptually_related_to

## Knowledge Gaps
- **22 isolated node(s):** `Temperature-Calibrated IQA Probabilities`, `ConvNeXt Tiny Grade Classifier`, `NETRAGRAM IQA Module`, `Conflicting Team Note Mapping 0 Reject 1 Usable 2 Good`, `Final Calibrated IQA Checkpoint` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 117 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `IQA Mapping 0 Good 1 Usable 2 Reject` and `Conflicting Team Note Mapping 0 Reject 1 Usable 2 Good`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `checkpoint_path()` connect `NAFNet Restoration` to `DR Grade Classification`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `NAFNet` connect `NAFNet Restoration` to `NAFNet Building Blocks`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `predict_lesions()` connect `Lesion Output Pipeline` to `UNet++ Segmentation Model`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `LesionUNetPlusPlus` (e.g. with `SegmentationGradCAM` and `predict_lesions()`) actually correct?**
  _`LesionUNetPlusPlus` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Temperature-Calibrated IQA Probabilities`, `ConvNeXt Tiny Grade Classifier`, `NETRAGRAM IQA Module` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Lesion Output Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.10220673635307782 - nodes in this community are weakly interconnected._