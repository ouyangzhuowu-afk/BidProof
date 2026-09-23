/**
 * Full app DOM smoke test: authenticated /app (no initial hash) -> actual run link
 * -> review -> summary -> decision and back. No browser, screenshots or network.
 * The host supplies jsdom with JSDOM_MODULE; no product dependency is added.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const dependency = process.env.JSDOM_MODULE || 'jsdom';
const apiUrl = isAbsolute(dependency) ? pathToFileURL(dependency).href : import.meta.resolve(dependency);
const { JSDOM } = await import(apiUrl);
let fileListFactory; let idl;
try {
  fileListFactory = (await import(new URL('./generated/idl/FileList.js', apiUrl).href)).default;
  idl = (await import(new URL('./generated/idl/utils.js', apiUrl).href)).default;
} catch {
  fileListFactory = (await import(new URL('./jsdom/living/generated/FileList.js', apiUrl).href)).default;
  idl = (await import(new URL('./jsdom/living/generated/utils.js', apiUrl).href)).default;
}
const source = await readFile(new URL('../../static/index.html', import.meta.url), 'utf8');
const dom = new JSDOM(source, { url: 'https://bidproof.invalid/app', pretendToBeVisual: true });
const { window } = dom;
const originals = new Map();
for (const key of ['window', 'document', 'location', 'history', 'navigator', 'localStorage', 'Element', 'HTMLElement',
  'HTMLInputElement', 'HTMLButtonElement', 'HTMLFormElement', 'HTMLDialogElement', 'Event', 'CustomEvent', 'MouseEvent', 'FormData', 'File', 'DataTransfer', 'EventSource']) {
  originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? window : window[key] });
}
window.matchMedia = (query) => ({ matches: query.includes('prefers-reduced-motion'), media: query,
  addEventListener() {}, removeEventListener() {} });
window.scrollTo = () => {};
window.HTMLElement.prototype.scrollIntoView = function () {};
window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
window.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); this.dispatchEvent(new window.Event('close')); };
globalThis.DataTransfer = class {
  constructor() {
    this.files = fileListFactory.create(window);
    this.items = { add: (file) => idl.implForWrapper(this.files).push(idl.implForWrapper(file)) };
  }
};
const sources = [];
globalThis.EventSource = class { constructor() { sources.push(this); } close() { this.closed = true; } };
const authChannels = [];
window.BroadcastChannel = class {
  constructor() { authChannels.push(this); }
  postMessage(data) { assert.equal(data, 'session-changed'); }
  close() { this.closed = true; }
};
const user = { user_id: 'qa-user', workspace_id: 'qa-space', username: '测试复核人', role: 'REVIEWER', active: true };
const project = { project_id: 'qa-project', code: 'DEFAULT', name: '测试项目', archived_at: null };
const reference = (source_id, filename, page, quote) => ({ source_id, filename, page, quote,
  locator: { kind: 'page', label: `第 ${page} 页`, index: page } });
let run = {
  run_id: 'smoke-run', revision: 4, workspace_id: 'qa-space', project_id: 'qa-project',
  tender_filename: '工作台集成测试招标.pdf', company_name: '测试企业', status: 'NEEDS_REVIEW', version_number: 1,
  created_at: '2026-09-22T08:00:00Z', updated_at: '2026-09-22T08:00:00Z', archived_at: null,
  requirement_count: 2, unresolved_count: 2, blocker_count: 2, fatal_risk_count: 1, decision: {},
  tags: [], duplicate_run_ids: [], evidence_assets: [{ asset_id: 'EVD-001', filename: '企业证据.pdf', pages: 3 }],
  source_documents: [
    { source_id: 'TENDER-001', role: 'tender', filename: '工作台集成测试招标.pdf', file_type: 'pdf', pages: 12 },
    { source_id: 'EVD-001', role: 'enterprise_evidence', filename: '企业证据.pdf', file_type: 'pdf', pages: 3 },
  ],
  scan_quality: { total_pages: 15, ocr_failed_pages: 0, ocr_required_pages: 0 },
  review: { items: [] }, research_state: {},
  requirements: [
    { requirement_id: 'R-FATAL', category: 'FATAL', criticality: 'BLOCKER', status: 'NEEDS_REVIEW', label: '废标风险',
      title: '提供有效资质，否则否决投标',
      source: reference('TENDER-001', '工作台集成测试招标.pdf', 12, '必须提供有效的资质证明。'),
      evidence: [reference('EVD-001', '企业证据.pdf', 3, '证书有效期至 2027 年。')] },
    { requirement_id: 'R-QUAL', category: 'QUALIFICATION', criticality: 'BLOCKER', status: 'UNKNOWN', label: '资格核验',
      title: '提交营业执照', source: reference('TENDER-001', '工作台集成测试招标.pdf', 8, '须提供营业执照。'), evidence: [] },
  ],
};
const requests = [];
const deferredRuns = new Map();
const unknown = [];
const domErrors = [];
const originalFetch = globalThis.fetch;
const reply = (value, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }));
globalThis.fetch = (input, options = {}) => {
  const url = new URL(String(input), window.location.origin);
  const method = options.method || 'GET';
  const body = options.body instanceof window.FormData ? Object.fromEntries(options.body.entries()) : options.body ? JSON.parse(options.body) : null;
  requests.push({ path: url.pathname, method, body });
  if (deferredRuns.has(url.pathname)) return deferredRuns.get(url.pathname);
  if (url.pathname === '/api/auth/status') return reply({ authenticated: true, setup_required: false, user });
  if (url.pathname === '/api/projects') return reply({ projects: [project] });
  if (url.pathname === '/api/members') return reply({ members: [user] });
  if (url.pathname === '/api/runs') return reply([run]);
  if (url.pathname === '/api/notifications') return reply({ notifications: [], count: 0 });
  if (url.pathname === '/api/accuracy/metrics') return reply({ review_population_complete: false, sample_size: 0, precision: null, recall: null });
  if (url.pathname === '/api/jobs') return method === 'POST' ? reply({ job_id: 'queued-rescan', status: 'PENDING' }, 202) : reply({ jobs: [] });
  if (url.pathname === '/api/runs/smoke-run' && method === 'GET') return reply(run);
  if (/^\/api\/runs\/race-[ab]\/(comments|audit|remediations)$/.test(url.pathname)) return reply({ comments: [], events: [], remediations: [] });
  if (url.pathname === '/api/runs/smoke-run/comments') return reply({ comments: [] });
  if (url.pathname === '/api/runs/smoke-run/audit') return reply({ events: [] });
  if (url.pathname === '/api/runs/smoke-run/remediations') return reply({ remediations: [] });
  if (url.pathname === '/api/runs/smoke-run/review' && method === 'POST') {
    assert.equal(body.revision, run.revision);
    assert.equal(body.decision, 'CONFIRM'); assert.equal(body.new_status, 'PASS');
    run = structuredClone(run);
    run.requirements.find((item) => item.requirement_id === body.requirement_id).status = 'PASS';
    run.review.items.push(body); run.revision += 1;
    run.unresolved_count = 1; run.blocker_count = 1; run.fatal_risk_count = 0;
    return reply(run);
  }
  unknown.push({ path: url.pathname, method });
  return reply({ detail: `Unstubbed request: ${method} ${url.pathname}` }, 404);
};
window.addEventListener('error', (event) => { domErrors.push(event.error?.message || event.message); });

const query = (selector) => {
  const node = window.document.querySelector(selector);
  assert.ok(node, `Expected app element ${selector}`);
  return node;
};
const pause = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
async function waitFor(predicate, label, timeout = 2000) {
  const until = Date.now() + timeout;
  while (!predicate() && Date.now() < until) await pause(10);
  assert.ok(predicate(), `${label}; DOM errors: ${domErrors.join('; ')}; unstubbed: ${JSON.stringify(unknown)}`);
}

try {
  await test('complete app boots at /app and actual run-list click reaches review workbench', async (suite) => {
    const { store } = await import('../src/core/store.js');
    const { store: legacy } = await import('../src/state.js');
    const { navigate } = await import('../src/core/router.js');
    await import('../src/app.js');

    await suite.test('authenticated no-hash startup binds the rendered task list', async () => {
      await waitFor(() => window.document.querySelector('#runs-list [data-run-open="smoke-run"]'), 'Task list must render from the API');
      // Allow project/member requests and their mount continuation to finish.
      await pause(20);
      assert.equal(query('#home-view').hidden, false);
      assert.equal(query('#current-username').textContent, user.username);
      assert.equal(store.get().currentUser.user_id, user.user_id);
      query('#runs-list [data-run-open="smoke-run"]').click();
      await waitFor(() => !query('#detail-view').hidden && query('#requirements').querySelector('.review-card'),
        'Clicking an actual rendered task link must enter and populate the workbench');
      assert.equal(window.location.hash, '#detail/smoke-run');
      assert.equal(query('#home-view').hidden, true);
      assert.equal(query('#loading-overlay').hidden, true);
      assert.equal(legacy.currentRun, store.get().currentRun);
      assert.equal(query('#detail-title').textContent, run.tender_filename);
      assert.equal(query('#requirements').querySelectorAll('.review-card').length, 2);
      assert.match(query('#evidence-reader').textContent, /双向原文对照/);
      assert.match(query('#detail-summary').textContent, /仍有 1 项废标风险待处理/);
      assert.equal(query('#detail-summary progress').value, 0);
      assert.equal(query('#detail-summary progress').max, 2);
    });

    await suite.test('card review updates the app summary through the shared state bridge', async () => {
      query('#requirements [data-requirement-id="R-FATAL"] [data-review="CONFIRM"]').click();
      await waitFor(() => query('#detail-summary progress').value === 1, 'Review event must refresh the full app summary');
      assert.equal(store.get().currentRun.revision, 5);
      assert.equal(legacy.currentRun.revision, 5);
      assert.match(query('#detail-summary').textContent, /还有 1 项需要核验/);
      assert.equal(query('#detail-summary').dataset.tone, 'review');
      assert.equal(requests.filter((entry) => entry.path.endsWith('/review')).length, 1);
      assert.equal(query('#requirements [data-requirement-id="R-FATAL"]').dataset.status, 'PASS');
    });

    await suite.test('registered decision route renders current data and returns to detail', async () => {
      await navigate('decision', 'smoke-run');
      assert.equal(query('#decision-view').hidden, false);
      assert.equal(query('#detail-view').hidden, true);
      assert.equal(window.location.hash, '#decision/smoke-run');
      assert.match(query('#decision-context-content').textContent, /未解决要求/);
      query('#back-detail').click();
      assert.equal(query('#detail-view').hidden, false);
      assert.equal(query('#detail-summary progress').value, 1);
    });

    await suite.test('home route rebinds the list after leaving and supports a second real click', async () => {
      query('#back-home').click();
      await waitFor(() => !query('#home-view').hidden && window.document.querySelector('#runs-list [data-run-open="smoke-run"]'),
        'Returning home must restore the task list');
      await pause(20);
      query('#runs-list [data-run-open="smoke-run"]').click();
      await waitFor(() => !query('#detail-view').hidden, 'Re-entering detail should remain possible after unmount/remount');
      assert.equal(query('#detail-summary progress').value, 1);
      assert.deepEqual(unknown, []);
      assert.deepEqual(domErrors, []);
    });
    await suite.test('slower earlier task cannot overwrite the latest selected task', async () => {
      let finishA; let finishB;
      deferredRuns.set('/api/runs/race-a', new Promise((done) => { finishA = done; }));
      deferredRuns.set('/api/runs/race-b', new Promise((done) => { finishB = done; }));
      const first = navigate('detail', 'race-a');
      const second = navigate('detail', 'race-b');
      finishB(await reply({ ...run, run_id: 'race-b', tender_filename: '最新选择B.pdf' }));
      await second;
      assert.equal(store.get().currentRun.run_id, 'race-b');
      finishA(await reply({ ...run, run_id: 'race-a', tender_filename: '旧选择A.pdf' }));
      await first;
      assert.equal(store.get().currentRun.run_id, 'race-b');
      assert.equal(query('#detail-title').textContent, '最新选择B.pdf');
      assert.equal(window.location.hash, '#detail/race-b');
      assert.equal(query('#loading-overlay').hidden, true);
    });
    await suite.test('leaving during a pending read keeps the destination and removes its overlay', async () => {
      let finish;
      deferredRuns.set('/api/runs/race-a', new Promise((done) => { finish = done; }));
      const pending = navigate('detail', 'race-a');
      assert.equal(query('#loading-overlay').hidden, false);
      query('#nav-runs').click();
      assert.equal(query('#loading-overlay').hidden, true);
      finish(await reply({ ...run, run_id: 'race-a' }));
      await pending;
      assert.equal(query('#home-view').hidden, false);
      assert.equal(window.location.hash, '#home');
      assert.equal(store.get().currentRun.run_id, 'race-b');
      assert.equal(query('#nav-runs').getAttribute('aria-current'), 'page');
    });
    await suite.test('rescans submit real FormData to the background queue with the captured parent', async () => {
      await navigate('detail', 'race-b');
      query('#rescan-run').click(); await waitFor(() => query('#intake-panel').open, 'Rescan opens intake');
      const transfer = new DataTransfer(); transfer.items.add(new window.File(['pdf test'], 'rescan.pdf', { type: 'application/pdf' }));
      query('#tender-file').files = transfer.files;
      query('#tender-file').dispatchEvent(new window.Event('change', { bubbles: true }));
      query('#company-name').value = '界面测试';
      query('#scan-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
      await waitFor(() => window.document.querySelector('#scancard-queued-rescan'), 'Rescan should be monitored in background');
      const sent = requests.filter((entry) => entry.path === '/api/jobs' && entry.method === 'POST');
      assert.equal(sent.length, 1); assert.equal(sent[0].body.parent_run_id, 'race-b');
      assert.equal(sent[0].body.tender.name, 'rescan.pdf');
      assert.equal(requests.some((entry) => entry.path.endsWith('/rescan')), false);
      assert.equal(store.get().currentRun.run_id, 'race-b'); assert.equal(legacy.rescanParentId, null);
      assert.equal(query('#intake-panel').open, false);
    });
    await suite.test('cross-tab auth changes clear private state and DOM and block late task responses', async () => {
      let finish;
      deferredRuns.set('/api/runs/race-a', new Promise((done) => { finish = done; }));
      const pending = navigate('detail', 'race-a');
      legacy.membersCache = [user]; legacy.projectsCache = [project];
      legacy.searchTerm = 'private clause'; legacy.runSearch = 'private project'; legacy.runTagFilter = 'private tag';
      legacy.pendingMfaToken = 'private MFA token';
      store.set({ members: [user], projects: [project] });
      const transfer = new DataTransfer(); transfer.items.add(new window.File(['private PDF'], 'private.pdf'));
      query('#tender-file').files = transfer.files;
      query('#tender-file').dispatchEvent(new window.Event('change', { bubbles: true }));
      assert.equal(authChannels.length, 1);
      authChannels[0].onmessage({ data: 'session-changed' });
      assert.equal(query('#auth-panel').open, true, 'Remote session invalidation exposes login immediately.');
      window.dispatchEvent(new window.CustomEvent('bidproof:unauthorized'));
      assert.equal(store.get().currentRun, null); assert.equal(store.get().currentUser, null);
      assert.deepEqual(store.get().members, []); assert.deepEqual(store.get().projects, []);
      assert.deepEqual(legacy.membersCache, []); assert.deepEqual(legacy.projectsCache, []);
      assert.equal(legacy.searchTerm, ''); assert.equal(legacy.runSearch, ''); assert.equal(legacy.runTagFilter, '');
      assert.equal(legacy.pendingMfaToken, '');
      assert.equal(query('#tender-file').files.length, 0, 'FileList clears synchronously, before queued form-reset work.');
      assert.equal(query('#tender-file-feedback').textContent.includes('private.pdf'), false);
      assert.equal(query('#app-main').childElementCount, 0);
      assert.equal(window.document.querySelector('.scandock'), null); assert.equal(sources[0].closed, true);
      finish(await reply({ ...run, run_id: 'race-a' })); await pending;
      await waitFor(() => query('#auth-panel').open, 'Expiry must expose authentication');
      assert.equal(store.get().currentRun, null); assert.equal(query('#app-main').childElementCount, 0);
      assert.deepEqual(domErrors, []);
    });
  });
} finally {
  window.dispatchEvent(new window.Event('pagehide'));
  const { unmountMatrix } = await import('../src/features/runs/matrix.js');
  const { unmountRunsView } = await import('../src/features/runs/list.js');
  const { unmountCollab } = await import('../src/features/runs/collab.js');
  const { unmountDecisionView } = await import('../src/features/runs/decision.js');
  const { store: legacy } = await import('../src/state.js');
  unmountMatrix(); unmountRunsView(); unmountCollab(); unmountDecisionView();
  clearTimeout(legacy.toastTimer);
  let toast;
  while ((toast = window.document.querySelector('.toast-region .toast'))) toast.click();
  await pause(0);
  dom.window.close(); globalThis.fetch = originalFetch;
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
}
