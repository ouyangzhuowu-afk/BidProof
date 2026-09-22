/** Transport regression: stubbed fetch only; no browser or live requests. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { request, ApiError, onUnauthorized } from '../src/core/http.js';

const savedFetch = globalThis.fetch;
const savedDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
Object.defineProperty(globalThis, 'document', { configurable: true, value: { cookie: '' } });
const reply = (status, body = { detail: 'test' }) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
let calls = 0;
let sequence = 0;
const path = () => `/api/transport-test/${++sequence}`;
const stub = (handler) => { calls = 0; globalThis.fetch = (...args) => { calls += 1; return handler(...args); }; };

try {
  for (const status of [401, 403, 404, 409, 422, 500]) {
    await test(`HTTP ${status} is reported once without blind retry`, async () => {
      let expired = 0; onUnauthorized(() => { expired += 1; });
      stub(() => reply(status));
      await assert.rejects(request(path()), (e) => e instanceof ApiError && e.status === status);
      assert.equal(calls, 1);
      assert.equal(expired, status === 401 ? 1 : 0);
    });
  }
  await test('transient GET 503 retries then returns the actual response', async () => {
    stub(() => calls === 1 ? reply(503) : reply(200, { recovered: true }));
    assert.deepEqual(await request(path(), { retries: 1 }), { recovered: true });
    assert.equal(calls, 2);
  });
  await test('a failed mutation is never automatically replayed', async () => {
    stub(() => reply(503));
    await assert.rejects(request(path(), { method: 'POST', body: '{}', retries: 5 }), (e) => e.status === 503);
    assert.equal(calls, 1);
  });
  await test('a transient network failure retries only for read requests', async () => {
    stub(() => { if (calls === 1) throw new TypeError('network'); return reply(200, { ok: true }); });
    assert.deepEqual(await request(path(), { retries: 1 }), { ok: true });
    assert.equal(calls, 2);
  });
  await test('concurrent identical reads share one request and cleanup after success', async () => {
    let resolve;
    stub(() => new Promise((done) => { resolve = done; }));
    const url = path(); const one = request(url); const two = request(url);
    assert.equal(calls, 1); resolve(reply(200, { shared: true }));
    assert.deepEqual(await one, await two);
    stub(() => reply(200, { refreshed: true }));
    assert.deepEqual(await request(url), { refreshed: true }); assert.equal(calls, 1);
  });
  await test('caught failures clean dedupe state without a second unhandled rejection', async () => {
    const rejections = []; const capture = (e) => rejections.push(e);
    process.on('unhandledRejection', capture);
    try {
      const url = path(); stub(() => reply(404));
      await assert.rejects(request(url));
      await new Promise((resolve) => { setImmediate(resolve); });
      assert.deepEqual(rejections, []);
      stub(() => reply(200, { retry: 'manual' }));
      assert.deepEqual(await request(url), { retry: 'manual' });
    } finally { process.removeListener('unhandledRejection', capture); }
  });
  await test('a truncated successful JSON response retries and never resolves as an empty result', async () => {
    stub(() => calls === 1 ? new Response('{broken', { status: 200, headers: { 'content-type': 'application/json' } }) : reply(200, { valid: true }));
    assert.deepEqual(await request(path(), { retries: 1 }), { valid: true }); assert.equal(calls, 2);
  });
  await test('a malformed mutation response is an error and never replays the write', async () => {
    stub(() => new Response('{broken', { status: 200, headers: { 'content-type': 'application/json' } }));
    await assert.rejects(request(path(), { method: 'POST' }), (e) => e.code === 'INVALID_RESPONSE'); assert.equal(calls, 1);
  });
  await test('malformed forbidden response preserves HTTP rejection without retry', async () => {
    stub(() => new Response('{broken', { status: 403, headers: { 'content-type': 'application/json' } }));
    await assert.rejects(request(path()), (e) => e.status === 403); assert.equal(calls, 1);
  });
  await test('HTML with HTTP 200 cannot impersonate a JSON result', async () => {
    stub(() => new Response('<h1>gateway page</h1>', { status: 200, headers: { 'content-type': 'text/html' } }));
    await assert.rejects(request(path(), { retries: 0 }), (e) => e.code === 'INVALID_RESPONSE');
  });
  await test('an explicit empty 204 response remains a supported success', async () => {
    stub(() => new Response(null, { status: 204 }));
    assert.deepEqual(await request(path(), { method: 'DELETE' }), {});
  });
  await test('pre-aborted requests stay aborted in the Safari-compatible signal path', async () => {
    const original = AbortSignal.any;
    AbortSignal.any = undefined;
    try {
      const controller = new AbortController(); controller.abort();
      stub((_url, options) => { assert.equal(options.signal.aborted, true); throw options.signal.reason; });
      await assert.rejects(request(path(), { signal: controller.signal }), (e) => e.isAborted);
      assert.equal(calls, 1);
    } finally { AbortSignal.any = original; }
  });
} finally {
  globalThis.fetch = savedFetch;
  if (savedDocument) Object.defineProperty(globalThis, 'document', savedDocument); else delete globalThis.document;
}
