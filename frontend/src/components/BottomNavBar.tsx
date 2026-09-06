import { TabType } from '../types';

interface BottomNavBarProps {
  activeTab: TabType;
  setActiveTab: (tab: TabType) => void;
}

export function BottomNavBar({ activeTab, setActiveTab }: BottomNavBarProps) {
  return (
    <nav className="no-print fixed bottom-0 left-0 w-full z-50 flex justify-around items-center px-2 pb-safe h-16 bg-surface-container-lowest border-t-2 border-outline-variant md:hidden shadow-lg">
      {/* Capture */}
      <button
        onClick={() => setActiveTab('capture')}
        className={`flex flex-col items-center justify-center pt-2 transition-all w-1/5 ${
          activeTab === 'capture'
            ? 'text-primary font-bold border-t-2 border-primary -mt-[2px]'
            : 'text-on-surface-variant hover:text-primary'
        }`}
      >
        <span
          className="material-symbols-outlined text-[24px]"
          style={{ fontVariationSettings: activeTab === 'capture' ? "'FILL' 1" : "'FILL' 0" }}
        >
          add_a_photo
        </span>
        <span className="font-label-lg text-[11px] mt-0.5 tracking-tight">Capture</span>
      </button>

      {/* Analysis */}
      <button
        onClick={() => setActiveTab('analysis')}
        className={`flex flex-col items-center justify-center pt-2 transition-all w-1/5 ${
          activeTab === 'analysis'
            ? 'text-primary font-bold border-t-2 border-primary -mt-[2px]'
            : 'text-on-surface-variant hover:text-primary'
        }`}
      >
        <span
          className="material-symbols-outlined text-[24px]"
          style={{ fontVariationSettings: activeTab === 'analysis' ? "'FILL' 1" : "'FILL' 0" }}
        >
          analytics
        </span>
        <span className="font-label-lg text-[11px] mt-0.5 tracking-tight">Analysis</span>
      </button>

      {/* Compare */}
      <button
        onClick={() => setActiveTab('compare')}
        className={`flex flex-col items-center justify-center pt-2 transition-all w-1/5 ${
          activeTab === 'compare'
            ? 'text-primary font-bold border-t-2 border-primary -mt-[2px]'
            : 'text-on-surface-variant hover:text-primary'
        }`}
      >
        <span
          className="material-symbols-outlined text-[24px]"
          style={{ fontVariationSettings: activeTab === 'compare' ? "'FILL' 1" : "'FILL' 0" }}
        >
          compare
        </span>
        <span className="font-label-lg text-[11px] mt-0.5 tracking-tight">Compare</span>
      </button>

      {/* Report */}
      <button
        onClick={() => setActiveTab('report')}
        className={`flex flex-col items-center justify-center pt-2 transition-all w-1/5 ${
          activeTab === 'report'
            ? 'text-primary font-bold border-t-2 border-primary -mt-[2px]'
            : 'text-on-surface-variant hover:text-primary'
        }`}
      >
        <span
          className="material-symbols-outlined text-[24px]"
          style={{ fontVariationSettings: activeTab === 'report' ? "'FILL' 1" : "'FILL' 0" }}
        >
          description
        </span>
        <span className="font-label-lg text-[11px] mt-0.5 tracking-tight">Report</span>
      </button>

      <button
        onClick={() => setActiveTab('history')}
        className={`flex w-1/5 flex-col items-center justify-center pt-2 transition-all ${
          activeTab === 'history'
            ? 'text-primary font-bold border-t-2 border-primary -mt-[2px]'
            : 'text-on-surface-variant hover:text-primary'
        }`}
      >
        <span className="material-symbols-outlined text-[24px]" style={{ fontVariationSettings: activeTab === 'history' ? "'FILL' 1" : "'FILL' 0" }}>history</span>
        <span className="font-label-lg mt-0.5 text-[11px] tracking-tight">History</span>
      </button>
    </nav>
  );
}
