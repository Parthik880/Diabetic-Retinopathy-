import { PatientRecord, EyeScanData, AnomalyItem, AnalysisState, HistoryRecord } from './types';

export const PIPELINE_STATE_LABELS: Record<AnalysisState, string> = {
  WAITING: 'Queued for analysis',
  IQA: 'Assessing image quality...',
  IQA_GOOD: 'Image quality: Good',
  IQA_USABLE: 'Image quality: Usable',
  IQA_REJECTED: 'Image quality rejected',
  RESTORING: 'Restoring usable retinal image...',
  RESTORATION_COMPLETE: 'Restoration complete',
  GRADING: 'Classifying diabetic retinopathy grade...',
  LESION_ANALYSIS: 'Analyzing retinal lesions and generating overlay...',
  PREPARING_RESULTS: 'Preparing report data...',
  COMPLETE: 'Analysis complete',
  RECAPTURE_REQUIRED: 'Recapture required',
  FAILED: 'Analysis failed',
};

export const ACTIVE_ANALYSIS_STATES = new Set<AnalysisState>([
  'WAITING', 'IQA', 'IQA_GOOD', 'IQA_USABLE', 'IQA_REJECTED', 'RESTORING',
  'RESTORATION_COMPLETE', 'GRADING', 'LESION_ANALYSIS', 'PREPARING_RESULTS',
]);

export interface AttentionMap {
  heatmap_path: string;
  values_path: string;
  width: number;
  height: number;
  method: string;
  target_layer?: string;
  target_class?: number;
  objective?: string;
}
export interface LesionRegion {
  region_id: number; x_min: number; y_min: number; x_max: number; y_max: number;
  center_x: number; center_y: number; width: number; height: number; mean_probability: number;
  area_pixels?: number; max_probability?: number; source_component_ids?: number[];
}
export interface LesionOutput {
  regions: LesionRegion[];
  raw_regions?: LesionRegion[];
  num_regions: number;
  detected: boolean;
  mask_png_path?: string;
  mask_layer_path?: string;
  color?: string;
  attention?: AttentionMap | null;
  attention_unavailable_reason?: string;
  probability_heatmap?: AttentionMap;
}
export interface AnalysisResult {
  run_id: string;
  eye?: 'OS' | 'OD';
  image_url?: string;
  original_image_url?: string;
  restored_image_url?: string | null;
  analysis_image_url?: string;
  analysis_source?: 'original' | 'restored';
  state: 'COMPLETE' | 'RECAPTURE_REQUIRED';
  state_history: { state: AnalysisState; at: string }[];
  invocation_counts: { iqa: number; nafnet: number; grading: number; lesions: number };
  quality: { quality: string; confidence: number; probabilities: Record<string, number> } | null;
  grading: { predicted_grade: number; confidence: number; probabilities: number[]; gradcam?: AttentionMap } | null;
  lesions: {
    raw_region_count?: number;
    displayed_region_count?: number;
    threshold?: number;
    postprocessing?: { pixel_threshold: number; region_threshold: number; minimum_area: Record<string, number>; merge_distance: Record<string, number> };
    combined_overlay_path: string;
    channel_order?: string[];
    lesions: Record<string, LesionOutput>;
  } | null;
  image_width: number;
  image_height: number;
  warnings: string[];
  device?: string;
  device_name?: string;
}

export interface ReportExportResult {
  folder: string;
  report: string;
  files: string[];
}

const emptyFinding = { title: 'Model output only', description: 'No automated clinical management recommendation is generated.', urgency: 'Routine' as const, actionNeeded: 'Clinician review' };

export function resetScan(scan: EyeScanData): EyeScanData {
  return { ...scan, result: undefined, review: { confirmed: false, flagged: false }, status: 'Needs Capture',
    statusText: scan.imageUrl ? 'Ready for analysis' : 'Pending capture', analysisState: 'WAITING',
    analysisError: undefined, analysisRequestId: undefined, analysisJobId: undefined,
    heatmapUrl: '', imageQualityScore: null, illuminationIndex: 'Not measured', focusMetric: 'Not measured' };
}

export function resetPatient(patient: PatientRecord): PatientRecord {
  return projectPatient({ ...patient, sessionId: patient.sessionId || crypto.randomUUID(),
    sessionStartedAt: patient.sessionStartedAt || new Date().toISOString(),
    leftEye: resetScan(patient.leftEye), rightEye: resetScan(patient.rightEye),
    isConfirmed: false, isFlagged: false, referralStatus: undefined, clinicalNotes: '' });
}

