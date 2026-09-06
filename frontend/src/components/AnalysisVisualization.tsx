import { useEffect, useRef, useState } from 'react';
import type { AnomalyItem, EyeScanData } from '../types';
import { DEFAULT_TOP_K, type TopK } from '../regionSelection';
import { TopKSelector } from './TopKSelector';

export type AnalysisView = 'grade' | 'attention' | 'detection' | 'annotation';
export const VIEW_LABELS: Record<AnalysisView, string> = {
  grade: 'Grade Analysis', attention: 'Lesion Grad-CAM', detection: 'Lesion Detection', annotation: 'Lesion Annotation',
};
export const CLASS_NAMES: Record<string, string> = { MA: 'Microaneurysms', HE: 'Hemorrhages', EX: 'Hard Exudates', SE: 'Soft Exudates' };
export const CLASS_COLORS: Record<string, string> = { MA: '#ff2d2d', HE: '#ff7e22', EX: '#ffe020', SE: '#23d2ff' };
export interface ViewSettings {
  imageMode: 'Original' | 'Grad-CAM' | 'Overlay';
  annotationMode: 'Original' | 'Mask' | 'Overlay';
  detectionMode: 'Boxes' | 'Coordinates';
  attentionType: 'Grad-CAM' | 'Probability';
  lesionClass: string;
  enabledClasses: string[];
  opacity: number;
  rawRegions: boolean;
  topK: TopK;
  regionClass: string;
}
export const INITIAL_SETTINGS: ViewSettings = { imageMode: 'Overlay', annotationMode: 'Overlay', detectionMode: 'Boxes',
  attentionType: 'Grad-CAM', lesionClass: 'HE', enabledClasses: ['MA', 'HE', 'EX', 'SE'], opacity: 0.5, rawRegions: false, topK: DEFAULT_TOP_K, regionClass: 'all' };

export function Segmented({ label, options, value, onChange }: {
  label: string; options: string[]; value: string; onChange: (value: string) => void;
}) {
  return <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1 p-1 rounded-lg border border-outline-variant bg-surface-container-low">
    {options.map(option => <button key={option} type="button" aria-pressed={value === option} onClick={() => onChange(option)}
      className={`px-3 py-2 rounded-md text-xs md:text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${value === option ? 'bg-primary text-on-primary' : 'text-on-surface-variant hover:bg-surface-container-high'}`}>
      {option}
    </button>)}
  </div>;
}

