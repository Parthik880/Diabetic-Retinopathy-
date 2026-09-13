const { test } = require('node:test');
const assert = require('node:assert/strict');
const { communicationUrl, openCommunication } = require('../communication.cjs');

test('email encodes recipient, subject and body without adding headers', () => {
  const url = new URL(communicationUrl({ action: 'email', recipient: 'test@example.com', subject: 'Report & review', body: 'Line 1\nLine 2 & cc=nobody' }));
  assert.equal(url.protocol, 'mailto:');
  assert.equal(decodeURIComponent(url.pathname), 'test@example.com');
  assert.equal(url.searchParams.get('subject'), 'Report & review');
  assert.equal(url.searchParams.get('body'), 'Line 1\nLine 2 & cc=nobody');
  assert.equal(url.searchParams.size, 2);
});

test('call accepts Indian/international and local numbers only', () => {
  assert.equal(communicationUrl({ action: 'call', recipient: '+919876543210' }), 'tel:+919876543210');
  assert.equal(communicationUrl({ action: 'call', recipient: '9876543210' }), 'tel:9876543210');
  for (const recipient of ['', '+91;123', 'javascript:alert(1)', '+919876543210?foo=bar']) {
    assert.throws(() => communicationUrl({ action: 'call', recipient }));
  }
});

test('arbitrary URL, SMS, header injection and invalid input never reach the shell', async () => {
  for (const request of [null, {}, { action: 'open', recipient: 'file:///c:/windows' },
    { action: 'sms', recipient: '+919876543210' },
    { action: 'email', recipient: 'test@example.com?bcc=other@example.com', subject: '', body: '' },
    { action: 'email', recipient: 'test@example.com', subject: 'x\r\nbcc: other@example.com', body: '' }]) {
    assert.equal((await openCommunication(request, { openExternal: () => assert.fail('Unsafe URL reached shell') })).opened, false);
  }
});

test('reports shell launch request, not delivery, and handles missing handlers', async () => {
  const request = { action: 'call', recipient: '+919876543210' };
  assert.deepEqual(await openCommunication(request, { openExternal: async url => assert.equal(url, 'tel:+919876543210') }), { opened: true });
  assert.equal((await openCommunication(request, { openExternal: async () => { throw new Error('No handler'); } })).opened, false);
});
