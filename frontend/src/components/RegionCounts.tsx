import type { AnalysisResult } from '../api';

export function RegionCounts({ result, displayed, selection }: { result?: AnalysisResult; displayed?: number; selection?: string }) {
  const output = result?.lesions;
  const count = output?.displayed_region_count ?? (output ? Object.values(output.lesions).reduce((sum, item) => sum + item.regions.length, 0) : null);
  return <div data-testid="region-counts" className="text-sm">
    <p className="font-bold">{displayed != null ? `${displayed} regions displayed · ${selection}` : 'Predicted Lesion Regions'}</p>
    <p className="text-xs text-on-surface-variant mt-1">{count ?? 'Not assessed'}{count != null && (output?.postprocessing ? ' retained after post-processing' : ' predicted regions; post-processing unavailable for this older run')}</p>
    <p className="text-xs text-on-surface-variant mt-1">{output?.raw_region_count != null
      ? `${output.raw_region_count} raw connected regions before size, proximity and region-score rules.`
      : output ? 'Raw component count is unavailable for this older run. Analyze again for post-processing.' : 'Run analysis to generate region counts.'}</p>
    <p className="text-xs text-on-surface-variant mt-1">Model predictions require clinician interpretation.</p>
  </div>;
}
