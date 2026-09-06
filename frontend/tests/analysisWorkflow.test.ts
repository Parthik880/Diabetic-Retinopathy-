import assert from 'node:assert/strict';
import { eyesRequiringAnalysis } from '../src/analysisWorkflow';
import type { PatientRecord } from '../src/types';

function patient(leftImage: boolean, rightImage: boolean, leftComplete = false, rightComplete = false) {
  const scan = (eye: 'OS' | 'OD', uploaded: boolean, complete: boolean) => ({
    eye,
    eyeLabel: eye,
    status: 'Good' as const,
    statusText: complete ? 'Analysis complete' : 'Ready for analysis',
    analysisState: complete ? 'COMPLETE' as const : 'WAITING' as const,
    imageUrl: uploaded ? `${eye}.png` : '',
    heatmapUrl: '',
    capturedAt: '2026-09-05T00:00:00Z',
    imageQualityScore: null,
    illuminationIndex: '',
    focusMetric: '',
    result: complete ? { state: 'COMPLETE' } : undefined,
  });
  return {
    leftEye: scan('OS', leftImage, leftComplete),
    rightEye: scan('OD', rightImage, rightComplete),
  } as PatientRecord;
}

assert.deepEqual(eyesRequiringAnalysis(patient(true, false)), ['OS'], 'Left-only upload');
assert.deepEqual(eyesRequiringAnalysis(patient(false, true)), ['OD'], 'Right-only upload');
assert.deepEqual(eyesRequiringAnalysis(patient(true, true)), ['OS', 'OD'], 'Both uploads use stable sequential order');
assert.deepEqual(eyesRequiringAnalysis(patient(true, true, false, true)), ['OS'], 'Completed Right is skipped');
assert.deepEqual(eyesRequiringAnalysis(patient(true, true, true, false)), ['OD'], 'Completed Left is skipped');
assert.deepEqual(eyesRequiringAnalysis(patient(true, true, true, true)), [], 'Both completed are skipped');

console.log('analysisWorkflow: 6 orchestration cases passed');
