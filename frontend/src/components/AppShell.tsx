import { Layers3, Upload } from "lucide-react";
import type { ReactNode, RefObject } from "react";
import logo from "../assets/retinagram-logo.jpeg";

interface AppShellProps {
  children: ReactNode;
  explainability: boolean;
  onExplainabilityChange: (value: boolean) => void;
  onFileChange: (file: File) => void;
  uploadRef: RefObject<HTMLInputElement | null>;
  busy: boolean;
}

export function AppShell({
  children,
  explainability,
  onExplainabilityChange,
  onFileChange,
  uploadRef,
  busy,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <img src={logo} alt="RetinaGram eye and landscape mark" className="brand-logo" />
          <div>
            <strong>RetinaGram</strong>
            <span>AI Retinal Screening</span>
          </div>
        </div>
        <div className="topbar-title"><Layers3 size={18} /><span>AI Model Visualizer</span></div>
        <div className="topbar-actions">
          <label className="mode-toggle">
            <input
              type="checkbox"
              checked={explainability}
              onChange={(event) => onExplainabilityChange(event.target.checked)}
            />
            <span className="toggle-track" aria-hidden="true"><span /></span>
            <span>Explainability Mode</span>
          </label>
          <input
            ref={uploadRef}
            className="visually-hidden"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onFileChange(file);
              event.target.value = "";
            }}
          />
          <button
            className="primary-action"
            type="button"
            onClick={() => uploadRef.current?.click()}
            disabled={busy}
          >
            <Upload size={17} strokeWidth={2.2} />
            {busy ? "Analyzing…" : "Upload New Image"}
          </button>
        </div>
      </header>
      <main className="workspace">{children}</main>
    </div>
  );
}
