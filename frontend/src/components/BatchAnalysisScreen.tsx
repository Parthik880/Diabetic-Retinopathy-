import { useEffect, useMemo, useState } from 'react';
import { controlBatch, discoverBatch, getBatch, startBatch, type BatchEyeCandidate, type BatchEyeSnapshot, type BatchPatientSnapshot, type BatchSnapshot } from '../api';
import type { AnalysisState } from '../types';

const RUNNING_STATES = new Set(['Processing', 'Pausing', 'Paused', 'Cancelling']);

const STAGES: Array<{ state: AnalysisState | 'IMAGE_LOADED' | 'REPORT'; label: string }> = [
  { state: 'IMAGE_LOADED', label: 'Image loaded' },
  { state: 'IQA', label: 'Image quality assessment' },
  { state: 'RESTORING', label: 'Restoration' },
  { state: 'GRADING', label: 'DR grading' },
  { state: 'LESION_INFERENCE', label: 'GPU lesion inference' },
  { state: 'LESION_MASK_PROCESSING', label: 'Mask processing' },
  { state: 'LESION_REGION_EXTRACTION', label: 'Region extraction' },
  { state: 'LESION_RESULTS_SAVING', label: 'Save lesion results' },
  { state: 'REPORT', label: 'Report generation' },
];

const ORDER: Partial<Record<AnalysisState, number>> = {
  WAITING: 0, IQA: 1, IQA_GOOD: 2, IQA_USABLE: 2, IQA_REJECTED: 2,
  RESTORING: 2, RESTORATION_COMPLETE: 3, GRADING: 3, LESION_ANALYSIS: 4,
  LESION_INFERENCE: 4, LESION_MASK_PROCESSING: 5, LESION_REGION_EXTRACTION: 6,
  LESION_RESULTS_SAVING: 7, PREPARING_RESULTS: 8, COMPLETE: 8, RECAPTURE_REQUIRED: 8, FAILED: 8,
};

function statusStyle(status: string) {
  if (status === 'Completed' || status === 'READY' || status === 'Ready after selection') return 'bg-primary/10 text-primary';
  if (status === 'Processing' || status === 'Finalizing') return 'bg-secondary-container/45 text-on-secondary-container';
  if (status === 'Recapture Required' || status === 'NEEDS_REVIEW' || status === 'Skipped') return 'bg-tertiary-fixed text-on-tertiary-fixed-variant';
  if (status === 'Failed' || status === 'INVALID') return 'bg-error-container text-on-error-container';
  return 'bg-surface-container-high text-on-surface-variant';
}

function Metric({ label, value, tone = 'default' }: { label: string; value: number; tone?: 'default' | 'warning' | 'error' }) {
  const color = tone === 'warning' ? 'text-tertiary' : tone === 'error' ? 'text-error' : 'text-primary';
  return <div className="min-w-0 px-4 py-3">
    <div className={`font-headline text-2xl font-extrabold tabular-nums ${color}`}>{value}</div>
    <div className="mt-0.5 text-xs font-bold text-on-surface-variant">{label}</div>
  </div>;
}

function PipelineStage({ label, state }: { label: string; state: 'done' | 'active' | 'pending' | 'skipped' | 'failed' }) {
  const icon = state === 'done' ? 'check_circle' : state === 'active' ? 'radio_button_checked' : state === 'failed' ? 'error' : state === 'skipped' ? 'remove_circle_outline' : 'radio_button_unchecked';
  const color = state === 'done' ? 'text-primary' : state === 'active' ? 'text-secondary' : state === 'failed' ? 'text-error' : 'text-on-surface-variant';
  return <li className={`flex items-center gap-2.5 text-sm font-bold ${color}`}>
    <span className={`material-symbols-outlined text-[19px] ${state === 'active' ? 'fill-1' : ''}`} aria-hidden="true">{icon}</span>
    <span>{label}{state === 'skipped' ? ' · Not required' : ''}</span>
  </li>;
}

function currentEye(snapshot: BatchSnapshot): BatchEyeSnapshot | null {
  const current = snapshot.currently_processing;
  if (!current) return null;
  const patient = snapshot.patients.find(item => item.patient_id === current.patient_id);
  return patient?.eyes[current.eye] || null;
}

