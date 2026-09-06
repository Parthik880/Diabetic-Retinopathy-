import { analyzeImage, resetPatient, resetScan, projectPatient, PIPELINE_STATE_LABELS, persistHistory, saveReport } from './api';
import { useRef, useState } from 'react';
import { TabType, PatientRecord, HistoryRecord } from './types';
import { SAMPLE_PATIENTS } from './data/samplePatients';
import { TopAppBar } from './components/TopAppBar';
import { BottomNavBar } from './components/BottomNavBar';
import { CaptureScreen } from './components/CaptureScreen';
import { AnalysisScreen } from './components/AnalysisScreen';
import { CompareScreen } from './components/CompareScreen';
import { ReportScreen } from './components/ReportScreen';
import { SpecialistReferralModal } from './components/SpecialistReferralModal';
import { ImageUploadModal } from './components/ImageUploadModal';
import { AddPatientModal } from './components/AddPatientModal';
import { HistoryScreen } from './components/HistoryScreen';
import { eyesRequiringAnalysis } from './analysisWorkflow';
import { createNewSession, sessionHasData } from './sessionWorkflow';
import { NewSessionDialog } from './components/NewSessionDialog';

export interface AnalysisProgress {
  currentEye: 'OS' | 'OD';
  currentIndex: number;
  total: number;
}

function patientFromHistory(record: HistoryRecord, eye: 'OS' | 'OD'): PatientRecord {
  const makeScan = (side: 'OS' | 'OD') => {
    const stored = side === 'OS' ? record.left_eye : record.right_eye;
    return {
      eye: side, eyeLabel: side === 'OS' ? 'Left Eye (OS)' : 'Right Eye (OD)',
      status: stored.completed ? 'Good' as const : 'Needs Capture' as const,
      statusText: stored.completed ? 'Analysis complete' : stored.state === 'RECAPTURE_REQUIRED' ? 'Recapture required' : 'Not analyzed',
      analysisState: stored.state || 'WAITING', imageUrl: stored.original_path || '', heatmapUrl: stored.overlay_path || '',
      capturedAt: stored.captured_at || record.scan_datetime, imageQualityScore: stored.result_data?.quality ? stored.result_data.quality.confidence * 100 : null,
      illuminationIndex: 'Not measured', focusMetric: 'Not measured', result: stored.result_data || undefined,
    };
  };
  return projectPatient({
    id: record.patient.id, sessionId: record.session_id, sessionStartedAt: record.scan_datetime,
    patientIdNumber: record.patient_id, name: record.patient_name,
    age: record.patient.age, gender: record.patient.gender, dob: record.patient.dob,
    diabeticHistoryYears: record.patient.diabeticHistoryYears, hba1c: record.patient.hba1c,
    bloodPressure: record.patient.bloodPressure, studyDate: record.scan_datetime,
    leftEye: makeScan('OS'), rightEye: makeScan('OD'), activeEye: eye,
    diagnosisName: '', retinalGrade: null, retinalGradeLabel: '', overallConfidence: null, lesions: [],
    criticalFinding: { title: 'Model output only', description: '', urgency: 'Routine', actionNeeded: 'Clinician review' },
    clinicalNotes: '', isConfirmed: false, isFlagged: false,
  });
}

