import { Activity, AlertTriangle, BrainCircuit, ChevronLeft, ChevronRight, CircleGauge, Image as ImageIcon, LoaderCircle, ScanSearch } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { assetUrl, loadArchitecture, loadGradeGradCAM, loadLesionRegions, loadStageVisualizations } from "../api";
import type { AnalysisResult, BlockVisualization, ExplorerArchitecture, GradeGradCAM, LesionRegion } from "../types";
import { ImageComparison } from "./ImageComparison";
import { type LightboxItem, VisualizationLightbox } from "./VisualizationLightbox";

type ModelId = "quality" | "restoration" | "grade" | "lesion";
type ViewMode = "feature" | "activation" | "both";

const gradeLabels = ["No DR", "Mild", "Moderate", "Severe", "Proliferative DR"];
const lesionLabels: Record<string, string> = { MA: "Microaneurysm", HE: "Hemorrhage", EX: "Hard Exudate", SE: "Soft Exudate" };

function formatParameters(value: number) {
  return value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value.toLocaleString();
}

function visualItems(visuals: BlockVisualization[]): LightboxItem[] {
  return visuals.flatMap((visual) => [
    {
      id: `${visual.id}-feature`, title: visual.label, kind: "Feature Map", fullUrl: assetUrl(visual.feature_map_url),
      alt: `${visual.label} deterministic representative RGB feature map`, downloadName: visual.feature_download_name,
      metadata: [
        { label: "Tensor", value: `[${visual.tensor_shape.join(", ")}]` },
        { label: "Channel", value: visual.channel_index == null ? "Non-spatial" : String(visual.channel_index) },
        { label: "Resolution", value: visual.spatial ? `${visual.height} × ${visual.width}` : "Non-spatial vector" },
        { label: "Block type", value: visual.block_type },
      ],
    },
    {
      id: `${visual.id}-activation`, title: visual.label, kind: "Activation View", fullUrl: assetUrl(visual.activation_heatmap_url),
      alt: `${visual.label} grayscale activation energy`, downloadName: visual.activation_download_name,
      metadata: [
        { label: "Tensor", value: `[${visual.tensor_shape.join(", ")}]` },
        { label: "Aggregation", value: "mean(abs(features), channel)" },
        { label: "Resolution", value: visual.spatial ? `${visual.height} × ${visual.width}` : "Non-spatial vector" },
        { label: "Block type", value: visual.block_type },
      ],
    },
  ]);
}

