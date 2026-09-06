import { Contrast, Expand, Focus, ScanLine, ShieldCheck, Sparkles } from "lucide-react";
import { assetUrl } from "../api";
import type { AnalysisResult } from "../types";
import { FeatureMapPanel } from "./FeatureMapPanel";
import { ImageComparison } from "./ImageComparison";

interface NafNetViewProps {
  result: AnalysisResult;
  explainability: boolean;
}

const flow = [
  ["Input", "input"],
  ["Encoder Block 1", "encoder_1"],
  ["Encoder Block 2", "encoder_2"],
  ["Bottleneck", "bottleneck"],
  ["Decoder Block 1", "decoder_1"],
  ["Decoder Block 2", "decoder_2"],
  ["Restored Output", "output"],
] as const;

export function NafNetView({ result, explainability }: NafNetViewProps) {
  const input = assetUrl(result.input_image_url);
  const restored = assetUrl(result.restoration?.output_image_url);
  const quality = result.quality;
  return (
    <div className="nafnet-view">
      <div className="stage-heading">
        <div><h1>Stage 3: NAFNet Image Restoration</h1><p>Removes noise, enhances details and restores the retinal image for better downstream analysis.</p></div>
        <span className="stage-badge">{result.device.toUpperCase()} inference</span>
      </div>

      <section className="why-strip">
        <div className="why-mark"><Sparkles size={21} /></div>
        <div><h2>Why this step matters</h2><p>Restoration can make low-contrast structures easier for later models to process. This checkpoint is generic SIDD denoising—not retinal-trained—so its output should be inspected, not treated as clinical enhancement.</p></div>
      </section>

      <div className="inspection-grid">
        <article className="image-card">
          <div className="card-heading"><h2>Input Image{quality && quality.quality !== "Good" ? " (Low Quality)" : ""}</h2><a href={input} target="_blank" rel="noreferrer" aria-label="Open input image full size"><Expand size={17} /></a></div>
          <div className="image-well"><img src={input} alt="Uploaded input image" /></div>
          <div className={`quality-line ${quality?.quality.toLowerCase() ?? "unknown"}`}><ScanLine size={17} /><span><strong>{quality ? `${quality.quality} quality` : "Quality unavailable"}</strong>{quality ? `${Math.round(quality.confidence * 100)}% model confidence` : "See stage details"}</span></div>
        </article>

        <article className="image-card restored-card">
          <div className="card-heading"><h2>Restored Image (Output of NAFNet)</h2>{restored && <a href={restored} target="_blank" rel="noreferrer" aria-label="Open restored image full size"><Expand size={17} /></a>}</div>
          {restored ? <ImageComparison before={input} after={restored} alt="Uploaded image" /> : <div className="unavailable">Restoration output is unavailable for this run.</div>}
          <div className="restoration-meta"><ShieldCheck size={16} /><span>{result.restoration ? `${result.restoration.width} × ${result.restoration.height} · prediction unchanged by visualization hooks` : "Original image used downstream"}</span></div>
        </article>

        <article className="feature-card">
          <div className="card-heading"><h2>Feature Maps (Encoder → Decoder)</h2><span className="mono-tag">8 channels</span></div>
          {explainability ? <FeatureMapPanel features={result.features} /> : <div className="explainability-off"><Focus size={28} /><h3>Explainability is paused</h3><p>Turn on Explainability Mode to inspect normalized activation channels.</p></div>}
        </article>
      </div>

      {explainability && (
        <section className="transformations">
          <div className="section-heading"><div><h2>Intermediate transformations</h2><p>A representative channel traces the model’s real forward pass from source to restored output.</p></div><span>Grayscale · independently normalized</span></div>
          <div className="flow-track">
            {flow.map(([label, key]) => {
              const image = key === "input" ? input : key === "output" ? restored : assetUrl(result.features[key]?.images[0]);
              return <div className="flow-node" key={key}><div>{image ? <img src={image} alt={`${label} representation`} /> : <span />}</div><strong>{label}</strong></div>;
            })}
          </div>
        </section>
      )}

      <section className="improvements">
        <div className="section-heading"><div><h2>Key improvements</h2><p>What restoration is intended to support in the rest of the pipeline.</p></div></div>
        <div className="improvement-list">
          <div><Sparkles /><span><strong>Noise reduction</strong><small>Suppresses distracting sensor noise</small></span></div>
          <div><Contrast /><span><strong>Better contrast</strong><small>Clarifies local tonal differences</small></span></div>
          <div><Focus /><span><strong>Preserves structures</strong><small>Residual reconstruction retains anatomy</small></span></div>
          <div><ShieldCheck /><span><strong>Downstream readiness</strong><small>Provides a cleaner candidate input</small></span></div>
        </div>
      </section>
    </div>
  );
}
