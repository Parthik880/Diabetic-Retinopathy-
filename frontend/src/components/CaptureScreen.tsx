import { useState } from 'react';
import { PatientRecord, TabType } from '../types';
import { ACTIVE_ANALYSIS_STATES, PIPELINE_STATE_LABELS } from '../api';
import type { AnalysisProgress } from '../App';

interface CaptureScreenProps {
  onAnalyze: () => Promise<void>;
  patient: PatientRecord;
  onUpdatePatient: (updated: PatientRecord) => void;
  onNavigate: (tab: TabType) => void;
  onOpenUploadModal: (eye: 'OS' | 'OD') => void;
  onOpenAddPatient?: () => void;
  analysisProgress: AnalysisProgress | null;
}

export function CaptureScreen({
  patient,
  onAnalyze,
  onUpdatePatient,
  onNavigate,
  onOpenUploadModal,
  onOpenAddPatient,
  analysisProgress,
}: CaptureScreenProps) {
  const [error, setError] = useState<string | null>(null);
  const parsedStudyDate = Date.parse(patient.studyDate);
  const studyDate = Number.isNaN(parsedStudyDate) ? patient.studyDate : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(parsedStudyDate));
  const currentScan = patient.activeEye === 'OS' ? patient.leftEye : patient.rightEye;
  const scans = [patient.leftEye, patient.rightEye];
  const isAnalyzing = scans.some(scan => Boolean(scan.analysisRequestId && ACTIVE_ANALYSIS_STATES.has(scan.analysisState)));
  const currentProgressScan = analysisProgress?.currentEye === 'OD' ? patient.rightEye : patient.leftEye;
  const completedEyes = scans.filter(scan => scan.result?.state === 'COMPLETE');
  const handleStartAnalysis = async () => {
    setError(null);
    try { await onAnalyze(); }
    catch (error) { setError(error instanceof Error ? error.message : 'Inference failed.'); }
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-4 md:px-6 py-6 pb-28 md:pb-12">
      {/* Patient Intake Header Details */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b-2 border-outline-variant pb-6 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-headline-md text-2xl md:text-3xl font-bold text-on-surface">
              Patient Intake & Image Capture
            </h1>
            <span className="bg-primary/10 border border-primary text-primary px-2.5 py-0.5 rounded text-xs font-bold">
              Active Session
            </span>
          </div>
          <p className="text-sm md:text-base text-on-surface-variant mt-1">
            Patient: <strong className="text-on-surface">{patient.name}</strong> • Age: {patient.age} • MRN: #{patient.patientIdNumber} • HbA1c: {patient.hba1c}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          <div className="text-xs text-on-surface-variant bg-surface-container-low px-3 py-2 rounded-lg border border-outline-variant">
            Study Date: <span className="font-semibold text-on-surface">{studyDate}</span>
          </div>
          {onOpenAddPatient && (
            <button
              onClick={onOpenAddPatient}
              className="flex items-center gap-1.5 px-3 py-2 bg-primary text-on-primary rounded-lg font-bold text-xs hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors shadow-2xs"
            >
              <span className="material-symbols-outlined text-base">person_add</span>
              <span>New Patient</span>
            </button>
          )}
        </div>
      </div>

      {(error || patient.leftEye.analysisError || patient.rightEye.analysisError) && <div role="alert" className="p-4 mb-4 border border-error text-error rounded-lg">
        <strong>One eye could not be analyzed.</strong> {error || patient.leftEye.analysisError || patient.rightEye.analysisError} Replace that image or retry; the other eye remains available.
      </div>}
      <label className="block mb-4 text-sm">View eye: <select aria-label="View eye" value={patient.activeEye}
        onChange={e => onUpdatePatient({ ...patient, activeEye: e.target.value as 'OS' | 'OD' })}>
        <option value="OS">Left (OS)</option><option value="OD">Right (OD)</option>
      </select></label>

      {analysisProgress && currentProgressScan && (
        <section className="mb-6 rounded-xl bg-surface-container-low p-5 ring-1 ring-outline-variant" aria-labelledby="analysis-progress-title">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <div><h2 id="analysis-progress-title" className="font-headline text-lg font-extrabold">Analyzing patient retinal images</h2><p className="text-sm text-on-surface-variant">Eye {analysisProgress.currentIndex} of {analysisProgress.total} · {analysisProgress.currentEye === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)'}</p></div>
            <span role="status" aria-live="polite" className="font-bold text-primary">{PIPELINE_STATE_LABELS[currentProgressScan.analysisState]}</span>
          </div>
          <ol className="mt-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
            <li className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-primary"><span className="material-symbols-outlined text-lg" aria-hidden="true">check_circle</span>Image loaded</li>
            {[
              ['IQA', 'Image quality'],
              ['RESTORING', 'Restoration if needed'],
              ['GRADING', 'DR grading'],
              ['LESION_INFERENCE', 'GPU lesion inference'],
              ['LESION_MASK_PROCESSING', 'Mask processing'],
              ['LESION_REGION_EXTRACTION', 'Region extraction'],
              ['LESION_RESULTS_SAVING', 'Save lesion results'],
              ['PREPARING_RESULTS', 'Results'],
            ].map(([key, label]) => {
              const order = ['WAITING','IQA','IQA_GOOD','IQA_USABLE','IQA_REJECTED','RESTORING','RESTORATION_COMPLETE','GRADING','LESION_ANALYSIS','LESION_INFERENCE','LESION_MASK_PROCESSING','LESION_REGION_EXTRACTION','LESION_RESULTS_SAVING','PREPARING_RESULTS','COMPLETE'];
              const target = order.indexOf(key);
              const current = order.indexOf(currentProgressScan.analysisState);
              const done = current > target || currentProgressScan.analysisState === 'COMPLETE';
              const active = current === target || (key === 'IQA' && currentProgressScan.analysisState.startsWith('IQA_')) || (key === 'RESTORING' && currentProgressScan.analysisState === 'RESTORATION_COMPLETE');
              return <li key={key} className={`flex items-center gap-2 rounded-lg px-3 py-2 ${active ? 'bg-primary text-on-primary' : done ? 'bg-white text-primary' : 'text-on-surface-variant'}`}><span className="material-symbols-outlined text-lg" aria-hidden="true">{done ? 'check_circle' : active ? 'progress_activity' : 'radio_button_unchecked'}</span>{label}</li>;
            })}
          </ol>
        </section>
      )}
      {/* Main Dual Eye Intake Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8">
        {/* Left Eye (OS) Card */}
        <div className="bg-surface-container-lowest rounded-xl flex flex-col relative border-2 border-outline-variant overflow-hidden group hover:border-outline transition-colors shadow-xs">
          {/* Card Header */}
          <div className="p-4 md:p-6 border-b-2 border-outline-variant bg-surface-container-low flex justify-between items-center">
            <div>
              <h2 className="font-headline-md text-xl md:text-2xl font-bold text-on-surface">
                Left Eye (OS)
              </h2>
              <span className="text-xs text-on-surface-variant">Oculus Sinister</span>
            </div>
            <div className="flex items-center gap-2 bg-secondary/10 border-2 border-secondary rounded-full px-3 py-1">
              <span className="material-symbols-outlined text-secondary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                warning
              </span>
              <span className="font-label-lg text-xs md:text-sm font-bold text-secondary">
                {patient.leftEye.statusText}
              </span>
            </div>
          </div>

          {/* Card Body / Preview */}
          <div className="flex-1 flex flex-col items-center justify-center p-6 md:p-10 relative min-h-[300px] md:min-h-[380px] bg-surface-container-lowest">
            {patient.leftEye.imageUrl ? (
              <div className="w-full h-full flex flex-col items-center justify-center relative group">
                <div className="relative w-full aspect-square max-h-[320px] bg-black rounded-lg overflow-hidden border-2 border-outline flex items-center justify-center">
                  <img
                    src={patient.leftEye.imageUrl}
                    alt="Left Eye (OS) Fundus Scan"
                    className="w-full h-full object-cover"
                    crossOrigin="anonymous"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-3 text-white p-4">
                    <button
                      onClick={() => onOpenUploadModal('OS')}
                      className="px-4 py-2 bg-primary text-on-primary rounded font-label-lg text-sm flex items-center gap-2 hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors"
                    >
                      <span className="material-symbols-outlined text-base">photo_camera</span>
                      Retake / Replace Image
                    </button>
                    <button
                      onClick={() => onNavigate('analysis')}
                      className="px-4 py-2 bg-white/20 backdrop-blur-sm text-white rounded font-label-lg text-sm flex items-center gap-2 hover:bg-white/30 transition-colors"
                    >
                      <span className="material-symbols-outlined text-base">zoom_in</span>
                      View In Analysis
                    </button>
                  </div>
                </div>

                <div className="w-full mt-3 flex justify-between items-center text-xs text-on-surface-variant px-1">
                  <span>IQA class confidence: <strong className="text-primary">{patient.leftEye.imageQualityScore == null ? 'Not assessed' : `${patient.leftEye.imageQualityScore}%`}</strong></span>
                  <span>{patient.leftEye.focusMetric}</span>
                </div>
              </div>
            ) : (
              <button
                onClick={() => onOpenUploadModal('OS')}
                className="w-full h-64 md:h-80 border-2 border-dashed border-outline hover:border-primary rounded-lg flex flex-col items-center justify-center gap-4 text-on-surface-variant hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary bg-surface-container-lowest hover:bg-surface-container-low"
              >
                <span className="material-symbols-outlined text-6xl text-on-surface group-hover:text-primary transition-colors">
                  photo_camera
                </span>
                <div className="text-center">
                  <span className="font-headline-md text-base md:text-lg font-bold text-on-surface block">
                    Tap to Capture Image
                  </span>
                  <span className="text-xs text-on-surface-variant mt-1 block">
                    Supports 45° - 50° fundus camera or digital file import
                  </span>
                </div>
              </button>
            )}
          </div>
        </div>

        {/* Right Eye (OD) Card */}
        <div className="bg-surface-container-lowest rounded-xl flex flex-col relative border-2 border-outline-variant overflow-hidden group hover:border-outline transition-colors shadow-xs">
          {/* Card Header */}
          <div className="p-4 md:p-6 border-b-2 border-outline-variant bg-surface-container-low flex justify-between items-center">
            <div>
              <h2 className="font-headline-md text-xl md:text-2xl font-bold text-on-surface">
                Right Eye (OD)
              </h2>
              <span className="text-xs text-on-surface-variant">Oculus Dexter</span>
            </div>
            <div className="flex items-center gap-2 bg-primary/10 border-2 border-primary rounded-full px-3 py-1">
              <span className="material-symbols-outlined text-primary text-sm" style={{ fontVariationSettings: "'FILL' 1" }}>
                check_circle
              </span>
              <span className="font-label-lg text-xs md:text-sm font-bold text-primary">
                {patient.rightEye.statusText}
              </span>
            </div>
          </div>

          {/* Card Body */}
          <div className="flex-1 flex flex-col items-center justify-center p-6 md:p-10 relative min-h-[300px] md:min-h-[380px] bg-surface-container-lowest">
            {patient.rightEye.imageUrl ? <div className="w-full h-full flex flex-col items-center justify-center relative group">
              <div className="relative w-full aspect-square max-h-[320px] bg-black rounded-lg overflow-hidden border-2 border-primary flex items-center justify-center">
                <img
                  src={patient.rightEye.imageUrl}
                  alt="Right Eye (OD) Fundus Scan"
                  className="w-full h-full object-cover"
                  crossOrigin="anonymous"
                />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-3 text-white p-4">
                  <button
                    onClick={() => onOpenUploadModal('OD')}
                    className="px-4 py-2 bg-primary text-on-primary rounded font-label-lg text-sm flex items-center gap-2 hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors"
                  >
                    <span className="material-symbols-outlined text-base">photo_camera</span>
                    Retake Image
                  </button>
                  <button
                    onClick={() => onNavigate('compare')}
                    className="px-4 py-2 bg-white/20 backdrop-blur-sm text-white rounded font-label-lg text-sm flex items-center gap-2 hover:bg-white/30 transition-colors"
                  >
                    <span className="material-symbols-outlined text-base">visibility</span>
                    Compare Scan
                  </button>
                </div>
              </div>

              <div className="w-full mt-3 flex justify-between items-center text-xs text-on-surface-variant px-1">
                <span>IQA class confidence: <strong className="text-primary">{patient.rightEye.imageQualityScore == null ? 'Not assessed' : `${patient.rightEye.imageQualityScore}%`}</strong></span>
                <span>{patient.rightEye.illuminationIndex}</span>
              </div>
            </div> : <button
              onClick={() => onOpenUploadModal('OD')}
              className="w-full h-64 md:h-80 border-2 border-dashed border-outline hover:border-primary rounded-lg flex flex-col items-center justify-center gap-4 text-on-surface-variant hover:text-primary transition-all focus:outline-none focus:ring-2 focus:ring-primary bg-surface-container-lowest hover:bg-surface-container-low"
            >
              <span className="material-symbols-outlined text-6xl text-on-surface">photo_camera</span>
              <span className="font-headline-md text-base md:text-lg font-bold text-on-surface">Tap to Capture Image</span>
              <span className="text-xs text-on-surface-variant">Right Eye (OD) fundus image</span>
            </button>}
          </div>
        </div>
      </div>

      {!isAnalyzing && completedEyes.length > 0 && (
        <section className="mt-6 flex flex-col justify-between gap-4 rounded-xl bg-primary/10 p-5 ring-1 ring-primary/20 sm:flex-row sm:items-center">
          <div><h2 className="font-headline text-lg font-extrabold text-on-surface">Retinal Analysis Complete</h2><p className="mt-1 text-sm text-on-surface-variant">{patient.leftEye.result?.state === 'COMPLETE' && '✓ Left Eye (OS)  '}{patient.rightEye.result?.state === 'COMPLETE' && '✓ Right Eye (OD)'}</p></div>
          <button onClick={() => onNavigate('report')} className="min-h-11 rounded-lg bg-primary px-5 text-sm font-extrabold text-on-primary">View Report</button>
        </section>
      )}

      {/* Clinical Image Acquisition Checklist */}
      <div className="mt-8 bg-surface-container-low rounded-xl p-6 border border-outline-variant">
        <h3 className="font-headline-md text-base md:text-lg font-bold text-on-surface mb-3 flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-xl">fact_check</span>
          Standard Retinal Imaging Protocol
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs md:text-sm text-on-surface-variant">
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-primary text-base mt-0.5">check</span>
            <span>Ensure 45° field centered on the fovea / macula</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-primary text-base mt-0.5">check</span>
            <span>Minimal pupil diameter ≥ 3.5mm without excessive glare</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="material-symbols-outlined text-primary text-base mt-0.5">check</span>
            <span>Automatic focus lock verified (Focus Metric &gt; 0.90)</span>
          </div>
        </div>
      </div>

      {/* Primary Action Button (FAB style) */}
      <div className="fixed bottom-20 md:bottom-8 right-4 md:right-8 z-30">
        <button
          onClick={handleStartAnalysis}
          disabled={isAnalyzing}
          className="h-14 px-6 md:px-8 bg-primary hover:bg-primary-fixed-dim active:bg-primary text-on-primary rounded-xl font-label-lg text-base md:text-lg flex items-center gap-3 shadow-xl transition-all hover:scale-105 active:scale-95 disabled:opacity-75 disabled:cursor-not-allowed"
        >
          {isAnalyzing ? (
            <>
              <span className="material-symbols-outlined text-2xl animate-spin">progress_activity</span>
              <span>{analysisProgress ? `${analysisProgress.currentEye === 'OS' ? 'Left' : 'Right'} eye · ${PIPELINE_STATE_LABELS[currentProgressScan.analysisState]}` : 'Analyzing retinal images'}</span>
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                analytics
              </span>
              <span>Analyze Retinal Images</span>
            </>
          )}
        </button>
      </div>

    </div>
  );
}
