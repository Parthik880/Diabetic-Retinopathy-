export type BatchProgressState = 'queued' | 'processing' | 'completed' | 'failed' | 'warning';

export function batchProgress(status: string, value: string) {
  const match = /^(\d+)\/(\d+)$/.exec(value);
  const completed = match ? Number(match[1]) : 0;
  const total = match ? Number(match[2]) : 0;
  const percent = total > 0 ? Math.min(100, Math.floor(completed * 100 / total)) : 0;
  const state: BatchProgressState = status === 'Processing' || status === 'Finalizing' ? 'processing'
    : status === 'Completed' ? 'completed'
    : status === 'Failed' ? 'failed'
    : status === 'Recapture Required' || status === 'Skipped' ? 'warning'
    : 'queued';
  return { completed, total, percent, state };
}

export function PatientProgressBar({ status, value }: { status: string; value: string }) {
  const progress = batchProgress(status, value);
  const shell = progress.state === 'processing' || progress.state === 'completed'
    ? 'border-primary/45 bg-primary/10'
    : progress.state === 'failed' ? 'border-error/45 bg-error-container/50'
    : progress.state === 'warning' ? 'border-tertiary/35 bg-tertiary-fixed/45'
    : 'border-outline-variant bg-surface-container-high';
  const fill = progress.state === 'failed' ? 'bg-error' : progress.state === 'warning' ? 'bg-tertiary' : 'bg-primary';
  return <div
    role="progressbar"
    aria-label={`${status}: ${progress.completed} of ${progress.total} eyes complete`}
    aria-valuemin={0}
    aria-valuemax={100}
    aria-valuenow={progress.percent}
    data-progress-state={progress.state}
    className={`relative h-3 min-w-32 overflow-hidden rounded-full border ${shell}`}
  >
    <span className={`block h-full ${fill}`} style={{ width: `${progress.percent}%` }} />
    {progress.state === 'processing' && progress.percent === 0 && <span aria-hidden="true" className="absolute left-0.5 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-primary" />}
  </div>;
}
