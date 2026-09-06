import assert from 'node:assert/strict';
import { selectRegions } from '../frontend/src/regionSelection';
import type { AnomalyItem } from '../frontend/src/types';

const region = (id: string, meanProbability: number, shortCode = 'HE') => ({ id, meanProbability, confidence: Math.round(meanProbability * 1000) / 10, shortCode, coordinates: { x: 12 } }) as AnomalyItem;
const data = [region('HE-2', .89101), region('HE-1', .89104), region('MA-1', .95, 'MA'), ...Array.from({length:60},(_,i)=>region(`EX-${i}`, .8-i/100,'EX'))];
const original = JSON.stringify(data);
for (const k of [5,10,20,25,50,'all'] as const) {
  const selected = selectRegions(data,k);
  assert.equal(selected.length,k==='all'?data.length:k);
  assert.equal(selected[0].id,'MA-1');
  assert.equal(selected[1].id,'HE-1'); // full precision, not rounded UI percentage
  assert.equal(selected[2].id,'HE-2');
  assert.ok(selected.every(r=>data.includes(r))); // same objects, IDs and coordinates
}
assert.equal(selectRegions(data,50,'HE').length,2);
assert.equal(selectRegions(data,25,'MA').length,1);
assert.equal(selectRegions(data,25,'SE').length,0);
assert.deepEqual(selectRegions([region('HE-2',.9),region('HE-1',.9)],5).map(r=>r.id),['HE-1','HE-2']);
assert.equal(JSON.stringify(data),original);
assert.deepEqual(selectRegions([],25),[]);
console.log('Top-K tests passed: all options, exact score order, ties, class-before-ranking, undersupply, stable identity, no mutation.');
