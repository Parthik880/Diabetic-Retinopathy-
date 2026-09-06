import type { AnalysisResult, BlockVisualization, ExplorerArchitecture, GradeGradCAM } from "./types";

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

export function assetUrl(path?: string | null): string {
  if (!path) return "";
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path}`;
}

export async function analyzeImage(file: File): Promise<AnalysisResult> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE}/api/analyze`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "The image could not be analyzed.");
  }
  return response.json() as Promise<AnalysisResult>;
}

export async function loadAnalysis(sessionId: string): Promise<AnalysisResult> {
  const response = await fetch(`${API_BASE}/api/analysis/${encodeURIComponent(sessionId)}`);
  if (!response.ok) throw new Error("The saved local analysis session is no longer available.");
  return response.json() as Promise<AnalysisResult>;
}

async function readJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? "The requested model visualization is unavailable.");
  }
  return response.json() as Promise<T>;
}

export function loadArchitecture(modelId: string): Promise<ExplorerArchitecture> {
  return readJson(`/api/explorer/${encodeURIComponent(modelId)}`);
}

export function loadBlockVisualization(sessionId: string, modelId: string, blockId: string): Promise<BlockVisualization> {
  return readJson(`/api/explorer/${encodeURIComponent(modelId)}/blocks/${encodeURIComponent(blockId)}?session_id=${encodeURIComponent(sessionId)}`);
}

export function loadGradeGradCAM(sessionId: string, targetClass: number): Promise<GradeGradCAM> {
  return readJson(`/api/explorer/grade/gradcam/${targetClass}?session_id=${encodeURIComponent(sessionId)}`);
}
