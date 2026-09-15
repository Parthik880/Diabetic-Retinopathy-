import assert from 'node:assert/strict';
import { renderToStaticMarkup } from 'react-dom/server';
import { batchProgress, PatientProgressBar } from '../src/batchProgress';

const render = (statuses: string[], progress: string) => statuses.map(status =>
  renderToStaticMarkup(<PatientProgressBar status={status} value={progress} />),
).join('');

for (const progress of ['0/1', '0/2']) {
  const five = render(Array(5).fill('Processing'), progress);
  assert.equal((five.match(/data-progress-state="processing"/g) || []).length, 5);
  assert.doesNotMatch(five, /data-progress-state="queued"/);
}

const firstChunk = render([...Array(115).fill('Processing'), ...Array(35).fill('Queued')], '0/1');
assert.equal((firstChunk.match(/data-progress-state="processing"/g) || []).length, 115);
assert.equal((firstChunk.match(/data-progress-state="queued"/g) || []).length, 35);
const secondChunk = render(Array(35).fill('Processing'), '0/1');
assert.equal((secondChunk.match(/data-progress-state="processing"/g) || []).length, 35);
assert.doesNotMatch(secondChunk, /data-progress-state="queued"/);

assert.deepEqual(batchProgress('Processing', '0/2'), { completed: 0, total: 2, percent: 0, state: 'processing' });
assert.equal(batchProgress('Processing', '1/2').percent, 50);
assert.equal(batchProgress('Completed', '2/2').percent, 100);
assert.deepEqual(batchProgress('Failed', '0/2'), { completed: 0, total: 2, percent: 0, state: 'failed' });

console.log('batchProgress: 5 single-eye, 5 paired-eye, 115+35 chunking, 0/2 active, 1/2, 2/2, and failed states passed');
