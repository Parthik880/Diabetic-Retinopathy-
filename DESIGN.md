---
name: RetinaGram AI Model Visualizer
description: A calm clinical retinal-imaging atlas for inspecting real local model computation.
colors:
  retinal-forest: "#0b573f"
  retinal-forest-deep: "#073c2d"
  retinal-forest-soft: "#397765"
  clinical-mint: "#e8f5ee"
  warm-cream: "#fbfcf8"
  paper-white: "#ffffff"
  structural-line: "#dbe8e0"
  deep-ink: "#173d32"
  muted-sage: "#5b776e"
  caution-amber: "#a96914"
  caution-wash: "#fff5df"
  error-red: "#9b342e"
  error-wash: "#fff0ed"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Inter, Segoe UI, sans-serif"
    fontSize: "clamp(30px, 4vw, 48px)"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Display, Inter, Segoe UI, sans-serif"
    fontSize: "clamp(26px, 2.5vw, 36px)"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.035em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Inter, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Inter, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Inter, Segoe UI, sans-serif"
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "0.06em"
rounded:
  feature: "7px"
  control: "10px"
  image: "11px"
  surface: "14px"
  upload: "18px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "9px"
  md: "12px"
  lg: "17px"
  xl: "22px"
  page-x: "26px"
components:
  button-primary:
    backgroundColor: "{colors.retinal-forest}"
    textColor: "{colors.paper-white}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.retinal-forest-deep}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.control}"
  navigation-active:
    backgroundColor: "{colors.retinal-forest}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "43px"
  card:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.deep-ink}"
    rounded: "{rounded.surface}"
    padding: "14px"
  chip:
    backgroundColor: "{colors.clinical-mint}"
    textColor: "{colors.retinal-forest}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "6px 9px"
  research-notice:
    backgroundColor: "{colors.caution-wash}"
    textColor: "{colors.caution-amber}"
    rounded: "{rounded.control}"
    padding: "9px 12px"
---

# Design System: RetinaGram AI Model Visualizer

## Overview

**Creative North Star: "The Calm Clinical Retinal-Imaging Atlas"**

RetinaGram is a quiet, evidence-minded inspection workspace: part clinical atlas, part engineering bench. Warm near-white fields and paper-white cards keep retinal imagery and model outputs dominant, while restrained mint and deep green communicate order, safety, and local system state without slipping into wellness branding or diagnostic theater.

The interface is dense enough for developers, researchers, and clinical project reviewers to compare real intermediate artifacts, but never visually dramatic about what the models mean. Model names, checkpoint provenance, execution device, stage state, dimensions, channel counts, and normalization language belong close to the evidence they qualify. Model-specific limitations stay beside the affected evidence; there is no standing warning banner.

This system is shipped for desktop and PC inspection. Its signature composition is a translucent sticky header, a full-width six-stage pipeline rail, and a horizontally scrollable stage explorer with one selected-stage detail area. Narrow-width CSS is defensive fallback behavior and must not be treated as a mobile product specification.

**Key Characteristics:**

- Light cream and white surfaces with a disciplined deep-green hierarchy.
- Modern system typography with strong headings and quiet metadata.
- Rounded, lightly bordered cards that frame evidence without decorating it.
- Explicit model provenance, local-session language, and evidence-specific limitations.
- Evidence-safe retinal images, RGB feature maps, grayscale activations, and restrained attribution language.
- Desktop-first spatial density organized around a six-stage pipeline rail.

## Colors

The palette feels clean, botanical, and clinical: green provides structure and state, mint provides low-emphasis grouping, and amber is reserved for epistemic caution.

### Primary

- **Retinal Forest:** The main action and active-state color. Use it for primary buttons, completed markers, selected navigation, progress bars, and concise status emphasis.
- **Retinal Forest Deep:** The strongest text and hover color. Use it for page headings, the RetinaGram wordmark, and deeper interactive states.
- **Retinal Forest Soft:** Supporting brand copy and explanatory text on mint surfaces.

### Secondary

- **Clinical Mint:** A low-pressure grouping surface for provenance strips, stage badges, feature metadata, result summaries, and explainability states. It is not a decorative wash for entire pages.

### Neutral

- **Warm Cream:** The lightest warm canvas option for section backgrounds.
- **Paper White:** The primary card and top-bar surface.
- **Structural Line:** The quiet border and divider color that separates cards, rail stages, and data rows.
- **Deep Ink:** Default high-contrast text inside content surfaces.
- **Muted Sage:** Supporting copy, captions, metadata, and secondary navigation.

