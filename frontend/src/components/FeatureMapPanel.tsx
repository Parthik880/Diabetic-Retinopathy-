import { Layers3 } from "lucide-react";
import { useMemo, useState } from "react";
import { assetUrl } from "../api";
import type { FeatureStage } from "../types";

interface FeatureMapPanelProps {
  features: Record<string, FeatureStage>;
}

const ORDER = ["encoder_1", "encoder_2", "bottleneck", "decoder_1", "decoder_2"];

export function FeatureMapPanel({ features }: FeatureMapPanelProps) {
  const available = useMemo(() => ORDER.filter((key) => features[key]), [features]);
  const [selected, setSelected] = useState(available[0] ?? "encoder_1");
  const feature = features[selected] ?? features[available[0]];

  if (!feature) {
    return <div className="feature-empty"><Layers3 size={28} /><p>Feature maps were not available for this run.</p></div>;
  }

  return (
    <section className="feature-panel">
      <div className="feature-tabs" role="tablist" aria-label="NAFNet feature stages">
        {available.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={feature.id === key}
            className={feature.id === key ? "active" : ""}
            onClick={() => setSelected(key)}
          >
            {features[key].label}
          </button>
        ))}
      </div>
      <div className="feature-content">
        <div className="feature-grid">
          {feature.images.map((image, index) => (
            <figure key={image}>
              <img src={assetUrl(image)} alt={`${feature.label} representative activation channel ${index + 1}`} />
              <figcaption>Channel {index + 1}</figcaption>
            </figure>
          ))}
        </div>
        <aside className="feature-info">
          <span className="feature-icon"><Layers3 size={20} /></span>
          <h3>{feature.label}</h3>
          <dl>
            <div><dt>Layer</dt><dd>{feature.layer}</dd></div>
            <div><dt>Channels shown</dt><dd>{feature.channels_shown} of {feature.channels_total}</dd></div>
            <div><dt>Dimensions</dt><dd>{feature.tensor_shape.join(" × ")}</dd></div>
          </dl>
          <p>{feature.explanation}</p>
        </aside>
      </div>
    </section>
  );
}
