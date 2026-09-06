import type { AnomalyItem } from './types';

export type TopK = 5 | 10 | 20 | 25 | 50 | 'all';
export const DEFAULT_TOP_K: TopK = 25;
export const TOP_K_OPTIONS: TopK[] = [5, 10, 20, 25, 50, 'all'];
export const topKLabel = (value: TopK) => value === 'all' ? 'All filtered' : `Top ${value}`;
export const regionScore = (region: AnomalyItem) => region.meanProbability ?? region.confidence / 100;

/** Shared by boxes, coordinates, region cards and report. Never mutates predictions. */
export function selectRegions(regions: AnomalyItem[], topK: TopK, regionClass = 'all') {
  const ranked = regions.filter(region => regionClass === 'all' || region.shortCode === regionClass)
    .sort((a, b) => regionScore(b) - regionScore(a) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return topK === 'all' ? ranked : ranked.slice(0, topK);
}
