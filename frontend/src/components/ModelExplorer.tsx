import { Activity, AlertTriangle, Binary, Boxes, BrainCircuit, ChevronRight, CircleGauge, Flame, Image as ImageIcon, Layers3, Network, ScanSearch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { assetUrl, loadArchitecture, loadGradeGradCAM } from "../api";
import type { AnalysisResult, ExplorerArchitecture, GradeGradCAM } from "../types";
import { BlockCard } from "./BlockCard";
import { ImageComparison } from "./ImageComparison";

type ModelId = "quality" | "restoration" | "grade" | "lesion";
type Lens = "architecture" | "features" | "heatmaps" | "tensor";

const gradeLabels = ["No DR", "Mild", "Moderate", "Severe", "Proliferative DR"];
const lesionLabels: Record<string, string> = { MA: "Microaneurysm", HE: "Hemorrhage", EX: "Hard Exudate", SE: "Soft Exudate" };

function formatParameters(value: number) {
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value.toLocaleString();
}

export function ModelExplorer({ modelId, result, explainability }: { modelId: ModelId; result: AnalysisResult; explainability: boolean }) {
  const [architecture, setArchitecture] = useState<ExplorerArchitecture | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [advanced, setAdvanced] = useState(false);
  const [lens, setLens] = useState<Lens>("architecture");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setExpanded(new Set());
    setAdvanced(false);
    loadArchitecture(modelId)
      .then((value) => {
        if (!active) return;
        setArchitecture(value);
        setExpanded(value.blocks.length ? new Set([value.blocks[0].id]) : new Set());
      })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Architecture could not be loaded."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [modelId]);

  const groups = useMemo(() => {
    const map = new Map<string, NonNullable<typeof architecture>["blocks"]>();
    architecture?.blocks.forEach((block) => map.set(block.group, [...(map.get(block.group) ?? []), block]));
    return [...map.entries()];
  }, [architecture]);

  function scrollToBlock(id: string) {
    setExpanded((current) => new Set(current).add(id));
    requestAnimationFrame(() => document.getElementById(`block-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  const titles: Record<ModelId, { title: string; copy: string }> = {
    quality: { title: "EfficientNet Image Quality Explorer", copy: "Inspect each real MBConv output before the calibrated three-class quality head." },
    restoration: { title: "NAFNet Image Restoration Explorer", copy: "Trace the width-32 network from the intro convolution through every NAFBlock and residual reconstruction." },
    grade: { title: "ConvNeXt DR Grade Explorer", copy: "Follow the classifier from its stride-4 stem through every ConvNeXt block to five grade probabilities." },
    lesion: { title: "MobileNetV3 + UNet++ Lesion Explorer", copy: "Inspect the encoder resolution changes, nested decoder nodes, and four-channel segmentation output." },
  };

  return (
    <section className="model-explorer">
      <div className="explorer-heading">
        <div><h1>{titles[modelId].title}</h1><p>{titles[modelId].copy}</p></div>
        <span className="device-chip"><Activity size={14} />{result.device.toUpperCase()}</span>
      </div>

      {loading && <div className="architecture-loading">Loading the repository model structure…</div>}
      {error && <div className="block-error">{error}</div>}
      {architecture && (
        <>
          <dl className="model-facts">
            <div><dt>Model</dt><dd>{architecture.model_name}</dd></div>
            <div><dt>Device</dt><dd>{architecture.device.toUpperCase()}</dd></div>
            <div><dt>Input</dt><dd>{architecture.input}</dd></div>
            <div><dt>Parameters</dt><dd>{formatParameters(architecture.parameter_count)}</dd></div>
            <div><dt>Blocks</dt><dd>{architecture.block_count} hook points</dd></div>
          </dl>

          <div className="explorer-tabs" role="tablist" aria-label="Model explorer views">
            {([
              ["architecture", Network, "Architecture"],
              ["features", Layers3, "Feature Maps"],
              ["heatmaps", Flame, "Heatmaps"],
              ["tensor", Binary, "Tensor Info"],
            ] as const).map(([id, Icon, label]) => <button role="tab" aria-selected={lens === id} className={lens === id ? "active" : ""} key={id} type="button" onClick={() => setLens(id)}><Icon size={15} />{label}</button>)}
          </div>

          <LensPanel lens={lens} groups={groups} onSelect={scrollToBlock} />

          <div className="explorer-toolbar">
            <div><h2>Block-by-block activations</h2><p>Collapsed by default. Opening a block runs one short-lived hook and caches its rendered images.</p></div>
            <div className="toolbar-actions">
              <label className="advanced-toggle"><input type="checkbox" checked={advanced} onChange={(event) => setAdvanced(event.target.checked)} /><span />Advanced: individual layers</label>
              <button type="button" onClick={() => setExpanded(new Set(architecture.blocks.slice(0, 6).map((block) => block.id)))}>Expand All · limit 6</button>
              <button type="button" onClick={() => setExpanded(new Set())}>Collapse all</button>
            </div>
          </div>
          <p className="performance-note"><AlertTriangle size={15} />Expand All is intentionally limited to six blocks at a time to keep CPU/GPU memory predictable. Every remaining block is available individually.</p>

          {!explainability ? (
            <div className="explainability-off"><ScanSearch size={28} /><h3>Explainability is paused</h3><p>Turn on Explainability Mode to run block hooks and render model activations.</p></div>
          ) : (
            <div className="block-stack">
              {architecture.blocks.map((block) => <BlockCard key={block.id} block={block} modelId={modelId} sessionId={result.session_id} advanced={advanced} expanded={expanded.has(block.id)} onToggle={() => setExpanded((current) => { const next = new Set(current); next.has(block.id) ? next.delete(block.id) : next.add(block.id); return next; })} />)}
            </div>
          )}

          <ModelOutcome modelId={modelId} result={result} />
        </>
      )}
    </section>
  );
}

function LensPanel({ lens, groups, onSelect }: { lens: Lens; groups: Array<[string, ExplorerArchitecture["blocks"]]>; onSelect: (id: string) => void }) {
  if (lens === "architecture") return <section className="architecture-tree"><div className="tree-title"><BrainCircuit size={19} /><span><strong>Architecture tree</strong><small>Generated from the loaded module structure</small></span></div><div className="tree-groups">{groups.map(([group, blocks]) => <div key={group}><strong>{group}</strong>{blocks.map((block) => <button type="button" key={block.id} onClick={() => onSelect(block.id)}><ChevronRight size={12} />{block.label}</button>)}</div>)}</div></section>;
  if (lens === "features") return <section className="lens-panel"><Layers3 /><div><h2>Grayscale feature maps</h2><p>The explorer chooses the channel with the highest mean absolute response for each captured tensor and percentile-normalizes it only for display. Channel intensity is not clinical confidence.</p></div></section>;
  if (lens === "heatmaps") return <section className="lens-panel heat"><Flame /><div><h2>Activation energy</h2><p>Intermediate heatmaps aggregate mean absolute activation across channels. They show where a block responds strongly and are never labeled Grad-CAM. ConvNeXt class-conditioned Grad-CAM appears separately in the classifier outcome.</p></div></section>;
  return <section className="lens-panel"><Binary /><div><h2>Tensor metadata</h2><p>Every expanded block reports the exact captured batch, channel, height, and width dimensions. Classifier vectors are explicitly labeled non-spatial instead of being presented as image evidence.</p></div></section>;
}

function ProbabilityBars({ values }: { values: Array<{ label: string; value: number }> }) {
  return <div className="outcome-bars">{values.map(({ label, value }) => <div key={label}><span><strong>{label}</strong><b>{(value * 100).toFixed(1)}%</b></span><i><em style={{ width: `${Math.max(value * 100, 0.8)}%` }} /></i></div>)}</div>;
}

function ModelOutcome({ modelId, result }: { modelId: ModelId; result: AnalysisResult }) {
  if (modelId === "quality" && result.quality) return <section className="model-outcome"><div className="outcome-heading"><CircleGauge /><span><h2>Quality model output</h2><p>Calibrated class probabilities from the actual EfficientNet-B0 + MLP checkpoint.</p></span><strong>{result.quality.quality} · {(result.quality.confidence * 100).toFixed(1)}%</strong></div><ProbabilityBars values={Object.entries(result.quality.probabilities).map(([label, value]) => ({ label, value }))} /></section>;
  if (modelId === "restoration" && result.restoration) return <section className="model-outcome"><div className="outcome-heading"><ImageIcon /><span><h2>Residual reconstruction output</h2><p>Source and restored pixels from the full-resolution NAFNet prediction.</p></span></div><div className="restoration-outcome"><ImageComparison before={assetUrl(result.input_image_url)} after={assetUrl(result.restoration.output_image_url)} alt="Uploaded image" /><p>The SIDD checkpoint is generic denoising—not retinal-trained clinical enhancement.</p></div></section>;
  if (modelId === "grade" && result.grade) return <GradeOutcome result={result} />;
  if (modelId === "lesion" && result.lesions) return <LesionOutcome result={result} />;
  return null;
}

function GradeOutcome({ result }: { result: AnalysisResult }) {
  const grade = result.grade!;
  const [target, setTarget] = useState(grade.predicted_grade);
  const [cam, setCam] = useState<GradeGradCAM | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    loadGradeGradCAM(result.session_id, target).then((value) => active && setCam(value)).catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Grad-CAM unavailable.")).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [result.session_id, target]);
  return <section className="model-outcome"><div className="outcome-heading"><BrainCircuit /><span><h2>DR grade probabilities and class-conditioned Grad-CAM</h2><p>Choose a target grade to recompute attribution from the final ConvNeXt feature block.</p></span><strong>Prediction: Grade {grade.predicted_grade} · {(grade.confidence * 100).toFixed(1)}%</strong></div><div className="grade-outcome"><ProbabilityBars values={grade.probabilities.map((value, index) => ({ label: `Grade ${index} · ${gradeLabels[index]}`, value }))} /><div className="gradcam-explorer"><div className="class-picker">{gradeLabels.map((label, index) => <button className={target === index ? "active" : ""} type="button" key={label} onClick={() => setTarget(index)}>G{index}</button>)}</div>{loading && <div className="cam-loading">Computing class {target} Grad-CAM…</div>}{error && <div className="block-error">{error}</div>}{cam && !loading && <><img src={assetUrl(cam.gradcam_url)} alt={`Grad-CAM for DR grade ${target}`} /><p>{cam.method} Attention is not a lesion mask.</p></>}</div></div></section>;
}

function LesionOutcome({ result }: { result: AnalysisResult }) {
  const lesions = result.lesions!;
  const [selected, setSelected] = useState(lesions.channel_order[0]);
  const mask = lesions.classes[selected]?.mask_url ?? lesions.classes[selected]?.probability_map_url;
  return <section className="model-outcome"><div className="outcome-heading"><Boxes /><span><h2>Four-channel lesion segmentation output</h2><p>Original image, selected thresholded mask, and the combined model overlay.</p></span></div><div className="lesion-toggles">{lesions.channel_order.map((code) => <button className={selected === code ? "active" : ""} type="button" key={code} onClick={() => setSelected(code)}><span>{code}</span><strong>{lesionLabels[code]}</strong><small>{lesions.classes[code].detected ? `${lesions.classes[code].num_regions} predicted regions` : "No retained region"}</small></button>)}</div><div className="lesion-images"><figure><div><img src={assetUrl(result.restoration?.output_image_url ?? result.input_image_url)} alt="Model input image" /></div><figcaption>Original model input</figcaption></figure><figure><div>{mask ? <img src={assetUrl(mask)} alt={`${lesionLabels[selected]} predicted binary mask`} /> : <span>Unavailable</span>}</div><figcaption>{lesionLabels[selected]} thresholded mask</figcaption></figure><figure><div><img src={assetUrl(lesions.overlay_url)} alt="Combined predicted lesion mask overlay" /></div><figcaption>Combined segmentation overlay</figcaption></figure></div><p className="method-note">{lesions.localization_note}</p></section>;
}
