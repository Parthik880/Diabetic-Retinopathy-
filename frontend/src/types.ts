import type { AnalysisResult } from './api';
export type TabType = 'capture' | 'analysis' | 'compare' | 'report' | 'history' | 'batch';
export type AnalysisState =
  | 'WAITING'
  | 'IQA'
  | 'IQA_GOOD'
  | 'IQA_USABLE'
  | 'IQA_REJECTED'
  | 'RESTORING'
  | 'RESTORATION_COMPLETE'
  | 'GRADING'
  | 'LESION_ANALYSIS'
  | 'LESION_INFERENCE'
  | 'LESION_MASK_PROCESSING'
  | 'LESION_REGION_EXTRACTION'
  | 'LESION_RESULTS_SAVING'
  | 'PREPARING_RESULTS'
  | 'COMPLETE'
  | 'RECAPTURE_REQUIRED'
  | 'FAILED';

export interface AnomalyItem {
  meanProbability?: number;
  areaPixels?: number;
  maxProbability?: number;
  sourceComponentIds?: number[];
  id: string;
  name: string;
  shortCode?: string;
  type: 'microaneurysm' | 'hemorrhage' | 'hard_exudate' | 'cotton_wool_spot' | 'neovascularization' | 'drusen';
  coordinates: {
    x: number;
    y: number;
    w: number;
    h: number;
    x2?: number;
    y2?: number;
    centerX?: number;
    centerY?: number;
    // Normalized percentage for responsive overlay rendering
    topPct: number;
    leftPct: number;
    widthPct: number;
    heightPct: number;
  };
  confidence: number;
  severity: 'Critical' | 'Review' | 'Normal' | 'Not assessed';
  color: string;
  badgeBg: string;
  badgeText: string;
  iconName: string;
  description?: string;
}

export interface EyeScanData {
  review?: { confirmed: boolean; flagged: boolean };
  result?: AnalysisResult;
  eye: 'OS' | 'OD';
  eyeLabel: string;
  status: 'Good' | 'Moderate' | 'Severe' | 'Normal' | 'AI Regenerating' | 'Needs Capture';
  statusText: string;
  analysisState: AnalysisState;
  analysisError?: string;
  analysisRequestId?: string;
  analysisJobId?: string;
  imageUrl: string;
  heatmapUrl: string;
  capturedAt: string;
  imageQualityScore: number | null;
  illuminationIndex: string;
  focusMetric: string;
}

export interface PatientRecord {
  id: string;
  sessionId?: string;
  sessionStartedAt?: string;
  patientIdNumber: string;
  name: string;
  age: number;
  gender: 'Female' | 'Male' | 'Other';
  dob: string;
  diabeticHistoryYears: number;
  hba1c: string;
  bloodPressure: string;
  studyDate: string;
  leftEye: EyeScanData;
  rightEye: EyeScanData;
  activeEye: 'OS' | 'OD';
  diagnosisName: string;
  retinalGrade: number | null;
  retinalGradeLabel: string;
  overallConfidence: number | null;
  lesions: AnomalyItem[];
  criticalFinding: {
    title: string;
    description: string;
    urgency: 'STAT' | 'Urgent' | 'Routine';
    actionNeeded: string;
  };
  clinicalNotes: string;
  isConfirmed: boolean;
  isFlagged: boolean;
  referralStatus?: {
    isReferred: boolean;
    specialistName?: string;
    urgency?: 'STAT' | 'Urgent' | 'Routine';
    referredAt?: string;
    notes?: string;
  };
}

export interface HistoryEyeRecord {
  available: boolean;
  completed: boolean;
  state: AnalysisState | null;
  result_data: AnalysisResult | null;
  original_path: string | null;
  restored_path: string | null;
  overlay_path: string | null;
  report_path: string | null;
  captured_at: string | null;
}

export interface HistoryRecord {
  session_id: string;
  patient_id: string;
  patient_name: string;
  patient: {
    id: string;
    age: number;
    gender: 'Female' | 'Male' | 'Other';
    dob: string;
    diabeticHistoryYears: number;
    hba1c: string;
    bloodPressure: string;
  };
  scan_datetime: string;
  updated_at: string;
  left_eye: HistoryEyeRecord;
  right_eye: HistoryEyeRecord;
}

export interface ReferralSubmission {
  id: string;
  patientId: string;
  patientName: string;
  specialistName: string;
  urgency: 'STAT' | 'Urgent' | 'Routine';
  notes: string;
  submittedAt: string;
  status: 'Pending Review' | 'In Review' | 'Accepted';
}