export function VisualizationControls({ view, settings, onChange, availableClasses }: {
  view: AnalysisView; settings: ViewSettings; onChange: (settings: ViewSettings) => void; availableClasses: string[];
}) {
  const update = (value: Partial<ViewSettings>) => onChange({ ...settings, ...value });
  return <div className="flex flex-wrap items-center gap-3" data-testid="visual-controls">
    {view === 'grade' && <Segmented label="Grade image mode" options={['Original', 'Grad-CAM', 'Overlay']} value={settings.imageMode}
      onChange={value => update({ imageMode: value as ViewSettings['imageMode'] })} />}
    {view === 'attention' && <>
      <label className="text-sm flex items-center gap-2">Lesion type
        <select aria-label="Lesion type" value={settings.lesionClass} onChange={e => update({ lesionClass: e.target.value })}
          className="border border-outline rounded-lg bg-surface-container-lowest px-3 py-2 max-w-full">
          {availableClasses.map(code => <option key={code} value={code}>{CLASS_NAMES[code] || code}</option>)}
        </select>
      </label>
      <Segmented label="Lesion visualization mechanism" options={['Grad-CAM', 'Probability']} value={settings.attentionType}
        onChange={value => update({ attentionType: value as ViewSettings['attentionType'] })} />
      <Segmented label="Lesion image mode" options={['Original', settings.attentionType === 'Probability' ? 'Heatmap' : 'Grad-CAM', 'Overlay']}
        value={settings.imageMode === 'Grad-CAM' && settings.attentionType === 'Probability' ? 'Heatmap' : settings.imageMode}
        onChange={value => update({ imageMode: (value === 'Heatmap' ? 'Grad-CAM' : value) as ViewSettings['imageMode'] })} />
    </>}
    {view === 'detection' && <Segmented label="Detection mode" options={['Boxes', 'Coordinates']} value={settings.detectionMode}
      onChange={value => update({ detectionMode: value as ViewSettings['detectionMode'] })} />}
    {view === 'detection' && <label className="flex items-center gap-2 text-xs font-semibold">
      <input type="checkbox" aria-label="View all raw model regions" checked={settings.rawRegions} className="accent-primary w-4 h-4"
        onChange={e => update({ rawRegions: e.target.checked })} />View all raw model regions
    </label>}
    {view === 'detection' && <>
      <label className="flex items-center gap-2 text-xs font-semibold">Lesion class
        <select aria-label="Region class" value={settings.regionClass} disabled={settings.rawRegions}
          onChange={e => update({ regionClass: e.target.value })} className="border border-outline rounded-lg bg-surface-container-lowest px-3 py-2 disabled:opacity-50">
          <option value="all">All classes</option>
          {availableClasses.map(code => <option key={code} value={code}>{CLASS_NAMES[code] || code}</option>)}
        </select>
      </label>
      <TopKSelector value={settings.topK} onChange={topK => update({ topK })} disabled={settings.rawRegions} />
      {settings.rawRegions && <p className="text-xs">Raw model output: all raw components; Top-K and class filtering bypassed.</p>}
    </>}
    {view === 'annotation' && <>
      <Segmented label="Annotation image mode" options={['Original', 'Mask', 'Overlay']} value={settings.annotationMode}
        onChange={value => update({ annotationMode: value as ViewSettings['annotationMode'] })} />
      <div role="group" aria-label="Visible lesion masks" className="flex flex-wrap gap-x-4 gap-y-2">
        {availableClasses.map(code => <label key={code} className="flex items-center gap-1.5 text-xs font-semibold cursor-pointer">
          <input type="checkbox" className="accent-primary w-4 h-4" checked={settings.enabledClasses.includes(code)}
            onChange={e => update({ enabledClasses: e.target.checked ? [...settings.enabledClasses, code] : settings.enabledClasses.filter(c => c !== code) })} />
          {CLASS_NAMES[code] || code}
        </label>)}
      </div>
    </>}
    {view !== 'detection' && <label className="inline-flex items-center gap-2 text-xs font-semibold whitespace-nowrap">
      Overlay opacity
      <input aria-label="Overlay opacity" type="range" min="0" max="100" value={Math.round(settings.opacity * 100)}
        className="w-24 accent-primary" onChange={e => update({ opacity: Number(e.target.value) / 100 })} />
      <span className="w-8 tabular-nums">{Math.round(settings.opacity * 100)}%</span>
    </label>}
  </div>;
}