### Tertiary

- **Caution Amber / Caution Wash:** Pair for research-only language, low-quality states, and interpretation limits. It communicates caution, not failure.
- **Error Red / Error Wash:** Pair only for execution failures or unavailable states that require recovery.

### Named Rules

**The Green Is Structure Rule.** Use the primary green to clarify navigation, progress, or action; do not flood large content areas with it.

**The Amber Means Epistemic Caution Rule.** Amber qualifies evidence and interpretation. Reserve red for actual system errors.

## Typography

**Display Font:** SF Pro Display / Inter / Segoe UI system fallback

**Body Font:** SF Pro Text / Inter / Segoe UI system fallback

**Label Font:** SF Pro Text / Inter / Segoe UI system fallback

**Character:** Native UI type keeps the application crisp and familiar across macOS and Windows. Tight display tracking creates authority; generous body leading and disciplined metadata keep dense evidence readable.

### Hierarchy

- **Display** (700, fluid 30–48px, 1.08): Empty-state and entry-point messages only; keep lines short and balanced.
- **Headline** (700, fluid 26–36px, 1.12): Pipeline-stage titles and primary screen headings.
- **Title** (700, 15px, 1.3): Section titles such as transformation and result modules.
- **Body** (400, 13px, 1.6): Stage descriptions, safeguard explanations, and other sustained reading; explanatory lines generally stay below roughly 780px.
- **Label** (700, 10px, 1.25, 0.06em tracking): Badges, device state, normalization notes, and compact metadata. Uppercase only when the label is a terse system tag.

### Named Rules

**The Quiet Metadata Rule.** Metadata may be small, but it must remain readable and adjacent to the artifact it explains; never reduce critical caveats to ornamental microcopy.

## Layout

The desktop frame uses a translucent sticky top bar above a flexible, full-width workspace with 20–28px responsive padding. There is no sidebar. The content canvas remains stable at 1366px, 1600px, and 1920px while architectural rails scroll internally instead of widening the page.

The six-stage pipeline rail spans the workspace before stage content. Each stage receives equal width, a circular status marker, a concise title, and a one- or two-line provenance description. Completed or error stages are revisit-able; unavailable stages remain visibly disabled. Preserve all six stages—Input Image, Quality Check, NAFNet Restoration, Grade Classification, Lesion Segmentation, and Final Report—as the product’s primary orientation device.

Each model uses one horizontal, no-wrap architectural stage strip. Cards expose an RGB feature thumbnail and a black-and-white activation thumbnail, support native horizontal scrolling and arrow controls, and feed one detail area below. NAFNet runs Input → Intro → Encoder Stages 1–4 → Bottleneck → Decoder Stages 4–1 → Ending → Restored Output.

The shipped scope is desktop/PC. At narrower desktop widths the top controls may wrap and the evidence detail may stack, but do not design new mobile navigation or claim handheld support. Defensive styles below 760px are resilience behavior only.

**The Evidence Gets the Width Rule.** Retinal images, comparisons, feature maps, and transformation traces take priority over explanatory prose in horizontal space.

## Elevation & Depth

The system is flat and layered, with borders and tonal surface changes doing most of the depth work. White evidence cards rest directly on the pale canvas behind a structural line; they do not float. Shadows are limited to the sticky top bar, primary actions, switch thumb, active feature tab, comparison divider, and small status glows where physical feedback matters.

### Shadow Vocabulary

- **Top-Bar Ambient** (`0 8px 24px rgba(23,61,50,.06)`): A quiet separation between fixed chrome and scrolling evidence.
- **Primary Action** (`0 8px 18px rgba(11,87,63,.17)`): Resting lift for the upload action; increase only on hover.
- **Selected Tab** (`0 3px 8px rgba(21,83,62,.08)`): Minimal lift that distinguishes the selected feature stage from the mint tab track.

### Named Rules

**The Flat Evidence Rule.** Evidence cards are bordered, not elevated. Shadow is feedback for chrome or interaction, never decoration around model output.

## Shapes

Rounded rectangles are consistent and modest. Major evidence cards and grouped data containers use the shared 14px surface radius; controls use 10px; image wells use 11px; feature thumbnails use 7px; the upload well uses 18px; badges, toggles, progress tracks, and circular stage markers use fully rounded geometry.

Borders remain one pixel and low contrast. Dark image wells may clip real imagery to a rounded frame, but the image itself stays uncropped through `object-fit: contain`. The only circular forms are status markers, toggle thumbs, the comparison handle, and small progress or session indicators.

