import { useEffect, useRef, useState } from 'react';
import type { PatientRecord } from '../types';
import { loadPatient, saveReport } from '../api';

const actionClass = 'shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary hover:bg-primary-container focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';

export function SendReportModal({ patient, onClose }: { patient: PatientRecord; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [pdf, setPdf] = useState('');
  const [manualCopy, setManualCopy] = useState('');
  const [contact, setContact] = useState<PatientRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const phone = contact?.phone?.trim() || '';
  const email = contact?.email?.trim() || '';
  const message = `Your RetinaGram screening report (${patient.patientIdNumber}, ${patient.activeEye === 'OS' ? 'left' : 'right'} eye) is ready. Please contact the clinic for your PDF and consult a qualified clinician for interpretation.`;

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);

  useEffect(() => {
    let active = true;
    loadPatient(patient.id).then(value => { if (active) setContact(value); })
      .catch(() => { if (active) setNotice('Local patient database unavailable. Contact actions are disabled until you reopen this dialog with the database available.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [patient.id]);

  const copy = async (text: string, success: string) => {
    setBusy(true);
    setManualCopy('');
    try {
      if (window.retinaDesktop) {
        if (!(await window.retinaDesktop.copyText(text)).copied) throw new Error('Clipboard unavailable.');
      } else { await navigator.clipboard.writeText(text); }
      setNotice(success);
    }
    catch { setManualCopy(text); setNotice('Clipboard unavailable. Select and copy the text below.'); }
    finally { setBusy(false); }
  };

  const sendEmail = async () => {
    if (!window.retinaDesktop) {
      setNotice('Open RetinaGram desktop to choose a PDF destination and launch your email app.');
      return;
    }
    setBusy(true); setNotice('Choose where to save the report PDF.'); setManualCopy('');
    try {
      const currentContact = await loadPatient(patient.id);
      setContact(currentContact);
      if (!currentContact.email) { setContact(currentContact); setNotice('No email registered'); return; }
      // Always export the selected eye's current report; never attach a stale PDF.
      const destination = await window.retinaDesktop.chooseReportFolder();
      if (!destination) { setNotice('Export cancelled. No email app was opened.'); return; }
      setNotice('Saving report PDF…');
      const exported = await saveReport(patient, patient.activeEye, destination);
      setPdf(exported.report);
      const opened = await window.retinaDesktop.openCommunication({
        action: 'email', recipient: currentContact.email,
        subject: `RetinaGram Screening Report - ${patient.patientIdNumber}`,
        body: 'Your RetinaGram retinal screening report is ready. Please review the attached/exported report and consult a qualified clinician for medical interpretation.',
      });
      setNotice(opened.opened
        ? 'Email app requested. Attach the saved PDF manually, review the recipient, then send. Nothing was sent by RetinaGram.'
        : 'Windows could not open an email app. Open your preferred app, address it to the email above, and attach the saved PDF manually.');
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Report preparation failed. Please retry.'); }
    finally { setBusy(false); }
  };

  const call = async () => {
    setBusy(true); setManualCopy('');
    try {
      const currentContact = await loadPatient(patient.id);
      setContact(currentContact);
      if (!currentContact.phone) { setNotice('No phone number registered'); return; }
      const opened = await window.retinaDesktop?.openCommunication({ action: 'call', recipient: currentContact.phone });
      setNotice(opened?.opened
        ? 'Call app requested. If no app appears, copy the number below and dial manually. RetinaGram has not placed a call.'
        : 'No calling app could be opened. Copy the number below and dial using your phone.');
    } catch { setNotice('Patient contacts could not be verified. Local patient database unavailable. Reopen this dialog to retry.'); }
    finally { setBusy(false); }
  };

  const sendSms = async () => {
    setBusy(true);
    try {
      const currentContact = await loadPatient(patient.id);
      setContact(currentContact);
      if (!currentContact.phone) { setNotice('No phone number registered'); return; }
      await copy(message, 'Message copied. Send it using your preferred messaging service.');
    } catch { setNotice('Patient contacts could not be verified. Local patient database unavailable. Reopen this dialog to retry.'); }
    finally { setBusy(false); }
  };

  return <dialog ref={dialog} aria-labelledby="send-report-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}
    className="no-print fixed inset-0 m-auto w-[560px] max-w-[calc(100%-48px)] max-h-[85vh] overflow-y-auto rounded-2xl border border-outline-variant bg-surface-container-lowest p-6 text-on-surface shadow-xl backdrop:bg-black/50">
    <header className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h2 id="send-report-title" className="font-headline text-xl font-extrabold">Send report</h2>
        <p className="mt-1 break-words text-sm text-on-surface-variant">{contact?.name || patient.name} · {contact?.patientIdNumber || patient.patientIdNumber} · {patient.activeEye === 'OS' ? 'Left eye' : 'Right eye'}</p>
      </div>
      <button type="button" autoFocus onClick={onClose} disabled={busy} aria-label="Close send report" className="rounded-lg p-2 hover:bg-surface-container-low focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50">
        <span className="material-symbols-outlined" aria-hidden="true">close</span>
      </button>
    </header>
    {loading && <p role="status" className="mt-3 text-sm text-on-surface-variant">Loading patient contacts from the local database…</p>}
    <div className="mt-5 divide-y divide-outline-variant">
      <section className="flex items-center justify-between gap-5 py-4">
        <div className="min-w-0"><h3 className="text-sm font-bold">Email</h3><p className="mt-1 break-all text-sm text-on-surface-variant">{email || 'No email registered'}</p></div>
        <button type="button" disabled={busy || !email} className={actionClass} onClick={sendEmail}>Send via Email</button>
      </section>
      <section className="flex items-center justify-between gap-5 py-4">
        <div className="min-w-0"><h3 className="text-sm font-bold">SMS</h3><p className="mt-1 break-all text-sm text-on-surface-variant">{phone || 'No phone number registered'}</p><p className="mt-1 text-xs text-on-surface-variant">Copies a short message; does not send.</p></div>
        <button type="button" disabled={busy || !phone} className={actionClass} onClick={sendSms}>Send via SMS</button>
      </section>
      <section className="flex items-center justify-between gap-5 py-4">
        <div className="min-w-0"><h3 className="text-sm font-bold">Call patient</h3><p className="mt-1 break-all text-base font-bold">{phone || 'No phone number registered'}</p>
          {phone && <button type="button" disabled={busy} onClick={() => copy(phone, 'Number copied. Dial using your preferred phone or calling app.')} className="mt-2 rounded text-sm font-bold text-primary underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50">Copy number</button>}
        </div>
        <button type="button" disabled={busy || !phone} className={actionClass} onClick={call}>Inform via Call</button>
      </section>
    </div>
    <p className="mt-3 text-xs leading-5 text-on-surface-variant">Email saves the PDF first, then requests your default mail app. You must attach it manually. No email, SMS, or call delivery service is configured.</p>
    {pdf && <div className="mt-4 rounded-lg border border-outline-variant p-3 text-sm"><p className="font-bold">Saved PDF — attach manually</p><p className="mt-1 select-all break-all">{pdf}</p></div>}
    {notice && <p role="status" aria-live="polite" className="mt-4 rounded-lg bg-surface-container-low p-3 text-sm leading-6">{notice}</p>}
    {manualCopy && <label className="mt-3 block text-sm font-bold">Copy manually<textarea readOnly rows={4} value={manualCopy} onFocus={event => event.target.select()} className="mt-1 w-full rounded-lg border border-outline p-3 text-sm font-normal focus:ring-2 focus:ring-primary" /></label>}
  </dialog>;
}