export function ModelExplorer({ modelId, result, explainability }: { modelId: ModelId; result: AnalysisResult; explainability: boolean }) {
  const [architecture, setArchitecture] = useState<ExplorerArchitecture | null>(null);
  const [visuals, setVisuals] = useState<BlockVisualization[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<ViewMode>("both");
  const [loading, setLoading] = useState(true);
  const [visualLoading, setVisualLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(null); setArchitecture(null); setVisuals([]);
    loadArchitecture(modelId).then((value) => {
      if (!active) return;
      setArchitecture(value);
      setSelectedId(value.blocks[0]?.id ?? "");
    }).catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Architecture could not be loaded."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [modelId]);

  useEffect(() => {
    if (!architecture || !explainability) return;
    let active = true;
    setVisualLoading(true); setError(null);
    loadStageVisualizations(result.session_id, modelId)
      .then((value) => active && setVisuals(value))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Stage activations could not be rendered."))
      .finally(() => active && setVisualLoading(false));
    return () => { active = false; };
  }, [architecture, explainability, modelId, result.session_id]);

  const updateScrollState = useCallback(() => {
    const element = stripRef.current;
    if (!element) return;
    setCanScrollLeft(element.scrollLeft > 8);
    setCanScrollRight(element.scrollLeft + element.clientWidth < element.scrollWidth - 8);
  }, []);

  useEffect(() => {
    updateScrollState();
    const element = stripRef.current;
    if (!element) return;
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(element);
    element.addEventListener("scroll", updateScrollState, { passive: true });
    return () => { observer.disconnect(); element.removeEventListener("scroll", updateScrollState); };
  }, [updateScrollState, visuals]);

  const selectedBlock = architecture?.blocks.find((block) => block.id === selectedId) ?? architecture?.blocks[0];
  const selectedVisual = visuals.find((visual) => visual.id === selectedBlock?.id);
  const items = useMemo(() => visualItems(visuals), [visuals]);
  const openVisual = (id: string) => {
    const index = items.findIndex((item) => item.id === id);
    if (index >= 0) setLightboxIndex(index);
  };

  const titles: Record<ModelId, { title: string; copy: string }> = {
    quality: { title: "EfficientNet Image Quality", copy: "A stage-level view of the real EfficientNet-B0 feature extractor and calibrated Good / Usable / Reject head." },
    restoration: { title: "NAFNet Image Restoration", copy: "Four encoder stages, the real 12-block bottleneck, four decoder stages, and residual reconstruction—without primitive-layer clutter." },
    grade: { title: "ConvNeXt DR Grading", copy: "The classifier’s four major stages, five class probabilities, and class-conditioned Grad-CAM kept clearly separate." },
    lesion: { title: "MobileNetV3 + UNet++ Lesions", copy: "The actual encoder sampling points, nested decoder stages, four-channel segmentation output, and retained lesion regions." },
  };

  return (
    <section className="model-explorer">
      <div className="explorer-heading">
        <div><h1>{titles[modelId].title}</h1><p>{titles[modelId].copy}</p></div>
        <span className="device-chip"><Activity size={14} />{result.device.toUpperCase()}</span>
      </div>
      {loading && <div className="architecture-loading"><LoaderCircle />Inspecting the loaded repository model…</div>}
      {error && <div className="block-error" role="alert">{error}</div>}
      {architecture && <>
        <dl className="model-facts">
          <div><dt>Model</dt><dd>{architecture.model_name}</dd></div>
          <div><dt>Input</dt><dd>{architecture.input}</dd></div>
          <div><dt>Parameters</dt><dd>{formatParameters(architecture.parameter_count)}</dd></div>
          <div><dt>Architectural stages</dt><dd>{architecture.block_count}</dd></div>
        </dl>

        <section className="flow-section" aria-labelledby="block-flow-title">
          <div className="flow-heading">
            <div><h2 id="block-flow-title">Architectural block flow</h2><p>One RGB-rendered representative channel and one black-and-white activation view per meaningful stage.</p></div>
            <div className="segmented" role="group" aria-label="Visualization mode">
              {([['feature', 'Feature Map'], ['activation', 'B&W Activation'], ['both', 'Both']] as const).map(([id, label]) => <button type="button" key={id} className={mode === id ? "active" : ""} aria-pressed={mode === id} onClick={() => setMode(id)}>{label}</button>)}
            </div>
          </div>
          {!explainability ? <div className="explainability-off"><ScanSearch size={28} /><h3>Explainability is paused</h3><p>Turn on Explainability Mode to capture meaningful model stages. Predictions remain unchanged.</p></div> : <>
            <div className="strip-shell">
              {canScrollLeft && <button className="strip-arrow left" type="button" aria-label="Scroll blocks left" onClick={() => stripRef.current?.scrollBy({ left: -520, behavior: "smooth" })}><ChevronLeft /></button>}
              <div className="block-strip" ref={stripRef} onWheel={(event) => { if (event.shiftKey && stripRef.current) { event.preventDefault(); stripRef.current.scrollLeft += event.deltaY; } }}>
                {architecture.blocks.map((block, index) => {
                  const visual = visuals.find((entry) => entry.id === block.id);
                  return <div className="block-flow-item" key={block.id}>
                    <article className={`stage-card ${selectedBlock?.id === block.id ? "selected" : ""}`}>
                      <button className="stage-select" type="button" onClick={() => setSelectedId(block.id)} aria-pressed={selectedBlock?.id === block.id}><strong>{block.label}</strong><span>{visual ? `${visual.channels} × ${visual.height} × ${visual.width}` : block.block_type}</span></button>
                      <div className={`stage-images ${mode}`}>
                        {(mode === "feature" || mode === "both") && <Thumbnail visual={visual} kind="feature" loading={visualLoading} onOpen={() => openVisual(`${block.id}-feature`)} />}
                        {(mode === "activation" || mode === "both") && <Thumbnail visual={visual} kind="activation" loading={visualLoading} onOpen={() => openVisual(`${block.id}-activation`)} />}
                      </div>
                    </article>
                    {index < architecture.blocks.length - 1 && <ChevronRight className="flow-arrow" aria-hidden="true" />}
                  </div>;
                })}
              </div>
              {canScrollRight && <button className="strip-arrow right" type="button" aria-label="Scroll blocks right" onClick={() => stripRef.current?.scrollBy({ left: 520, behavior: "smooth" })}><ChevronRight /></button>}
            </div>
            <p className="scroll-hint">Scroll horizontally with a trackpad, Shift + mouse wheel, the arrow controls, or the visible scrollbar.</p>
          </>}
        </section>

        {selectedBlock && <section className="selected-detail">
          <div className="selected-copy"><h2>Selected Block</h2><h3>{selectedBlock.label}</h3><p>{selectedBlock.description}</p><span>{selectedBlock.block_type}</span></div>
          {selectedVisual ? <>
            <DetailImage label="Feature Map" src={selectedVisual.feature_thumbnail_url} alt={`${selectedBlock.label} feature map`} onOpen={() => openVisual(`${selectedBlock.id}-feature`)} />
            <DetailImage label="B&W Activation" src={selectedVisual.activation_thumbnail_url} alt={`${selectedBlock.label} activation view`} onOpen={() => openVisual(`${selectedBlock.id}-activation`)} />
            <dl className="tensor-facts"><div><dt>Tensor</dt><dd>[{selectedVisual.tensor_shape.join(", ")}]</dd></div><div><dt>Channels</dt><dd>{selectedVisual.channels}</dd></div><div><dt>Resolution</dt><dd>{selectedVisual.spatial ? `${selectedVisual.height} × ${selectedVisual.width}` : "Non-spatial"}</dd></div><div><dt>Representative channel</dt><dd>{selectedVisual.channel_index ?? "—"}</dd></div></dl>
          </> : <div className="detail-loading">{visualLoading ? "Rendering stage thumbnails…" : "Visualization unavailable."}</div>}
        </section>}

        {architecture.blocks.some((block) => block.internals.length > 0) && <details className="advanced-panel"><summary>Advanced Internals</summary><p>Primitive layers are available for technical reference, but are intentionally excluded from the default flow.</p><div>{architecture.blocks.filter((block) => block.internals.length).map((block) => <section key={block.id}><strong>{block.label}</strong><span>{block.internals.map((item) => item.label).join(" · ")}</span></section>)}</div></details>}
        <ModelOutcome modelId={modelId} result={result} />
      </>}
      {lightboxIndex != null && <VisualizationLightbox items={items} index={lightboxIndex} onChange={setLightboxIndex} onClose={() => setLightboxIndex(null)} />}
    </section>
  );
}

function Thumbnail({ visual, kind, loading, onOpen }: { visual?: BlockVisualization; kind: "feature" | "activation"; loading: boolean; onOpen: () => void }) {
  if (!visual) return <div className="thumbnail-placeholder">{loading ? <LoaderCircle /> : <span>—</span>}</div>;
  const feature = kind === "feature";
  return <button className="thumbnail-button" type="button" onClick={onOpen} aria-label={`Open ${visual.label} ${feature ? "feature map" : "activation view"}`}><img src={assetUrl(feature ? visual.feature_thumbnail_url : visual.activation_thumbnail_url)} alt={`${visual.label} ${feature ? "feature map" : "activation view"}`} /><small>{feature ? "Feature" : "Activation"}</small></button>;
}

function DetailImage({ label, src, alt, onOpen }: { label: string; src: string; alt: string; onOpen: () => void }) {
  return <figure className="detail-image"><button type="button" onClick={onOpen} aria-label={`Open ${label}`}><img src={assetUrl(src)} alt={alt} /></button><figcaption>{label}</figcaption></figure>;
}

function ProbabilityBars({ values }: { values: Array<{ label: string; value: number }> }) {
  return <div className="outcome-bars">{values.map(({ label, value }) => <div key={label}><span><strong>{label}</strong><b>{(value * 100).toFixed(1)}%</b></span><i><em style={{ transform: `scaleX(${Math.max(value, 0.008)})` }} /></i></div>)}</div>;
}

function ModelOutcome({ modelId, result }: { modelId: ModelId; result: AnalysisResult }) {
  if (modelId === "quality" && result.quality) return <section className="model-outcome"><div className="outcome-heading"><CircleGauge /><span><h2>Quality prediction</h2><p>Calibrated probabilities from the actual EfficientNet-B0 + MLP checkpoint.</p></span><strong>{result.quality.quality} · {(result.quality.confidence * 100).toFixed(1)}%</strong></div><ProbabilityBars values={Object.entries(result.quality.probabilities).map(([label, value]) => ({ label, value }))} /></section>;
  if (modelId === "restoration" && result.restoration) return <section className="model-outcome"><div className="outcome-heading"><ImageIcon /><span><h2>Restored output</h2><p>Full-resolution residual reconstruction from the loaded NAFNet checkpoint.</p></span></div><div className="restoration-outcome"><ImageComparison before={assetUrl(result.input_image_url)} after={assetUrl(result.restoration.output_image_url)} alt="Uploaded retinal image" /><p><AlertTriangle size={17} />The supplied SIDD checkpoint is generic denoising, not retinal-trained clinical enhancement.</p></div></section>;
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
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true; setLoading(true); setError(null); setCam(null);
    loadGradeGradCAM(result.session_id, target).then((value) => active && setCam(value)).catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Grad-CAM unavailable.")).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [result.session_id, target]);
  const item: LightboxItem | null = cam ? { id: `gradcam-${target}`, title: `Grade ${target} — ${gradeLabels[target]}`, kind: "Class-conditioned Grad-CAM", fullUrl: assetUrl(cam.gradcam_url), alt: `Grad-CAM for DR grade ${target}`, downloadName: `convnext_grade_${target}_gradcam.png`, metadata: [{ label: "Target class", value: `G${target}` }, { label: "Prediction", value: `Grade ${grade.predicted_grade}` }, { label: "Target probability", value: `${(cam.probabilities[target] * 100).toFixed(1)}%` }, { label: "Method", value: "Final ConvNeXt feature block" }] } : null;
  return <section className="model-outcome"><div className="outcome-heading"><BrainCircuit /><span><h2>Prediction and class-conditioned Grad-CAM</h2><p>The predicted class is selected by default; choose G0–G4 to recompute the explanation.</p></span><strong>Grade {grade.predicted_grade} · {(grade.confidence * 100).toFixed(1)}%</strong></div><div className="grade-outcome"><ProbabilityBars values={grade.probabilities.map((value, index) => ({ label: `Grade ${index} · ${gradeLabels[index]}`, value }))} /><div className="gradcam-explorer"><div className="class-picker" role="group" aria-label="Grad-CAM target class">{gradeLabels.map((label, index) => <button className={target === index ? "active" : ""} type="button" key={label} onClick={() => setTarget(index)} aria-pressed={target === index}>G{index}</button>)}</div>{loading && <div className="cam-loading"><LoaderCircle />Computing G{target} Grad-CAM…</div>}{error && <div className="block-error">{error}</div>}{cam && !loading && <><button className="cam-image" type="button" onClick={() => setOpen(true)}><img src={assetUrl(cam.gradcam_url)} alt={`Grad-CAM for DR grade ${target}`} /></button><p>{cam.method} It is not a lesion mask.</p></>}</div></div>{open && item && <VisualizationLightbox items={[item]} index={0} onChange={() => undefined} onClose={() => setOpen(false)} />}</section>;
}

function LesionOutcome({ result }: { result: AnalysisResult }) {
  const lesions = result.lesions!;
  const [maskClass, setMaskClass] = useState(lesions.channel_order[0]);
  const [filter, setFilter] = useState("All");
  const [limit, setLimit] = useState(25);
  const [regions, setRegions] = useState<LesionRegion[]>(lesions.regions ?? []);
  const [regionCount, setRegionCount] = useState(lesions.region_count ?? 0);
  const [selectedRegion, setSelectedRegion] = useState<LesionRegion | null>(null);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let active = true; setLoading(true);
    loadLesionRegions(result.session_id, limit, filter).then((payload) => { if (active) { setRegions(payload.regions); setRegionCount(payload.available_count); } }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [filter, limit, result.session_id]);
  const modelInput = assetUrl(result.restoration?.output_image_url ?? result.input_image_url);
  const overlay = assetUrl(lesions.overlay_url);
  const mask = assetUrl(lesions.classes[maskClass]?.mask_url ?? lesions.classes[maskClass]?.probability_map_url);
  const outputItems: LightboxItem[] = [
    { id: "lesion-input", title: "Lesion segmentation input", kind: "Original fundus", fullUrl: modelInput, alt: "Fundus image used by the lesion model", downloadName: "lesion_model_input.png", metadata: [{ label: "Role", value: "Segmentation model input" }] },
    { id: "lesion-mask", title: `${maskClass} — ${lesionLabels[maskClass]}`, kind: "Segmentation Mask", fullUrl: mask, alt: `${lesionLabels[maskClass]} retained segmentation mask`, downloadName: `lesion_${maskClass.toLowerCase()}_retained_mask.png`, metadata: [{ label: "Class", value: maskClass }, { label: "Threshold", value: String(lesions.threshold) }, { label: "Retained regions", value: String(lesions.classes[maskClass].num_regions) }] },
    { id: "lesion-overlay", title: "Retained lesion regions", kind: "Segmentation Overlay", fullUrl: overlay, alt: "Overlay of retained predicted lesion regions", downloadName: "lesion_top25_retained_overlay.png", metadata: [{ label: "Retained regions", value: String(lesions.region_count) }, { label: "Ranking", value: lesions.confidence_method }] },
  ];
  const regionItems: LightboxItem[] = regions.map((region) => ({
    id: `region-${region.rank}`, title: `Region #${String(region.rank).padStart(2, "0")} — ${region.class_name}`, kind: "Lesion Region", fullUrl: assetUrl(region.crop_url), alt: `${region.class_name} region crop`, downloadName: region.download_name,
    secondaryUrl: overlay, secondaryAlt: "Retinal overlay with selected region highlighted",
    highlight: { left: region.bbox_normalized[0] * 100, top: region.bbox_normalized[1] * 100, width: Math.max(.8, (region.bbox_normalized[2] - region.bbox_normalized[0]) * 100), height: Math.max(.8, (region.bbox_normalized[3] - region.bbox_normalized[1]) * 100) },
    metadata: [{ label: "Confidence", value: region.confidence.toFixed(3) }, { label: "Center", value: `x=${region.center_pixels[0]}, y=${region.center_pixels[1]}` }, { label: "Bounding box", value: region.bbox_pixels.join(", ") }, { label: "Area", value: `${region.area_pixels.toLocaleString()} pixels` }, { label: "Class", value: `${region.class_code} · ${region.class_name}` }],
  }));
  const lightboxItems = [...outputItems, ...regionItems];
  const openItem = (id: string) => { const index = lightboxItems.findIndex((item) => item.id === id); if (index >= 0) setLightboxIndex(index); };
  return <section className="lesion-outcome">
    <div className="outcome-heading"><ImageIcon /><span><h2>Lesion segmentation final view</h2><p>Original fundus, retained class mask, and the overlay built from the same highest-ranked regions shown below.</p></span><strong>{lesions.region_count} retained region{lesions.region_count === 1 ? "" : "s"}</strong></div>
    <div className="lesion-toggles" role="group" aria-label="Lesion mask class">{lesions.channel_order.map((code) => <button className={maskClass === code ? "active" : ""} type="button" key={code} onClick={() => setMaskClass(code)} aria-pressed={maskClass === code}><span>{code}</span><strong>{lesionLabels[code]}</strong><small>{lesions.classes[code].num_regions} in Top 25</small></button>)}</div>
    <div className="lesion-images">{[
      ["lesion-input", modelInput, "Original fundus"], ["lesion-mask", mask, `${maskClass} segmentation mask`], ["lesion-overlay", overlay, "Retained-region overlay"],
    ].map(([id, src, label]) => <figure key={id}><button type="button" onClick={() => openItem(id)}><div className="retina-frame"><img src={src} alt={label} />{id === "lesion-overlay" && selectedRegion && <span className="region-highlight" style={{ left: `${selectedRegion.bbox_normalized[0] * 100}%`, top: `${selectedRegion.bbox_normalized[1] * 100}%`, width: `${Math.max(.8, (selectedRegion.bbox_normalized[2] - selectedRegion.bbox_normalized[0]) * 100)}%`, height: `${Math.max(.8, (selectedRegion.bbox_normalized[3] - selectedRegion.bbox_normalized[1]) * 100)}%` }} />}</div></button><figcaption>{label}</figcaption></figure>)}</div>
    <section className="regions-section">
      <div className="regions-heading"><div><h2>Top Detected Lesion Regions</h2><p>{regionCount < limit ? `${regionCount} retained region${regionCount === 1 ? "" : "s"}` : `${limit} highest-ranked retained regions from the segmentation output`}</p></div><div className="region-controls"><div className="segmented compact" role="group" aria-label="Lesion class filter">{["All", ...lesions.channel_order].map((code) => <button type="button" key={code} className={filter === code ? "active" : ""} onClick={() => setFilter(code)} aria-pressed={filter === code}>{code}</button>)}</div><div className="segmented compact" role="group" aria-label="Region count">{[5, 10, 25].map((count) => <button type="button" key={count} className={limit === count ? "active" : ""} onClick={() => setLimit(count)} aria-pressed={limit === count}>Top {count}</button>)}</div></div></div>
      {loading ? <div className="regions-loading"><LoaderCircle />Updating retained regions…</div> : regions.length ? <div className="region-strip">{regions.map((region) => <article key={region.rank} className={selectedRegion?.rank === region.rank ? "selected" : ""}><button type="button" className="region-select" onClick={() => setSelectedRegion(region)} aria-pressed={selectedRegion?.rank === region.rank}><span>#{String(region.rank).padStart(2, "0")}</span><strong>{region.class_code}</strong></button><button type="button" className="region-crop" onClick={() => openItem(`region-${region.rank}`)} aria-label={`Open region ${region.rank} crop`}><img src={assetUrl(region.crop_url)} alt={`${region.class_name} region ${region.rank}`} /></button><div><strong>{region.class_name}</strong><b>{(region.confidence * 100).toFixed(1)}%</b><small>x {region.center_pixels[0]}, y {region.center_pixels[1]} · {region.area_pixels}px²</small></div></article>)}</div> : <div className="no-regions">No valid predicted regions remain for this filter at the configured threshold.</div>}
      <p className="method-note">Confidence is the maximum predicted class probability within each connected component. No regions or probabilities are fabricated.</p>
    </section>
    <p className="clinical-note"><AlertTriangle size={17} />{lesions.localization_note}</p>
    {lightboxIndex != null && <VisualizationLightbox items={lightboxItems} index={lightboxIndex} onChange={setLightboxIndex} onClose={() => setLightboxIndex(null)} />}
  </section>;
}