const classes: Record<string, [string, AnomalyItem['type'], string]> = {
  MA: ['Microaneurysms', 'microaneurysm', '#BA1A1A'],
  HE: ['Hemorrhages', 'hemorrhage', '#9C3F4E'],
  EX: ['Hard Exudates', 'hard_exudate', '#7D5700'],
  SE: ['Soft Exudates', 'cotton_wool_spot', '#B45309'],
};

export function projectPatient(patient: PatientRecord, eye = patient.activeEye, raw = false): PatientRecord {
  const scan = eye === 'OS' ? patient.leftEye : patient.rightEye;
  const result = scan.result;
  const lesions: AnomalyItem[] = Object.entries(result?.lesions?.lesions || {}).flatMap(([code, value]) =>
    (raw ? value.raw_regions || [] : value.regions).map(region => ({
      id: `${eye}-${raw ? 'raw-' : ''}${code}-${region.region_id}`, name: classes[code][0], shortCode: code, type: classes[code][1],
      areaPixels: region.area_pixels, maxProbability: region.max_probability, sourceComponentIds: region.source_component_ids,
      meanProbability: region.mean_probability,
      coordinates: { x: region.x_min, y: region.y_min, w: region.width, h: region.height,
        x2: region.x_max, y2: region.y_max, centerX: region.center_x, centerY: region.center_y,
        leftPct: region.x_min / result.image_width * 100, topPct: region.y_min / result.image_height * 100,
        widthPct: region.width / result.image_width * 100, heightPct: region.height / result.image_height * 100 },
      confidence: Math.round(region.mean_probability * 1000) / 10,
      severity: 'Not assessed', color: classes[code][2], badgeBg: 'bg-secondary-container', badgeText: 'text-on-secondary-container',
      iconName: 'search', description: 'Predicted mask region. Score is mean pixel probability; clinical severity is not assessed.',
    })));
  return { ...patient, activeEye: eye, lesions,
    isConfirmed: scan.review?.confirmed || false, isFlagged: scan.review?.flagged || false,
    diagnosisName: result?.grading ? `DR grade ${result.grading.predicted_grade}` : 'DR grade unavailable',
    retinalGrade: result?.grading?.predicted_grade ?? null,
    retinalGradeLabel: result?.grading ? 'Model class 0–4 (repository class ordering)' : 'No grading result for this image',
    overallConfidence: result?.grading ? Math.round(result.grading.confidence * 1000) / 10 : null,
    criticalFinding: { ...emptyFinding, description: result ? result.warnings.join(' ') : 'Select a scan and run analysis.' },
  };
}

interface AnalysisJob {
  job_id: string;
  eye?: 'OS' | 'OD';
  state: AnalysisState;
  result: AnalysisResult | null;
  error: string | null;
  state_history?: { state: AnalysisState; at: string }[];
}

class AnalysisApiError extends Error {}

function responseError(payload: any, fallback: string) {
  if (typeof payload?.detail === 'string') return payload.detail;
  if (typeof payload?.detail?.message === 'string') return payload.detail.message;
  if (typeof payload?.error === 'string') return payload.error;
  return fallback;
}

