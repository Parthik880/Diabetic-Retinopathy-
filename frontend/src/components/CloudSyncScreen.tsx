import { useCallback, useEffect, useRef, useState } from 'react';

type Settings = { automatic: boolean; patient_metadata: boolean; reports: boolean; retinal_images: boolean };
type Overview = {
  status: 'Not connected' | 'Connecting' | 'Connected' | 'Syncing' | 'Sync complete' | 'Sync failed' | 'Offline';
  configured: boolean; message: string; settings: Settings;
  counts: { patients: number; sessions: number; reports: number; images: number; file_bytes: number; database_bytes: number };
  pending_items: number; unsynced_items: number; last_synced_at: string | null;
};
type Category = 'temporary' | 'artifacts' | 'reports' | 'images' | 'history';
type Preview = { file_count: number; bytes: number; unsynced_items: number; warning: string };
const button = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-primary px-4 text-sm font-bold text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-45';
const icon = (name: string, extra = '') => <span aria-hidden="true" className={`material-symbols-outlined ${extra}`}>{name}</span>;
const formatBytes = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(2)} GB` : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;

async function storageRequest<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(path, payload === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'The local storage request failed. Please retry.');
  return result;
}

export function CloudSyncScreen({ onBack, onDataCleared }: { onBack: () => void; onDataCleared: () => void }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [clearing, setClearing] = useState(false);
  const refresh = useCallback(async () => {
    try { setOverview(await storageRequest<Overview>('/api/sync')); setError(''); }
    catch (error) { setError((error as Error).message); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const perform = async (action: 'connect' | 'now') => {
    setBusy(true); setError('');
    setOverview(value => value ? { ...value, status: action === 'connect' ? 'Connecting' : 'Syncing' } : value);
    try { const result = await storageRequest<{ message: string }>(`/api/sync/${action}`, {}); setNotice(result.message); }
    catch (error) { setError((error as Error).message); }
    finally { await refresh(); setBusy(false); }
  };
  const updateSetting = async (key: keyof Settings, checked: boolean) => {
    if (!overview) return;
    setBusy(true); setError('');
    try {
      const settings = await storageRequest<Settings>('/api/sync/settings', { ...overview.settings, [key]: checked });
      setOverview({ ...overview, settings });
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  };
  const openFolder = async () => {
    try {
      if (!window.retinaDesktop) throw new Error('Open the desktop app to open its data folder.');
      const result = await window.retinaDesktop.openDataFolder();
      if (!result.opened) throw new Error(result.error || 'Windows could not open the data folder.');
    } catch (error) { setError((error as Error).message); }
  };
  const counts = overview?.counts;
  const totalBytes = counts ? counts.file_bytes + counts.database_bytes : 0;
  const connected = overview?.status === 'Connected' || overview?.status === 'Sync complete';

  return <div className="mx-auto w-full max-w-7xl px-6 py-6">
    <button type="button" onClick={onBack} className="inline-flex items-center gap-1 rounded text-sm font-bold text-primary hover:underline focus-visible:ring-2 focus-visible:ring-primary">{icon('arrow_back', 'text-base')}Back</button>
    <h1 className="mt-2 font-headline text-3xl font-extrabold text-primary">Cloud Sync</h1>
    <p className="mt-1 text-sm text-on-surface-variant">Keep patient records and reports available across your RetinaGram devices.</p>
    {error && <div role="alert" className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-error/30 bg-error-container p-4 text-sm text-error"><p>{error}</p><button className="font-bold underline" onClick={refresh}>Retry</button></div>}
    {notice && <p role="status" className="mt-4 text-sm text-primary">{notice}</p>}
    <div className="mt-6 grid grid-cols-[1.55fr_1fr] gap-5">
      <div className="space-y-4 rounded-xl border border-outline-variant bg-surface-container-lowest p-5">
        <section className="flex items-center justify-between gap-5 border-b border-outline-variant pb-5">
          <div className="min-w-0">
            <div className="flex items-start gap-3">
              <div className="rounded-xl bg-primary/10 p-3 text-primary">{icon('cloud', 'text-3xl')}</div>
              <div><h2 className="font-headline text-lg font-extrabold">Cloud synchronization</h2><p role="status" className="mt-1 flex items-center gap-2 text-sm font-bold"><span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-primary' : 'bg-error'}`} />{overview?.status || 'Not connected'}</p></div>
            </div>
            <p className="mt-4 max-w-sm text-sm leading-6 text-on-surface-variant">Your patient data currently stays on this PC.<br />Connect cloud storage to securely synchronize selected records.</p>
            <button type="button" disabled={busy || !overview} onClick={() => perform('connect')} className="mt-4 inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-bold text-on-primary hover:bg-primary-container focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-45">{icon('cloud_upload', 'text-lg')}{overview?.status === 'Connecting' ? 'Connecting…' : 'Connect Cloud'}</button>
          </div>
          <div aria-hidden="true" className="flex w-40 shrink-0 flex-col items-center text-primary/40">
            <span className="material-symbols-outlined" style={{ fontSize: 72 }}>cloud_upload</span>
            <div className="mt-2 flex items-end gap-3"><span className="material-symbols-outlined" style={{ fontSize: 48 }}>desktop_windows</span><span className="material-symbols-outlined" style={{ fontSize: 40 }}>tablet_mac</span><span className="material-symbols-outlined" style={{ fontSize: 32 }}>smartphone</span></div>
            <p className="mt-2 text-center text-xs text-on-surface-variant">Same data. More access. Better care.</p>
          </div>
        </section>
        <section aria-labelledby="sync-overview-title">
          <h2 id="sync-overview-title" className="font-headline text-base font-extrabold">Sync overview</h2>
          <dl className="mt-3 grid grid-cols-3 gap-3">
            {[
              ['Patients', counts?.patients.toLocaleString() ?? '—', 'stored locally', 'badge'],
              ['Reports', counts?.reports.toLocaleString() ?? '—', 'generated', 'description'],
              ['Local storage', counts ? formatBytes(totalBytes) : '—', 'currently used', 'storage'],
            ].map(([label, value, hint, name]) => <div key={label} className="flex gap-3 rounded-lg border border-outline-variant p-3"><span className="text-primary">{icon(name, 'text-2xl')}</span><div><dt className="text-xs text-on-surface-variant">{label}</dt><dd className="mt-1 font-headline text-xl font-extrabold tabular-nums text-primary">{value}</dd><p className="mt-1 text-xs text-on-surface-variant">{hint}</p></div></div>)}
          </dl>
        </section>
      </div>
      <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5" aria-labelledby="synchronization-title">
        <h2 id="synchronization-title" className="font-headline text-base font-extrabold">Synchronization</h2>
        <div className="mt-5 space-y-5">
          {([
            ['automatic', 'Automatic sync', 'Upload new patient records and reports when internet is available.'],
            ['patient_metadata', 'Patient metadata', 'Patient details and session information'],
            ['reports', 'Reports', 'Generated PDF reports'],
            ['retinal_images', 'Retinal images', 'Original and restored fundus images'],
          ] as const).map(([key, label, hint]) => <label key={key} className="flex cursor-pointer items-start gap-3">
            <input type="checkbox" role={key === 'automatic' ? 'switch' : undefined} checked={overview?.settings[key] ?? (key === 'patient_metadata' || key === 'reports')}
              disabled={busy || !overview || (key === 'automatic' && !overview.configured)} onChange={event => updateSetting(key, event.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 accent-primary focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed" />
            <span><span className="block text-sm font-bold">{label}</span><span className="mt-0.5 block text-xs leading-5 text-on-surface-variant">{hint}</span></span>
          </label>)}
        </div>
        <div className="mt-6 flex items-center justify-between gap-4">
          <dl className="grid grid-cols-[auto_auto] gap-x-5 gap-y-3 text-xs"><dt>Last sync</dt><dd className="font-bold">{overview?.last_synced_at ? new Date(overview.last_synced_at).toLocaleString() : 'Never'}</dd><dt>Pending items</dt><dd className="font-bold tabular-nums">{overview?.pending_items ?? '—'}</dd></dl>
          <button type="button" onClick={() => perform('now')} disabled={!overview?.configured || busy} className={button}>{overview?.status === 'Syncing' ? 'Syncing…' : 'Sync now'}</button>
        </div>
        {!overview?.configured && <p className="mt-5 flex items-center gap-2 text-xs text-on-surface-variant">{icon('info', 'text-base')}Cloud provider is not configured yet.</p>}
      </section>
      <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5" aria-labelledby="offline-storage-title">
        <div className="flex gap-3 text-primary">{icon('stacks', 'text-3xl')}<div><h2 id="offline-storage-title" className="font-headline text-base font-extrabold">Offline storage</h2><p className="mt-1 text-xs text-on-surface-variant">RetinaGram keeps patient information required for offline screening on this device.</p></div></div>
        <div className="mt-5 flex items-end justify-between gap-4">
          <dl className="grid flex-1 grid-cols-5 gap-3">{[
            ['Local patient records', counts?.patients], ['Scan sessions', counts?.sessions], ['Images', counts?.images], ['Reports', counts?.reports], ['Storage used', counts ? formatBytes(totalBytes) : undefined],
          ].map(([label, value]) => <div key={label}><dt className="text-xs text-on-surface-variant">{label}</dt><dd className="mt-1 text-lg font-bold tabular-nums text-primary">{value ?? '—'}</dd></div>)}</dl>
          <button type="button" onClick={openFolder} className={button}>{icon('folder_open', 'text-lg')}Open data folder</button>
        </div>
        <p className="mt-4 text-xs text-on-surface-variant">Storage includes the local database and managed image/report files. Exports outside the data folder are not counted.</p>
      </section>
      <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5" aria-labelledby="data-management-title">
        <div className="flex items-start gap-3">{icon('delete', 'text-2xl text-error')}<div><h2 id="data-management-title" className="font-headline text-base font-extrabold">Data management</h2><h3 className="mt-2 text-sm font-bold">Clear local data</h3><p className="mt-1 text-xs leading-5 text-on-surface-variant">Remove locally stored RetinaGram patient records, scans, reports and generated analysis files from this computer.</p></div></div>
        <div className="mt-4 text-right"><button type="button" disabled={!overview} onClick={() => setClearing(true)} className="min-h-10 rounded-lg border border-error px-4 text-sm font-bold text-error hover:bg-error-container focus-visible:ring-2 focus-visible:ring-error disabled:opacity-45">Clear local data…</button></div>
      </section>
    </div>
    {clearing && <ClearLocalDataModal onClose={() => setClearing(false)} onCleared={message => { setClearing(false); setNotice(message); onDataCleared(); void refresh(); }} />}
  </div>;
}

function ClearLocalDataModal({ onClose, onCleared }: { onClose: () => void; onCleared: (message: string) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { const node = dialog.current!; node.showModal(); return () => node.close(); }, []);
  useEffect(() => {
    let active = true;
    setPreview(null);
    if (categories.length) storageRequest<Preview>('/api/storage/preview', { categories }).then(value => { if (active) setPreview(value); }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [categories]);
  const clear = async () => {
    setBusy(true); setError('');
    try {
      const result = await storageRequest<{ retained_files: number; message: string }>('/api/storage/clear', { categories, acknowledged, confirmation });
      onCleared(result.message);
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  };
  return <dialog ref={dialog} aria-labelledby="clear-data-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} className="fixed inset-0 m-auto w-[560px] max-h-[85vh] overflow-y-auto rounded-2xl border border-outline-variant bg-surface-container-lowest p-6 text-on-surface shadow-xl backdrop:bg-black/50">
    <h2 id="clear-data-title" className="font-headline text-xl font-extrabold">Clear local data</h2>
    <p className="mt-2 text-sm leading-6 text-on-surface-variant">Choose what to remove from this PC. Cloud records will not be deleted. Legacy JSON backups and exports outside the app data folder are not removed.</p>
    <div className="mt-5 space-y-4">{([
      ['temporary', 'Temporary inference files'], ['artifacts', 'Generated analysis artifacts'], ['reports', 'Locally saved reports'], ['images', 'Retinal images'], ['history', 'Patient and session history'],
    ] as const).map(([key, label]) => <label key={key} className="flex items-center gap-3 text-sm"><input type="checkbox" disabled={busy} checked={categories.includes(key)} onChange={event => setCategories(event.target.checked ? [...categories, key] : categories.filter(item => item !== key))} className="h-4 w-4 accent-primary" />{label}</label>)}</div>
    {preview && <div role="status" className="mt-5 rounded-lg bg-error-container p-3 text-sm leading-6 text-error"><p>{preview.file_count} managed files · {formatBytes(preview.bytes)} selected.</p>{preview.unsynced_items > 0 && <p className="font-bold">Some selected records have not been synchronized and may be permanently lost. {preview.unsynced_items} unsynchronized records are stored on this PC.</p>}</div>}
    <label className="mt-5 flex items-start gap-3 text-sm leading-6"><input type="checkbox" disabled={busy} checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-primary" /><span>I understand that data which has not been synchronized may be permanently lost.</span></label>
    {categories.includes('history') && <label className="mt-4 block text-sm font-bold">Type DELETE to remove patient and session history<input value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} autoComplete="off" className="mt-2 block w-full rounded-lg border border-outline px-3 py-2 font-normal focus:ring-2 focus:ring-error" /></label>}
    {error && <p role="alert" className="mt-4 text-sm text-error">{error}</p>}
    <div className="mt-6 flex justify-end gap-3"><button type="button" autoFocus disabled={busy} onClick={onClose} className={button}>Cancel</button><button type="button" onClick={clear} disabled={busy || !preview || !acknowledged || (categories.includes('history') && confirmation !== 'DELETE')} className="min-h-10 rounded-lg bg-error px-4 text-sm font-bold text-white hover:opacity-90 focus-visible:ring-2 focus-visible:ring-error disabled:cursor-not-allowed disabled:opacity-45">{busy ? 'Clearing…' : 'Clear selected data'}</button></div>
  </dialog>;
}
