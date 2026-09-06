import type { HistoryRecord } from './types';

export type HistoryDateFilter = 'all' | 'today' | '7' | '30';
export type HistoryEyeFilter = 'all' | 'OS' | 'OD' | 'both';

export interface PatientHistoryGroup {
  patientId: string;
  patientName: string;
  sessions: HistoryRecord[];
  latestScan: string;
  eyes: Array<'OS' | 'OD'>;
}

export function completedEyes(record: HistoryRecord): Array<'OS' | 'OD'> {
  return [record.left_eye.completed && 'OS', record.right_eye.completed && 'OD'].filter(Boolean) as Array<'OS' | 'OD'>;
}

export function recordMatchesFilters(record: HistoryRecord, dateFilter: HistoryDateFilter, eyeFilter: HistoryEyeFilter, now = new Date()): boolean {
  const eyes = completedEyes(record);
  if (eyeFilter === 'both' && eyes.length !== 2) return false;
  if ((eyeFilter === 'OS' || eyeFilter === 'OD') && !eyes.includes(eyeFilter)) return false;
  if (dateFilter === 'all') return true;
  const scanDate = new Date(record.scan_datetime);
  if (Number.isNaN(scanDate.getTime())) return false;
  if (dateFilter === 'today') {
    return scanDate.getFullYear() === now.getFullYear() && scanDate.getMonth() === now.getMonth() && scanDate.getDate() === now.getDate();
  }
  const age = now.getTime() - scanDate.getTime();
  return age >= 0 && age <= Number(dateFilter) * 24 * 60 * 60 * 1000;
}

export function groupHistoryByPatient(
  records: HistoryRecord[], query = '', dateFilter: HistoryDateFilter = 'all', eyeFilter: HistoryEyeFilter = 'all', now = new Date(),
): PatientHistoryGroup[] {
  const needle = query.trim().toLocaleLowerCase();
  const allByPatient = new Map<string, HistoryRecord[]>();
  for (const record of records) {
    const sessions = allByPatient.get(record.patient_id) || [];
    sessions.push(record);
    allByPatient.set(record.patient_id, sessions);
  }
  return [...allByPatient.entries()].flatMap(([patientId, allSessions]) => {
    const sessions = [...allSessions].sort((a, b) => Date.parse(b.scan_datetime) - Date.parse(a.scan_datetime));
    const latest = sessions[0];
    if (needle && !`${latest.patient_name} ${patientId}`.toLocaleLowerCase().includes(needle)) return [];
    const matchingSessions = sessions.filter(record => recordMatchesFilters(record, dateFilter, eyeFilter, now));
    if (!matchingSessions.length) return [];
    const eyes = (['OS', 'OD'] as const).filter(eye => matchingSessions.some(record => completedEyes(record).includes(eye)));
    return [{ patientId, patientName: latest.patient_name, sessions, latestScan: latest.scan_datetime, eyes }];
  }).sort((a, b) => Date.parse(b.latestScan) - Date.parse(a.latestScan));
}
