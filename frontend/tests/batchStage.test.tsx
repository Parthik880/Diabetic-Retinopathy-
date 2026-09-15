import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { GlobalBatchStage } from '../src/batchStage';

for (const [index, label, percent] of [
  [1, 'Quality Check', 25],
  [2, 'Restoration / Preparation', 50],
  [3, 'DR + Lesion Analysis', 75],
  [4, 'Finalizing Report', 100],
] as const) {
  const html = renderToStaticMarkup(<GlobalBatchStage index={index} total={4} label={label} percent={percent} />);
  assert.match(html, new RegExp(`data-batch-stage="${index}"`));
  assert.match(html, new RegExp(`aria-valuenow="${percent}"`));
  assert.match(html, new RegExp(label.replace('+', '\\+')));
  assert.equal((html.match(/role="progressbar"/g) || []).length, 1);
}

console.log('batchStage: backend-provided stages render as 25, 50, 75, and 100 percent');
