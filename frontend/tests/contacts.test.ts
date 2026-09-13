import assert from 'node:assert/strict';
import { normalizeEmail, normalizePhone } from '../src/contacts';
import { createNewSession } from '../src/sessionWorkflow';
import { resetPatient, persistHistory } from '../src/api';
import { SAMPLE_PATIENTS } from '../src/data/samplePatients';

assert.equal(normalizePhone(' +91 (98765) 43210 '), '+919876543210');
assert.equal(normalizePhone('98765-43210'), '9876543210');
assert.equal(normalizeEmail(' test@example.com '), 'test@example.com');
for (const normalize of [normalizeEmail, normalizePhone]) assert.equal(normalize('  '), '');
for (const invalid of ['123', '+12+3456789', 'abc9876543', '1234567890123456']) assert.throws(() => normalizePhone(invalid));
for (const invalid of ['test', 'test@', 'x@y.com?bcc=z', 'test @example.com']) assert.throws(() => normalizeEmail(invalid));
const patient = resetPatient({ ...SAMPLE_PATIENTS[0], phone: '+919876543210', email: 'test@example.com' });
assert.equal(createNewSession(patient).phone, patient.phone);
assert.equal(createNewSession(patient).email, patient.email);
let saved: any;
globalThis.fetch = async (_url, options) => {
  saved = JSON.parse(options!.body as string);
  return new Response(JSON.stringify({ record: saved }), { status: 200 });
};
await persistHistory(patient);
assert.equal(saved.patient.email, patient.email);
assert.equal(saved.patient.phone, patient.phone);
console.log('contacts: optional/invalid values, normalization, new sessions and history metadata passed');
