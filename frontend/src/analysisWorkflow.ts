import { PatientRecord } from './types';

export const ANALYSIS_EYE_ORDER = ['OS', 'OD'] as const;

/** Eyes with an uploaded original that have not reached a successful terminal result. */
export function eyesRequiringAnalysis(patient: PatientRecord): Array<'OS' | 'OD'> {
  return ANALYSIS_EYE_ORDER.filter(eye => {
    const scan = eye === 'OS' ? patient.leftEye : patient.rightEye;
    return Boolean(scan.imageUrl) && scan.result?.state !== 'COMPLETE';
  });
}
