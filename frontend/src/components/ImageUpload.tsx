import { ImagePlus, ShieldCheck, Sparkles } from "lucide-react";
import { useState } from "react";

interface ImageUploadProps {
  onFile: (file: File) => void;
  busy: boolean;
}

export function ImageUpload({ onFile, busy }: ImageUploadProps) {
  const [dragging, setDragging] = useState(false);
  return (
    <section className="empty-workspace" aria-labelledby="upload-heading">
      <div
        className={dragging ? "upload-well dragging" : "upload-well"}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files[0];
          if (file) onFile(file);
        }}
      >
        <div className="upload-symbol"><ImagePlus size={32} strokeWidth={1.6} /></div>
        <h1 id="upload-heading">See the retinal pipeline, stage by stage.</h1>
        <p>Upload one fundus image to run the repository’s real quality, restoration, grading, and lesion models.</p>
        <label className={busy ? "upload-label disabled" : "upload-label"}>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onFile(file);
            }}
          />
          <Sparkles size={17} /> {busy ? "Running local models…" : "Choose retinal image"}
        </label>
        <span className="drop-hint">or drop a JPG, PNG, WebP, BMP, or TIFF up to 20 MB</span>
      </div>
      <div className="privacy-note"><ShieldCheck size={18} /><span><strong>Local by design.</strong> Uploads and generated activation images stay inside this localhost project.</span></div>
    </section>
  );
}
