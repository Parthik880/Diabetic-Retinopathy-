import type { PatientRecord } from './types';

export type PatientDetails = Pick<PatientRecord, 'id' | 'patientIdNumber' | 'name' | 'age' | 'gender' | 'phone' | 'email' | 'dob' | 'diabeticHistoryYears' | 'hba1c' | 'bloodPressure'>;
export interface DataOverview {
  cloud_connected: boolean; cloud_status: string; cloud_state: 'not_connected' | 'offline' | 'connected' | 'syncing' | 'sync_complete' | 'sync_failed';
  cloud_message: string; last_sync: string | null; pending_items: number | null; pending_reports: number | null;
  pending_images: number | null; failed_items: number | null;
  storage_backend: string; database_engine: string; database_status: 'Ready' | 'Unavailable';
  patient_count: number; session_count: number; report_count: number;
  storage_bytes: number; data_folder: string; busy: boolean; analysis_runs: number;
  retinal_image_count: number; generated_overlay_count: number; runtime_cache_bytes: number;
  sync_settings: { automatic: boolean; patients: boolean; reports: boolean; images: boolean };
  categories: Array<{ id: string; label: string; files: number; bytes: number }>;
}
export interface ClearPreview { token: string; categories: string[]; file_count: number; bytes: number; patient_count: number; session_count: number }
export async function dataRequest<T>(url: string, method = 'GET', payload?: unknown): Promise<T> {
  const response = await fetch(url, { method, ...(method !== 'GET' ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}) } : {}) });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof result?.detail === 'string' ? result.detail : 'Local data could not be updated. Please try again.');
  return result as T;
}
