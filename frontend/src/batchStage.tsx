export function GlobalBatchStage({ index, total, label, percent }: {
  index: number; total: number; label: string; percent: number;
}) {
  return <div className="mt-4 rounded-xl border border-primary/20 bg-surface-container-lowest p-4">
    <div className="flex items-end justify-between gap-4">
      <div>
        <p className="text-xs font-extrabold uppercase tracking-[0.08em] text-primary">Stage {index} of {total}</p>
        <p className="mt-1 font-headline text-lg font-extrabold text-on-surface">{label}</p>
      </div>
      <span className="font-headline text-2xl font-extrabold tabular-nums text-primary">{percent}%</span>
    </div>
    <div role="progressbar" aria-label={`Batch pipeline: ${label}`} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={percent} data-batch-stage={index}
      className="mt-3 h-2.5 overflow-hidden rounded-full bg-primary/12">
      <span className="block h-full bg-primary" style={{ width: `${percent}%` }} />
    </div>
  </div>;
}
