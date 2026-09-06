import { TOP_K_OPTIONS, topKLabel, type TopK } from '../regionSelection';

export function TopKSelector({ value, onChange, disabled = false, label = 'Regions shown' }: {
  value: TopK; onChange: (value: TopK) => void; disabled?: boolean; label?: string;
}) {
  return <label className="flex items-center gap-2 text-xs font-semibold">
    {label}
    <select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value === 'all' ? 'all' : Number(event.target.value) as TopK)}
      className="border border-outline rounded-lg bg-surface-container-lowest px-3 py-2 disabled:opacity-50">
      {TOP_K_OPTIONS.map(k => <option key={k} value={k}>{topKLabel(k)}</option>)}
    </select>
  </label>;
}
