import { useEffect, useMemo, useState } from 'react';
import { loadHistory } from '../api';
import { completedEyes, groupHistoryByPatient, HistoryDateFilter, HistoryEyeFilter } from '../historyGrouping';
import { HistoryRecord } from '../types';

interface HistoryScreenProps {
  onOpenRecord: (record: HistoryRecord, eye: 'OS' | 'OD') => void;
  onDownloadRecord: (record: HistoryRecord, eye: 'OS' | 'OD') => Promise<string | null>;
}

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });
const timeFormatter = new Intl.DateTimeFormat(undefined, { timeStyle: 'short' });

function gradeSummary(record: HistoryRecord, eye: 'OS' | 'OD') {
  const stored = eye === 'OS' ? record.left_eye : record.right_eye;
  const grade = stored.result_data?.grading?.predicted_grade;
  return grade == null ? null : `${eye}: Grade ${grade}`;
}

function sessionStatus(record: HistoryRecord) {
  const eyes = completedEyes(record);
  if (eyes.length === 2) return 'Complete';
  if (eyes.length === 1) return 'Partially complete';
  return 'Saved session';
}

export function HistoryScreen({ onOpenRecord, onDownloadRecord }: HistoryScreenProps) {
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [dateFilter, setDateFilter] = useState<HistoryDateFilter>('all');
  const [eyeFilter, setEyeFilter] = useState<HistoryEyeFilter>('all');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadSessionId, setDownloadSessionId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const perPage = 10;

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadHistory().then(value => { if (active) setRecords(value); })
      .catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'History could not be loaded.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const groups = useMemo(() => groupHistoryByPatient(records, query, dateFilter, eyeFilter), [records, query, dateFilter, eyeFilter]);
  const selectedGroup = useMemo(() => selectedPatientId
    ? groupHistoryByPatient(records).find(group => group.patientId === selectedPatientId) || null
    : null, [records, selectedPatientId]);
  const pageCount = Math.max(1, Math.ceil(groups.length / perPage));
  const currentPage = Math.min(page, pageCount);
  const visible = groups.slice((currentPage - 1) * perPage, currentPage * perPage);
  const changeFilter = <T,>(setter: (value: T) => void, value: T) => { setter(value); setPage(1); };

  const download = async (record: HistoryRecord, eye: 'OS' | 'OD') => {
    const key = `${record.session_id}-${eye}`;
    setDownloading(key); setError(null); setNotice(null); setDownloadSessionId(null);
    try {
      const folder = await onDownloadRecord(record, eye);
      if (folder) setNotice(`${eye} report saved to ${folder}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The report could not be saved.');
    } finally { setDownloading(null); }
  };

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-7 pb-28 md:px-6 md:pb-12">
      <div className="mb-6 flex flex-col justify-between gap-4 border-b-2 border-outline-variant pb-6 md:flex-row md:items-end">
        <div>
          <h1 className="font-headline text-3xl font-extrabold tracking-[-0.03em] text-on-surface">Scan History</h1>
          <p className="mt-1 text-sm text-on-surface-variant">Patients and all of their locally stored screening sessions.</p>
        </div>
        <div className="text-xs font-bold text-primary">{groups.length} {groups.length === 1 ? 'patient' : 'patients'} · {records.length} {records.length === 1 ? 'session' : 'sessions'}</div>
      </div>

      <div className="mb-5 grid gap-3 rounded-xl bg-surface-container-low p-4 ring-1 ring-outline-variant md:grid-cols-[1fr_auto_auto]">
        <label className="relative min-w-0">
          <span className="sr-only">Search by patient name or ID</span>
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-xl text-on-surface-variant" aria-hidden="true">search</span>
          <input value={query} onChange={event => changeFilter(setQuery, event.target.value)} placeholder="Search by patient name or ID" className="min-h-11 w-full rounded-lg border border-outline-variant bg-white pl-10 pr-3 text-base outline-none focus:ring-2 focus:ring-primary" />
        </label>
        <select aria-label="History date filter" value={dateFilter} onChange={event => changeFilter(setDateFilter, event.target.value as HistoryDateFilter)} className="min-h-11 rounded-lg border border-outline-variant bg-white px-3 text-sm font-bold outline-none focus:ring-2 focus:ring-primary">
          <option value="all">All dates</option><option value="today">Today</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option>
        </select>
        <select aria-label="History eye filter" value={eyeFilter} onChange={event => changeFilter(setEyeFilter, event.target.value as HistoryEyeFilter)} className="min-h-11 rounded-lg border border-outline-variant bg-white px-3 text-sm font-bold outline-none focus:ring-2 focus-visible:ring-primary">
          <option value="all">All eyes</option><option value="OS">Left (OS)</option><option value="OD">Right (OD)</option><option value="both">Both</option>
        </select>
      </div>

      {error && <div role="alert" className="mb-4 rounded-xl border border-error/30 bg-error-container px-4 py-3 text-sm font-semibold text-error">{error}</div>}
      {notice && <div role="status" className="mb-4 rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 text-sm font-semibold text-primary">{notice}</div>}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(390px,0.9fr)]">
        <section aria-label="Patient history list" className="min-w-0 overflow-hidden rounded-xl bg-white shadow-[0_10px_32px_rgba(20,32,24,0.08)] ring-1 ring-outline-variant">
          {loading ? <div role="status" className="py-20 text-center text-on-surface-variant">Loading patient history…</div> : visible.length ? <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] text-left text-sm">
                <thead className="bg-surface-container-low text-[11px] uppercase tracking-[0.06em] text-on-surface-variant"><tr><th className="px-3 py-3">Patient name</th><th className="px-3 py-3">Patient ID</th><th className="px-3 py-3">Last scan</th><th className="px-3 py-3">Sessions</th><th className="px-3 py-3">Eye(s)</th><th className="px-3 py-3 text-right">Actions</th></tr></thead>
                <tbody className="divide-y divide-outline-variant">
                  {visible.map(group => <tr key={group.patientId} className={selectedPatientId === group.patientId ? 'bg-primary/5' : 'hover:bg-surface-container-low/70'}>
                    <td className="max-w-[160px] px-3 py-4 font-extrabold text-on-surface"><span className="block truncate" title={group.patientName}>{group.patientName}</span></td>
                    <td className="px-3 py-4 font-bold tabular-nums text-on-surface-variant">#{group.patientId}</td>
                    <td className="whitespace-nowrap px-3 py-4 text-on-surface-variant">{dateTimeFormatter.format(new Date(group.latestScan))}</td>
                    <td className="whitespace-nowrap px-3 py-4 font-bold text-on-surface">{group.sessions.length} {group.sessions.length === 1 ? 'session' : 'sessions'}</td>
                    <td className="px-3 py-4"><div className="flex gap-1.5">{group.eyes.map(eye => <span key={eye} className="rounded-md bg-primary/10 px-2 py-1 text-xs font-extrabold text-primary">{eye}</span>)}</div></td>
                    <td className="px-3 py-4 text-right"><button type="button" onClick={() => setSelectedPatientId(group.patientId)} className="whitespace-nowrap rounded-lg bg-primary px-3 py-2 text-xs font-extrabold text-on-primary hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">View history</button></td>
                  </tr>)}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-outline-variant px-4 py-3 text-xs text-on-surface-variant">
              <span>Page {currentPage} of {pageCount}</span>
              <div className="flex gap-2"><button disabled={page <= 1} onClick={() => setPage(value => Math.max(1, value - 1))} className="rounded-lg border border-outline-variant px-3 py-2 font-bold disabled:opacity-40">Previous</button><button disabled={page >= pageCount} onClick={() => setPage(value => Math.min(pageCount, value + 1))} className="rounded-lg border border-outline-variant px-3 py-2 font-bold disabled:opacity-40">Next</button></div>
            </div>
          </> : <div className="p-12 text-center"><span className="material-symbols-outlined text-5xl text-primary" aria-hidden="true">history</span><h2 className="mt-3 font-headline text-xl font-extrabold">No patients found</h2><p className="mt-2 text-sm text-on-surface-variant">Try changing the search or filters.</p></div>}
        </section>

        <aside aria-label="Selected patient sessions" className="min-h-[420px] rounded-xl bg-surface-container-low p-5 ring-1 ring-outline-variant lg:sticky lg:top-[96px]">
          {selectedGroup ? <>
            <header className="border-b border-outline-variant pb-4">
              <h2 className="truncate font-headline text-2xl font-extrabold tracking-[-0.025em] text-on-surface" title={selectedGroup.patientName}>{selectedGroup.patientName}</h2>
              <p className="mt-1 text-sm font-semibold text-on-surface-variant">Patient ID: #{selectedGroup.patientId}</p>
              <p className="mt-2 text-xs font-extrabold uppercase tracking-[0.06em] text-primary">{selectedGroup.sessions.length} screening {selectedGroup.sessions.length === 1 ? 'session' : 'sessions'}</p>
            </header>
            <div className="mt-4 max-h-[calc(100vh-260px)] space-y-3 overflow-y-auto pr-1">
              {selectedGroup.sessions.map(record => {
                const eyes = completedEyes(record);
                const summaries = (['OS', 'OD'] as const).map(eye => gradeSummary(record, eye)).filter((value): value is string => Boolean(value));
                const directEye = eyes.length === 1 ? eyes[0] : null;
                return <article key={record.session_id} className="rounded-xl bg-white p-4 shadow-[0_4px_16px_rgba(20,32,24,0.07)]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0"><h3 className="font-extrabold text-on-surface">{dateFormatter.format(new Date(record.scan_datetime))} <span className="font-normal text-on-surface-variant">• {timeFormatter.format(new Date(record.scan_datetime))}</span></h3><p className="mt-1 break-all text-xs text-on-surface-variant">Session: {record.session_id}</p></div>
                    <span className={`whitespace-nowrap rounded-md px-2 py-1 text-[11px] font-extrabold ${eyes.length === 2 ? 'bg-primary/10 text-primary' : 'bg-surface-container-high text-on-surface-variant'}`}>{sessionStatus(record)}</span>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">{eyes.map(eye => <span key={eye} className="rounded-md border border-primary/30 px-2 py-1 text-xs font-extrabold text-primary">{eye}</span>)}{summaries.map(summary => <span key={summary} className="text-xs font-semibold text-on-surface-variant">{summary}</span>)}</div>
                  <div className="relative mt-4 flex flex-wrap gap-2">
                    <button type="button" disabled={!eyes.length} onClick={() => onOpenRecord(record, eyes[0] || 'OS')} className="min-h-9 rounded-lg bg-primary px-3 text-xs font-extrabold text-on-primary hover:bg-primary-container disabled:cursor-not-allowed disabled:opacity-45">View Reports</button>
                    <button type="button" disabled={!eyes.length || Boolean(downloading)} onClick={() => directEye ? void download(record, directEye) : setDownloadSessionId(value => value === record.session_id ? null : record.session_id)} aria-expanded={downloadSessionId === record.session_id} className="min-h-9 rounded-lg border border-primary px-3 text-xs font-extrabold text-primary hover:bg-primary/10 disabled:cursor-not-allowed disabled:opacity-45">{downloading?.startsWith(record.session_id) ? 'Saving…' : 'Download'}</button>
                    {downloadSessionId === record.session_id && eyes.length === 2 && <div className="absolute bottom-11 right-0 z-10 min-w-56 rounded-xl bg-white p-2 shadow-[0_12px_32px_rgba(20,32,24,0.18)] ring-1 ring-outline-variant">
                      <button type="button" onClick={() => void download(record, 'OS')} className="block w-full rounded-lg px-3 py-2 text-left text-xs font-bold text-on-surface hover:bg-surface-container-low">Download Left Eye Report</button>
                      <button type="button" onClick={() => void download(record, 'OD')} className="mt-1 block w-full rounded-lg px-3 py-2 text-left text-xs font-bold text-on-surface hover:bg-surface-container-low">Download Right Eye Report</button>
                    </div>}
                  </div>
                </article>;
              })}
            </div>
          </> : <div className="flex min-h-[380px] flex-col items-center justify-center px-8 text-center"><span className="material-symbols-outlined text-5xl text-primary" aria-hidden="true">patient_list</span><h2 className="mt-4 font-headline text-xl font-extrabold text-on-surface">Select a patient</h2><p className="mt-2 max-w-sm text-sm leading-6 text-on-surface-variant">Select a patient to view previous screening sessions.</p></div>}
        </aside>
      </div>
    </div>
  );
}
