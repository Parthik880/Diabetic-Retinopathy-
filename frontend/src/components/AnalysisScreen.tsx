import { AnalysisVisualization, VisualizationControls, VIEW_LABELS, INITIAL_SETTINGS, type AnalysisView } from './AnalysisVisualization';
import { projectPatient } from '../api';
import { RegionCounts } from './RegionCounts';
import { selectRegions, topKLabel } from '../regionSelection';
import { useEffect, useState } from 'react';
import { PatientRecord, AnomalyItem, TabType } from '../types';

interface AnalysisScreenProps {
  patient: PatientRecord;
  onUpdatePatient: (updated: PatientRecord) => void;
  onNavigate: (tab: TabType) => void;
}

export function AnalysisScreen({
  patient: sourcePatient,
  onUpdatePatient,
  onNavigate,
}: AnalysisScreenProps) {
  const [view, setView] = useState<AnalysisView>('grade');
  const [settings, setSettings] = useState(INITIAL_SETTINGS);
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null);
  const activeEye = sourcePatient.activeEye;
  const [confirmationToast, setConfirmationToast] = useState<string | null>(null);

  const patient = projectPatient(sourcePatient, activeEye);
  const currentScan = activeEye === 'OS' ? patient.leftEye : patient.rightEye;
  const shownRegions = settings.rawRegions ? projectPatient(sourcePatient, activeEye, true).lesions : selectRegions(patient.lesions, settings.topK, settings.regionClass);
  const selectionLabel = settings.rawRegions ? 'Raw model output' : `${topKLabel(settings.topK)} · ${settings.regionClass === 'all' ? 'all classes' : settings.regionClass}`;

  useEffect(() => { setSelectedAnomalyId(null); setConfirmationToast(null); }, [activeEye, currentScan.result?.run_id]);

  const handleConfirmDiagnosis = () => {
    onUpdatePatient({
      ...patient,
      [activeEye === 'OS' ? 'leftEye' : 'rightEye']: { ...currentScan, review: { confirmed: true, flagged: false } },
    });
    setConfirmationToast('Diagnosis confirmed by clinician. Record updated.');
    setTimeout(() => setConfirmationToast(null), 3500);
  };

  const handleFlagForReview = () => {
    onUpdatePatient({
      ...patient,
      [activeEye === 'OS' ? 'leftEye' : 'rightEye']: { ...currentScan, review: { confirmed: false, flagged: true } },
    });
    setConfirmationToast('Scan flagged for senior retina specialist review.');
    setTimeout(() => setConfirmationToast(null), 3500);
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 md:px-6 py-6 pb-28 md:pb-12">
      {/* Toast Notification */}
      {confirmationToast && (
        <div className="fixed top-20 right-4 z-50 bg-primary text-on-primary px-4 py-3 rounded-lg shadow-xl border border-primary-fixed flex items-center gap-3 animate-fade-in">
          <span className="material-symbols-outlined text-xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            check_circle
          </span>
          <span className="font-label-lg text-sm">{confirmationToast}</span>
        </div>
      )}

      {/* Screen Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b-2 border-outline-variant pb-6 mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => onNavigate('capture')}
            className="p-1.5 rounded-full hover:bg-surface-container-low transition-colors text-on-surface"
            title="Back to Capture"
          >
            <span className="material-symbols-outlined text-2xl">arrow_back</span>
          </button>
          <div>
            <h1 className="font-headline-md text-2xl md:text-3xl font-bold text-on-surface">
              Analysis Results
            </h1>
            <p className="text-sm text-on-surface-variant">
              Patient ID: #{patient.patientIdNumber} • {patient.name} • {activeEye === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)'}
            </p>
          </div>
        </div>

        {/* View Controls: Eye Switcher + Coordinate Grid Toggle */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Eye Switcher */}
          <div className="inline-flex rounded-lg border border-outline-variant p-1 bg-surface-container-low">
            <button
              onClick={() => { setSelectedAnomalyId(null); onUpdatePatient({ ...sourcePatient, activeEye: 'OS' }); }}
              className={`px-3 py-1 text-xs md:text-sm font-label-lg rounded ${
                activeEye === 'OS'
                  ? 'bg-primary text-on-primary font-bold shadow-xs'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              OS (Left)
            </button>
            <button
              onClick={() => { setSelectedAnomalyId(null); onUpdatePatient({ ...sourcePatient, activeEye: 'OD' }); }}
              className={`px-3 py-1 text-xs md:text-sm font-label-lg rounded ${
                activeEye === 'OD'
                  ? 'bg-primary text-on-primary font-bold shadow-xs'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              OD (Right)
            </button>
          </div>


        </div>
      </div>

      <div className="mb-5 p-4 rounded-lg border border-outline-variant text-sm" data-testid="model-result">
        <strong>IQA: {currentScan.result?.quality?.quality || 'Not assessed'}</strong>
        {currentScan.result?.quality && <span> · Class confidence {(currentScan.result.quality.confidence * 100).toFixed(1)}%</span>}
        {currentScan.result && <span> · State {currentScan.result.state}</span>}
        {currentScan.result?.warnings.map(warning => <p key={warning}>{warning}</p>)}
        {currentScan.result && <p>Inference run: {currentScan.result.run_id}</p>}
      </div>
      {currentScan.result?.state === 'RECAPTURE_REQUIRED' && (
        <section role="alert" className="mb-6 rounded-xl border-2 border-secondary bg-secondary/10 p-6">
          <h2 className="font-headline-md text-xl font-bold text-on-surface">Recapture required</h2>
          <p className="mt-2 max-w-2xl text-sm text-on-surface-variant">The image-quality model rejected this scan. Restoration, grading, and lesion analysis were intentionally skipped.</p>
          <button onClick={() => onNavigate('capture')} className="mt-4 rounded-lg bg-primary px-4 py-2 font-bold text-on-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">Return to capture</button>
        </section>
      )}
      <div role="tablist" aria-label="Analysis views" className="grid grid-cols-2 md:grid-cols-4 gap-1 p-1 mb-6 rounded-lg border border-outline-variant bg-surface-container-low">
        {(Object.keys(VIEW_LABELS) as AnalysisView[]).map((key, index, keys) => <button key={key} id={`analysis-tab-${key}`} role="tab"
          aria-selected={view === key} aria-controls="analysis-visual-panel" tabIndex={view === key ? 0 : -1}
          onClick={() => setView(key)} onKeyDown={e => {
            const next = e.key === 'ArrowRight' ? keys[(index + 1) % keys.length] : e.key === 'ArrowLeft' ? keys[(index + keys.length - 1) % keys.length]
              : e.key === 'Home' ? keys[0] : e.key === 'End' ? keys[keys.length - 1] : null;
            if (next) { e.preventDefault(); setView(next); document.getElementById(`analysis-tab-${next}`)?.focus(); }
          }}
          className={`px-3 py-3 rounded-md text-sm font-bold transition-colors focus-visible:outline-2 focus-visible:outline-primary focus-visible:outline-offset-2 ${view === key ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:bg-surface-container-high'}`}>
          {VIEW_LABELS[key]}
        </button>)}
      </div>
      {/* Main Analysis Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        <div className="lg:col-span-7 flex flex-col gap-4 min-w-0" role="tabpanel" id="analysis-visual-panel" aria-labelledby={`analysis-tab-${view}`}>
          <VisualizationControls view={view} settings={settings} onChange={setSettings}
            availableClasses={currentScan.result?.lesions?.channel_order || Object.keys(currentScan.result?.lesions?.lesions || {})} />
          {view === 'detection' && <RegionCounts result={currentScan.result} displayed={shownRegions.length} selection={selectionLabel} />}
          <AnalysisVisualization scan={currentScan} view={view} settings={settings} lesions={shownRegions}
            selectedId={selectedAnomalyId} onSelect={setSelectedAnomalyId} />
        </div>

        {/* Right: Diagnostic Summary Card (5 cols on large screens) */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {/* Diagnostic Summary Panel (Matching HTML #1 / Image 1.jpeg) */}
          <div className="bg-surface-container-lowest rounded-xl border-2 border-outline p-6 flex flex-col gap-6 shadow-xs">
            {/* Header / Primary Diagnosis */}
            <div className="border-b-2 border-outline pb-4">
              <div className="inline-flex items-center gap-2 text-on-surface mb-1.5">
                <span className="material-symbols-outlined text-base text-primary" style={{ fontVariationSettings: "'FILL' 1" }}>
                  visibility
                </span>
                <span className="font-label-lg text-xs md:text-sm font-bold tracking-wide uppercase text-on-surface-variant">
                  Macula-Centered Fundus Photo
                </span>
              </div>
              <h2 className="font-headline-md text-2xl md:text-3xl font-bold text-secondary">
                {patient.diagnosisName}
              </h2>
              <span className="text-xs text-on-surface-variant font-medium mt-1 block">
                {patient.retinalGradeLabel}
              </span>
            </div>

            {/* AI Confidence Meter */}
            <div className="flex flex-col gap-2">
              <div className="flex justify-between items-baseline">
                <span className="font-body-md text-sm md:text-base font-medium text-on-surface">
                  Grade Class Confidence
                </span>
                <span className="font-headline-md text-xl md:text-2xl font-bold text-primary">
                  {patient.overallConfidence == null ? 'Unavailable' : `${patient.overallConfidence}%`}
                </span>
              </div>
              <div className="w-full bg-surface-container-highest rounded-full h-4 overflow-hidden border border-outline">
                <div
                  className="bg-primary h-full rounded-full transition-all duration-500"
                  style={{ width: `${patient.overallConfidence == null ? 'Unavailable' : `${patient.overallConfidence}%`}` }}
                />
              </div>
            </div>

            {/* Detected Lesion Pills */}
            <div className="flex flex-col gap-3">
              <h3 className="font-headline-md text-base md:text-lg font-bold text-on-surface">
                Predicted Region Types
              </h3>
              <div className="flex flex-wrap gap-2">
                {Array.from(new Set(patient.lesions.map(l => l.name))).map(name =>
                  <div key={name} className="bg-surface px-3 py-1.5 rounded-full border border-outline text-sm">{name}</div>)}
                {!patient.lesions.length && <span>{currentScan.result?.lesions ? 'No regions retained for display' : 'Lesions not assessed'}</span>}
              </div>
            </div>

            {/* Confirmation / Review Action Buttons */}
            <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-outline-variant">
              <button
                disabled={!currentScan.result?.grading} onClick={handleConfirmDiagnosis}
                className={`flex-1 font-label-lg text-sm h-12 rounded-lg flex items-center justify-center gap-2 transition-all ${
                  patient.isConfirmed
                    ? 'bg-status-success text-white ring-2 ring-status-success'
                    : 'bg-primary text-on-primary hover:bg-primary-fixed hover:text-on-primary-fixed'
                }`}
              >
                <span className="material-symbols-outlined text-lg" style={{ fontVariationSettings: "'FILL' 1" }}>
                  edit_document
                </span>
                {patient.isConfirmed ? 'Diagnosis Confirmed ✓' : 'Confirm Diagnosis'}
              </button>

              <button
                onClick={handleFlagForReview}
                className={`flex-1 font-label-lg text-sm h-12 rounded-lg flex items-center justify-center gap-2 transition-all ${
                  patient.isFlagged
                    ? 'bg-error text-white ring-2 ring-error'
                    : 'bg-transparent border-2 border-primary text-primary hover:bg-surface-variant'
                }`}
              >
                <span className="material-symbols-outlined text-lg">flag</span>
                {patient.isFlagged ? 'Flagged for Senior Review' : 'Flag for Review'}
              </button>
            </div>

            <button
              onClick={() => setView('annotation')}
              className="w-full text-center text-xs text-primary font-bold hover:underline mt-1"
            >
              View Lesion Masks
            </button>
            {/* Quick Navigation link to Compare */}
            <button
              onClick={() => onNavigate('compare')}
              className="w-full text-center text-xs text-primary font-bold hover:underline flex items-center justify-center gap-1 mt-1"
            >
              <span>Compare OS and OD Side-by-Side</span>
              <span className="material-symbols-outlined text-sm">arrow_forward</span>
            </button>
          </div>
        </div>
      </div>

      {/* Detected Anomalies Detailed List (Matching HTML #3 / Image 5.jpeg) */}
      <section className="mt-10">
        <h2 className="font-headline-md text-xl md:text-2xl font-bold text-primary mb-6 flex items-center gap-2">
          <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
            manage_search
          </span>
          {settings.rawRegions ? `Raw Model Output (${shownRegions.length})` : 'Predicted Lesion Regions'}
        </h2>
        <div className="mb-6"><RegionCounts result={currentScan.result} displayed={shownRegions.length} selection={selectionLabel} /></div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
          {shownRegions.map((lesion) => {
            const isSelected = selectedAnomalyId === lesion.id;
            return (
              <div
                key={lesion.id}
                onClick={() => { setSelectedAnomalyId(isSelected ? null : lesion.id); setView('detection'); }}
                className={`bg-surface-container-lowest rounded-lg border flex flex-col relative overflow-hidden transition-all cursor-pointer shadow-xs p-5 gap-3 ${
                  isSelected
                    ? 'border-2 border-primary ring-2 ring-primary/30 bg-surface-container-low'
                    : 'border-outline-variant hover:border-primary'
                }`}
              >
                {/* Critical / Review Status Badge */}
                <div className="absolute top-3 right-3">
                  {lesion.severity === 'Critical' ? (
                    <div className="bg-error-container border border-error text-error px-2 py-0.5 rounded text-[10px] font-label-lg flex items-center gap-1 font-bold">
                      <span className="material-symbols-outlined text-[12px]">warning</span> Critical
                    </div>
                  ) : (
                    <div className="bg-secondary-container border border-secondary text-on-secondary-container px-2 py-0.5 rounded text-[10px] font-label-lg flex items-center gap-1 font-bold">
                      <span className="material-symbols-outlined text-[12px]">info</span> {lesion.severity}
                    </div>
                  )}
                </div>

                {/* Title & Icon */}
                <div className="flex items-center gap-2.5 pr-16">
                  <span
                    className="material-symbols-outlined text-xl"
                    style={{ color: lesion.color }}
                  >
                    {lesion.iconName}
                  </span>
                  <h3 className="font-headline-md text-base md:text-lg font-bold text-on-surface">
                    {lesion.name}
                  </h3>
                </div>

                {/* Precise Bounding Box Coordinates */}
                <div className="font-body-md text-on-surface-variant text-xs">
                  Coordinates:{' '}
                  <span className="text-on-surface font-mono bg-surface-container px-1.5 py-0.5 rounded border border-outline-variant">
                    [X: {lesion.coordinates.x}, Y: {lesion.coordinates.y}, W: {lesion.coordinates.w}, H: {lesion.coordinates.h}]
                  </span>
                </div>

                {/* Description if available */}
                {lesion.description && (
                  <p className="text-xs text-on-surface-variant line-clamp-2">
                    {lesion.description}
                  </p>
                )}

                {/* Confidence Bar */}
                <div className="mt-auto pt-2">
                  <div className="flex justify-between font-label-lg text-xs mb-1 text-on-surface">
                    <span>Mean pixel probability</span>
                    <span className="text-primary font-bold">{lesion.confidence}%</span>
                  </div>
                  <div className="w-full bg-surface-variant rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-primary h-2 rounded-full transition-all duration-500"
                      style={{ width: `${lesion.confidence}%` }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
