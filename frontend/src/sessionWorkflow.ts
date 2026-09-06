import { projectPatient, resetScan } from './api';
import type { EyeScanData, PatientRecord } from './types';

export function sessionHasData(patient: PatientRecord): boolean {
  return [patient.leftEye, patient.rightEye].some(scan => Boolean(
    scan.imageUrl || scan.result || scan.analysisRequestId || scan.analysisJobId || scan.analysisError,
  ));
}

function blankScan(scan: EyeScanData): EyeScanData {
  return resetScan({ ...scan, imageUrl: '', capturedAt: '' });
}

export function createNewSession(
  patient: PatientRecord,
  startedAt = new Date(),
  sessionId: string = crypto.randomUUID(),
): PatientRecord {
  const startedAtIso = startedAt.toISOString();
  return projectPatient({
    ...patient,
    sessionId,
    sessionStartedAt: startedAtIso,
    studyDate: startedAtIso,
    leftEye: blankScan(patient.leftEye),
    rightEye: blankScan(patient.rightEye),
    activeEye: 'OS',
    clinicalNotes: '',
    isConfirmed: false,
    isFlagged: false,
    referralStatus: undefined,
  });
}