function pipelineState(eye: BatchEyeSnapshot | null, stage: typeof STAGES[number]['state']): 'done' | 'active' | 'pending' | 'skipped' | 'failed' {
  if (!eye) return 'pending';
  if (eye.stage === 'FAILED') return stage === 'REPORT' ? 'pending' : 'failed';
  const rank = ORDER[eye.stage] ?? 0;
  if (stage === 'IMAGE_LOADED') return 'done';
  if (stage === 'RESTORING' && eye.quality_route === 'GOOD') return 'skipped';
  if (stage === 'REPORT') return eye.status === 'Completed' ? 'done' : eye.status === 'Finalizing' ? 'active' : rank >= 8 ? 'active' : 'pending';
  const targets: Partial<Record<typeof stage, number>> = {
    IQA: 1, RESTORING: 2, GRADING: 3, LESION_INFERENCE: 4,
    LESION_MASK_PROCESSING: 5, LESION_REGION_EXTRACTION: 6, LESION_RESULTS_SAVING: 7,
  };
  const target = targets[stage] ?? 8;
  return rank > target ? 'done' : rank === target ? 'active' : 'pending';
}

type BatchSelections = Record<string, Partial<Record<'OS' | 'OD', string>>>;

function isReviewResolved(patient: BatchPatientSnapshot, selections: BatchSelections): boolean {
  if (patient.discovery_status !== 'NEEDS_REVIEW' || patient.issues.some(issue => !issue.startsWith('Duplicate '))) return false;
  return (['OS', 'OD'] as const).every(eye => patient.eye_candidates[eye].length <= 1
    || patient.eye_candidates[eye].some(candidate => candidate.source_path === selections[patient.patient_id]?.[eye]));
}

function EyeCandidateCell({ patientId, eye, candidates, selected, onSelect, disabled }: {
  patientId: string;
  eye: 'OS' | 'OD';
  candidates: BatchEyeCandidate[];
  selected?: string;
  onSelect: (path: string) => void;
  disabled: boolean;
}) {
  if (!candidates.length) return <span className="text-on-surface-variant" aria-label={`${eye} not detected`}>—</span>;
  if (candidates.length === 1) return <details className="max-w-[220px]">
    <summary className="cursor-pointer truncate font-bold text-primary" title={candidates[0].source_path}>✓ {candidates[0].source_name}</summary>
    <p className="mt-1 break-all text-[11px] leading-4 text-on-surface-variant">{candidates[0].source_path}</p>
  </details>;
  return <fieldset className="min-w-[220px]" disabled={disabled}>
    <legend className="mb-1 text-xs font-extrabold text-tertiary">Select one of {candidates.length}</legend>
    <div className="space-y-1.5">{candidates.map(candidate => <label key={candidate.source_path} className="flex cursor-pointer items-start gap-2 rounded-lg p-1.5 hover:bg-surface-container-low">
      <input type="radio" name={`${patientId}-${eye}`} checked={selected === candidate.source_path} onChange={() => onSelect(candidate.source_path)} className="mt-0.5 h-4 w-4 accent-primary" />
      <span className="min-w-0"><span className="block truncate text-xs font-bold" title={candidate.source_path}>{candidate.source_name}</span><span className="block break-all text-[10px] leading-4 text-on-surface-variant">{candidate.source_path}</span></span>
    </label>)}</div>
  </fieldset>;
}

