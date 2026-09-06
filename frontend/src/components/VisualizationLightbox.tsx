import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { useEffect, useRef } from "react";

export interface LightboxItem {
  id: string;
  title: string;
  kind: string;
  fullUrl: string;
  alt: string;
  downloadName: string;
  metadata: Array<{ label: string; value: string }>;
  secondaryUrl?: string;
  secondaryAlt?: string;
  highlight?: { left: number; top: number; width: number; height: number };
}

export function VisualizationLightbox({ items, index, onChange, onClose }: { items: LightboxItem[]; index: number; onChange: (index: number) => void; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const item = items[index];

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft" && items.length > 1) onChange((index - 1 + items.length) % items.length);
      if (event.key === "ArrowRight" && items.length > 1) onChange((index + 1) % items.length);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [index, items.length, onChange, onClose]);

  if (!item) return null;
  return (
    <div className="lightbox-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="lightbox" role="dialog" aria-modal="true" aria-labelledby="lightbox-title">
        <header>
          <div><h2 id="lightbox-title">{item.title}</h2><p>{item.kind}</p></div>
          <div className="lightbox-actions">
            <a href={item.fullUrl} download={item.downloadName} aria-label={`Download ${item.kind}`}><Download size={18} /></a>
            <button ref={closeRef} type="button" onClick={onClose} aria-label="Close image preview"><X size={20} /></button>
          </div>
        </header>
        <div className={item.secondaryUrl ? "lightbox-media split" : "lightbox-media"}>
          <figure><img src={item.fullUrl} alt={item.alt} /><figcaption>{item.kind}</figcaption></figure>
          {item.secondaryUrl && <figure className="highlighted-retina"><div><img src={item.secondaryUrl} alt={item.secondaryAlt ?? "Retinal image with selected region"} />{item.highlight && <span style={{ left: `${item.highlight.left}%`, top: `${item.highlight.top}%`, width: `${item.highlight.width}%`, height: `${item.highlight.height}%` }} />}</div><figcaption>Retained-region overlay</figcaption></figure>}
        </div>
        <dl className="lightbox-meta">{item.metadata.map((entry) => <div key={entry.label}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>)}</dl>
        {items.length > 1 && <footer>
          <button type="button" onClick={() => onChange((index - 1 + items.length) % items.length)}><ChevronLeft size={18} />Previous</button>
          <span>{index + 1} of {items.length}</span>
          <button type="button" onClick={() => onChange((index + 1) % items.length)}>Next<ChevronRight size={18} /></button>
        </footer>}
      </section>
    </div>
  );
}