export default function App() {
  const smokeMode = new URLSearchParams(window.location.search).get('smoke') === '1';
  const initialPatients = smokeMode ? SAMPLE_PATIENTS.map(resetPatient) : [];
  const [activeTab, setActiveTab] = useState<TabType>('capture');
  const [patients, setPatients] = useState<PatientRecord[]>(initialPatients);
  const patientsRef = useRef<PatientRecord[]>(initialPatients);
  const [currentPatientId, setCurrentPatientId] = useState<string>(initialPatients[0]?.id || '');
  const [analysisProgress, setAnalysisProgress] = useState<AnalysisProgress | null>(null);

  // Modals
  const [isReferralModalOpen, setIsReferralModalOpen] = useState(false);
  const [uploadModalState, setUploadModalState] = useState<{ isOpen: boolean; eye: 'OS' | 'OD' }>({
    isOpen: false,
    eye: 'OS',
  });
  const [isAddPatientOpen, setIsAddPatientOpen] = useState(false);
  const [isNewSessionOpen, setIsNewSessionOpen] = useState(false);
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [newSessionError, setNewSessionError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const currentPatientSource = patients.find((p) => p.id === currentPatientId) || patients[0];
  const currentPatient = currentPatientSource ? projectPatient(currentPatientSource) : undefined;

  const replacePatients = (next: PatientRecord[]) => {
    patientsRef.current = next;
    setPatients(next);
  };

  const mutatePatient = (patientId: string, transform: (patient: PatientRecord) => PatientRecord) => {
    let updated: PatientRecord | undefined;
    const next = patientsRef.current.map(patient => {
      if (patient.id !== patientId) return patient;
      updated = transform(patient);
      return updated;
    });
    replacePatients(next);
    return updated;
  };

  const handleUpdatePatient = (updated: PatientRecord) => {
    mutatePatient(updated.id, () => updated);
  };

  const handleAddPatient = (inputPatient: PatientRecord) => {
    const newPatient = resetPatient(inputPatient);
    replacePatients([newPatient, ...patientsRef.current]);
    setCurrentPatientId(newPatient.id);
    setActiveTab('capture');
    setToastMessage(`Patient #${newPatient.patientIdNumber} (${newPatient.name}) registered successfully!`);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const startNewSession = async (saveCurrent: boolean) => {
    const snapshot = patientsRef.current.find(patient => patient.id === currentPatientId);
    if (!snapshot || isStartingSession) return;
    setIsStartingSession(true);
    setNewSessionError(null);
    try {
      if (saveCurrent) await persistHistory(snapshot);
      const fresh = createNewSession(snapshot);
      mutatePatient(snapshot.id, () => fresh);
      setAnalysisProgress(null);
      setActiveTab('capture');
      setIsNewSessionOpen(false);
      setToastMessage(`New scan session started for #${fresh.patientIdNumber} (${fresh.name}).`);
      setTimeout(() => setToastMessage(null), 4000);
    } catch (error) {
      setNewSessionError(error instanceof Error ? error.message : 'The current session could not be saved.');
      setIsNewSessionOpen(true);
    } finally {
      setIsStartingSession(false);
    }
  };

  const handleNewSessionRequest = () => {
    if (!currentPatient) return;
    if (sessionHasData(currentPatient)) {
      setNewSessionError(null);
      setIsNewSessionOpen(true);
    } else {
      void startNewSession(false);
    }
  };

  const handleImageSelected = (eye: 'OS' | 'OD', imageUrl: string) => {
    if (!currentPatient) return;
    const key = eye === 'OS' ? 'leftEye' : 'rightEye';
    handleUpdatePatient({ ...currentPatient, activeEye: eye, isConfirmed: false,
      [key]: resetScan({ ...currentPatient[key], imageUrl, capturedAt: new Date().toISOString() }) });
    setActiveTab('capture');
  };

  const analyzeEye = async (patientId: string, eye: 'OS' | 'OD', currentIndex: number, total: number) => {
    const key = eye === 'OS' ? 'leftEye' : 'rightEye';
    const patient = patientsRef.current.find(item => item.id === patientId);
    const imageUrl = patient?.[key].imageUrl;
    if (!patient || !imageUrl) return;
    const requestId = crypto.randomUUID();
    setAnalysisProgress({ currentEye: eye, currentIndex, total });
    console.info(`[RetinaGram][${patient.patientIdNumber}][${eye}] Analysis started`);
    mutatePatient(patientId, p => ({ ...p, [key]: {
      ...resetScan(p[key]), analysisState: 'WAITING', analysisRequestId: requestId,
      statusText: PIPELINE_STATE_LABELS.WAITING,
    }, isConfirmed: false }));
    try {
      const result = await analyzeImage(imageUrl, eye, (analysisState, jobId) => {
        console.info(`[RetinaGram][${patient.patientIdNumber}][${eye}] ${PIPELINE_STATE_LABELS[analysisState]}`);
        mutatePatient(patientId, p => p[key].imageUrl === imageUrl && p[key].analysisRequestId === requestId
          ? { ...p, [key]: { ...p[key], analysisState, analysisJobId: jobId, statusText: PIPELINE_STATE_LABELS[analysisState] } }
          : p);
      });
      const updated = mutatePatient(patientId, p => p[key].imageUrl === imageUrl && p[key].analysisRequestId === requestId
        ? { ...p, [key]: { ...p[key], result, analysisState: result.state,
            analysisRequestId: undefined, analysisJobId: result.run_id,
            analysisError: undefined, statusText: PIPELINE_STATE_LABELS[result.state],
            imageQualityScore: result.quality ? Math.round(result.quality.confidence * 1000) / 10 : null,
            heatmapUrl: result.lesions?.combined_overlay_path || '' } }
        : p);
      console.info(`[RetinaGram][${patient.patientIdNumber}][${eye}] ${PIPELINE_STATE_LABELS[result.state]}`);
      if (updated && (updated.leftEye.result?.state === 'COMPLETE' || updated.rightEye.result?.state === 'COMPLETE')) {
        try { await persistHistory(updated); }
        catch (historyError) { console.error('[RetinaGram] History persistence failed', historyError); }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Analysis failed. Check backend logs and retry.';
      mutatePatient(patientId, p => p[key].imageUrl === imageUrl && p[key].analysisRequestId === requestId
        ? { ...p, [key]: { ...p[key], analysisState: 'FAILED', analysisRequestId: undefined,
            analysisError: message, statusText: PIPELINE_STATE_LABELS.FAILED } }
        : p);
      console.error(`[RetinaGram][${patient.patientIdNumber}][${eye}] Analysis failed`, error);
    }
  };

  const handleAnalyze = async () => {
    if (!currentPatient) return;
    const eyes = eyesRequiringAnalysis(currentPatient);
    if (!eyes.length) throw new Error(currentPatient.leftEye.imageUrl || currentPatient.rightEye.imageUrl
      ? 'Every uploaded eye is already complete.' : 'Select at least one retinal image first.');
    for (let index = 0; index < eyes.length; index += 1) {
      await analyzeEye(currentPatient.id, eyes[index], index + 1, eyes.length);
    }
    setAnalysisProgress(null);
  };

  const openHistoryRecord = (record: HistoryRecord, eye: 'OS' | 'OD') => {
    const restored = patientFromHistory(record, eye);
    const exists = patientsRef.current.some(item => item.id === restored.id);
    replacePatients(exists ? patientsRef.current.map(item => item.id === restored.id ? restored : item) : [restored, ...patientsRef.current]);
    setCurrentPatientId(restored.id);
    setActiveTab('report');
  };

  const downloadHistoryRecord = async (record: HistoryRecord, eye: 'OS' | 'OD') => {
    if (!window.retinaDesktop) throw new Error('The native folder picker is available in the RetinaGram desktop app.');
    const destination = await window.retinaDesktop.chooseReportFolder();
    if (!destination) return null;
    const exported = await saveReport(patientFromHistory(record, eye), eye, destination);
    return exported.folder;
  };

  const handleReferralSuccess = (specialistName: string, urgency: 'STAT' | 'Urgent' | 'Routine') => {
    const updated = {
      ...currentPatient,
      referralStatus: {
        isReferred: true,
        specialistName,
        urgency,
        referredAt: new Date().toISOString(),
      },
    };
    handleUpdatePatient(updated);
  };

  return (
    <div className="min-h-screen bg-surface-container-lowest text-on-surface flex flex-col antialiased selection:bg-primary selection:text-on-primary">
      {/* Top Clinical Application Bar */}
      <TopAppBar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        patient={currentPatient}
        patients={patients}
        onSelectPatient={(p) => setCurrentPatientId(p.id)}
        onOpenAddPatient={() => setIsAddPatientOpen(true)}
        onStartNewSession={handleNewSessionRequest}
      />

      {/* Floating Notification Toast */}
      {toastMessage && (
        <div className="fixed top-18 right-4 z-50 bg-primary text-on-primary px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 text-xs md:text-sm font-bold animate-fade-in border border-primary-fixed">
          <span className="material-symbols-outlined text-base">check_circle</span>
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 pt-[72px]">
        <div role="status" className="max-w-7xl mx-auto px-6 py-2 text-sm text-on-surface-variant">Local offline inference · Patient scans and history stay on this PC.</div>
        {!currentPatient && activeTab !== 'history' && (
          <section className="mx-auto mt-16 max-w-2xl px-6 text-center">
            <span className="material-symbols-outlined text-6xl text-primary" aria-hidden="true">person_add</span>
            <h1 className="mt-4 font-headline text-3xl font-extrabold tracking-[-0.03em]">Begin a retinal screening session</h1>
            <p className="mx-auto mt-3 max-w-xl text-on-surface-variant">Register the patient, upload the available left and/or right fundus images, then run the eye-scoped analysis.</p>
            <button onClick={() => setIsAddPatientOpen(true)} className="mt-6 min-h-12 rounded-xl bg-primary px-6 font-extrabold text-on-primary shadow-[0_8px_24px_rgba(0,82,39,0.22)]">Register patient</button>
          </section>
        )}
        {activeTab === 'capture' && currentPatient && (
          <CaptureScreen
            onAnalyze={handleAnalyze}
            patient={currentPatient}
            analysisProgress={analysisProgress}
            onUpdatePatient={handleUpdatePatient}
            onNavigate={setActiveTab}
            onOpenUploadModal={(eye) => setUploadModalState({ isOpen: true, eye })}
            onOpenAddPatient={() => setIsAddPatientOpen(true)}
          />
        )}

        {activeTab === 'analysis' && currentPatient && (
          <AnalysisScreen
            key={currentPatient.id}
            patient={currentPatient}
            onUpdatePatient={handleUpdatePatient}
            onNavigate={setActiveTab}
          />
        )}

        {activeTab === 'compare' && currentPatient && (
          <CompareScreen
            key={currentPatient.id}
            onInspectEye={(eye) => { handleUpdatePatient({ ...currentPatient, activeEye: eye }); setActiveTab('analysis'); }}
            patient={currentPatient}
            onNavigate={setActiveTab}
            onOpenReferralModal={() => setIsReferralModalOpen(true)}
          />
        )}

        {activeTab === 'report' && currentPatient && (
          <ReportScreen
            key={currentPatient.id}
            patient={currentPatient}
            onUpdatePatient={handleUpdatePatient}
            onOpenReferralModal={() => setIsReferralModalOpen(true)}
          />
        )}
        {activeTab === 'history' && <HistoryScreen onOpenRecord={openHistoryRecord} onDownloadRecord={downloadHistoryRecord} />}
      </main>

      {/* Mobile Fixed Bottom Navigation */}
      <BottomNavBar activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Modals */}
      {isAddPatientOpen && (
        <AddPatientModal
          onClose={() => setIsAddPatientOpen(false)}
          onAddPatient={handleAddPatient}
        />
      )}
      {isReferralModalOpen && currentPatient && (
        <SpecialistReferralModal
          patient={currentPatient}
          onClose={() => setIsReferralModalOpen(false)}
          onReferralSuccess={handleReferralSuccess}
        />
      )}

      {isNewSessionOpen && (
        <NewSessionDialog
          saving={isStartingSession}
          error={newSessionError}
          onCancel={() => { if (!isStartingSession) { setIsNewSessionOpen(false); setNewSessionError(null); } }}
          onConfirm={() => void startNewSession(true)}
        />
      )}

      {uploadModalState.isOpen && (
        <ImageUploadModal
          eye={uploadModalState.eye}
          onClose={() => setUploadModalState({ isOpen: false, eye: 'OS' })}
          onImageSelected={handleImageSelected}
        />
      )}
    </div>
  );
}
