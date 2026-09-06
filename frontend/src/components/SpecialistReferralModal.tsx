import { useState, FormEvent } from 'react';
import { PatientRecord } from '../types';

interface SpecialistReferralModalProps {
  patient: PatientRecord;
  onClose: () => void;
  onReferralSuccess: (specialistName: string, urgency: 'STAT' | 'Urgent' | 'Routine') => void;
}

export function SpecialistReferralModal({
  patient,
  onClose,
  onReferralSuccess,
}: SpecialistReferralModalProps) {
  const [specialist, setSpecialist] = useState('Dr. Catherine Hayes, MD (Vitreoretinal Specialist)');
  const [urgency, setUrgency] = useState<'STAT' | 'Urgent' | 'Routine'>('Urgent');
  const [notes, setNotes] = useState(
    `${patient.diagnosisName}. ${patient.lesions.length} predicted lesion regions. Clinician notes required.`
  );
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true); setError(null);

    try {
      const response = await fetch('/api/referral', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patientId: patient.patientIdNumber,
          patientName: patient.name,
          specialistName: specialist,
          urgency,
          notes,
        }),
      });
      if (!response.ok) throw new Error('Unable to save local referral draft.');
    } catch {
      setError('Local backend unavailable; referral draft was not saved.');
      setIsSubmitting(false); return;
    }

    setTimeout(() => {
      setIsSubmitting(false);
      setIsSuccess(true);
      setTimeout(() => {
        onReferralSuccess(specialist, urgency);
        onClose();
      }, 1500);
    }, 800);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-surface-container-lowest rounded-2xl max-w-lg w-full border-2 border-outline shadow-2xl overflow-hidden animate-scale-up">
        {/* Modal Header */}
        <div className="p-5 bg-surface-container-low border-b-2 border-outline-variant flex justify-between items-center">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                forward_to_inbox
              </span>
            </div>
            <div>
              <h3 className="font-headline-md text-lg font-bold text-on-surface">
                Save Local Specialist Referral Draft
              </h3>
              <p className="text-xs text-on-surface-variant">
                Patient #{patient.patientIdNumber} • {patient.name}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-surface-container transition-colors text-on-surface-variant hover:text-on-surface"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        {/* Modal Body */}
        {isSuccess ? (
          <div className="p-8 flex flex-col items-center justify-center text-center gap-3">
            <div className="w-16 h-16 rounded-full bg-primary/10 border-2 border-primary flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                check_circle
              </span>
            </div>
            <h4 className="font-headline-md text-xl font-bold text-on-surface">
              Draft Saved Locally
            </h4>
            <p className="text-xs md:text-sm text-on-surface-variant">
              Draft for <strong>{specialist}</strong> saved with <strong>{urgency}</strong> priority. Nothing has been transmitted.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {/* Target Specialist Select */}
            <div>
              <label className="block text-xs font-bold text-on-surface mb-1">
                Select Receiving Specialist / Clinic
              </label>
              <select
                value={specialist}
                onChange={(e) => setSpecialist(e.target.value)}
                className="w-full p-2.5 bg-surface-container-lowest border border-outline rounded-lg text-sm text-on-surface focus:ring-2 focus:ring-primary focus:border-primary outline-none"
              >
                <option value="Dr. Catherine Hayes, MD (Vitreoretinal Specialist)">
                  Dr. Catherine Hayes, MD — Vitreoretinal Specialist (On-Call)
                </option>
                <option value="Dr. Robert Vance, MD (Comprehensive Ophthalmology)">
                  Dr. Robert Vance, MD — Comprehensive Ophthalmology
                </option>
                <option value="Dr. Ananya Sharma, MD (Diabetic Eye Center)">
                  Dr. Ananya Sharma, MD — Diabetic Retinopathy Clinic
                </option>
                <option value="Hospital Rapid Triage Telehealth Queue">
                  Hospital Rapid Triage Telehealth Queue (STAT AI)
                </option>
              </select>
            </div>

            {/* Urgency Level Selector */}
            <div>
              <label className="block text-xs font-bold text-on-surface mb-1.5">
                Referral Priority Level
              </label>
              <div className="grid grid-cols-3 gap-2">
                {(['Routine', 'Urgent', 'STAT'] as const).map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setUrgency(level)}
                    className={`py-2 px-3 rounded-lg border text-xs font-bold transition-all ${
                      urgency === level
                        ? level === 'STAT'
                          ? 'bg-error text-on-error border-error shadow-xs'
                          : level === 'Urgent'
                          ? 'bg-secondary text-white border-secondary shadow-xs'
                          : 'bg-primary text-on-primary border-primary shadow-xs'
                        : 'bg-surface-container-lowest text-on-surface border-outline-variant hover:bg-surface-container-low'
                    }`}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>

            {/* Attached Telehealth Assets */}
            <div className="bg-surface-container-low p-3 rounded-lg border border-outline-variant text-xs space-y-1.5">
              <span className="font-bold text-on-surface block">Attached Diagnostic Package:</span>
              <div className="flex flex-wrap gap-2 text-[11px] text-on-surface-variant">
                <span className="bg-surface-container-lowest px-2 py-0.5 rounded border border-outline-variant flex items-center gap-1">
                  <span className="material-symbols-outlined text-[12px]">image</span> Fundus Scan {patient.activeEye}
                </span>
                <span className="bg-surface-container-lowest px-2 py-0.5 rounded border border-outline-variant flex items-center gap-1">
                  <span className="material-symbols-outlined text-[12px]">visibility</span> Model results (when available)
                </span>
                <span className="bg-surface-container-lowest px-2 py-0.5 rounded border border-outline-variant flex items-center gap-1">
                  <span className="material-symbols-outlined text-[12px]">analytics</span> {patient.lesions.length} Predicted Regions
                </span>
              </div>
            </div>

            {error && <p role="alert" className="text-error text-sm">{error}</p>}
            <p className="text-xs">Saved locally only. No remote specialist service is connected.</p>
            {/* Clinical Referral Notes */}
            <div>
              <label className="block text-xs font-bold text-on-surface mb-1">
                Clinical Referral Notes
              </label>
              <textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full p-2.5 bg-surface-container-lowest border border-outline rounded-lg text-xs text-on-surface focus:ring-2 focus:ring-primary focus:border-primary outline-none"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 py-2.5 rounded-lg border border-outline text-on-surface font-label-lg text-sm hover:bg-surface-container transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex-1 py-2.5 rounded-lg bg-primary hover:bg-primary-fixed-dim text-on-primary font-label-lg text-sm transition-colors flex items-center justify-center gap-2 shadow-xs"
              >
                {isSubmitting ? (
                  <>
                    <span className="material-symbols-outlined text-base animate-spin">progress_activity</span>
                    Saving...
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined text-base">send</span>
                    Save Local Draft
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
