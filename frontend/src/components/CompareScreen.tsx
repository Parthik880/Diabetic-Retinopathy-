import { useState } from 'react';
import { RegionCounts } from './RegionCounts';
import { selectRegions, topKLabel } from '../regionSelection';
import { exportResult, projectPatient } from '../api';
import type { PatientRecord, TabType } from '../types';
import { AnalysisVisualization, VisualizationControls, INITIAL_SETTINGS, CLASS_NAMES, type AnalysisView, type ViewSettings } from './AnalysisVisualization';

interface CompareScreenProps {
  patient: PatientRecord;
  onNavigate: (tab: TabType) => void;
  onOpenReferralModal: () => void;
  onInspectEye: (eye: 'OS' | 'OD') => void;
}
const VIEWS: Record<AnalysisView, string> = { grade: 'Grade Grad-CAM', attention: 'Lesion Heatmap', detection: 'Lesion Detection', annotation: 'Lesion Annotation' };

export function CompareScreen({ patient, onNavigate, onOpenReferralModal, onInspectEye }: CompareScreenProps) {
  const [view, setView] = useState<AnalysisView>('grade');
  const [settings, setSettings] = useState<ViewSettings>({ ...INITIAL_SETTINGS, attentionType: 'Probability' });
  const [selected, setSelected] = useState<Record<string, string | null>>({ OS: null, OD: null });
  const [notice, setNotice] = useState<string | null>(null);
  const eyes = ['OS', 'OD'] as const;
  const left = patient.leftEye.result;
  const right = patient.rightEye.result;
  const classes = Array.from(new Set([...Object.keys(left?.lesions?.lesions || {}), ...Object.keys(right?.lesions?.lesions || {})]));
  const leftGrade = left?.grading?.predicted_grade;
  const rightGrade = right?.grading?.predicted_grade;
  const comparison = leftGrade == null || rightGrade == null ? 'Analyze both eyes to compare predicted DR grades.'
    : leftGrade === rightGrade ? `Both eyes have the same predicted DR grade (${leftGrade}).`
    : `Higher predicted DR grade: ${leftGrade > rightGrade ? 'Left eye (OS)' : 'Right eye (OD)'}.`;

  return <div className="w-full max-w-7xl mx-auto px-4 md:px-6 py-6 pb-28 md:pb-12">
    <div className="flex flex-col md:flex-row md:items-end justify-between border-b-2 border-outline-variant pb-6 mb-6 gap-4">
      <div><h1 className="text-2xl md:text-3xl font-bold">Left Eye vs Right Eye</h1>
        <p className="text-sm text-on-surface-variant mt-1">Patient #{patient.patientIdNumber} · {patient.name} · Two independent scans</p></div>
      <div className="flex flex-wrap gap-3">
        <button onClick={() => { if (!left && !right) { setNotice('Analyze at least one eye before exporting.'); return; } eyes.forEach(eye => exportResult(projectPatient(patient, eye))); setNotice('Available OS / OD model JSON results exported.'); }}
          className="px-4 py-2 border-2 border-outline rounded-lg font-semibold text-sm hover:bg-surface-container-low">Export Results</button>
        <button onClick={onOpenReferralModal} className="px-4 py-2 bg-primary text-on-primary rounded-lg font-semibold text-sm hover:bg-primary-container">Share / Local Draft</button>
      </div>
    </div>
    {notice && <p role="status" className="mb-4 text-sm text-primary">{notice}</p>}
    <div className="flex flex-col gap-4 mb-6">
      <div className="flex flex-wrap gap-3 items-center">
        <label className="flex flex-wrap gap-2 items-center text-sm font-bold">Comparison View
          <select aria-label="Comparison View" value={view} onChange={e => setView(e.target.value as AnalysisView)} className="border border-outline rounded-lg px-3 py-2 bg-surface-container-lowest">
            {Object.entries(VIEWS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label><span className="text-xs text-on-surface-variant">Synchronized for OS and OD</span>
      </div>
      <VisualizationControls view={view} settings={settings} onChange={setSettings} availableClasses={classes} />
    </div>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6" data-testid="bilateral-panels">
      {eyes.map(eye => {
        const projected = projectPatient(patient, eye);
        const scan = eye === 'OS' ? patient.leftEye : patient.rightEye;
        const result = scan.result;
        const detected = Object.entries(result?.lesions?.lesions || {}).filter(([, value]) => value.detected);
        return <section key={eye} className="min-w-0 flex flex-col gap-4" data-testid={`compare-eye-${eye}`}>
          <div className="flex items-center justify-between gap-3 pb-3 border-b border-outline-variant">
            <h2 className="text-xl font-bold">{eye === 'OS' ? 'OS · Left Eye' : 'OD · Right Eye'}</h2>
            <button onClick={() => onInspectEye(eye)} className="text-sm font-bold text-primary underline underline-offset-2">Inspect {eye}</button>
          </div>
          <AnalysisVisualization scan={scan} view={view} settings={settings} lesions={settings.rawRegions ? projectPatient(patient, eye, true).lesions : selectRegions(projected.lesions, settings.topK, settings.regionClass)} compact selectedId={selected[eye]} onSelect={id => setSelected(prev => ({ ...prev, [eye]: id }))} />
          <div className="bg-surface-container-low border border-outline-variant rounded-lg p-4 text-sm">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 tabular-nums">
              <div><dt className="text-xs text-on-surface-variant">Predicted DR grade</dt><dd className="font-bold text-lg" data-testid={`compare-grade-${eye}`}>{result?.grading?.predicted_grade ?? 'Unavailable'}</dd></div>
              <div><dt className="text-xs text-on-surface-variant">Grade class confidence</dt><dd className="font-bold text-lg">{result?.grading ? `${(result.grading.confidence * 100).toFixed(1)}%` : 'Unavailable'}</dd></div>
              <div><dt className="text-xs text-on-surface-variant">IQA</dt><dd className="font-bold">{result?.quality?.quality || 'Not assessed'}</dd></div>
              <div><dt className="text-xs text-on-surface-variant">IQA class confidence</dt><dd className="font-bold">{result?.quality ? `${(result.quality.confidence * 100).toFixed(1)}%` : 'Unavailable'}</dd></div>
            </dl>
            <p className="mt-3 text-xs"><strong>Lesions:</strong> {result?.lesions ? detected.length ? detected.map(([code, value]) => `${code} (${value.num_regions})`).join(' · ') : 'No retained regions' : 'Not assessed'}</p>
            {result && <p className="mt-2 text-xs text-on-surface-variant break-all">Inference run: {result.run_id}</p>}
            <div className="mt-3"><RegionCounts result={result} displayed={view === 'detection' ? (settings.rawRegions ? projectPatient(patient, eye, true).lesions.length : selectRegions(projected.lesions, settings.topK, settings.regionClass).length) : undefined}
              selection={settings.rawRegions ? 'Raw model output' : `${topKLabel(settings.topK)} · ${settings.regionClass}`} /></div>
          </div>
        </section>;
      })}
    </div>
    <section className="mt-8 p-6 rounded-xl border-2 border-outline bg-surface-container-lowest" data-testid="bilateral-summary">
      <h2 className="text-xl font-bold mb-4">Bilateral Analysis</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        {eyes.map(eye => {
          const result = (eye === 'OS' ? patient.leftEye : patient.rightEye).result;
          const detected = Object.entries(result?.lesions?.lesions || {}).filter(([, output]) => output.detected).map(([code]) => CLASS_NAMES[code] || code);
          return <div key={eye}><h3 className="font-bold mb-1">{eye === 'OS' ? 'Left eye (OS)' : 'Right eye (OD)'}</h3>
            <p>DR grade: {result?.grading?.predicted_grade ?? 'Unavailable'}</p><p className="text-on-surface-variant">Lesions: {result?.lesions ? detected.join(', ') || 'No retained regions' : 'Not assessed'}</p></div>;
        })}
      </div>
      <p className="mt-5 pt-4 border-t border-outline-variant font-bold text-primary">{comparison}</p>
      <p className="mt-1 text-xs text-on-surface-variant">This compares model outputs only. No progression, treatment, or management conclusion is inferred.</p>
      <button onClick={() => onNavigate('report')} className="mt-4 text-sm font-bold text-primary underline underline-offset-2">Open Report</button>
    </section>
  </div>;
}
