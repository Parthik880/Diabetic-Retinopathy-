const assert = require('node:assert/strict');
const { contactUrl } = require('./contact-actions.cjs');
const email = new URL(contactUrl({ kind: 'email', address: 'fixture@example.test', subject: 'Report ready', body: 'Attach the PDF yourself.\nThank you.' }));
assert.equal(email.protocol, 'mailto:');
assert.equal(decodeURIComponent(email.pathname), 'fixture@example.test');
assert.equal(email.searchParams.get('subject'), 'Report ready');
assert.equal(email.searchParams.get('body'), 'Attach the PDF yourself.\nThank you.');
assert.equal(contactUrl({ kind: 'call', address: '+1 (202) 555-0146' }), 'tel:+12025550146');
assert.equal(contactUrl({ kind: 'sms', address: '+1 202 555 0146', body: 'Ready & available' }), 'sms:+12025550146?body=Ready%20%26%20available');
for (const payload of [null, {}, { kind: 'file', address: 'C:/Windows' }, { kind: 'email', address: 'a@b.test?bcc=hidden@x.test' }, { kind: 'email', address: 'a@b.test\r\nBCC:x@y.test' }, { kind: 'call', address: 'javascript:alert(1)' }, { kind: 'sms', address: '' }, { kind: 'call', address: '+---' }]) {
  assert.throws(() => contactUrl(payload));
}
console.log('Contact actions: encoded Email/SMS/Call and unsafe/empty input checks passed; no external apps launched.');
