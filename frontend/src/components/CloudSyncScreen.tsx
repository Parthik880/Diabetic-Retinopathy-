import { useEffect, useState } from 'react';
import { dataRequest, type ClearPreview, type DataOverview } from '../dataApi';
import { DataDialog } from './DataDialog';

const button = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-primary px-4 text-sm font-bold text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-45';
const icon = (name: string, extra = '') => <span className={`material-symbols-outlined ${extra}`} aria-hidden="true">{name}</span>;
const formatStorage = (value: number) => value >= 1024 ** 3 ? `${(value / 1024 ** 3).toFixed(2)} GB` : value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MB` : value >= 1024 ? `${(value / 1024).toFixed(1)} KB` : `${value} B`;
const display = (value: number | null) => value === null ? '—' : value.toLocaleString();

function OverviewStat({ iconName, label, value, note }: { iconName: string; label: string; value: string | number; note: string }) {
  return <div className="rounded-xl border border-outline-variant px-4 py-3.5">
    <div className="flex items-start gap-3 text-primary">{icon(iconName, 'text-xl')}<div><div className="text-xs text-on-surface-variant">{label}</div><div className="mt-1 font-headline text-xl font-extrabold tabular-nums text-primary">{value}</div><div className="mt-1 text-[11px] text-on-surface-variant">{note}</div></div></div>
  </div>;
}

function OfflineStat({ label, value }: { label: string; value: string | number }) {
  return <div><dt className="text-xs leading-4 text-on-surface-variant">{label}</dt><dd className="mt-1 font-headline text-lg font-extrabold tabular-nums text-primary">{value}</dd></div>;
}

export function CloudSyncScreen({ onBack, onDataCleared }: { onBack: () => void; onDataCleared: (categories: string[]) => Promise<void> }) {
  const [data, setData] = useState<DataOverview | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<ClearPreview | null>(null);
  const [typed, setTyped] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const load = async () => { setError(''); try { setData(await dataRequest('/api/data')); } catch (err) { setError((err as Error).message); } };
  useEffect(() => { void load(); }, []);
  const action = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };
  const closeClear = () => { setClearOpen(false); setPreview(null); setSelected([]); setTyped(''); setConfirmed(false); };
  const updateSetting = (key: keyof DataOverview['sync_settings'], checked: boolean) => void action(async () => {
    if (data) setData(await dataRequest('/api/data/sync-settings', 'PUT', { ...data.sync_settings, [key]: checked }));
  });

  return <div className="mx-auto w-full max-w-7xl px-5 pb-24 pt-6 md:px-7">
    <button type="button" onClick={onBack} className="inline-flex min-h-9 items-center gap-1 rounded-md text-sm font-bold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary">{icon('arrow_back', 'text-lg')}Back</button>
    <h1 className="mt-2 font-headline text-3xl font-extrabold tracking-[-0.03em] text-primary">Cloud Sync</h1>
    <p className="mt-1 text-sm text-on-surface-variant">Keep patient records and reports available across your RetinaGram devices.</p>

    {error && !clearOpen && <div role="alert" className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-error/30 bg-error-container px-4 py-3 text-sm text-error"><span>{error}</span><button type="button" className="font-bold underline underline-offset-4" onClick={() => void load()}>Retry</button></div>}
    {notice && <p role="status" className="mt-4 rounded-lg bg-primary/10 px-4 py-3 text-sm font-bold text-primary">{notice}</p>}

    {!data ? <p role="status" className="mt-8 text-sm text-on-surface-variant">{error ? 'Local data status is temporarily unavailable.' : 'Reading local data status…'}</p> : <>
      <div className="mt-6 grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <section aria-labelledby="cloud-status-title" className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
          <div className="flex items-start justify-between gap-6 border-b border-outline-variant pb-5">
            <div className="min-w-0">
              <div className="flex items-start gap-3">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">{icon('cloud', 'text-2xl')}</span>
                <div><h2 id="cloud-status-title" className="font-headline text-lg font-extrabold">Cloud synchronization</h2><p role="status" className="mt-1 flex items-center gap-2 text-sm font-bold"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${data.cloud_connected ? 'bg-primary' : 'bg-error'}`} />{data.cloud_status}</p></div>
              </div>
              <p className="mt-5 text-sm text-on-surface-variant">Your patient data currently stays on this PC.</p>
              <p className="mt-2 max-w-md text-sm leading-6 text-on-surface-variant">Connect cloud storage to securely synchronize selected records.</p>
              <button type="button" className="mt-4 inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-bold text-white hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2" onClick={() => setNotice(data.cloud_message)}>{icon('cloud_upload', 'text-lg')}Connect Cloud</button>
            </div>
            <div className="hidden w-40 shrink-0 self-center text-center text-primary/40 sm:block" aria-hidden="true">
              {icon('cloud_upload', 'text-6xl')}
              <div className="mt-3 flex justify-center gap-3">{icon('desktop_windows', 'text-4xl')}{icon('tablet_mac', 'text-4xl')}{icon('smartphone', 'text-4xl')}</div>
              <p className="mt-2 text-[11px] leading-4 text-on-surface-variant">Same data. More access.<br />Better care.</p>
            </div>
          </div>
          <h3 className="mt-5 font-headline text-base font-extrabold">Sync overview</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <OverviewStat iconName="badge" label="Patients" value={data.patient_count} note="stored locally" />
            <OverviewStat iconName="description" label="Reports" value={data.report_count} note="generated" />
            <OverviewStat iconName="storage" label="Local storage" value={formatStorage(data.storage_bytes)} note="currently used" />
          </div>
        </section>

        <section aria-labelledby="synchronization-title" className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
          <h2 id="synchronization-title" className="font-headline text-lg font-extrabold">Synchronization</h2>
          <div className="mt-5 space-y-5">
            <label className="flex items-start gap-3"><input type="checkbox" checked={data.sync_settings.automatic} disabled={busy || !data.cloud_connected} onChange={event => updateSetting('automatic', event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" /><span><span className="block text-sm font-bold">Automatic sync</span><span className="mt-1 block text-xs text-on-surface-variant">Upload new patient records and reports when internet is available.</span></span></label>
            <label className="flex items-start gap-3"><input type="checkbox" checked={data.sync_settings.patients} disabled={busy} onChange={event => updateSetting('patients', event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" /><span><span className="block text-sm font-bold">Patient metadata</span><span className="mt-1 block text-xs text-on-surface-variant">Patient details and session information</span></span></label>
            <label className="flex items-start gap-3"><input type="checkbox" checked={data.sync_settings.reports} disabled={busy} onChange={event => updateSetting('reports', event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" /><span><span className="block text-sm font-bold">Reports</span><span className="mt-1 block text-xs text-on-surface-variant">Generated PDF reports</span></span></label>
            <label className="flex items-start gap-3"><input type="checkbox" checked={data.sync_settings.images} disabled={busy} onChange={event => updateSetting('images', event.target.checked)} className="mt-0.5 h-4 w-4 accent-primary" /><span><span className="block text-sm font-bold">Retinal images</span><span className="mt-1 block text-xs text-on-surface-variant">Original and restored fundus images</span></span></label>
          </div>
          <div className="mt-7 flex items-end justify-between gap-4">
            <dl className="grid gap-x-8 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2"><div><dt className="inline text-on-surface-variant">Last sync</dt><dd className="ml-4 inline font-bold">{data.last_sync ? new Date(data.last_sync).toLocaleString() : 'Never'}</dd></div><div><dt className="inline text-on-surface-variant">Pending items</dt><dd className="ml-4 inline font-bold tabular-nums">{display(data.pending_items)}</dd></div></dl>
            <button type="button" className={button} disabled={busy || !data.cloud_connected} onClick={() => void action(async () => { await dataRequest('/api/data/sync', 'POST'); await load(); })}>Sync now</button>
          </div>
          {!data.cloud_connected && <p className="mt-5 flex items-center gap-2 text-xs text-on-surface-variant">{icon('info', 'text-xl text-primary')}Cloud provider is not configured yet.</p>}
          {data.failed_items !== null && <p className="mt-2 text-xs text-error">Failed items: {display(data.failed_items)}</p>}
        </section>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <section aria-labelledby="offline-storage-title" className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
          <div className="flex items-start gap-3 text-primary">{icon('layers', 'text-2xl')}<div><h2 id="offline-storage-title" className="font-headline text-lg font-extrabold">Offline storage</h2><p className="mt-1 text-xs text-on-surface-variant">RetinaGram keeps patient information required for offline screening on this device.</p></div></div>
          <div className="mt-6 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <dl className="grid flex-1 grid-cols-2 gap-5 sm:grid-cols-5">
              <OfflineStat label="Local patient records" value={data.patient_count} />
              <OfflineStat label="Scan sessions" value={data.session_count} />
              <OfflineStat label="Images" value={data.retinal_image_count} />
              <OfflineStat label="Reports" value={data.report_count} />
              <OfflineStat label="Storage used" value={formatStorage(data.storage_bytes)} />
            </dl>
            <button type="button" className={`${button} shrink-0`} onClick={() => void action(async () => { if (!(await window.retinaDesktop?.openDataFolder())?.opened) throw new Error('Native folder opening is available in the RetinaGram desktop app.'); })}>{icon('folder_open', 'text-xl')}Open data folder</button>
          </div>
          <p className="mt-5 text-[11px] leading-5 text-on-surface-variant">Storage includes the local database and managed image/report files. Exports outside the data folder are not counted. {data.database_engine}: {data.database_status}.</p>
        </section>

        <section aria-labelledby="data-management-title" className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
          <div className="flex items-start gap-3">{icon('delete', 'text-2xl text-error')}<div><h2 id="data-management-title" className="font-headline text-lg font-extrabold">Data management</h2><h3 className="mt-3 text-sm font-bold">Clear local data</h3><p className="mt-1 text-xs leading-5 text-on-surface-variant">Remove locally stored RetinaGram patient records, scans, reports and generated analysis files from this computer.</p></div></div>
          <div className="mt-5 text-right"><button type="button" disabled={busy || data.busy} className="min-h-10 rounded-lg border border-error px-4 text-sm font-bold text-error hover:bg-error-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error disabled:opacity-45" onClick={() => { setError(''); setClearOpen(true); }}>Clear local data…</button></div>
          {data.busy && <p className="mt-3 text-xs text-on-surface-variant">Finish or cancel active analysis before clearing data.</p>}
        </section>
      </div>
    </>}

    {clearOpen && data && <DataDialog title="Clear local data" onClose={closeClear} busy={busy}>
      {error && <p role="alert" className="mb-4 rounded-lg bg-error-container p-3 text-sm text-error">{error}</p>}
      {!preview ? <><p className="mb-3 text-sm text-on-surface-variant">Choose only the application-owned data to remove. Nothing is selected by default.</p><div className="space-y-3">{data.categories.map(category => <label key={category.id} className="flex items-center gap-3 text-sm"><input type="checkbox" checked={selected.includes(category.id)} onChange={event => setSelected(event.target.checked ? [...selected, category.id] : selected.filter(id => id !== category.id))} className="h-5 w-5 accent-primary" />{category.label}</label>)}</div><button disabled={busy || !selected.length} className={`${button} mt-5`} onClick={() => void action(async () => setPreview(await dataRequest('/api/data/clear-preview', 'POST', { categories: selected })))}>Review selected data</button></> : <>
        <p className="text-sm font-bold">{preview.file_count} managed files ({formatStorage(preview.bytes)}) selected.</p><ul className="my-3 list-disc pl-5 text-sm">{preview.categories.map(id => <li key={id}>{data.categories.find(category => category.id === id)?.label}</li>)}</ul><p className="text-sm text-on-surface-variant">This cannot be undone. External exports, database schema, PostgreSQL cluster files, and checkpoints remain.</p>
        {preview.categories.includes('history') && <label className="mt-4 block text-sm font-bold">Delete {preview.patient_count} patients and {preview.session_count} sessions. Type DELETE to confirm.<input aria-label="Type DELETE to confirm" autoComplete="off" value={typed} onChange={event => setTyped(event.target.value)} className="mt-2 w-full rounded-lg border border-outline px-3 py-2 focus-visible:ring-2 focus-visible:ring-error" /></label>}
        <label className="mt-4 flex items-start gap-3 text-sm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} className="mt-0.5 h-5 w-5 accent-primary" />I acknowledge that the selected local data will be permanently removed.</label>
        <div className="mt-5 flex flex-wrap justify-end gap-3"><button disabled={busy} className={button} onClick={() => { setPreview(null); setConfirmed(false); setTyped(''); }}>Back</button><button disabled={busy || !confirmed || (preview.categories.includes('history') && typed !== 'DELETE')} className="min-h-10 rounded-lg bg-error px-4 text-sm font-bold text-white disabled:opacity-45" onClick={() => void action(async () => { const result = await dataRequest<{ deleted_files: number; skipped_files: number }>('/api/data/clear', 'POST', { token: preview.token, confirmed, typed }); closeClear(); setNotice(`${result.deleted_files} files removed. ${result.skipped_files} changed or unavailable files skipped.`); await onDataCleared(preview.categories); await load(); })}>{busy ? 'Clearing…' : 'Clear selected data'}</button></div>
      </>}
    </DataDialog>}
  </div>;
}
