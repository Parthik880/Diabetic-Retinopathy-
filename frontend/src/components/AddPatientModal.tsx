import { useState, FormEvent, ChangeEvent } from 'react';
import { PatientRecord, AnomalyItem, EyeScanData } from '../types';

interface AddPatientModalProps {
  onClose: () => void;
  onAddPatient: (patient: PatientRecord) => void;
}

const DEFAULT_LESIONS: AnomalyItem[] = [
  {
    id: 'an-new-1',
    name: 'Microaneurysms',
    shortCode: 'MA',
    type: 'microaneurysm',
    coordinates: {
      x: 120,
      y: 450,
      w: 20,
      h: 20,
      topPct: 28,
      leftPct: 35,
      widthPct: 7,
      heightPct: 7,
    },
    confidence: 89,
    severity: 'Critical',
    color: '#ba1a1a',
    badgeBg: 'bg-error-container',
    badgeText: 'text-error',
    iconName: 'trip_origin',
    description: 'Focal dilation of retinal capillaries in temporal arcade.'
  },
  {
    id: 'an-new-2',
    name: 'Cotton Wool Spots',
    shortCode: 'CWS',
    type: 'cotton_wool_spot',
    coordinates: {
      x: 190,
      y: 320,
      w: 30,
      h: 25,
      topPct: 48,
      leftPct: 42,
      widthPct: 10,
      heightPct: 9,
    },
    confidence: 93,
    severity: 'Critical',
    color: '#ba1a1a',
    badgeBg: 'bg-error-container',
    badgeText: 'text-error',
    iconName: 'cloud',
    description: 'Nerve fiber layer infarcts indicating focal retinal ischemia.'
  },
  {
    id: 'an-new-3',
    name: 'Hemorrhages',
    shortCode: 'HEM',
    type: 'hemorrhage',
    coordinates: {
      x: 280,
      y: 210,
      w: 40,
      h: 30,
      topPct: 62,
      leftPct: 58,
      widthPct: 8,
      heightPct: 8,
    },
    confidence: 91,
    severity: 'Critical',
    color: '#ba1a1a',
    badgeBg: 'bg-error-container',
    badgeText: 'text-error',
    iconName: 'water_drop',
    description: 'Dot-blot intraretinal hemorrhage clusters.'
  }
];

