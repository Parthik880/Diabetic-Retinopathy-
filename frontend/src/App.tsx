import { AlertCircle, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { analyzeImage, loadAnalysis } from "./api";
import { AppShell } from "./components/AppShell";
import { ImageUpload } from "./components/ImageUpload";
import { ModelExplorer } from "./components/ModelExplorer";
import { PipelineStepper } from "./components/PipelineStepper";
import { StagePlaceholder } from "./components/StagePlaceholder";
import type { AnalysisResult } from "./types";

export default function App() {
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [selectedStage, setSelectedStage] = useState("restoration");
  const [explainability, setExplainability] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const sessionId = new URLSearchParams(window.location.search).get("session");
    if (!sessionId) return;
    setBusy(true);
    loadAnalysis(sessionId)
      .then(setResult)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "The saved session could not be loaded."))
      .finally(() => setBusy(false));
  }, []);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const analysis = await analyzeImage(file);
      setResult(analysis);
      window.history.replaceState(null, "", `?session=${analysis.session_id}`);
      const restoration = analysis.stages.find((stage) => stage.id === "restoration");
      setSelectedStage(restoration?.state === "complete" ? "restoration" : "quality");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The image could not be analyzed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell
      explainability={explainability}
      onExplainabilityChange={setExplainability}
      onFileChange={upload}
      uploadRef={uploadRef}
      busy={busy}
    >
      {error && <div className="error-banner" role="alert"><AlertCircle size={19} /><span><strong>Analysis could not start.</strong>{error}</span><button type="button" onClick={() => setError(null)} aria-label="Dismiss error"><X size={17} /></button></div>}
      {busy && <div className="analysis-progress" role="status"><span /><div><strong>Running RetinaGram locally</strong><small>Quality → restoration → grade → lesion segmentation. CPU runs may take several minutes.</small></div></div>}
      {!result ? <ImageUpload onFile={upload} busy={busy} /> : <>
        <PipelineStepper stages={result.stages} selected={selectedStage} onSelect={(stage) => setSelectedStage(stage.id)} />
        {result.warnings.length > 0 && <div className="warning-ribbon"><AlertCircle size={16} /><span>{result.warnings.join(" · ")}</span></div>}
        {["quality", "restoration", "grade", "lesion"].includes(selectedStage) ? (
          <ModelExplorer modelId={selectedStage as "quality" | "restoration" | "grade" | "lesion"} result={result} explainability={explainability} />
        ) : <StagePlaceholder stage={selectedStage} result={result} />}
      </>}
    </AppShell>
  );
}