**The Soft Frame, Honest Image Rule.** Round the container, not the evidence: never crop, mask, recolor, or beautify retinal imagery merely to match the interface silhouette.

## Components

### Buttons

- **Shape:** Compact rounded control, 40px minimum height and 10px corners.
- **Primary:** Retinal Forest with white text, 16px horizontal padding, and a small action shadow. Use for uploading or the single highest-priority action in the frame.
- **Hover / Focus:** Deepen to Retinal Forest Deep, lift by 1px, and preserve the shared 3px translucent green focus outline with 3px offset.
- **Disabled:** Lower opacity and communicate waiting state without changing layout.

### Toggle

- **Style:** A 39 × 22px pill track with a 16px white thumb. Checked state uses Retinal Forest; unchecked state uses a muted green-gray.
- **Behavior:** Pair the control with the explicit “Explainability Mode” label. Turning it off replaces feature imagery with an explanatory paused state; it must never imply that predictions changed.

### Navigation

- **Style:** The sticky header carries brand, visualizer identity, explainability mode, and upload action. The six-stage rail provides primary navigation below it.
- **State:** Hover uses a pale green wash. The selected pipeline stage uses a mint field and strong green marker.
- **Context:** Keep execution device and model provenance near the current model heading.

### Pipeline Rail

- **Structure:** Six equal stages inside one 14px white container with subtle vertical dividers.
- **State:** Completed markers are solid green with checks; the selected stage gets a pale mint field; errors use the error pair; unavailable stages remain neutral and disabled.
- **Copy:** Every stage includes a model or processing description, such as EfficientNet-B0, NAFNet, ConvNeXt, or UNet++, wherever that provenance is known.

### Cards / Containers

- **Corner Style:** Major cards use 14px corners; nested information surfaces use 9–12px corners.
- **Background:** Paper White for evidence, Clinical Mint for context and provenance, and dark green-black wells for image contrast.
- **Shadow Strategy:** Follow the Flat Evidence Rule.
- **Border:** One-pixel Structural Line around major evidence groups.
- **Internal Padding:** 14px for compact evidence cards; 17–22px for wider result and explanatory groups.

### Notices

- **Model limitation:** Use compact amber copy only beside the affected output, such as the generic SIDD restoration limitation. Do not show a standing research warning.
- **Error:** Error Wash with red text and an optional dismiss action.
- **Progress:** Clinical Mint with a compact green spinner and a concrete pipeline sequence.

### Image Comparison

The restoration card uses a horizontal range control over two contained versions of the same image. A white vertical divider, circular green handle, and Before/After tags reveal the relationship without implying clinical improvement. The adjacent metadata must state dimensions and that visualization hooks did not alter the prediction.

### Feature Maps and Transformation Rail

Feature maps are organized by meaningful model stages, not primitive layers. Each stage shows one deterministic representative channel with a fixed RetinaGram RGB ramp and one separately labeled black-and-white mean-absolute activation view. The selected stage shows tensor dimensions, channel count, spatial resolution, selected channel, model block type, and optional genuine internals. Images remain ordinary image elements so their native context menu and meaningful download filenames work.

The separate transformation rail uses one representative channel to explain the real forward sequence from input to restored output. It is a provenance diagram, not a causal or lesion-localization claim.

## Do's and Don'ts

### Do:

- **Do** keep the six-stage rail visible above completed-stage content on desktop.
- **Do** keep model names, device state, tensor dimensions, channel counts, normalization, and checkpoint limitations beside the relevant artifact.
- **Do** render source and restored retinal images contained within dark wells so the full image remains inspectable.
- **Do** describe feature maps as normalized internal activations and Grad-CAM as attention, never as proof of pathology.
- **Do** place concise model-specific limitations beside the affected result without repeating a standing warning.
- **Do** preserve semantic controls, descriptive alternative text, and the visible shared focus treatment.

### Don't:

- **Don't** present RetinaGram as a diagnostic device or invent performance, pathology, or treatment claims.
- **Don't** imply that generic SIDD-trained NAFNet restoration is retinal-trained clinical enhancement.
- **Don't** crop, retouch, recolor, or selectively emphasize retinal evidence to make a result look more convincing.
- **Don't** turn the calm cream, white, mint, and green system into a dark theme, saturated dashboard, or neon AI aesthetic.
- **Don't** use shadow as a default card treatment or replace quiet borders with heavy chrome.
- **Don't** describe narrow-width fallback CSS as a supported mobile experience; the current design contract is desktop/PC-only.
