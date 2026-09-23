/** Slow responses, session boundaries and recoverable module failures. No live network. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { isAbsolute } from 'node:path';
import test from 'node:test';
const dependency = process.env.JSDOM_MODULE || 'jsdom';
const { JSDOM } = await import(isAbsolute(dependency) ? pathToFileURL(dependency).href : dependency);
const dom = new JSDOM(await readFile(new URL('../../static/index.html', import.meta.url), 'utf8'), { url: 'https://bidproof.invalid/app', pretendToBeVisual: true });
const w = dom.window;
const originals = new Map();
for (const key of ['window', 'document', 'location', 'history', 'navigator', 'localStorage', 'Element', 'HTMLElement', 'HTMLInputElement', 'HTMLButtonElement', 'HTMLFormElement', 'HTMLDialogElement', 'Event', 'CustomEvent', 'MouseEvent', 'FormData']) {
  originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? w : w[key] });
}
w.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
w.scrollTo = () => {}; w.HTMLElement.prototype.scrollIntoView = function () {};
const oldFetch = globalThis.fetch;
const pause = () => new Promise((resolve) => { setImmediate(resolve); });
const reply = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const run = (id, revision = 1) => ({ run_id: id, revision, blocker_count: 0, unresolved_count: 0, requirement_count: 0, requirements: [], decision: { decision: 'HOLD', note: '人工说明' } });
const { store } = await import('../src/core/store.js');
const decisions = await import('../src/features/runs/decision.js');
const collab = await import('../src/features/runs/collab.js');
const jobs = await import('../src/features/jobs/index.js');
const account = await import('../src/features/admin/account.js');
const { installRuntimeBoundary } = await import('../src/core/runtime.js');
const { configureTelemetry } = await import('../src/core/telemetry.js');
const { resetSessionTransport } = await import('../src/core/http.js');
const { clearToasts } = await import('../src/core/toast.js');
const { revealSecret } = await import('../src/ui/secret-reveal.js');
const submit = (selector) => document.querySelector(selector).dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
const clear = () => { decisions.unmountDecisionView(); collab.unmountCollab(); jobs.unmountJobsView(); };
try {
  await test('a decision response cannot replace another task selected while saving', async () => {
    const pending = deferred(); const sent = [];
    globalThis.fetch = (_url, options) => { sent.push(JSON.parse(options.body)); return pending.promise; };
    store.set({ currentRun: run('A', 4) }); decisions.mountDecisionView();
    submit('#decision-form'); await pause();
    assert.equal(sent[0].revision, 4);
    decisions.unmountDecisionView(); store.set({ currentRun: run('B', 2) });
    pending.resolve(reply(run('A', 5))); await pause();
    assert.equal(store.get().currentRun.run_id, 'B');
  });
  await test('a decision response cannot roll back a newer same-task revision', async () => {
    const pending = deferred(); globalThis.fetch = () => pending.promise;
    store.set({ currentRun: run('A', 4) }); decisions.mountDecisionView(); submit('#decision-form'); await pause();
    store.set({ currentRun: run('A', 8) }); pending.resolve(reply(run('A', 5))); await pause();
    assert.equal(store.get().currentRun.revision, 8); clear();
  });
  await test('a 409 preserves the draft and explicitly reloads the version without replaying the decision', async () => {
    let posts = 0;
    globalThis.fetch = (_url, options) => options.method === 'POST' ? (posts++, reply({ detail: 'conflict' }, 409)) : reply(run('A', 8));
    store.set({ currentRun: run('A', 4) }); decisions.mountDecisionView();
    document.querySelector('#decision-note').value = '保留这份人工决定说明';
    submit('#decision-form'); await pause();
    assert.equal(store.get().currentRun.revision, 4);
    assert.equal(document.querySelector('#decision-note').value, '保留这份人工决定说明');
    assert.ok(document.querySelector('[data-decision-refresh]'));
    document.querySelector('[data-decision-refresh]').click(); await pause();
    assert.equal(store.get().currentRun.revision, 8);
    assert.equal(document.querySelector('#decision-note').value, '保留这份人工决定说明');
    assert.equal(posts, 1); clear();
  });
  await test('a failed decision never mutates the task or clears the draft', async () => {
    globalThis.fetch = () => reply({ detail: '暂时无法保存' }, 503);
    store.set({ currentRun: run('A', 4) }); decisions.mountDecisionView();
    document.querySelector('#decision-note').value = '未保存内容'; submit('#decision-form'); await pause();
    assert.equal(store.get().currentRun.revision, 4);
    assert.equal(document.querySelector('#decision-note').value, '未保存内容');
    assert.match(document.querySelector('#decision-message').textContent, /决策未保存/); clear();
  });
  await test('decision edits typed during a save remain visibly unsaved', async () => {
    const pending = deferred(); globalThis.fetch = () => pending.promise;
    store.set({ currentRun: run('A', 4) }); decisions.mountDecisionView();
    document.querySelector('#decision-note').value = '提交时的说明'; submit('#decision-form'); await pause();
    document.querySelector('#decision-note').value = '等待时补充的新说明';
    pending.resolve(reply({ ...run('A', 5), decision: { decision: 'HOLD', note: '提交时的说明' } })); await pause();
    assert.equal(store.get().currentRun.decision.note, '提交时的说明');
    assert.equal(document.querySelector('#decision-note').value, '等待时补充的新说明');
    assert.match(document.querySelector('#decision-message').textContent, /新编辑仍未保存/); clear();
  });
  await test('all collaboration panels reject late results from a different task', async () => {
    const old = new Map();
    globalThis.fetch = (url) => {
      const panel = String(url).split('/').at(-1);
      if (String(url).includes('/A/')) { const pending = deferred(); old.set(panel, pending); return pending.promise; }
      return reply({ comments: [{ user_id: 'B', body: 'B 的评论', created_at: '2026-09-23T01:00:00Z' }], events: [{ event_type: 'B 审计', created_at: '2026-09-23T01:00:00Z' }], remediations: [{ remediation_id: 'B-fix', title: 'B 的整改', status: 'OPEN' }] });
    };
    collab.mountCollab(); store.set({ currentRun: run('A') }); collab.loadCollab();
    store.set({ currentRun: run('B') }); collab.loadCollab(); await pause();
    for (const pending of old.values()) pending.resolve(reply({ comments: [{ user_id: 'A', body: 'A PRIVATE' }], events: [{ event_type: 'A PRIVATE' }], remediations: [{ title: 'A PRIVATE' }] }));
    await pause();
    assert.match(document.querySelector('#comments-list').textContent, /B 的评论/);
    assert.match(document.querySelector('#audit-events').textContent, /B 审计/);
    assert.match(document.querySelector('#remediations-list').textContent, /B 的整改/);
    for (const id of ['comments-list', 'audit-events', 'remediations-list']) assert.equal(document.getElementById(id).textContent.includes('A PRIVATE'), false);
    clear();
  });
  await test('saving an old comment cannot clear a new task draft', async () => {
    const pending = deferred(); globalThis.fetch = () => pending.promise;
    collab.mountCollab(); store.set({ currentRun: run('A') });
    const input = document.querySelector('#comment-form [name="body"]'); input.value = 'A comment';
    submit('#comment-form'); await pause();
    store.set({ currentRun: run('B') }); input.value = 'B draft';
    pending.resolve(reply({ body: 'A comment' })); await pause();
    assert.equal(input.value, 'B draft'); clear();
  });
  await test('a new session viewing the same task cannot receive old collaboration responses', async () => {
    const responses = [];
    globalThis.fetch = () => { const pending = deferred(); responses.push(pending); return pending.promise; };
    collab.mountCollab(); store.set({ currentRun: run('A') }); collab.loadCollab();
    collab.unmountCollab(); resetSessionTransport();
    collab.mountCollab();
    for (const id of ['comments-list', 'audit-events', 'remediations-list']) document.getElementById(id).textContent = 'new session';
    for (const pending of responses) pending.resolve(reply({ comments: [{ body: 'PRIVATE' }], events: [{ event_type: 'PRIVATE' }], remediations: [{ title: 'PRIVATE' }] }));
    await pause();
    for (const id of ['comments-list', 'audit-events', 'remediations-list']) assert.equal(document.getElementById(id).textContent, 'new session');
    clear();
  });
  await test('comment saving preserves text edited during the same-task request', async () => {
    const pending = deferred(); globalThis.fetch = (_url, options) => options.method === 'POST' ? pending.promise : reply({ comments: [] });
    collab.mountCollab(); store.set({ currentRun: run('A') });
    const input = document.querySelector('#comment-form [name="body"]'); input.value = 'first draft';
    submit('#comment-form'); await pause(); input.value = 'next draft';
    pending.resolve(reply({ body: 'first draft' })); await pause();
    assert.equal(input.value, 'next draft'); clear();
  });
  await test('one failed collaboration panel exposes retry while the other panels remain usable', async () => {
    globalThis.fetch = (url) => String(url).endsWith('/comments') ? reply({ detail: 'forbidden' }, 403) : reply({ events: [], remediations: [] });
    collab.mountCollab(); store.set({ currentRun: run('A') }); collab.loadCollab(); await pause();
    assert.ok(document.querySelector('#collab-retry-comments'));
    assert.match(document.querySelector('#audit-events').textContent, /暂无审计记录/);
    globalThis.fetch = () => reply({ comments: [{ body: '恢复后的评论', user_id: 'U', created_at: '2026-09-23T00:00:00Z' }] });
    document.querySelector('#collab-retry-comments').click(); await pause();
    assert.match(document.querySelector('#comments-list').textContent, /恢复后的评论/); clear();
  });
  await test('remediation inputs reach the API and status choices match the backend contract', async () => {
    const writes = [];
    globalThis.fetch = (_url, options) => {
      if (options.method === 'POST' || options.method === 'PATCH') writes.push(JSON.parse(options.body));
      return reply(options.method === 'GET' ? { remediations: [{ remediation_id: 'fix-1', title: '待补材料', status: 'OPEN' }], comments: [], events: [] } : { remediation_id: 'fix-1' });
    };
    collab.mountCollab(); store.set({ currentRun: run('A') });
    document.querySelector('#remediation-title-input').value = '补充企业资质';
    document.querySelector('#remediation-due').value = '2026-10-01';
    submit('#remediation-form'); await pause();
    assert.equal(writes[0].title, '补充企业资质'); assert.equal(writes[0].due_date, '2026-10-01');
    const status = document.querySelector('[data-remediation-status]');
    assert.deepEqual([...status.options].map((option) => option.value), ['OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED']);
    status.value = 'DONE'; status.dispatchEvent(new w.Event('change', { bubbles: true })); await pause();
    assert.deepEqual(writes[1], { status: 'DONE' }); clear();
  });
  await test('API tokens require an explicit scope selection and only send selected permissions', async () => {
    const writes = [];
    globalThis.fetch = (url, options) => {
      if (options.method === 'POST') { writes.push(JSON.parse(options.body)); return reply({ token: 'test-only-secret', token_prefix: 'test', name: '归档' }); }
      return reply(String(url).includes('/tokens') ? { tokens: [] } : String(url).includes('/sessions') ? { sessions: [] } : { mfa_enabled: false });
    };
    account.mountAccount(); await pause();
    document.querySelector('#token-name').value = '归档'; submit('#token-form'); await pause();
    assert.equal(writes.length, 0); assert.match(document.querySelector('#token-message').textContent, /至少选择/);
    document.querySelector('#token-form [value="run:read"]').checked = true;
    submit('#token-form'); await pause();
    assert.deepEqual(writes, [{ name: '归档', permissions: ['run:read'] }]);
    account.unmountAccount();
  });
  await test('jobs cannot restart polling or render after unmount', async () => {
    const pending = deferred(); globalThis.fetch = () => pending.promise;
    const originalTimeout = globalThis.setTimeout; let pollers = 0;
    globalThis.setTimeout = (callback, delay, ...args) => { if (delay === 5000) pollers++; return originalTimeout(callback, delay, ...args); };
    try {
      jobs.mountJobsView(); jobs.unmountJobsView();
      document.querySelector('#jobs-list').textContent = 'new view';
      pending.resolve(reply({ jobs: [{ job_id: 'OLD', status: 'RUNNING', updated_at: '2026-09-23T01:00:00Z' }] })); await pause();
      assert.equal(pollers, 0); assert.equal(document.querySelector('#jobs-list').textContent, 'new view');
    } finally { globalThis.setTimeout = originalTimeout; clear(); }
  });
  await test('a delayed clipboard failure cannot reveal a previous session secret', async () => {
    let rejectCopy; let prompts = 0;
    const originalPrompt = w.prompt; const originalClipboard = Object.getOwnPropertyDescriptor(w.navigator, 'clipboard');
    Object.defineProperty(w.navigator, 'clipboard', { configurable: true, value: { writeText: () => new Promise((_resolve, reject) => { rejectCopy = reject; }) } });
    w.prompt = () => { prompts++; };
    const target = document.createElement('div'); document.body.append(target);
    try {
      const handle = revealSecret(target, { title: 'API 令牌', values: ['private-token'] });
      target.querySelector('[data-secret-copy]').click();
      resetSessionTransport(); handle.clear(); rejectCopy(new Error('clipboard denied')); await pause();
      assert.equal(prompts, 0); assert.equal(target.textContent, '');
    } finally {
      target.remove(); w.prompt = originalPrompt;
      if (originalClipboard) Object.defineProperty(w.navigator, 'clipboard', originalClipboard); else delete w.navigator.clipboard;
    }
  });
  await test('global runtime errors and offline changes provide safe recoverable notices', () => {
    const events = []; configureTelemetry((event) => events.push(event));
    const dispose = installRuntimeBoundary(); assert.equal(installRuntimeBoundary(), dispose);
    Object.defineProperty(w.navigator, 'onLine', { configurable: true, value: false });
    w.dispatchEvent(new w.Event('offline'));
    assert.equal(document.querySelector('.runtime-notice').hidden, false);
    w.dispatchEvent(new w.ErrorEvent('error', { error: new TypeError('PRIVATE PDF CONTENT') }));
    assert.equal(document.querySelector('.runtime-notice--error').hidden, false);
    assert.equal(document.querySelector('.runtime-notices').textContent.includes('PRIVATE'), false);
    Object.defineProperty(w.navigator, 'onLine', { configurable: true, value: true });
    w.dispatchEvent(new w.Event('online')); assert.equal(document.querySelector('.runtime-notice').hidden, true);
    const rejection = new w.Event('unhandledrejection'); rejection.reason = new Error('secret token'); w.dispatchEvent(rejection);
    assert.equal(events.length, 2); assert.equal(JSON.stringify(events).includes('secret'), false);
    dispose(); configureTelemetry(null); assert.equal(document.querySelector('.runtime-notices'), null);
  });
} finally {
  clear(); account.unmountAccount(); clearToasts(); resetSessionTransport(); configureTelemetry(null); globalThis.fetch = oldFetch;
  dom.window.close();
  for (const [key, descriptor] of originals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
}
