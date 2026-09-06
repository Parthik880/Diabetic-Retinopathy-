import { TabType, PatientRecord } from '../types';

interface TopAppBarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
  patient?: PatientRecord;
  patients: PatientRecord[];
  onSelectPatient: (patient: PatientRecord) => void;
  onOpenAddPatient: () => void;
  onStartNewSession: () => void;
}

const tabs: Array<{ id: TabType; label: string; icon: string }> = [
  { id: 'capture', label: 'Capture', icon: 'add_a_photo' },
  { id: 'analysis', label: 'Analysis', icon: 'analytics' },
  { id: 'compare', label: 'Compare', icon: 'compare' },
  { id: 'report', label: 'Report', icon: 'description' },
  { id: 'history', label: 'History', icon: 'history' },
  { id: 'batch', label: 'Batch Analysis', icon: 'stacks' },
];

export function TopAppBar({ activeTab, setActiveTab, patient, patients, onSelectPatient, onOpenAddPatient, onStartNewSession }: TopAppBarProps) {
  return (
    <header className="no-print fixed inset-x-0 top-0 z-40 h-[72px] border-b border-outline-variant bg-surface-container-lowest/95 px-4 shadow-[0_6px_24px_rgba(20,32,24,0.08)] backdrop-blur-md md:px-6">
      <div className="mx-auto flex h-full max-w-[1600px] items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => setActiveTab('capture')}
          className="group flex min-w-fit items-center gap-3 rounded-xl px-1 py-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          aria-label="RetinaGram home"
        >
          <img src="/logo.png.jpeg" alt="RetinaGram" className="h-11 w-11 rounded-[13px] object-cover shadow-[0_3px_12px_rgba(0,82,39,0.18)]" />
          <span className="hidden leading-none sm:block">
            <span className="block font-headline text-[19px] font-extrabold tracking-[-0.025em] text-primary">RetinaGram</span>
            <span className="mt-1 block text-[11px] font-semibold tracking-[0.04em] text-on-surface-variant">AI Retinal Screening</span>
          </span>
        </button>

        <nav className="hidden items-center gap-1 rounded-xl bg-surface-container-low p-1 md:flex" aria-label="Primary navigation">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              aria-current={activeTab === tab.id ? 'page' : undefined}
              className={`flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-bold transition-colors outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                activeTab === tab.id ? 'bg-primary text-on-primary shadow-[0_2px_8px_rgba(0,82,39,0.22)]' : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
              }`}
            >
              <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{tab.icon}</span>
              <span className="hidden xl:inline">{tab.label}</span>
            </button>
          ))}
        </nav>

        <div className="flex min-w-0 items-center gap-2">
          {patient && <label className="hidden min-w-0 items-center gap-2 rounded-xl border border-outline-variant bg-surface-container-low px-3 py-2 lg:flex">
            <span className="material-symbols-outlined text-[18px] text-primary" aria-hidden="true">person</span>
            <span className="sr-only">Current patient</span>
            <select
              value={patient.id}
              onChange={(event) => {
                const selected = patients.find((candidate) => candidate.id === event.target.value);
                if (selected) onSelectPatient(selected);
              }}
              className="max-w-[220px] cursor-pointer truncate bg-transparent text-sm font-bold text-on-surface outline-none"
              aria-label="Current patient"
            >
              {patients.map((candidate) => <option key={candidate.id} value={candidate.id}>#{candidate.patientIdNumber} - {candidate.name}</option>)}
            </select>
          </label>}
          {patient && <button
            type="button"
            onClick={onStartNewSession}
            className="flex min-h-10 items-center gap-1.5 rounded-lg border border-primary bg-surface-container-lowest px-3 text-xs font-bold text-primary transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">restart_alt</span>
            <span className="hidden xl:inline">New session</span>
          </button>}
          <button
            type="button"
            onClick={onOpenAddPatient}
            className="flex min-h-10 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-bold text-on-primary shadow-[0_3px_12px_rgba(0,82,39,0.2)] transition-colors hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
          >
            <span className="material-symbols-outlined text-[18px]" aria-hidden="true">person_add</span>
            <span className="hidden xl:inline">New patient</span>
          </button>
        </div>
      </div>
    </header>
  );
}
