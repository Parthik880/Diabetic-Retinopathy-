export const GRADE_LABELS: Record<number, string> = {
  0: 'No diabetic retinopathy',
  1: 'Mild NPDR',
  2: 'Moderate NPDR',
  3: 'Severe NPDR',
  4: 'Proliferative DR',
};

export const LESION_LABELS: Record<string, string> = {
  MA: 'Microaneurysms',
  HE: 'Hemorrhages',
  EX: 'Hard Exudates',
  SE: 'Soft Exudates',
};

export function gradeLabel(grade?: number | null) {
  return grade == null ? 'Unavailable' : GRADE_LABELS[grade] || `Grade ${grade}`;
}

export function qualityLabel(value?: string) {
  if (value === 'Reject') return 'Poor - Recapture recommended';
  return value || 'Unavailable';
}

export function qualityMessage(value?: string) {
  if (value === 'Good') return 'Image is of sufficient quality for reliable screening analysis.';
  if (value === 'Usable') return 'Image is usable for screening; clinician review remains required.';
  if (value === 'Reject') return 'Image quality may limit analysis. Recapture is recommended.';
  return 'Image quality assessment is unavailable.';
}

export function screeningRecommendation(grade?: number | null) {
  if (grade === 0) return 'No signs of diabetic retinopathy were identified by the screening system. Routine ophthalmic screening is recommended.';
  if (grade === 1) return 'Features consistent with mild diabetic retinopathy were identified. Ophthalmic follow-up is recommended.';
  if (grade === 2) return 'Features consistent with moderate diabetic retinopathy were identified. Ophthalmologist evaluation and follow-up are recommended.';
  if (grade === 3 || grade === 4) return 'Features requiring prompt ophthalmic evaluation were identified. Referral to an ophthalmologist is recommended.';
  return 'A screening recommendation is unavailable because DR grading did not complete.';
}
