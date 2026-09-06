import { ChevronDown, Cpu, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { assetUrl, loadBlockVisualization } from "../api";
import type { BlockVisualization, ExplorerBlock } from "../types";

interface BlockCardProps {
  block: ExplorerBlock;
  modelId: string;
  sessionId: string;
  expanded: boolean;
  advanced: boolean;
  onToggle: () => void;
}

export function BlockCard({ block, modelId, sessionId, expanded, advanced, onToggle }: BlockCardProps) {
  const [selectedId, setSelectedId] = useState(block.id);
  const [visual, setVisual] = useState<BlockVisualization | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedId(block.id);
    setVisual(null);
    setError(null);
  }, [block.id]);

  useEffect(() => {
    if (!expanded) return;
    let active = true;
    setLoading(true);
    setError(null);
    loadBlockVisualization(sessionId, modelId, selectedId)
      .then((value) => active && setVisual(value))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : "Activation capture failed."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [expanded, modelId, selectedId, sessionId]);

  return (
    <article className={expanded ? "block-card expanded" : "block-card"} id={`block-${block.id}`}>
      <button className="block-summary" type="button" onClick={onToggle} aria-expanded={expanded}>
        <span className="block-index"><Cpu size={16} /></span>
        <span><strong>{block.label}</strong><small>{block.block_type} · {block.description}</small></span>
        <ChevronDown size={18} />
      </button>
      {expanded && (
        <div className="block-detail">
          {advanced && block.internals.length > 0 && (
            <div className="internal-picker" aria-label="Individual layer selection">
              <button type="button" className={selectedId === block.id ? "active" : ""} onClick={() => setSelectedId(block.id)}>Block output</button>
              {block.internals.map((item) => <button type="button" key={item.id} className={selectedId === item.id ? "active" : ""} onClick={() => setSelectedId(item.id)}>{item.label}</button>)}
            </div>
          )}
          {loading && <div className="block-loading"><LoaderCircle size={20} />Running this block through the real model…</div>}
          {error && <div className="block-error">{error}</div>}
          {!loading && visual && (
            <>
              <div className="visual-pair">
                <figure><div><a href={assetUrl(visual.feature_map_url)} target="_blank" rel="noreferrer" title="Open feature map at captured resolution"><img src={assetUrl(visual.feature_map_url)} alt={`${visual.label} representative RGB feature`} /></a></div><figcaption><strong>Intermediate output</strong><span>Representative channel · RGB rendering</span></figcaption></figure>
                <figure><div><a href={assetUrl(visual.activation_heatmap_url)} target="_blank" rel="noreferrer" title="Open heatmap at captured resolution"><img src={assetUrl(visual.activation_heatmap_url)} alt={`${visual.label} mean absolute activation heatmap`} /></a></div><figcaption><strong>Activation heatmap</strong><span>Channel mean absolute response</span></figcaption></figure>
              </div>
              <div className="tensor-strip">
                <span><small>Tensor</small><strong>[{visual.tensor_shape.join(", ")}]</strong></span>
                <span><small>Channels</small><strong>{visual.channels.toLocaleString()}</strong></span>
                <span><small>Spatial size</small><strong>{visual.spatial ? `${visual.height} × ${visual.width}` : "Non-spatial vector"}</strong></span>
                <span><small>Block type</small><strong>{visual.block_type}</strong></span>
              </div>
              <p className="method-note">{visual.feature_method} {visual.heatmap_method}</p>
            </>
          )}
        </div>
      )}
    </article>
  );
}
