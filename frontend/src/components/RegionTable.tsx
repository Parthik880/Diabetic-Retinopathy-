import type { AnomalyItem } from '../types';

export function RegionTable({ regions }: { regions: AnomalyItem[] }) {
  return <div className="region-table overflow-x-auto"><table className="w-full text-left text-xs border border-outline-variant">
    <thead className="bg-surface-container border-b border-outline-variant font-bold"><tr>
      <th className="p-2.5">Region / type</th><th className="p-2.5">[X, Y, W, H] px</th>
      <th className="p-2.5">Area px</th><th className="p-2.5">Mean probability</th>
    </tr></thead>
    <tbody className="divide-y divide-outline-variant">
      {regions.map(region => <tr key={region.id} className="break-inside-avoid">
        <td className="p-2.5"><span className="font-semibold">{region.name}</span><span className="block text-on-surface-variant">{region.id}</span></td>
        <td className="p-2.5 tabular-nums">[{region.coordinates.x}, {region.coordinates.y}, {region.coordinates.w}, {region.coordinates.h}]</td>
        <td className="p-2.5 tabular-nums">{region.areaPixels ?? 'Unavailable'}</td>
        <td className="p-2.5 font-bold text-primary tabular-nums">{region.confidence}%</td>
      </tr>)}
      {!regions.length && <tr><td colSpan={4} className="p-3">No retained regions for this eye.</td></tr>}
    </tbody>
  </table></div>;
}
