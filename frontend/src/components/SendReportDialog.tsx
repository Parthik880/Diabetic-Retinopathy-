import { useState } from 'react';
import type { PatientRecord } from '../types';
import { DataDialog } from './DataDialog';

export function SendReportDialog({ patient, onClose }: { patient: PatientRecord; onClose: () => void }) {
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const message = `Hello ${patient.name}, your RetinaGram screening report is ready. Please contact the clinic to receive your report and discuss the results.`;
  const launch = async (kind: 'email' | 'sms' | 'call') => {
    setBusy(true); setNotice('');
    try {
      const opened = await window.retinaDesktop?.contactPatient({ kind, address: kind === 'email' ? patient.email! : patient.phone!, subject: 'Your RetinaGram screening report', body: kind === 'email' ? `${message}\n\nPlease attach the exported PDF before sending.` : message });
      setNotice(opened?.opened ? (kind === 'call' ? 'Call app requested. Complete the call in that app.' : 'Message app requested. Review and send there. The PDF has not been attached.') : 'No compatible app opened. Use the copy action below.');
    } catch { setNotice('The contact app could not be opened. Use the copy action below.'); }
    finally { setBusy(false); }
  };
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); setNotice('Copied to clipboard.'); }
    catch { setNotice('Clipboard is unavailable. Select and copy the text below.'); }
  };
  return <DataDialog title="Send Report" onClose={onClose} busy={busy}>
    <p className="mb-4 text-sm text-on-surface-variant">For {patient.name}. Review the message in your chosen app. Export and attach the PDF yourself.</p>
    <div className="divide-y divide-outline-variant">
      {([
        ['email', 'Send via Email', 'mail', patient.email, 'No email registered'],
        ['sms', 'Send via SMS', 'sms', patient.phone, 'No phone number registered'],
        ['call', 'Inform via Call', 'call', patient.phone, 'No phone number registered'],
      ] as const).map(([kind, label, icon, address, missing]) => <div key={kind} className="py-3">
        <button onClick={() => void launch(kind)} disabled={!address?.trim() || busy} className="flex min-h-11 w-full items-center gap-3 rounded-lg px-2 text-left text-sm font-bold text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:text-on-surface-variant disabled:opacity-60"><span className="material-symbols-outlined" aria-hidden="true">{icon}</span>{label}</button>
        <p className="ml-2 break-all text-xs text-on-surface-variant">{address || missing}</p>
        {address && <button onClick={() => void copy(kind === 'call' ? address : `${address}\n${message}`)} className="ml-2 mt-2 min-h-9 text-xs font-bold text-primary underline underline-offset-4">{kind === 'call' ? 'Copy number' : 'Copy recipient and message'}</button>}
      </div>)}
    </div>
    <details className="mt-4 text-sm"><summary className="cursor-pointer font-bold text-primary">Message preview</summary><p className="mt-2 select-text leading-6">{message}</p></details>
    {notice && <p role="status" className="mt-4 rounded-lg bg-surface-container-low p-3 text-sm">{notice}</p>}
  </DataDialog>;
}
