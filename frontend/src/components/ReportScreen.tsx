import { useState } from 'react';
import { ACTIVE_ANALYSIS_STATES, PIPELINE_STATE_LABELS, saveBothReports, saveReport } from '../api';
import { PatientRecord } from '../types';
import { gradeLabel, LESION_LABELS, qualityLabel, qualityMessage, screeningRecommendation } from '../reporting';

interface ReportScreenProps {
  patient: PatientRecord;
  onUpdatePatient: (patient: PatientRecord) => void;
  onOpenReferralModal: () => void;
}

export function ReportScreen({ patient, onUpdatePatient, onOpenReferralModal }: ReportScreenProps) {
  const scan = patient.activeEye === 'OS' ? patient.leftEye : patient.rightEye;
  const result = scan.result;
  const grade = result?.grading?.predicted_grade;
  const [saveState, setSaveState] = useState<'idle' | 'choosing' | 'saving' | 'saving-both'>('idle');
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const handleSave = async () => {
    if (!result) return;
    if (!window.retinaDesktop) {
      setNotice({ type: 'error', text: 'The native folder picker is available in the RetinaGram desktop app.' });
      return;
    }
    setNotice(null);
    setSaveState('choosing');
    try {
      const destination = await window.retinaDesktop.chooseReportFolder();
      if (!destination) {
        setSaveState('idle');
        return;
      }
      setSaveState('saving');
      const exported = await saveReport(patient, patient.activeEye, destination);
      setNotice({ type: 'success', text: `Report saved to ${exported.folder}` });
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof Error ? error.message : 'Report could not be saved.' });
    } finally {
      setSaveState('idle');
    }
  };

  const handleSaveBoth = async () => {
    if (!window.retinaDesktop) return setNotice({ type: 'error', text: 'The native folder picker is available in the RetinaGram desktop app.' });
    setNotice(null); setSaveState('choosing');
    try {
      const destination = await window.retinaDesktop.chooseReportFolder();
      if (!destination) return;
      setSaveState('saving-both');
      const exported = await saveBothReports(patient, destination);
      setNotice({ type: 'success', text: `Both eye reports saved to ${exported.folder}` });
    } catch (error) {
      setNotice({ type: 'error', text: error instanceof Error ? error.message : 'Reports could not be saved.' });
    } finally { setSaveState('idle'); }
  };

  const eyeTabs = (
    <div role="tablist" aria-label="Report eye" className="mb-5 inline-flex rounded-xl bg-surface-container-low p-1 ring-1 ring-outline-variant">
      {(['OS', 'OD'] as const).map(eye => {
        const eyeScan = eye === 'OS' ? patient.leftEye : patient.rightEye;
        return <button key={eye} role="tab" aria-selected={patient.activeEye === eye} onClick={() => onUpdatePatient({ ...patient, activeEye: eye })} className={`min-h-10 rounded-lg px-4 text-sm font-extrabold ${patient.activeEye === eye ? 'bg-primary text-on-primary shadow-[0_2px_8px_rgba(0,82,39,0.2)]' : 'text-on-surface-variant hover:text-on-surface'}`}>
          {eye === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)'} <span className="ml-1 text-xs opacity-75">{eyeScan.result?.state === 'COMPLETE' ? '✓' : eyeScan.statusText}</span>
        </button>;
      })}
    </div>
  );

  if (!result || result.state !== 'COMPLETE') {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-1 items-center justify-center px-6 py-24 pb-32">
        <section className="w-full rounded-2xl border border-outline-variant bg-surface-container-lowest p-10 text-center shadow-[0_10px_32px_rgba(20,32,24,0.08)]">
          {eyeTabs}
          <span className="material-symbols-outlined text-5xl text-primary" aria-hidden="true">description</span>
          <h1 className="mt-4 font-headline text-2xl font-extrabold tracking-[-0.025em]">{ACTIVE_ANALYSIS_STATES.has(scan.analysisState) && scan.analysisRequestId ? 'Analysis in progress' : result?.state === 'RECAPTURE_REQUIRED' || scan.analysisState === 'RECAPTURE_REQUIRED' ? 'Recapture required' : 'No screening report yet'}</h1>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-on-surface-variant">{ACTIVE_ANALYSIS_STATES.has(scan.analysisState) && scan.analysisRequestId ? PIPELINE_STATE_LABELS[scan.analysisState] : result?.state === 'RECAPTURE_REQUIRED' ? 'Image quality was rejected. Capture a new image; no grade or lesion findings were generated.' : `Complete analysis for ${patient.activeEye === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)'} before creating its report.`}</p>
        </section>
      </div>
    );
  }

  const lesionEntries = Object.entries(LESION_LABELS).map(([code, label]) => ({ code, label, data: result.lesions?.lesions?.[code] }));

  return (
    <div className="report-screen mx-auto w-full max-w-6xl px-4 py-7 pb-32 md:px-6 md:pb-14">
      {eyeTabs}
      {notice && (
        <div role={notice.type === 'error' ? 'alert' : 'status'} className={`mb-4 flex items-start gap-2 rounded-xl border px-4 py-3 text-sm font-semibold ${notice.type === 'success' ? 'border-primary/30 bg-primary/10 text-primary' : 'border-error/30 bg-error-container text-error'}`}>
          <span className="material-symbols-outlined text-xl" aria-hidden="true">{notice.type === 'success' ? 'check_circle' : 'error'}</span>
          <span className="min-w-0 break-words">{notice.text}</span>
        </div>
      )}

      <section className="overflow-hidden rounded-2xl bg-surface-container-lowest shadow-[0_14px_44px_rgba(20,32,24,0.11)] ring-1 ring-outline-variant" aria-labelledby="report-title">
        <header className="flex flex-col justify-between gap-5 border-b border-outline-variant bg-[#f7fbf8] px-6 py-5 sm:flex-row sm:items-center md:px-8">
          <div className="flex items-center gap-3">
            <img src="/logo.png.jpeg" alt="RetinaGram" className="h-14 w-14 rounded-2xl object-cover shadow-[0_4px_14px_rgba(0,82,39,0.16)]" />
            <div>
              <h1 className="font-headline text-2xl font-extrabold tracking-[-0.03em] text-primary">RetinaGram</h1>
              <p className="mt-0.5 text-xs font-semibold tracking-[0.04em] text-on-surface-variant">AI Retinal Screening</p>
            </div>
          </div>
          <div className="sm:text-right">
            <h2 id="report-title" className="font-headline text-xl font-extrabold tracking-[-0.02em] text-on-surface">Diabetic Retinopathy</h2>
            <p className="text-sm font-semibold text-on-surface-variant">Screening Report</p>
          </div>
        </header>

        <div className="space-y-7 p-6 md:p-8">
          <section aria-labelledby="patient-information-heading">
            <h3 id="patient-information-heading" className="border-b border-outline-variant pb-2 font-headline text-sm font-extrabold">Patient information</h3>
            <dl className="mt-4 grid grid-cols-2 gap-x-8 gap-y-4 text-sm md:grid-cols-4">
              {[
                ['Patient name', patient.name],
                ['Patient ID', patient.patientIdNumber],
                ['Age / gender', `${patient.age} / ${patient.gender}`],
                ['Date and time of scan', scan.capturedAt],
                ['Image eye', patient.activeEye === 'OS' ? 'Left (OS)' : 'Right (OD)'],
                ['Report ID', result.run_id],
                ['Inference device', result.device_name || result.device],
              ].filter(([, value]) => value).map(([label, value]) => (
                <div key={label} className={label === 'Report ID' ? 'col-span-2 md:col-span-1' : ''}>
                  <dt className="text-[11px] font-bold uppercase tracking-[0.06em] text-on-surface-variant">{label}</dt>
                  <dd className={`mt-1 font-bold text-on-surface ${label === 'Report ID' ? 'break-all text-xs' : ''}`}>{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section aria-labelledby="analysis-heading">
            <h3 id="analysis-heading" className="font-headline text-sm font-extrabold">Main analysis</h3>
            <div className={`mt-3 grid gap-4 ${result.restored_image_url ? 'lg:grid-cols-[1fr_1fr_1fr_0.78fr]' : 'lg:grid-cols-[1fr_1fr_0.78fr]'}`}>
              <figure>
                <figcaption className="mb-2 text-[11px] font-bold uppercase tracking-[0.06em] text-on-surface-variant">Original fundus image</figcaption>
                <div className="aspect-[3/2] overflow-hidden rounded-xl bg-black ring-1 ring-outline-variant"><img src={result.image_url || scan.imageUrl} alt={`${patient.activeEye} original fundus`} className="h-full w-full object-contain" /></div>
              </figure>
              {result.restored_image_url && <figure>
                <figcaption className="mb-2 text-[11px] font-bold uppercase tracking-[0.06em] text-on-surface-variant">NAFNet restored image</figcaption>
                <div className="aspect-[3/2] overflow-hidden rounded-xl bg-black ring-1 ring-outline-variant"><img src={result.restored_image_url} alt={`${patient.activeEye} NAFNet restored fundus`} className="h-full w-full object-contain" /></div>
              </figure>}
              <figure>
                <figcaption className="mb-2 text-[11px] font-bold uppercase tracking-[0.06em] text-on-surface-variant">AI analysis / lesion overlay</figcaption>
                <div className="aspect-[3/2] overflow-hidden rounded-xl bg-black ring-1 ring-outline-variant">{result.lesions?.combined_overlay_path ? <img src={result.lesions.combined_overlay_path} alt={`${patient.activeEye} lesion overlay`} className="h-full w-full object-contain" /> : <div className="flex h-full items-center justify-center text-sm text-white/70">Overlay unavailable</div>}</div>
              </figure>
              <aside className="flex min-h-[180px] flex-col justify-between rounded-xl bg-primary/10 p-5">
                <div>
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-primary">DR grade</p>
                  <p className="mt-4 font-headline text-2xl font-extrabold tracking-[-0.03em] text-on-surface">{gradeLabel(grade)}</p>
                  <p className="mt-1 text-sm font-semibold text-on-surface-variant">{grade == null ? 'Grade unavailable' : `Grade ${grade}`}</p>
                </div>
                <div className="mt-5 border-t border-primary/20 pt-4">
                  <p className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-on-surface-variant">Confidence</p>
                  <p className="mt-1 font-headline text-3xl font-extrabold tabular-nums text-primary">{result.grading ? `${(result.grading.confidence * 100).toFixed(1)}%` : 'Unavailable'}</p>
                </div>
              </aside>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-[1.35fr_0.85fr]">
            <section className="rounded-xl border border-outline-variant p-5" aria-labelledby="lesion-heading">
              <h3 id="lesion-heading" className="font-headline text-sm font-extrabold">Lesion detection</h3>
              <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4">
                {lesionEntries.map(({ code, label, data }) => (
                  <div key={code}>
                    <dt className="text-xs text-on-surface-variant">{label}</dt>
                    <dd className={`mt-1 text-sm font-extrabold ${data?.detected ? 'text-primary' : 'text-on-surface'}`}>{data ? (data.detected ? 'Detected' : 'Not detected') : 'Unavailable'}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section className={`rounded-xl p-5 ${result.quality?.quality === 'Reject' ? 'bg-[#fff1e5]' : 'bg-primary/10'}`} aria-labelledby="quality-heading">
              <h3 id="quality-heading" className="font-headline text-sm font-extrabold">Image quality</h3>
              <p className={`mt-4 font-headline text-xl font-extrabold ${result.quality?.quality === 'Reject' ? 'text-secondary' : 'text-primary'}`}>{qualityLabel(result.quality?.quality)}</p>
              <p className="mt-2 text-xs leading-5 text-on-surface-variant">{qualityMessage(result.quality?.quality)}</p>
            </section>
          </div>

          <section className="rounded-xl bg-[#f7fbf8] p-5" aria-labelledby="recommendation-heading">
            <h3 id="recommendation-heading" className="font-headline text-sm font-extrabold">Screening recommendation</h3>
            <p className="mt-2 max-w-[75ch] text-sm leading-6 text-on-surface-variant">{screeningRecommendation(grade)}</p>
          </section>

          <footer className="flex flex-col gap-2 border-t border-outline-variant pt-4 text-[11px] leading-5 text-on-surface-variant sm:flex-row sm:items-end sm:justify-between">
            <p className="max-w-3xl">This report is generated by an AI-assisted retinal screening system and is not a substitute for professional medical diagnosis.</p>
            <p className="whitespace-nowrap font-bold">Page 1 of 1</p>
          </footer>
        </div>
      </section>

      <div className="no-print mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
        <button type="button" onClick={handleSave} disabled={saveState !== 'idle'} className="flex min-h-14 items-center justify-center gap-2 rounded-xl bg-primary px-6 text-base font-extrabold text-on-primary shadow-[0_8px_24px_rgba(0,82,39,0.22)] transition-colors hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-65">
          <span className="material-symbols-outlined text-xl" aria-hidden="true">{saveState === 'saving' ? 'progress_activity' : 'save'}</span>
          {saveState === 'choosing' ? 'Choose destination...' : saveState === 'saving' ? 'Saving report...' : `Save ${patient.activeEye === 'OS' ? 'Left Eye' : 'Right Eye'} Report`}
        </button>
        {patient.leftEye.result?.state === 'COMPLETE' && patient.rightEye.result?.state === 'COMPLETE' && <button type="button" onClick={handleSaveBoth} disabled={saveState !== 'idle'} className="flex min-h-14 items-center justify-center gap-2 rounded-xl border border-primary bg-primary/10 px-6 text-sm font-extrabold text-primary hover:bg-primary/15 disabled:opacity-60"><span className="material-symbols-outlined text-xl" aria-hidden="true">save_as</span>{saveState === 'saving-both' ? 'Saving both reports...' : 'Save Both Reports'}</button>}
        <button type="button" onClick={onOpenReferralModal} className="flex min-h-14 items-center justify-center gap-2 rounded-xl border border-outline bg-surface-container-lowest px-6 text-sm font-extrabold text-on-surface transition-colors hover:bg-surface-container-low focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
          <span className="material-symbols-outlined text-xl" aria-hidden="true">assignment</span>
          Save referral draft
        </button>
      </div>
    </div>
  );
}