function waitForPoll(milliseconds: number) {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

export async function analyzeImage(
  imageUrl: string,
  eye: 'OS' | 'OD',
  onStateChange?: (state: AnalysisState, jobId: string) => void,
): Promise<AnalysisResult> {
  let blob: Blob;
  try {
    const image = await fetch(imageUrl);
    if (!image.ok) throw new Error('Image could not be read.');
    blob = await image.blob();
  } catch {
    throw new Error('Cannot read the selected image. Upload a local retinal image; a remote sample may be unavailable.');
  }
  if (blob.size > 20 * 1024 * 1024) throw new Error('Image exceeds the 20 MB limit.');
  const body = new FormData();
  body.append('file', blob, 'retinal-image');
  body.append('eye', eye);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 300000);
  try {
    const response = await fetch('/api/analysis-jobs', { method: 'POST', body, signal: controller.signal });
    const created = await response.json().catch(() => null);
    if (!response.ok) throw new AnalysisApiError(responseError(created, `Analysis could not be queued (${response.status}).`));
    if (!created?.job_id) throw new AnalysisApiError('Backend returned an invalid analysis job response.');
    const jobId = created.job_id as string;
    const publishedStates = new Set<AnalysisState>();
    onStateChange?.('WAITING', jobId);
    publishedStates.add('WAITING');

    while (true) {
      const statusResponse = await fetch(`/api/analysis-jobs/${jobId}`, { signal: controller.signal });
      const job = await statusResponse.json().catch(() => null) as AnalysisJob | null;
      if (!statusResponse.ok || !job) {
        throw new AnalysisApiError(responseError(job, `Analysis status could not be read (${statusResponse.status}).`));
      }
      for (const item of job.state_history || []) {
        if (!publishedStates.has(item.state)) {
          publishedStates.add(item.state);
          onStateChange?.(item.state, jobId);
        }
      }
      if (!publishedStates.has(job.state)) {
        publishedStates.add(job.state);
        onStateChange?.(job.state, jobId);
      }
      if (job.state === 'FAILED') {
        throw new AnalysisApiError(job.error || `Analysis failed (run ${jobId}). Check backend logs and retry.`);
      }
      if (job.state === 'COMPLETE' || job.state === 'RECAPTURE_REQUIRED') {
        if (!job.result?.run_id) throw new AnalysisApiError('Backend reached a terminal state without a result.');
        if (job.result.eye !== eye) throw new AnalysisApiError('Backend response eye does not match the selected scan. Please retry.');
        return job.result;
      }
      await waitForPoll(250);
    }
  } catch (error) {
    if (error instanceof AnalysisApiError) throw error;
    throw new Error(controller.signal.aborted
      ? 'Inference timed out after five minutes. Check backend logs and retry.'
      : 'Local backend unavailable. Start the desktop application or backend and retry.');
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function saveReport(patient: PatientRecord, eye: 'OS' | 'OD', destination: string): Promise<ReportExportResult> {
  const scan = eye === 'OS' ? patient.leftEye : patient.rightEye;
  if (!scan.result) throw new Error('Run the retinal analysis before saving a report.');
  const response = await fetch('/api/reports/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      destination,
      run_id: scan.result.run_id,
      session_id: patient.sessionId,
      patient: {
        name: patient.name,
        id: patient.patientIdNumber,
        age: patient.age,
        gender: patient.gender,
        eye,
        scan_datetime: scan.capturedAt,
      },
    }),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail || `Report export failed (${response.status}).`);
  if (!result?.report || !result?.folder) throw new Error('Report export returned an invalid response.');
  return result;
}

export async function saveBothReports(patient: PatientRecord, destination: string): Promise<ReportExportResult> {
  const reports = (['OS', 'OD'] as const).flatMap(eye => {
    const scan = eye === 'OS' ? patient.leftEye : patient.rightEye;
    return scan.result?.state === 'COMPLETE'
      ? [{ run_id: scan.result.run_id, eye, scan_datetime: scan.capturedAt }]
      : [];
  });
  if (!reports.length) throw new Error('No completed eye reports are available to save.');
  const response = await fetch('/api/reports/export-both', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      destination,
      session_id: patient.sessionId,
      reports,
      patient: { name: patient.name, id: patient.patientIdNumber, age: patient.age, gender: patient.gender },
    }),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail || `Report export failed (${response.status}).`);
  if (!result?.folder) throw new Error('Report export returned an invalid response.');
  return result;
}

function historyEye(scan: EyeScanData) {
  const result = scan.result || null;
  return {
    available: Boolean(scan.imageUrl),
    completed: result?.state === 'COMPLETE',
    state: result?.state || scan.analysisState || null,
    result_data: result,
    original_path: result?.original_image_url || result?.image_url || scan.imageUrl || null,
    restored_path: result?.restored_image_url || null,
    overlay_path: result?.lesions?.combined_overlay_path || null,
    report_path: null,
    captured_at: scan.capturedAt || null,
  };
}

export async function persistHistory(patient: PatientRecord): Promise<HistoryRecord> {
  const response = await fetch('/api/history/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: patient.sessionId || patient.id,
      patient_id: patient.patientIdNumber,
      patient_name: patient.name,
      patient: {
        id: patient.id, age: patient.age, gender: patient.gender, dob: patient.dob,
        diabeticHistoryYears: patient.diabeticHistoryYears, hba1c: patient.hba1c,
        bloodPressure: patient.bloodPressure,
      },
      scan_datetime: patient.sessionStartedAt || [patient.leftEye.capturedAt, patient.rightEye.capturedAt]
        .filter(Boolean).sort().at(-1) || new Date().toISOString(),
      left_eye: historyEye(patient.leftEye),
      right_eye: historyEye(patient.rightEye),
    }),
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail || `History could not be saved (${response.status}).`);
  return result.record as HistoryRecord;
}

export async function loadHistory(): Promise<HistoryRecord[]> {
  const response = await fetch('/api/history');
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(result?.detail || `History could not be loaded (${response.status}).`);
  return Array.isArray(result?.records) ? result.records : [];
}

export function exportResult(patient: PatientRecord) {
  const result = (patient.activeEye === 'OS' ? patient.leftEye : patient.rightEye).result;
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = `retina-${result.run_id}.json`; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
