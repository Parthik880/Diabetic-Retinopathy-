import { useEffect, useRef, type ReactNode } from 'react';

export function DataDialog({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);
  return <dialog ref={dialog} aria-labelledby="data-dialog-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} className="m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-lg overflow-y-auto rounded-2xl bg-surface-container-lowest p-6 text-on-surface shadow-xl backdrop:bg-black/40">
    <div className="mb-5 flex items-center justify-between gap-4">
      <h2 id="data-dialog-title" className="font-headline text-xl font-extrabold">{title}</h2>
      <button type="button" autoFocus disabled={busy} aria-label="Close dialog" onClick={onClose} className="flex h-10 w-10 items-center justify-center rounded-lg hover:bg-surface-container-low focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"><span className="material-symbols-outlined" aria-hidden="true">close</span></button>
    </div>
    {children}
  </dialog>;
}