export function AnalysisVisualization({ scan, view, settings, lesions, selectedId, onSelect, compact = false }: {
  scan: EyeScanData; view: AnalysisView; settings: ViewSettings; lesions: AnomalyItem[];
  selectedId?: string | null; onSelect?: (id: string | null) => void; compact?: boolean;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const imagePlane = useRef<HTMLDivElement>(null);
  const [bounds, setBounds] = useState({ width: 1, height: 1 });
  const [natural, setNatural] = useState({ width: 1, height: 1 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number } | null>(null);
  const [failedLayers, setFailedLayers] = useState<string[]>([]);
  const result = scan.result;
  const width = result?.image_width || natural.width;
  const height = result?.image_height || natural.height;
  const scale = Math.min(bounds.width / width, bounds.height / height);
  const selected = lesions.find(lesion => lesion.id === selectedId);
  const highlighted = lesions.find(lesion => lesion.id === (hovered || selectedId));
  const channel = result?.lesions?.lesions[settings.lesionClass];
  const attention = view === 'grade' ? result?.grading?.gradcam
    : settings.attentionType === 'Grad-CAM' ? channel?.attention : channel?.probability_heatmap;
  const overlayMode = view === 'annotation' ? settings.annotationMode : settings.imageMode;
  const showOriginal = view === 'detection' || overlayMode === 'Original' || overlayMode === 'Overlay';
  const source = result?.analysis_image_url || result?.image_url || scan.imageUrl;
  const coordinates = view === 'detection' && settings.detectionMode === 'Coordinates';
  const showAttention = (view === 'grade' || view === 'attention') && overlayMode !== 'Original';
  const showMasks = view === 'annotation' && overlayMode !== 'Original';
  const note = view === 'grade' ? 'Grade Grad-CAM: relative influence on the predicted DR class; not a probability map.'
    : view === 'attention' ? settings.attentionType === 'Grad-CAM'
      ? 'Segmentation Grad-CAM: mean class-channel logit over the predicted mask pixels.'
      : 'Segmentation probability: independent sigmoid probability at each pixel. This is not Grad-CAM.'
    : view === 'detection' ? `${settings.rawRegions ? 'Raw model output before region processing.' : 'Regions retained after post-processing.'} Boxes are derived from segmentation. Scores are mean pixel probabilities, not clinical confidence or severity.`
    : 'Predicted segmentation masks, not manual or ground-truth annotations. Layers use original image pixels.';
  const unavailable = !result ? 'No analysis for this eye. Capture a scan and run analysis.'
    : showAttention && !attention ? view === 'grade' ? 'Grade Grad-CAM is unavailable for this run. Analyze this eye again to generate it.'
      : settings.attentionType === 'Grad-CAM' ? channel?.attention_unavailable_reason || 'Lesion Grad-CAM is unavailable for this class or run.'
      : 'Segmentation probability map is unavailable for this class or run.'
    : showMasks && (!result.lesions || Object.values(result.lesions.lesions).some(item => !item.mask_layer_path))
      ? 'Browser mask layers are unavailable for this run. Analyze this eye again.' : null;

  useEffect(() => {
    if (!stage.current) return;
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect; setBounds({ width, height });
    });
    observer.observe(stage.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { setCursor(null); setHovered(null); setFailedLayers([]); }, [scan.eye, result?.run_id, source]);

  const recordPoint = (event: React.PointerEvent) => {
    if (!coordinates || !imagePlane.current || !result) return;
    const rect = imagePlane.current.getBoundingClientRect();
    setCursor({ x: Math.min(width - 1, Math.max(0, Math.floor((event.clientX - rect.left) / rect.width * width))),
      y: Math.min(height - 1, Math.max(0, Math.floor((event.clientY - rect.top) / rect.height * height))) });
  };
  const failLayer = (path: string) => setFailedLayers(prev => prev.includes(path) ? prev : [...prev, path]);
  const ticksX = Array.from({ length: 5 }, (_, i) => Math.round((width - 1) * i / 4));
  const ticksY = Array.from({ length: 5 }, (_, i) => Math.round((height - 1) * i / 4));
  const fontSize = width / (compact ? 28 : 42);

  return <div className="flex flex-col gap-3 min-w-0" data-testid={`visualization-${scan.eye}`} data-view={view} data-run-id={result?.run_id || ''}>
    <div ref={stage} className="relative w-full aspect-[4/3] bg-black rounded-xl border-2 border-outline overflow-hidden" data-testid={`image-stage-${scan.eye}`}>
      <div ref={imagePlane} className="absolute" data-testid={`image-plane-${scan.eye}`} data-original-width={width} data-original-height={height}
        style={{ width: width * scale, height: height * scale, left: (bounds.width - width * scale) / 2, top: (bounds.height - height * scale) / 2 }}
        onPointerMove={recordPoint} onPointerDown={recordPoint}>
        {source && <img src={source} alt={`${scan.eye} original retinal image`} onLoad={e => setNatural({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
          onError={() => failLayer(source)} draggable={false} className="absolute inset-0 w-full h-full" style={{ opacity: showOriginal ? 1 : 0 }} />}
        {showAttention && attention && !failedLayers.includes(attention.heatmap_path) && <img src={attention.heatmap_path}
          data-testid={`attention-layer-${scan.eye}`} alt={`${scan.eye} ${view === 'grade' ? 'grade Grad-CAM' : settings.attentionType === 'Grad-CAM' ? 'segmentation Grad-CAM' : 'segmentation probability'} layer`}
          onError={() => failLayer(attention.heatmap_path)} className="absolute inset-0 w-full h-full pointer-events-none" draggable={false}
          style={{ opacity: overlayMode === 'Overlay' ? settings.opacity : 1 }} />}
        {showMasks && Object.entries(result?.lesions?.lesions || {}).filter(([code]) => settings.enabledClasses.includes(code)).map(([code, output]) =>
          output.mask_layer_path && !failedLayers.includes(output.mask_layer_path) && <img key={code} src={output.mask_layer_path}
            data-testid={`mask-layer-${scan.eye}-${code}`} alt={`${scan.eye} ${CLASS_NAMES[code]} predicted mask`}
            className="absolute inset-0 w-full h-full pointer-events-none" style={{ opacity: overlayMode === 'Overlay' ? settings.opacity : 1, imageRendering: 'pixelated' }}
            onError={() => failLayer(output.mask_layer_path)} draggable={false} />)}
        {view === 'detection' && result && <svg className="absolute inset-0 w-full h-full" viewBox={`0 0 ${width} ${height}`} aria-label="Original image coordinates and predicted regions">
          {coordinates && <g pointerEvents="none">
            {ticksX.map(x => <g key={`x-${x}`}><line x1={x} y1={0} x2={x} y2={height} stroke="#9bf6b1" strokeOpacity="0.55" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <text x={Math.min(Math.max(x + fontSize / 3, fontSize / 3), width - fontSize * 3)} y={fontSize} fill="white" stroke="black" strokeWidth={fontSize / 10} paintOrder="stroke" fontSize={fontSize}>X {x}</text></g>)}
            {ticksY.slice(1).map(y => <g key={`y-${y}`}><line x1={0} y1={y} x2={width} y2={y} stroke="#9bf6b1" strokeOpacity="0.55" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <text x={fontSize / 3} y={Math.min(y - fontSize / 3, height - fontSize / 3)} fill="white" stroke="black" strokeWidth={fontSize / 10} paintOrder="stroke" fontSize={fontSize}>Y {y}</text></g>)}
          </g>}
          {lesions.map(lesion => <g key={lesion.id}>
            <rect x={lesion.coordinates.x} y={lesion.coordinates.y} width={lesion.coordinates.w} height={lesion.coordinates.h}
              role="button" tabIndex={0} aria-label={`${lesion.shortCode} region ${lesion.id}`} aria-pressed={selectedId === lesion.id}
              data-region-id={lesion.id} onClick={e => { e.stopPropagation(); onSelect?.(selectedId === lesion.id ? null : lesion.id); }}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect?.(lesion.id); } }}
              onPointerEnter={() => setHovered(lesion.id)} onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(lesion.id)} onBlur={() => setHovered(null)}
              fill={selectedId === lesion.id ? '#ffffff33' : 'transparent'} stroke={selectedId === lesion.id ? '#ffffff' : CLASS_COLORS[lesion.shortCode] || lesion.color}
              strokeWidth={selectedId === lesion.id || hovered === lesion.id ? 3 : 1.2} vectorEffect="non-scaling-stroke" className="cursor-pointer focus:outline-none" />
            {coordinates && selectedId === lesion.id && <circle cx={lesion.coordinates.centerX} cy={lesion.coordinates.centerY} r={width / 180} fill="white" stroke="black" vectorEffect="non-scaling-stroke" />}
          </g>)}
          {cursor && coordinates && <g pointerEvents="none" stroke="white" strokeWidth="1" vectorEffect="non-scaling-stroke">
            <line x1={cursor.x - width / 70} y1={cursor.y} x2={cursor.x + width / 70} y2={cursor.y} />
            <line x1={cursor.x} y1={cursor.y - width / 70} x2={cursor.x} y2={cursor.y + width / 70} />
          </g>}
        </svg>}
        {view === 'detection' && highlighted && <div className="absolute pointer-events-none text-xs font-bold text-white bg-black/90 border border-white/60 rounded px-2 py-1 max-w-[90%]"
          style={{ left: `${Math.min(highlighted.coordinates.leftPct, 60)}%`, top: `${Math.max(0, highlighted.coordinates.topPct - 6)}%` }}>
          {highlighted.shortCode} · {highlighted.confidence}% mean probability
        </div>}
      </div>
      {(unavailable || !source) && <div role="status" className="absolute inset-x-4 bottom-4 rounded-lg bg-black/85 text-white p-3 text-sm">
        {unavailable || 'No retinal image has been selected.'}
      </div>}
    </div>
    {failedLayers.length > 0 && <p role="alert" className="text-sm text-error">An image layer could not be loaded. The run may no longer be available; analyze this eye again.</p>}
    <p className="text-xs text-on-surface-variant leading-relaxed">{note}</p>
    {view === 'detection' && settings.rawRegions && !Object.values(result?.lesions?.lesions || {}).some(item => item.raw_regions) && <p role="status" className="text-xs">Raw model regions are unavailable for this run. Analyze this eye again.</p>}
    {(view === 'grade' || view === 'attention') && <div className="flex items-center gap-3 text-xs text-on-surface-variant">
      <span>{view === 'attention' && settings.attentionType === 'Probability' ? '0 probability' : 'Low attention'}</span>
      <div className="h-2 flex-1 rounded-full heatmap-gradient border border-outline-variant" />
      <span>{view === 'attention' && settings.attentionType === 'Probability' ? '1 probability' : 'High attention'}</span>
    </div>}
    {view === 'annotation' && <div className="flex flex-wrap gap-3 text-xs">
      {Object.keys(result?.lesions?.lesions || {}).map(code => <span key={code} className="flex items-center gap-1.5">
        <span className="w-3 h-3 inline-block rounded-sm border border-outline" style={{ backgroundColor: CLASS_COLORS[code] }} />{code}</span>)}
      <span className="text-on-surface-variant">Mask threshold {result?.lesions?.threshold ?? 'unavailable'} · {result?.lesions?.postprocessing ? 'full mask, unaffected by display-region filters' : 'legacy mask; analyze again for full raw output'}</span>
      {settings.enabledClasses.length === 0 && <span>No mask classes selected.</span>}
    </div>}
    {view === 'detection' && <div className="bg-surface-container-low border border-outline-variant rounded-lg p-4 text-sm" data-testid={`region-details-${scan.eye}`}>
      <div className="flex flex-wrap justify-between gap-2 mb-2"><strong>{selected ? `${selected.name} · ${scan.eye}` : 'Select a predicted region'}</strong>
        {selected && <button onClick={() => onSelect?.(null)} className="text-primary font-bold text-xs underline underline-offset-2">Clear selection</button>}</div>
      <p className="text-xs text-on-surface-variant">Image resolution: {result ? `${width} × ${height} px` : 'Unavailable'} · origin at top left</p>
      {coordinates && <p className="text-xs tabular-nums mt-1" data-testid={`cursor-${scan.eye}`}>{cursor ? `Pointer X: ${cursor.x} · Y: ${cursor.y}` : 'Move over the image to inspect original-pixel coordinates.'}</p>}
      {selected && <dl className="grid grid-cols-2 gap-x-4 gap-y-2 mt-3 text-xs tabular-nums">
        <div><dt className="text-on-surface-variant">Mean pixel probability</dt><dd className="font-bold">{selected.confidence}%</dd></div>
        <div><dt className="text-on-surface-variant">Center (original pixels)</dt><dd className="font-bold">X: {selected.coordinates.centerX} · Y: {selected.coordinates.centerY}</dd></div>
        <div><dt className="text-on-surface-variant">Inclusive bounding region</dt><dd className="font-bold">X1: {selected.coordinates.x} · Y1: {selected.coordinates.y}<br />X2: {selected.coordinates.x2} · Y2: {selected.coordinates.y2}</dd></div>
        <div><dt className="text-on-surface-variant">Region dimensions</dt><dd className="font-bold">W: {selected.coordinates.w} · H: {selected.coordinates.h}</dd></div>
        <div><dt className="text-on-surface-variant">Component area</dt><dd className="font-bold">{selected.areaPixels ?? 'Unavailable'} px</dd></div>
        <div><dt className="text-on-surface-variant">Maximum pixel probability</dt><dd className="font-bold">{selected.maxProbability == null ? 'Unavailable' : `${(selected.maxProbability * 100).toFixed(1)}%`}</dd></div>
        {selected.sourceComponentIds && <div className="col-span-2"><dt className="text-on-surface-variant">Source component IDs</dt><dd>{selected.sourceComponentIds.join(', ')}</dd></div>}
      </dl>}
    </div>}
  </div>;
}
