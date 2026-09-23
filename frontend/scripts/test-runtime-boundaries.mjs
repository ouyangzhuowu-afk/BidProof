import assert from 'node:assert/strict';
import test from 'node:test';
import { assertRunEnvelope, assertDecisionCommand } from '../src/core/validators.js';
import { configureTelemetry, reportDiagnostic, sameOriginSink } from '../src/core/telemetry.js';
import { readPreference, writePreference } from '../src/core/storage.js';

await test('critical task validation rejects a different task, missing revision and invalid verdict', () => {
  const valid = { run_id: 'A', revision: 1, requirements: [{ requirement_id: 'R', status: 'UNKNOWN' }] };
  assert.doesNotThrow(() => assertRunEnvelope(valid, 'A'));
  for (const bad of [null, { ...valid, run_id: 'B' }, { ...valid, revision: 0 }, { ...valid, requirements: [{}] }]) {
    assert.throws(() => assertRunEnvelope(bad, 'A'));
  }
});
await test('decision commands require known intent, bounded input and a positive revision', () => {
  const valid = { decision: 'HOLD', note: '人工说明', revision: 2, unresolved_requirement_ids: ['R'] };
  assert.doesNotThrow(() => assertDecisionCommand(valid));
  for (const bad of [{ ...valid, revision: undefined }, { ...valid, decision: 'approve' }, { ...valid, note: 'x'.repeat(4001) }, { ...valid, unresolved_requirement_ids: [null] }]) assert.throws(() => assertDecisionCommand(bad));
});
await test('diagnostics never retain message, stack, request URL, form data or arbitrary context', () => {
  const events = []; configureTelemetry((event) => events.push(event), { release: 'release-1' });
  const error = Object.assign(new TypeError('秘密招标正文 secret-token'), { url: '/api?token=secret', quote: '原文', stack: 'private.pdf:12' });
  reportDiagnostic(error, { module: 'network', code: 'TIMEOUT', status: 503, requestId: 'password=123' });
  assert.equal(events.length, 1);
  const body = JSON.stringify(events[0]);
  for (const text of ['秘密', 'secret', 'private.pdf', 'password', 'stack', 'message', 'url', 'quote']) assert.equal(body.includes(text), false);
  assert.equal(events[0].error_type, 'TypeError');
  assert.equal(events[0].status, 503); assert.equal(events[0].release, 'release-1');
  assert.equal(Object.isFrozen(events[0]), true);
});
await test('diagnostic repetition and high volume are bounded, and sink failure is isolated', async () => {
  const events = []; configureTelemetry((event) => events.push(event));
  for (let i = 0; i < 100; i++) reportDiagnostic(new Error('same'), { status: 500 });
  assert.equal(events.length, 1);
  for (let status = 400; status < 450; status++) reportDiagnostic(new Error(), { status });
  assert.equal(events.length, 10);
  configureTelemetry(() => { throw new Error('vendor failure'); });
  assert.doesNotThrow(() => reportDiagnostic(new Error()));
  configureTelemetry(() => Promise.reject(new Error('vendor async failure')));
  reportDiagnostic(new Error()); await new Promise((resolve) => { setImmediate(resolve); });
  configureTelemetry(null);
});
await test('optional telemetry transport refuses foreign origins and query strings', async () => {
  const oldLocation = Object.getOwnPropertyDescriptor(globalThis, 'location');
  const oldFetch = globalThis.fetch;
  Object.defineProperty(globalThis, 'location', { configurable: true, value: { origin: 'https://bidproof.invalid', hash: '#detail/private-run-id' } });
  try {
    assert.throws(() => sameOriginSink('https://other.invalid/events'));
    assert.throws(() => sameOriginSink('/events?token=secret'));
    const sent = []; globalThis.fetch = (...args) => { sent.push(args); return Promise.resolve(new Response(null, { status: 204 })); };
    configureTelemetry(sameOriginSink('/events'));
    reportDiagnostic(new Error('private note'));
    await new Promise((resolve) => { setImmediate(resolve); });
    assert.equal(sent.length, 1); assert.equal(sent[0][0], '/events');
    assert.equal(JSON.parse(sent[0][1].body).route, 'detail');
    assert.equal(sent[0][1].body.includes('private'), false);
  } finally {
    configureTelemetry(null); globalThis.fetch = oldFetch;
    if (oldLocation) Object.defineProperty(globalThis, 'location', oldLocation); else delete globalThis.location;
  }
});
await test('disabled browser storage falls back to a per-tab preference', () => {
  const old = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw new Error('SecurityError'); } });
  try {
    writePreference('theme-test', 'dark'); assert.equal(readPreference('theme-test'), 'dark');
    writePreference('theme-test', null); assert.equal(readPreference('theme-test'), null);
  } finally { if (old) Object.defineProperty(globalThis, 'localStorage', old); else delete globalThis.localStorage; }
});
