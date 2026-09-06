import { Check, TriangleAlert } from "lucide-react";
import type { PipelineStage } from "../types";

interface PipelineStepperProps {
  stages: PipelineStage[];
  selected: string;
  onSelect: (stage: PipelineStage) => void;
}

export function PipelineStepper({ stages, selected, onSelect }: PipelineStepperProps) {
  const shortLabels: Record<string, string> = { input: "Input", quality: "Quality", restoration: "NAFNet", grade: "Grade", lesion: "Lesions", report: "Final" };
  return (
    <ol className="pipeline" aria-label="RetinaGram analysis pipeline">
      {stages.map((stage) => {
        const available = stage.state === "complete" || stage.state === "error";
        return (
          <li key={stage.id} className={`${stage.state} ${selected === stage.id ? "selected" : ""}`}>
            <button
              type="button"
              onClick={() => available && onSelect(stage)}
              disabled={!available}
              aria-current={selected === stage.id ? "step" : undefined}
            >
              <span className="stage-marker">
                {stage.state === "complete" ? <Check size={15} /> : stage.state === "error" ? <TriangleAlert size={14} /> : stage.number}
              </span>
              <span className="stage-copy"><strong>{shortLabels[stage.id] ?? stage.label}</strong><span>{stage.description}</span></span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
