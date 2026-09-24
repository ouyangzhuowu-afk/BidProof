/**
 * First-run acceptance through real app event wiring: rendered starters, file
 * selection, queued FormData, SSE completion and result navigation. HTTP is stubbed.
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
const user = { user_id: 'starter-owner', workspace_id: 'starter-workspace', username: '新用户', role: 'OWNER', active: true };
const project = { project_id: 'starter-project', code: 'DEFAULT', name: '默认项目', archived_at: null };
const run = {
  run_id: 'starter-result', revision: 1, workspace_id: user.workspace_id, project_id: project.project_id,
  tender_filename: '【合成示例】系统运维-招标文件.pdf', company_name: '示例软件服务企业', status: 'NEEDS_REVIEW',
  version_number: 1, created_at: '2026-09-24T10:00:00Z', updated_at: '2026-09-24T10:00:00Z', archived_at: null,
  requirement_count: 1, unresolved_count: 1, blocker_count: 1, fatal_risk_count: 1, decision: {},
  tags: [], duplicate_run_ids: [], review: { items: [] }, evidence_assets: [], source_documents: [],
  requirements: [{ requirement_id: 'REQ-ONE', category: 'FATAL', criticality: 'BLOCKER', status: 'UNKNOWN',
    label: '废标风险', title: '提供类似运维项目业绩证明', evidence: [],
    source: { source_id: 'TENDER-001', filename: '合成招标文件.pdf', page: 1, quote: '应提交类似项目业绩证明。' } }],
};
const requests = []; const unknown = []; const domErrors = [];
const originalFetch = globalThis.fetch;
let holdSamples = false;
let authenticated = true;
const pendingSamples = [];
const jsonReply = (value, status = 200) => Promise.resolve(new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } }));
const sampleReply = (url) => new Response(`%PDF-1.7\nsynthetic ${url.searchParams.get('scenario')} ${url.searchParams.get('kind')}`, { headers: { 'content-type': 'application/pdf' } });
globalThis.fetch = (input, options = {}) => {
  const url = new URL(String(input), window.location.origin);
  const method = options.method || 'GET';
  requests.push({ path: url.pathname, query: url.search, method, body: options.body });
  if (url.pathname === '/api/auth/status') return jsonReply({ authenticated, setup_required: false, ...(authenticated ? { user } : {}) });
  if (url.pathname === '/api/projects') return jsonReply({ projects: [project] });
  if (url.pathname === '/api/members') return jsonReply({ members: [user] });
  if (url.pathname === '/api/runs') return jsonReply([]);
  if (url.pathname === '/api/notifications') return jsonReply({ notifications: [], count: 0 });
  if (url.pathname === '/api/accuracy/metrics') return jsonReply({ review_population_complete: false, sample_size: 0, precision: null, recall: null });
  if (url.pathname === '/api/jobs') return method === 'POST' ? jsonReply({ job_id: 'starter-job', status: 'PENDING' }, 202) : jsonReply({ jobs: [] });
  if (url.pathname === '/api/sample-tender') {
    if (holdSamples) return new Promise((resolve) => { pendingSamples.push(() => resolve(sampleReply(url))); });
    return Promise.resolve(sampleReply(url));
  }
  if (url.pathname === `/api/runs/${run.run_id}`) return jsonReply(run);
  if (url.pathname === `/api/runs/${run.run_id}/comments`) return jsonReply({ comments: [] });
  if (url.pathname === `/api/runs/${run.run_id}/audit`) return jsonReply({ events: [] });
  if (url.pathname === `/api/runs/${run.run_id}/remediations`) return jsonReply({ remediations: [] });
  unknown.push(`${method} ${url.pathname}`);
  return jsonReply({ detail: 'Unstubbed route' }, 404);
};
window.addEventListener('error', (event) => domErrors.push(event.error?.message || event.message));
const query = (selector) => {
  const node = document.querySelector(selector); assert.ok(node, `Expected ${selector}`); return node;
};
const pause = (ms = 0) => new Promise((resolve) => { setTimeout(resolve, ms); });
async function waitFor(predicate, label, timeout = 2500) {
  const until = Date.now() + timeout;
  while (!predicate() && Date.now() < until) await pause(10);
  assert.ok(predicate(), `${label}; errors=${domErrors.join(';')}; unexpected=${unknown.join(';')}`);
}
const selectFile = (selector, name) => {
  const transfer = new DataTransfer(); transfer.items.add(new window.File(['%PDF private manually selected'], name, { type: 'application/pdf' }));
  query(selector).files = transfer.files; query(selector).dispatchEvent(new window.Event('change', { bubbles: true }));
};
// jsdom's HTMLInputElement._formReset currently omits the native file-selection
// reset. Supply that browser primitive before app listeners, as in intake tests.
// Selection, validation, FormData construction and application events stay real.
query('#scan-form').addEventListener('reset', (event) => {
  queueMicrotask(() => {
    if (!event.defaultPrevented) { query('#tender-file').value = ''; query('#evidence-files').value = ''; }
  });
});
const resetIntake = async () => {
  for (const button of document.querySelectorAll('#scan-form [data-remove-file]')) button.click();
  query('#scan-form').reset(); await pause();
  if (query('#intake-panel').open) query('#close-intake').click();
};
const guideCount = () => query('#first-run-guide .first-run__count').textContent;

try {
  await test('first-run starter journey uses real app handlers and preserves newer user intent', async (suite) => {
    const { store } = await import('../src/core/store.js');
    const { navigate } = await import('../src/core/router.js');
    const app = await import('../src/app.js'); await app.ready;

    await suite.test('empty home offers exactly three actionable starters and software supplies two distinct files', async () => {
      await waitFor(() => document.querySelectorAll('#runs-list [data-starter]').length === 3, 'Render three starters');
      await pause(20);
      assert.match(guideCount(), /0 \/ 3/);
      query('[data-starter="software"]').click();
      await waitFor(() => query('#intake-panel').open, 'Software example opens intake');
      assert.equal(query('#tender-file').files.length, 1); assert.equal(query('#evidence-files').files.length, 1);
      assert.equal(query('#tender-file').files[0].name, '【合成示例】软件实施-招标文件.pdf');
      assert.equal(query('#evidence-files').files[0].name, '【合成示例】软件实施-企业材料.pdf');
      assert.ok(query('#tender-file').files[0].size > 0);
      assert.match(query('#tender-file-feedback').textContent, /软件实施-招标文件/);
      assert.match(guideCount(), /1 \/ 3/);
      assert.equal(requests.some((entry) => entry.path === '/api/jobs' && entry.method === 'POST'), false,
        'Selecting a template prepares files; it must not submit a job without confirmation.');
      await resetIntake();
    });

    await suite.test('operations template uploads native FormData and only viewing its completed result reaches 3/3', async () => {
      query('[data-starter="operations"]').click();
      await waitFor(() => query('#intake-panel').open, 'Operations example opens intake');
      assert.equal(query('#tender-file').files[0].name, run.tender_filename);
      assert.equal(query('#evidence-files').files[0].name, '【合成示例】系统运维-企业材料.pdf');
      const samples = requests.filter((entry) => entry.path === '/api/sample-tender');
      assert.deepEqual(samples.map((entry) => entry.query).sort(), [
        '?scenario=software&kind=tender', '?scenario=software&kind=evidence',
        '?scenario=operations&kind=tender', '?scenario=operations&kind=evidence',
      ].sort(), 'Each scenario fetches exactly one tender and one evidence document.');
      assert.equal(query('#scan-form').checkValidity(), true);
      query('#scan-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
      await waitFor(() => document.querySelector('#scancard-starter-job'), 'Real submit handler starts queued job');
      const submissions = requests.filter((entry) => entry.path === '/api/jobs' && entry.method === 'POST');
      assert.equal(submissions.length, 1); const form = submissions[0].body;
      assert.ok(form instanceof window.FormData);
      assert.equal(form.get('tender').name, run.tender_filename);
      assert.equal(form.getAll('evidence').length, 1);
      assert.equal(form.get('evidence').name, '【合成示例】系统运维-企业材料.pdf');
      assert.equal(form.get('project_id'), project.project_id);
      assert.equal(form.has('parent_run_id'), false);
      assert.equal(query('#intake-panel').open, false); assert.match(guideCount(), /2 \/ 3/);
      assert.equal(sources.length, 1);
      sources[0].onmessage({ data: JSON.stringify({ status: 'COMPLETED', run_id: run.run_id }) });
      await waitFor(() => document.querySelector('[data-scan-open="starter-result"]'), 'Completion exposes an actual result action');
      assert.match(guideCount(), /2 \/ 3/, 'Completion alone does not pretend the result has been viewed.');
      query('[data-scan-open="starter-result"]').click();
      await waitFor(() => !query('#detail-view').hidden && store.get().currentRun?.run_id === run.run_id, 'Result action loads detail');
      assert.match(guideCount(), /3 \/ 3/); assert.equal(query('#first-run-guide details').open, false);
      assert.equal(window.location.hash, `#detail/${run.run_id}`);
      assert.equal(query('#requirements').querySelectorAll('.review-card').length, 1);
      assert.equal(sources[0].closed, true);
      await navigate('home');
      await waitFor(() => document.querySelector('[data-starter="own"]'), 'Home restores first-run actions');
      await pause(20);
    });

    await suite.test('own-material starter opens without downloads and a delayed example preserves manually selected files', async () => {
      const initialSamples = requests.filter((entry) => entry.path === '/api/sample-tender').length;
      query('[data-starter="own"]').click(); await waitFor(() => query('#intake-panel').open, 'Own materials opens intake');
      assert.equal(query('#tender-file').files.length, 0);
      assert.equal(requests.filter((entry) => entry.path === '/api/sample-tender').length, initialSamples);
      await resetIntake();
      holdSamples = true; query('[data-starter="software"]').click();
      await waitFor(() => pendingSamples.length === 2, 'Two sample downloads remain pending');
      query('#top-new-scan').click(); await waitFor(() => query('#intake-panel').open, 'A user can open their own upload during preparation');
      selectFile('#tender-file', '真实手工招标.pdf'); selectFile('#evidence-files', '真实手工资质.pdf');
      query('#company-name').value = '用户手工企业名称';
      pendingSamples.splice(0).forEach((finish) => finish());
      await waitFor(() => !query('[data-starter="software"]').disabled, 'Preparation settles');
      assert.equal(query('#tender-file').files[0].name, '真实手工招标.pdf');
      assert.equal(query('#evidence-files').files[0].name, '真实手工资质.pdf');
      assert.equal(query('#company-name').value, '用户手工企业名称');
      assert.match(query('#app-toast').textContent, /保留你选好的材料/);
      await resetIntake();
    });

    await suite.test('session invalidation discards late samples without restoring files, private DOM or progress', async () => {
      query('[data-starter="operations"]').click();
      await waitFor(() => pendingSamples.length === 2, 'Sample download starts before logout');
      authenticated = false;
      authChannels[0].onmessage({ data: 'session-changed' });
      assert.equal(store.get().currentUser, null); assert.equal(query('#app-main').childElementCount, 0);
      assert.equal(query('#tender-file').files.length, 0); assert.equal(query('#evidence-files').files.length, 0);
      pendingSamples.splice(0).forEach((finish) => finish()); await pause(30);
      assert.equal(query('#intake-panel').open, false); assert.equal(query('#app-main').childElementCount, 0);
      assert.equal(query('#tender-file').files.length, 0); assert.equal(query('#evidence-files').files.length, 0);
      assert.equal(document.querySelector('#first-run-guide'), null);
      assert.equal(query('#auth-panel').open, true);
      assert.deepEqual(unknown, []); assert.deepEqual(domErrors, []);
    });
  });
} finally {
  window.dispatchEvent(new window.Event('pagehide'));
  const { unmountMatrix } = await import('../src/features/runs/matrix.js');
  const { unmountRunsView } = await import('../src/features/runs/list.js');
  const { unmountCollab } = await import('../src/features/runs/collab.js');
  const { unmountDecisionView } = await import('../src/features/runs/decision.js');
  const { store: legacy } = await import('../src/state.js');
  unmountMatrix(); unmountRunsView(); unmountCollab(); unmountDecisionView(); clearTimeout(legacy.toastTimer);
  let toast; while ((toast = document.querySelector('.toast-region .toast'))) toast.click();
  await pause(); dom.window.close(); globalThis.fetch = originalFetch;
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
  }
}
