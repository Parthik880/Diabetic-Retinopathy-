import assert from 'node:assert/strict';
import { groupHistoryByPatient } from '../src/historyGrouping';
import { createNewSession, sessionHasData } from '../src/sessionWorkflow';
import type { HistoryRecord, PatientRecord } from '../src/types';

function record(sessionId: string, patientId: string, patientName: string, scan: string, eyes: Array<'OS' | 'OD'>, runId: string): HistoryRecord {
  const eye = (side: 'OS' | 'OD') => ({
    available: eyes.includes(side), completed: eyes.includes(side), state: eyes.includes(side) ? 'COMPLETE' as const : null,
    result_data: eyes.includes(side) ? { run_id: `${runId}${side}`, state: 'COMPLETE' } as any : null,
    original_path: eyes.includes(side) ? `/${sessionId}/${side}.png` : null,
    restored_path: null, overlay_path: null, report_path: null, captured_at: scan,
  });
  return {
    session_id: sessionId, patient_id: patientId, patient_name: patientName, scan_datetime: scan, updated_at: scan,
    patient: { id: `patient-${patientId}`, age: 50, gender: 'Female', dob: '1976-01-01', diabeticHistoryYears: 4, hba1c: '7.1%', bloodPressure: '120/80' },
    left_eye: eye('OS'), right_eye: eye('OD'),
  };
}

const records = [
  record('kate-1', 'RH-9344', 'Kate', '2026-08-01T10:00:00Z', ['OS'], 'run-1'),
  record('kate-3', 'RH-9344', 'Kate', '2026-09-05T16:55:00Z', ['OS', 'OD'], 'run-3'),
  record('kate-2', 'RH-9344', 'Kate', '2026-09-03T10:00:00Z', ['OD'], 'run-2'),
  record('other-kate', 'RH-7777', 'Kate', '2026-09-04T10:00:00Z', ['OS'], 'run-4'),
];
const now = new Date('2026-09-05T18:00:00Z');
const grouped = groupHistoryByPatient(records, '', 'all', 'all', now);
assert.equal(grouped.length, 2, 'Same-name patients with different MRNs remain separate');
const kate = grouped.find(group => group.patientId === 'RH-9344')!;
assert.equal(kate.sessions.length, 3, 'Three sessions render as one patient group');
assert.deepEqual(kate.sessions.map(item => item.session_id), ['kate-3', 'kate-2', 'kate-1'], 'Sessions sort newest first');
assert.equal(kate.sessions[2].left_eye.result_data?.run_id, 'run-1OS', 'Exact old-session result remains attached');
assert.deepEqual(groupHistoryByPatient(records, '9344', 'all', 'all', now).map(group => group.patientId), ['RH-9344']);
assert.equal(groupHistoryByPatient(records, 'Kate', 'all', 'all', now).length, 2, 'Name search matches both stable IDs');
assert.deepEqual(groupHistoryByPatient(records, '', 'today', 'all', now).map(group => group.patientId), ['RH-9344']);
assert.equal(groupHistoryByPatient(records, '', 'all', 'OD', now).find(group => group.patientId === 'RH-9344')?.sessions.length, 3);
assert.deepEqual(groupHistoryByPatient(records, '', 'all', 'both', now).map(group => group.patientId), ['RH-9344']);
assert.equal(groupHistoryByPatient(JSON.parse(JSON.stringify(records)), '', 'all', 'all', now).length, 2, 'Grouping survives persisted JSON reload');

const current = {
  ...records[0].patient,
  id: 'patient-RH-9344', patientIdNumber: 'RH-9344', name: 'Kate', studyDate: records[0].scan_datetime,
  sessionId: 'kate-1', sessionStartedAt: records[0].scan_datetime, activeEye: 'OS',
  leftEye: { eye: 'OS', eyeLabel: 'Left Eye (OS)', status: 'Good', statusText: 'Analysis complete', analysisState: 'COMPLETE', imageUrl: '/old.png', heatmapUrl: '/overlay.png', capturedAt: records[0].scan_datetime, imageQualityScore: 99, illuminationIndex: '', focusMetric: '', result: records[0].left_eye.result_data },
  rightEye: { eye: 'OD', eyeLabel: 'Right Eye (OD)', status: 'Needs Capture', statusText: 'Pending capture', analysisState: 'WAITING', imageUrl: '', heatmapUrl: '', capturedAt: '', imageQualityScore: null, illuminationIndex: '', focusMetric: '' },
  diagnosisName: '', retinalGrade: null, retinalGradeLabel: '', overallConfidence: null, lesions: [],
  criticalFinding: { title: '', description: '', urgency: 'Routine', actionNeeded: '' }, clinicalNotes: '', isConfirmed: false, isFlagged: false,
} as PatientRecord;
assert.equal(sessionHasData(current), true);
const fresh = createNewSession(current, new Date('2026-09-05T17:18:00Z'), 'new-session-id');
assert.equal(fresh.patientIdNumber, current.patientIdNumber, 'New Session retains the MRN');
assert.equal(fresh.name, current.name, 'New Session retains patient identity');
assert.equal(fresh.sessionId, 'new-session-id');
assert.equal(fresh.studyDate, '2026-09-05T17:18:00.000Z');
assert.equal(fresh.leftEye.imageUrl, '');
assert.equal(fresh.leftEye.result, undefined);
assert.equal(sessionHasData(fresh), false);

console.log('historyGrouping: grouped list, filters, persistence, exact sessions, and New Session identity passed');