export function AddPatientModal({ onClose, onAddPatient }: AddPatientModalProps) {
  const generatedId = `RH-${Math.floor(1000 + Math.random() * 9000)}`;
  
  const [formData, setFormData] = useState({
    name: '',
    patientIdNumber: generatedId,
    age: '54',
    gender: 'Female' as 'Female' | 'Male' | 'Other',
    dob: '1972-06-15',
    diabeticHistoryYears: '8',
    hba1c: '7.8%',
    bloodPressure: '132/84 mmHg',
    presetScanType: 'empty' as 'empty' | 'sample_npdr' | 'sample_normal',
    clinicalNotes: 'Routine annual diabetic retinopathy screening examination.'
  });

  const [customOsUrl, setCustomOsUrl] = useState<string>('');
  const [customOdUrl, setCustomOdUrl] = useState<string>('');

  const handleQuickFill = () => {
    const randomPatients = [
      { name: 'Robert Chen', age: '62', gender: 'Male' as const, dob: '1964-03-22', hba1c: '8.1%', bp: '140/88 mmHg', years: '14' },
      { name: 'Maria Santos', age: '49', gender: 'Female' as const, dob: '1977-11-09', hba1c: '7.4%', bp: '126/80 mmHg', years: '6' },
      { name: 'David K. Miller', age: '71', gender: 'Male' as const, dob: '1955-08-30', hba1c: '9.2%', bp: '148/92 mmHg', years: '20' },
      { name: 'Aisha Al-Mansoor', age: '53', gender: 'Female' as const, dob: '1973-01-14', hba1c: '7.9%', bp: '130/82 mmHg', years: '9' }
    ];
    const picked = randomPatients[Math.floor(Math.random() * randomPatients.length)];
    setFormData((prev) => ({
      ...prev,
      name: picked.name,
      age: picked.age,
      gender: picked.gender,
      dob: picked.dob,
      hba1c: picked.hba1c,
      bloodPressure: picked.bp,
      diabeticHistoryYears: picked.years
    }));
  };

  const handleCustomFileUpload = (e: ChangeEvent<HTMLInputElement>, eye: 'OS' | 'OD') => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        if (eye === 'OS') setCustomOsUrl(reader.result as string);
        else setCustomOdUrl(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    const timestamp = new Date();
    const formattedDate = `${timestamp.getFullYear()}-${String(timestamp.getMonth() + 1).padStart(2, '0')}-${String(
      timestamp.getDate()
    ).padStart(2, '0')} ${String(timestamp.getHours()).padStart(2, '0')}:${String(
      timestamp.getMinutes()
    ).padStart(2, '0')} EST`;

    const sampleModNpdrUrl =
      '/samples/retina-a.jpg';
    const sampleNormalUrl =
      '/samples/retina-b.jpg';
    const sampleHeatmap =
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCnaGVurj-kMh5s9oQj-rdaDnMDj7zZ1G708m4aLW6_asA0ZyqV3qTOfpyziFiG6wInaFvqv7ewNeEJ8-_AfHeSGTMzoH4irpV6p3Koqk_vLvepxMVn-ZrQem0cYyxKfbkI99JUzZCx7bHOVTpCQMo_6ZQFWUrZJaLiVd2FSO1z4yM66fHvt2NZYQfUot3aVtxsGa6mPSchHq1GgJSepRyoc7qGL-1qUn7zDUFwTsnYgYVIuHu5-GtTJw';

    let leftScan: EyeScanData = {
      eye: 'OS',
      analysisState: 'WAITING',
      eyeLabel: 'Left Eye (OS)',
      status: 'Moderate',
      statusText: 'Moderate - AI Ready',
      imageUrl: customOsUrl || sampleModNpdrUrl,
      heatmapUrl: sampleHeatmap,
      capturedAt: formattedDate,
      imageQualityScore: 97,
      illuminationIndex: 'Optimal (0.95)',
      focusMetric: 'Sharp Focus (1.04)'
    };

    let rightScan: EyeScanData = {
      eye: 'OD',
      analysisState: 'WAITING',
      eyeLabel: 'Right Eye (OD)',
      status: 'Good',
      statusText: 'Good',
      imageUrl: customOdUrl || sampleNormalUrl,
      heatmapUrl: sampleHeatmap,
      capturedAt: formattedDate,
      imageQualityScore: 98,
      illuminationIndex: 'Optimal (0.96)',
      focusMetric: 'Sharp Focus (1.05)'
    };

    let diagnosis = 'Moderate NPDR';
    let retinalGrade = 3;
    let gradeLabel = 'Grade 3: Moderate Nonproliferative Diabetic Retinopathy';
    let confidence = 92;
    let lesionsList = DEFAULT_LESIONS;

    if (formData.presetScanType === 'empty') {
      leftScan = {
        ...leftScan,
        status: 'Needs Capture',
        statusText: 'Pending Capture',
        imageUrl: customOsUrl || '',
        imageQualityScore: null,
        illuminationIndex: 'Pending',
        focusMetric: 'Pending'
      };
      rightScan = {
        ...rightScan,
        status: 'Needs Capture',
        statusText: 'Pending Capture',
        imageUrl: customOdUrl || '',
        imageQualityScore: null,
        illuminationIndex: 'Pending',
        focusMetric: 'Pending'
      };
      diagnosis = 'Pending Clinical Capture';
      retinalGrade = 0;
      gradeLabel = 'Grade 0: Scan Acquisition Required';
      confidence = 0;
      lesionsList = [];
    } else if (formData.presetScanType === 'sample_normal') {
      leftScan = {
        ...leftScan,
        status: 'Normal',
        statusText: 'Good / Clear',
        imageUrl: customOsUrl || sampleNormalUrl,
      };
      diagnosis = 'No Apparent Retinopathy';
      retinalGrade = 1;
      gradeLabel = 'Grade 1: No Apparent Diabetic Retinopathy (Normal)';
      confidence = 98;
      lesionsList = [];
    }

    const newPatient: PatientRecord = {
      id: `pt-${Date.now()}`,
      patientIdNumber: formData.patientIdNumber,
      name: formData.name.trim(),
      age: parseInt(formData.age, 10) || 50,
      gender: formData.gender,
      dob: formData.dob,
      diabeticHistoryYears: parseInt(formData.diabeticHistoryYears, 10) || 5,
      hba1c: formData.hba1c.includes('%') ? formData.hba1c : `${formData.hba1c}%`,
      bloodPressure: formData.bloodPressure,
      studyDate: formattedDate,
      activeEye: 'OS',
      diagnosisName: diagnosis,
      retinalGrade,
      retinalGradeLabel: gradeLabel,
      overallConfidence: confidence,
      leftEye: leftScan,
      rightEye: rightScan,
      lesions: lesionsList,
      criticalFinding: {
        title: retinalGrade >= 3 ? 'Paramacular Ischemia Risk' : 'No Critical Pathologies',
        description:
          retinalGrade >= 3
            ? 'Clusters of microaneurysms and cotton wool spots detected within 1.5 disc diameters of foveal center.'
            : 'Foveal avascular zone intact. No microaneurysms or ischemic lesions detected.',
        urgency: retinalGrade >= 3 ? 'Urgent' : 'Routine',
        actionNeeded:
          retinalGrade >= 3
            ? 'Macular OCT recommended within 3–4 weeks for DME evaluation.'
            : 'Standard annual screening cadence.'
      },
      clinicalNotes: formData.clinicalNotes,
      isConfirmed: false,
      isFlagged: false
    };

    onAddPatient(newPatient);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-3 md:p-4 overflow-y-auto">
      <div className="bg-surface-container-lowest rounded-2xl max-w-2xl w-full border-2 border-outline shadow-2xl overflow-hidden my-auto animate-scale-up">
        {/* Modal Header */}
        <div className="p-4 md:p-5 bg-surface-container-low border-b-2 border-outline-variant flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                person_add
              </span>
            </div>
            <div>
              <h3 className="font-headline-md text-lg md:text-xl font-bold text-on-surface">
                New Patient Registration
              </h3>
              <p className="text-xs text-on-surface-variant">
                Create electronic health record & initialize retinal scan screening study
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-full hover:bg-surface-container transition-colors text-on-surface-variant"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="p-5 md:p-6 space-y-5 max-h-[78vh] overflow-y-auto">
          {/* Quick Preload Toolbar */}
          <div className="flex items-center justify-between p-3 bg-surface-container-low rounded-xl border border-outline-variant">
            <span className="text-xs font-semibold text-on-surface-variant flex items-center gap-1.5">
              <span className="material-symbols-outlined text-base text-primary">magic_button</span>
              Fast Clinical Testing:
            </span>
            <button
              type="button"
              onClick={handleQuickFill}
              className="px-3 py-1 bg-surface-container-lowest hover:bg-surface-container border border-outline-variant text-primary text-xs font-bold rounded-lg transition-colors shadow-2xs"
            >
              Autofill Sample Patient
            </button>
          </div>

          {/* Section 1: Demographics & Identifiers */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-primary border-b border-outline-variant pb-1">
              1. Patient Demographics & ID
            </h4>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">
                  Full Name <span className="text-error">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Jonathan Mercer"
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">
                  Medical Record Number (MRN)
                </label>
                <input
                  type="text"
                  value={formData.patientIdNumber}
                  onChange={(e) => setFormData({ ...formData, patientIdNumber: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Age</label>
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={formData.age}
                  onChange={(e) => setFormData({ ...formData, age: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Gender</label>
                <select
                  value={formData.gender}
                  onChange={(e) => setFormData({ ...formData, gender: e.target.value as any })}
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="Female">Female</option>
                  <option value="Male">Male</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Date of Birth</label>
                <input
                  type="date"
                  value={formData.dob}
                  onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          {/* Section 2: Clinical Biomarkers */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-primary border-b border-outline-variant pb-1">
              2. Clinical Biomarkers & History
            </h4>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">
                  Diabetes Duration (Years)
                </label>
                <input
                  type="number"
                  min="0"
                  max="70"
                  value={formData.diabeticHistoryYears}
                  onChange={(e) => setFormData({ ...formData, diabeticHistoryYears: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">HbA1c Baseline</label>
                <input
                  type="text"
                  value={formData.hba1c}
                  onChange={(e) => setFormData({ ...formData, hba1c: e.target.value })}
                  placeholder="e.g., 8.2%"
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Blood Pressure</label>
                <input
                  type="text"
                  value={formData.bloodPressure}
                  onChange={(e) => setFormData({ ...formData, bloodPressure: e.target.value })}
                  placeholder="e.g., 135/85 mmHg"
                  className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>
          </div>

          {/* Section 3: Retinal Study Initialization */}
          <div className="space-y-3">
            <h4 className="text-xs font-bold uppercase tracking-wider text-primary border-b border-outline-variant pb-1">
              3. Study Initial Scans
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <label
                className={`p-3 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center text-center gap-1.5 ${
                  formData.presetScanType === 'sample_npdr'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-outline-variant bg-surface-container-low text-on-surface hover:border-outline'
                }`}
              >
                <input
                  type="radio"
                  name="presetScanType"
                  value="sample_npdr"
                  checked={formData.presetScanType === 'sample_npdr'}
                  onChange={() => setFormData({ ...formData, presetScanType: 'sample_npdr' })}
                  className="hidden"
                />
                <span className="material-symbols-outlined text-2xl">visibility</span>
                <span className="text-xs font-bold">Moderate NPDR</span>
                <span className="text-[10px] text-on-surface-variant leading-tight">Pre-load diagnostic scan with lesions</span>
              </label>

              <label
                className={`p-3 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center text-center gap-1.5 ${
                  formData.presetScanType === 'sample_normal'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-outline-variant bg-surface-container-low text-on-surface hover:border-outline'
                }`}
              >
                <input
                  type="radio"
                  name="presetScanType"
                  value="sample_normal"
                  checked={formData.presetScanType === 'sample_normal'}
                  onChange={() => setFormData({ ...formData, presetScanType: 'sample_normal' })}
                  className="hidden"
                />
                <span className="material-symbols-outlined text-2xl">check_circle</span>
                <span className="text-xs font-bold">Normal Retina</span>
                <span className="text-[10px] text-on-surface-variant leading-tight">Pre-load Grade 1 healthy scan</span>
              </label>

              <label
                className={`p-3 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center text-center gap-1.5 ${
                  formData.presetScanType === 'empty'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-outline-variant bg-surface-container-low text-on-surface hover:border-outline'
                }`}
              >
                <input
                  type="radio"
                  name="presetScanType"
                  value="empty"
                  checked={formData.presetScanType === 'empty'}
                  onChange={() => setFormData({ ...formData, presetScanType: 'empty' })}
                  className="hidden"
                />
                <span className="material-symbols-outlined text-2xl">add_a_photo</span>
                <span className="text-xs font-bold">Clean Intake</span>
                <span className="text-[10px] text-on-surface-variant leading-tight">Capture fresh fundus photos live</span>
              </label>
            </div>

            {/* Optional custom files upload accordion */}
            <div className="pt-2">
              <span className="text-xs font-bold text-on-surface mb-2 block">
                Optional: Upload Custom Fundus Files (OS / OD):
              </span>
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 border border-dashed border-outline rounded-lg bg-surface-container-low text-center">
                  <span className="text-xs font-bold text-on-surface block mb-1">Left Eye (OS)</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleCustomFileUpload(e, 'OS')}
                    className="text-[11px] text-on-surface-variant file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 w-full"
                  />
                  {customOsUrl && <span className="text-[10px] text-primary font-bold mt-1 block">Image Loaded</span>}
                </div>

                <div className="p-3 border border-dashed border-outline rounded-lg bg-surface-container-low text-center">
                  <span className="text-xs font-bold text-on-surface block mb-1">Right Eye (OD)</span>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleCustomFileUpload(e, 'OD')}
                    className="text-[11px] text-on-surface-variant file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 w-full"
                  />
                  {customOdUrl && <span className="text-[10px] text-primary font-bold mt-1 block">Image Loaded</span>}
                </div>
              </div>
            </div>
          </div>

          {/* Section 4: Clinical Notes */}
          <div>
            <label className="block text-xs font-bold text-on-surface mb-1">
              Initial Clinical Notes / Indication
            </label>
            <textarea
              rows={2}
              value={formData.clinicalNotes}
              onChange={(e) => setFormData({ ...formData, clinicalNotes: e.target.value })}
              className="w-full px-3 py-2 bg-surface-container-low border border-outline rounded-lg text-xs md:text-sm text-on-surface focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Modal Actions */}
          <div className="pt-4 border-t-2 border-outline-variant flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs md:text-sm font-bold text-on-surface-variant hover:text-on-surface transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!formData.name.trim()}
              className="px-6 py-2.5 bg-primary text-on-primary font-bold text-xs md:text-sm rounded-lg hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors shadow-xs flex items-center gap-1.5 disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-base">check</span>
              Register & Begin Screening
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
