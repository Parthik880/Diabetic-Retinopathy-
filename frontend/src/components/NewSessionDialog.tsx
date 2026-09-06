import { useEffect, useRef } from 'react';

interface NewSessionDialogProps {
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}

export function NewSessionDialog({ saving, error, onCancel, onConfirm }: NewSessionDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, saving]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !saving) onCancel(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="new-session-title" aria-describedby="new-session-description" className="w-full max-w-md rounded-2xl bg-surface-container-lowest p-6 shadow-[0_20px_60px_rgba(20,32,24,0.24)] ring-1 ring-outline-variant">
        <div className="flex items-start gap-3">
          <span className="material-symbols-outlined rounded-xl bg-primary/10 p-2 text-primary" aria-hidden="true">restart_alt</span>
          <div className="min-w-0">
            <h2 id="new-session-title" className="font-headline text-xl font-extrabold tracking-[-0.025em] text-on-surface">Start a new session?</h2>
            <p id="new-session-description" className="mt-2 text-sm leading-6 text-on-surface-variant">The current scan session will be saved to History before a new session is created.</p>
          </div>
        </div>
        {error && <p role="alert" className="mt-4 rounded-xl bg-error-container px-4 py-3 text-sm font-semibold text-error">{error} The current session was not reset.</p>}
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" disabled={saving} onClick={onCancel} className="min-h-10 rounded-lg border border-outline px-4 text-sm font-bold text-on-surface transition-colors hover:bg-surface-container-low disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">Cancel</button>
          <button ref={confirmRef} type="button" disabled={saving} onClick={onConfirm} className="min-h-10 rounded-lg bg-primary px-4 text-sm font-bold text-on-primary shadow-[0_3px_12px_rgba(0,82,39,0.2)] transition-colors hover:bg-primary-container disabled:cursor-wait disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">{saving ? 'Saving session…' : 'Start New Session'}</button>
        </div>
      </section>
    </div>
  );
}
