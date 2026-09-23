/** Transport regression: stubbed fetch only; no browser or live requests. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { request, requestBlob, saveBlob, ApiError, onUnauthorized, resetSessionTransport, watchJob } from '../src/core/http.js';
import { exportRun } from '../src/api/runs.js';

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
  await test('pre-aborted requests never reach the network', async () => {
    const original = AbortSignal.any;
    AbortSignal.any = undefined;
    try {
      const controller = new AbortController(); controller.abort();
      stub((_url, options) => { assert.equal(options.signal.aborted, true); throw options.signal.reason; });
      await assert.rejects(request(path(), { signal: controller.signal }), (e) => e.isAborted);
      assert.equal(calls, 0);
    } finally { AbortSignal.any = original; }
  });
  await test('Safari-compatible cancellation stays connected through JSON body reading', async () => {
    const original = AbortSignal.any; AbortSignal.any = undefined;
    try {
      const controller = new AbortController();
      let started;
      const reading = new Promise((resolve) => { started = resolve; });
      stub((_url, options) => ({ ok: true, status: 200, headers: new Headers({ 'content-type': 'application/json' }),
        json: () => new Promise((_resolve, reject) => { options.signal.addEventListener('abort', () => reject(options.signal.reason)); started(); }) }));
      const pending = request(path(), { signal: controller.signal });
      await reading; controller.abort();
      await assert.rejects(pending, (error) => error.isAborted);
      assert.equal(calls, 1);
    } finally { AbortSignal.any = original; }
  });
  await test('session reset rejects a late successful response and frees GET deduplication', async () => {
    let finish;
    stub(() => new Promise((resolve) => { finish = resolve; }));
    const url = path(); const old = request(url);
    resetSessionTransport();
    finish(reply(200, { private: 'old session' }));
    await assert.rejects(old, (error) => error.isAborted);
    stub(() => reply(200, { current: true }));
    assert.deepEqual(await request(url), { current: true });
  });
  await test('binary responses keep bytes and server filename headers', async () => {
    stub(() => new Response('%PDF-test', { headers: { 'content-type': 'application/pdf', 'content-disposition': 'attachment; filename="report-v2.pdf"' } }));
    const response = await requestBlob(path());
    assert.equal(await response.text(), '%PDF-test');
    assert.equal(response.headers.get('content-disposition'), 'attachment; filename="report-v2.pdf"');
  });
  await test('binary downloads cannot resolve after their session is invalidated', async () => {
    let finish;
    stub(() => new Promise((resolve) => { finish = resolve; }));
    const pending = requestBlob(path()); resetSessionTransport();
    finish(new Response('private PDF'));
    await assert.rejects(pending, (error) => error.isAborted);
  });
  await test('Safari-compatible cancellation stays attached while the binary body is read', async () => {
    const original = AbortSignal.any; AbortSignal.any = undefined;
    try {
      let started; const reading = new Promise((resolve) => { started = resolve; });
      stub((_url, options) => ({ ok: true, status: 200, headers: new Headers(),
        blob: () => new Promise((_resolve, reject) => { options.signal.addEventListener('abort', () => reject(options.signal.reason)); started(); }) }));
      const pending = requestBlob(path()); await reading; resetSessionTransport();
      await assert.rejects(pending, (error) => error.isAborted); assert.equal(calls, 1);
    } finally { AbortSignal.any = original; }
  });
  await test('binary body timeout is reported without replaying an export', async () => {
    stub((_url, options) => ({ ok: true, status: 200, headers: new Headers(),
      blob: () => new Promise((_resolve, reject) => { options.signal.addEventListener('abort', () => reject(options.signal.reason)); }) }));
    // AbortSignal.timeout uses an unreferenced timer in Node; keep this test alive.
    const keepAlive = setTimeout(() => {}, 1000);
    try { await assert.rejects(requestBlob(path(), { method: 'POST', timeoutMs: 5 }), (error) => error.isTimeout); }
    finally { clearTimeout(keepAlive); }
    assert.equal(calls, 1);
  });
  await test('export checks its original session immediately before creating a download URL', async () => {
    const originalBlob = Response.prototype.blob; const originalCreate = URL.createObjectURL;
    let reads = 0; let created = 0;
    Response.prototype.blob = async function () {
      const blob = await originalBlob.call(this);
      if (++reads === 2) resetSessionTransport();
      return blob;
    };
    URL.createObjectURL = () => { created++; return 'blob:test'; };
    stub(() => new Response('private PDF'));
    try { await assert.rejects(exportRun('session-private', 'pdf'), (error) => error.isAborted); assert.equal(created, 0); }
    finally { Response.prototype.blob = originalBlob; URL.createObjectURL = originalCreate; }
  });
  await test('session reset immediately revokes any pending download object URL', () => {
    const originalCreate = URL.createObjectURL; const originalRevoke = URL.revokeObjectURL;
    const revoked = []; let clicks = 0;
    URL.createObjectURL = () => 'blob:private-report'; URL.revokeObjectURL = (url) => revoked.push(url);
    document.body = { append() {} }; document.createElement = () => ({ click() { clicks++; }, remove() {} });
    try {
      saveBlob(new Blob(['private PDF']), 'private.pdf'); assert.equal(clicks, 1);
      resetSessionTransport(); assert.deepEqual(revoked, ['blob:private-report']);
    } finally { URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke; delete document.body; delete document.createElement; }
  });
  await test('session reset closes subscriptions and ignores queued SSE messages', () => {
    const original = globalThis.EventSource; const sources = []; const received = [];
    globalThis.EventSource = class { constructor() { sources.push(this); } close() { this.closed = true; } };
    try {
      watchJob('session-job', { onProgress: (v) => received.push(v), onDone: (v) => received.push(v), onError: (v) => received.push(v) });
      resetSessionTransport();
      assert.equal(sources[0].closed, true);
      sources[0].onmessage({ data: JSON.stringify({ status: 'RUNNING' }) });
      assert.deepEqual(received, []);
    } finally { globalThis.EventSource = original; }
  });
} finally {
  globalThis.fetch = savedFetch;
  if (savedDocument) Object.defineProperty(globalThis, 'document', savedDocument); else delete globalThis.document;
}