export function BatchAnalysisScreen() {
  const [snapshot, setSnapshot] = useState<BatchSnapshot | null>(null);
  const [outputPath, setOutputPath] = useState('');
  const [createPatientFolders, setCreatePatientFolders] = useState(true);
  const [skipUnresolved, setSkipUnresolved] = useState(true);
  const [selections, setSelections] = useState<BatchSelections>({});
  const [reviewed, setReviewed] = useState(false);
  const [showPatients, setShowPatients] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!snapshot || !RUNNING_STATES.has(snapshot.state)) return;
    let stopped = false;
    const poll = window.setInterval(() => {
      void getBatch(snapshot.batch_id).then(value => { if (!stopped) setSnapshot(value); }).catch(err => {
        if (!stopped) setError(err instanceof Error ? err.message : 'Batch status could not be read.');
      });
    }, 750);
    return () => { stopped = true; window.clearInterval(poll); };
  }, [snapshot?.batch_id, snapshot?.state]);

  const activeEye = useMemo(() => snapshot ? currentEye(snapshot) : null, [snapshot]);
  const chooseInput = async () => {
    if (!window.retinaDesktop) return setError('Folder selection is available in the RetinaGram desktop app.');
    const path = await window.retinaDesktop.chooseBatchInputFolder();
    if (!path) return;
    setBusy(true); setError(null); setReviewed(false); setShowPatients(false); setSelections({}); setSkipUnresolved(true);
    try { setSnapshot(await discoverBatch(path)); }
    catch (err) { setError(err instanceof Error ? err.message : 'The input folder could not be scanned.'); }
    finally { setBusy(false); }
  };
  const chooseOutput = async () => {
    if (!window.retinaDesktop) return setError('Folder selection is available in the RetinaGram desktop app.');
    const path = await window.retinaDesktop.chooseBatchOutputFolder();
    if (path) setOutputPath(path);
  };
  const begin = async () => {
    if (!snapshot || !outputPath || !reviewed) return;
    setBusy(true); setError(null);
    try { setSnapshot(await startBatch(snapshot.batch_id, outputPath, createPatientFolders, selections, skipUnresolved)); }
    catch (err) { setError(err instanceof Error ? err.message : 'Batch analysis could not be started.'); }
    finally { setBusy(false); }
  };
  const control = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!snapshot) return;
    setBusy(true); setError(null);
    try { setSnapshot(await controlBatch(snapshot.batch_id, action)); }
    catch (err) { setError(err instanceof Error ? err.message : `Batch ${action} failed.`); }
    finally { setBusy(false); }
  };

  const counts = snapshot?.counts;
  const resolvedReviewCount = snapshot?.patients.filter(patient => isReviewResolved(patient, selections)).length || 0;
  const readyToRun = (counts?.ready || 0) + resolvedReviewCount;
  const canStart = Boolean(snapshot && snapshot.state === 'Review' && readyToRun > 0 && outputPath && reviewed && !busy);

  return <div className="mx-auto w-full max-w-[1440px] px-4 pb-24 pt-8 md:px-6 lg:px-8">
    <div className="flex flex-col gap-3 border-b border-outline-variant pb-6 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="font-headline text-3xl font-extrabold tracking-[-0.03em] text-on-surface md:text-4xl">Batch Analysis</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-on-surface-variant md:text-base">Process multiple retinal images and generate patient reports automatically.</p>
      </div>
      {snapshot && <span className={`w-fit rounded-lg px-3 py-2 text-xs font-extrabold ${statusStyle(snapshot.state)}`}>{snapshot.state}</span>}
    </div>

    {error && <div role="alert" className="mt-5 flex items-start gap-2 rounded-xl bg-error-container px-4 py-3 text-sm font-bold text-on-error-container">
      <span className="material-symbols-outlined text-[20px]" aria-hidden="true">error</span><span>{error}</span>
    </div>}

    <section aria-label="Batch workflow" className="mt-6 overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest">
      <div className="grid divide-y divide-outline-variant lg:grid-cols-3 lg:divide-x lg:divide-y-0">
        <div className="p-5">
          <div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-extrabold text-on-primary">1</span><h2 className="font-headline text-lg font-extrabold">Select Input Folder</h2></div>
          <p className="mt-3 min-h-10 text-sm leading-5 text-on-surface-variant">Structured patient folders and ID_Name_OS/OD filenames are supported.</p>
          <button type="button" onClick={() => void chooseInput()} disabled={busy || Boolean(snapshot && snapshot.state !== 'Review')} className="mt-4 flex min-h-11 items-center gap-2 rounded-xl border border-primary px-4 text-sm font-extrabold text-primary transition-colors hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">
            <span className="material-symbols-outlined text-[19px]" aria-hidden="true">folder_open</span>{busy && !snapshot ? 'Scanning…' : 'Choose Folder'}
          </button>
          {snapshot && <p className="mt-3 break-all text-xs font-semibold text-on-surface-variant" title={snapshot.input_path}>{snapshot.input_path}</p>}
        </div>

        <div className="p-5">
          <div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-extrabold text-on-primary">2</span><h2 className="font-headline text-lg font-extrabold">Review &amp; Confirm</h2></div>
          {counts ? <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
            <span><strong className="tabular-nums">{counts.total_patients}</strong> patients</span><span><strong className="tabular-nums">{counts.total_images}</strong> images</span>
            <span className="text-primary"><strong className="tabular-nums">{counts.ready}</strong> ready</span><span className={counts.needs_review ? 'text-tertiary' : 'text-on-surface-variant'}><strong className="tabular-nums">{counts.needs_review}</strong> need review</span>
            <button type="button" className={`w-fit text-left underline-offset-4 ${counts.invalid ? 'font-bold text-error underline' : 'text-on-surface-variant'}`} onClick={() => setShowPatients(true)} disabled={!counts.invalid}><strong className="tabular-nums">{counts.invalid}</strong> invalid</button><span className="capitalize text-on-surface-variant">{snapshot?.mode} mode</span>
            <span><strong className="tabular-nums">{counts.paired_patients}</strong> paired</span><span><strong className="tabular-nums">{counts.single_eye_patients}</strong> single-eye</span>
          </div> : <p className="mt-3 text-sm text-on-surface-variant">Choose a folder to detect patients and eye images.</p>}
          <button type="button" onClick={() => setShowPatients(value => !value)} disabled={!snapshot} className="mt-4 min-h-11 rounded-xl px-1 text-sm font-extrabold text-primary underline decoration-primary/35 underline-offset-4 disabled:opacity-40">{showPatients ? 'Hide Patient List' : 'View Patient List'}</button>
          {snapshot?.state === 'Review' && <label className="mt-2 flex cursor-pointer items-start gap-2 text-sm font-bold text-on-surface">
            <input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" />
            I reviewed the detected patients and eye assignments.
          </label>}
        </div>

        <div className="p-5">
          <div className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-extrabold text-on-primary">3</span><h2 className="font-headline text-lg font-extrabold">Start Batch Analysis</h2></div>
          <button type="button" onClick={() => void chooseOutput()} disabled={!snapshot || snapshot.state !== 'Review'} className="mt-3 flex min-h-10 items-center gap-2 rounded-lg border border-outline px-3 text-xs font-extrabold text-on-surface hover:bg-surface-container-low disabled:opacity-40"><span className="material-symbols-outlined text-[18px]" aria-hidden="true">drive_folder_upload</span>Choose Output Folder</button>
          <p className="mt-2 min-h-5 break-all text-xs font-semibold text-on-surface-variant">{outputPath || 'No output folder selected'}</p>
          <label className="mt-2 flex items-center gap-2 text-sm font-bold"><input type="checkbox" checked={createPatientFolders} onChange={event => setCreatePatientFolders(event.target.checked)} disabled={snapshot?.state !== 'Review'} className="h-4 w-4 accent-primary" />Create patient-wise folders</label>
          {snapshot?.state === 'Review' && Boolean((counts?.needs_review || 0) + (counts?.invalid || 0)) && <label className="mt-2 flex items-start gap-2 text-sm font-bold text-on-surface">
            <input type="checkbox" checked={skipUnresolved} onChange={event => setSkipUnresolved(event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" />
            <span>Skip unresolved entries<span className="mt-0.5 block text-xs font-medium text-on-surface-variant">READY patients and resolved duplicate selections will still run.</span></span>
          </label>}
          <button type="button" onClick={() => void begin()} disabled={!canStart} className="mt-4 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 text-sm font-extrabold text-on-primary shadow-[0_6px_18px_rgba(0,82,39,0.2)] hover:bg-primary-container disabled:cursor-not-allowed disabled:bg-surface-container-highest disabled:text-on-surface-variant disabled:shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"><span className="material-symbols-outlined text-[19px]" aria-hidden="true">play_arrow</span>Start Batch Analysis</button>
          {snapshot?.state === 'Review' && <p className="mt-2 text-xs font-semibold text-on-surface-variant">{readyToRun} patient{readyToRun === 1 ? '' : 's'} ready to run</p>}
        </div>
      </div>
    </section>

    {snapshot && snapshot.state !== 'Review' && <>
      <section className="mt-6 rounded-2xl bg-surface-container-low p-5" aria-labelledby="batch-progress-title">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><h2 id="batch-progress-title" className="font-headline text-xl font-extrabold">Batch Progress</h2><p className="mt-1 text-xs font-semibold text-on-surface-variant">Counts update from completed pipeline and output events.</p></div>
          <div className="flex flex-wrap gap-2">
            {snapshot.can_pause && <button onClick={() => void control('pause')} disabled={busy} className="min-h-10 rounded-lg border border-primary px-3 text-xs font-extrabold text-primary hover:bg-primary/10">Pause Batch</button>}
            {snapshot.can_resume && <button onClick={() => void control('resume')} disabled={busy} className="min-h-10 rounded-lg bg-primary px-3 text-xs font-extrabold text-on-primary">Resume Batch</button>}
            {snapshot.can_cancel && <button onClick={() => void control('cancel')} disabled={busy} className="min-h-10 rounded-lg border border-error px-3 text-xs font-extrabold text-error hover:bg-error-container">Cancel Batch</button>}
          </div>
        </div>
        <div className="mt-4 grid divide-y divide-outline-variant rounded-xl bg-surface-container-lowest sm:grid-cols-4 sm:divide-x sm:divide-y-0 xl:grid-cols-7">
          <Metric label="Total Patients" value={counts!.total_patients} /><Metric label="Total Images" value={counts!.total_images} /><Metric label="Completed" value={counts!.completed} />
          <Metric label="Processing" value={counts!.processing} /><Metric label="Queued" value={counts!.queued} /><Metric label="Recapture Required" value={counts!.recapture_required} tone="warning" /><Metric label="Failed" value={counts!.failed} tone="error" />
        </div>
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <section className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-5" aria-labelledby="currently-processing-title">
          <h2 id="currently-processing-title" className="font-headline text-xl font-extrabold">Currently Processing</h2>
          {snapshot.currently_processing ? <>
            <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-surface-container-low px-4 py-3">
              <div><div className="text-sm font-extrabold">Patient {snapshot.currently_processing.patient_id}</div><div className="mt-0.5 text-xs font-semibold text-on-surface-variant">{snapshot.currently_processing.eye === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)'}</div></div>
              <span className="material-symbols-outlined text-2xl text-primary" aria-hidden="true">neurology</span>
            </div>
            <ol className="mt-4 space-y-2.5">{STAGES.map(stage => <PipelineStage key={stage.state} label={stage.label} state={pipelineState(activeEye, stage.state)} />)}</ol>
          </> : <div className="mt-4 rounded-xl bg-surface-container-low px-4 py-6 text-sm font-semibold text-on-surface-variant">{snapshot.state === 'Completed' ? 'All scheduled patients are complete.' : snapshot.state === 'Paused' ? 'Paused at a safe scheduling boundary.' : snapshot.state === 'Cancelled' ? 'No further patients will be scheduled.' : 'Waiting for the next eye.'}</div>}
        </section>

        <section className="rounded-2xl border border-outline-variant bg-inverse-surface p-5 text-inverse-on-surface" aria-labelledby="live-log-title">
          <div className="flex items-center justify-between"><h2 id="live-log-title" className="font-headline text-xl font-extrabold">Live Log</h2><span className="text-xs font-bold text-primary-fixed-dim">Patient IDs only</span></div>
          <div className="mt-4 h-64 overflow-y-auto rounded-xl bg-black/20 p-3 font-mono text-xs leading-6" role="log" aria-live="polite">
            {snapshot.logs.length ? [...snapshot.logs].reverse().map((log, index) => <div key={`${log.time}-${index}`} className="border-b border-white/5 py-0.5"><span className="text-primary-fixed-dim">{log.time}</span> <span className="text-white">[{log.patient_id}]{log.eye ? `[${log.eye}]` : ''}</span> <span className="text-inverse-on-surface/80">{log.message}</span></div>) : <div className="text-inverse-on-surface/60">No batch events yet.</div>}
          </div>
        </section>
      </div>
    </>}

    {snapshot && (showPatients || snapshot.state !== 'Review') && <section className="mt-6 overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest" aria-labelledby="detected-patients-title">
      <div className="flex items-center justify-between border-b border-outline-variant px-5 py-4"><div><h2 id="detected-patients-title" className="font-headline text-xl font-extrabold">Detected Patients</h2><p className="mt-1 text-xs font-semibold text-on-surface-variant">Independent eye status is preserved for OS-only, OD-only, and paired patients.</p></div><span className="text-sm font-extrabold tabular-nums text-primary">{snapshot.patients.length}</span></div>
      <div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="bg-surface-container-low text-xs uppercase tracking-[0.04em] text-on-surface-variant"><tr><th className="px-5 py-3">#</th><th className="px-5 py-3">Patient ID</th><th className="px-5 py-3">Name</th><th className="px-5 py-3">OS</th><th className="px-5 py-3">OD</th><th className="px-5 py-3">Status</th><th className="px-5 py-3 text-right">Progress</th></tr></thead>
        <tbody className="divide-y divide-outline-variant">{snapshot.patients.map(patient => {
          const resolved = isReviewResolved(patient, selections);
          const displayStatus = snapshot.state === 'Review' ? resolved ? 'Ready after selection' : patient.discovery_status : patient.status;
          return <tr key={`${patient.patient_id}-${patient.index}`} className="align-top hover:bg-surface-container-low/60">
            <td className="px-5 py-4 tabular-nums text-on-surface-variant">{patient.index}</td>
            <td className="px-5 py-4 font-extrabold text-on-surface">{patient.patient_id}</td>
            <td className="px-5 py-4 font-semibold">{patient.name || <span className="font-medium text-on-surface-variant">Unknown</span>}</td>
            <td className="px-5 py-4"><EyeCandidateCell patientId={patient.patient_id} eye="OS" candidates={patient.eye_candidates.OS} selected={selections[patient.patient_id]?.OS} disabled={snapshot.state !== 'Review'} onSelect={path => setSelections(value => ({ ...value, [patient.patient_id]: { ...value[patient.patient_id], OS: path } }))} /></td>
            <td className="px-5 py-4"><EyeCandidateCell patientId={patient.patient_id} eye="OD" candidates={patient.eye_candidates.OD} selected={selections[patient.patient_id]?.OD} disabled={snapshot.state !== 'Review'} onSelect={path => setSelections(value => ({ ...value, [patient.patient_id]: { ...value[patient.patient_id], OD: path } }))} /></td>
            <td className="px-5 py-4"><span className={`inline-flex rounded-lg px-2.5 py-1.5 text-xs font-extrabold ${statusStyle(displayStatus)}`}>{displayStatus.replace('_', ' ')}</span>{patient.issues.length > 0 && <ul className="mt-2 max-w-[220px] space-y-1 text-xs font-semibold text-tertiary">{patient.issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}</td>
            <td className="px-5 py-4 text-right font-extrabold tabular-nums">{patient.progress}</td>
          </tr>;
        })}</tbody>
      </table></div>
      {!snapshot.patients.length && <div className="px-5 py-10 text-center text-sm font-semibold text-on-surface-variant">No valid patients were detected. Check the folder names and patient.json fields.</div>}
      {snapshot.invalid_items.length > 0 && <div className="border-t border-outline-variant bg-error-container/35 px-5 py-4">
        <h3 className="text-sm font-extrabold text-error">Rejected items and reasons</h3>
        <ul className="mt-3 divide-y divide-error/15">{snapshot.invalid_items.map(item => <li key={`${item.path}-${item.reason}`} className="grid gap-1 py-2 text-xs sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] sm:gap-4">
          <span className="min-w-0"><span className="block truncate font-extrabold text-on-surface" title={item.path}>{item.name}</span><span className="block break-all text-[10px] text-on-surface-variant">{item.path}</span></span>
          <span className="font-semibold text-error">Reason: {item.reason}</span>
        </li>)}</ul>
      </div>}
      {snapshot.state === 'Review' && snapshot.logs.length > 0 && <details className="border-t border-outline-variant px-5 py-4">
        <summary className="cursor-pointer text-sm font-extrabold text-primary">Discovery log</summary>
        <div className="mt-3 max-h-48 overflow-y-auto rounded-xl bg-inverse-surface p-3 font-mono text-xs leading-6 text-inverse-on-surface" role="log">
          {snapshot.logs.map((log, index) => <div key={`${log.time}-${index}`}><span className="text-primary-fixed-dim">{log.time}</span> <span>[{log.patient_id}]{log.eye ? `[${log.eye}]` : ''}</span> {log.message}</div>)}
        </div>
      </details>}
    </section>}

    {snapshot?.output_root && <p className="mt-4 break-all text-xs font-semibold text-on-surface-variant">Output: <span className="text-on-surface">{snapshot.output_root}</span></p>}
  </div>;
}
