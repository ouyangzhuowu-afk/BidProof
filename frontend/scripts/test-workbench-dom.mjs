/**
 * DOM-only interaction regression. This does not run a browser or assess visuals.
 * Uses a separately installed jsdom, never a runtime/product dependency:
 * JSDOM_MODULE=/absolute/path/to/jsdom/lib/api.js node scripts/test-workbench-dom.mjs
 * Without JSDOM_MODULE, the host must make `jsdom` resolvable.
 * All HTTP calls are stubbed; HTML scripts/resources are never executed or fetched.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const jsdomPath = process.env.JSDOM_MODULE || 'jsdom';
const { JSDOM } = await import(isAbsolute(jsdomPath) ? pathToFileURL(jsdomPath).href : jsdomPath);
const source = await readFile(new URL('../../static/index.html', import.meta.url), 'utf8');
const dom = new JSDOM(source, { url: 'https://bidproof.invalid/app', pretendToBeVisual: true });
const { window } = dom;
const originalGlobals = new Map();
for (const key of ['window', 'document', 'localStorage', 'Element', 'HTMLElement', 'HTMLInputElement',
  'HTMLButtonElement', 'HTMLFormElement', 'Event', 'CustomEvent', 'MouseEvent', 'FormData']) {
  originalGlobals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? window : window[key] });
}
window.matchMedia = (query) => ({ matches: query.includes('prefers-reduced-motion'), media: query,
  addEventListener() {}, removeEventListener() {} });
window.HTMLElement.prototype.scrollIntoView = function () {};
window.document.querySelector('#detail-view').hidden = false;

const originalFetch = globalThis.fetch;
const { store } = await import('../src/core/store.js');
const { mountMatrix, unmountMatrix, resetMatrixView, renderMatrixSection } = await import('../src/features/runs/matrix.js');
const { getReviewProgress } = await import('../src/features/runs/review-model.js');
const initialState = store.get();
const maliciousQuote = '必须提供有效期内的证明 <img src="evil.invalid" onerror="alert(1)">，否则否决投标。';
let serverRun;
let requests = [];
let unexpectedRequests = [];
let conflictNext = false;
let failureNext = false;

function reference(sourceId, filename, page, quote) {
  return { source_id: sourceId, filename, page, quote, locator: { kind: 'page', index: page, label: `第 ${page} 页` } };
}

function fixture() {
  const tender = '招标文件.pdf';
  const evidence = '企业资质.pdf';
  return {
    run_id: 'dom-qa-run', revision: 7, tender_filename: tender, status: 'NEEDS_REVIEW',
    source_documents: [
      { source_id: 'TENDER-001', role: 'tender', filename: tender, file_type: 'pdf', pages: 20 },
      { source_id: 'EVD-001', role: 'enterprise_evidence', filename: evidence, file_type: 'pdf', pages: 10 },
    ],
    review: { items: [] },
    requirements: [
      { requirement_id: 'R-FATAL', category: 'FATAL', criticality: 'BLOCKER', label: '废标红线',
        title: '资质有效期不满足将否决投标', status: 'NEEDS_REVIEW',
        source: reference('TENDER-001', tender, 12, maliciousQuote),
        evidence: [reference('EVD-001', evidence, 3, '证书有效期至 2027 年，必须核对原件。')] },
      { requirement_id: 'R-MISSING', category: 'QUALIFICATION', criticality: 'BLOCKER', label: '基本资格',
        title: '提供符合要求的资格证明', status: 'UNKNOWN',
        source: reference('TENDER-001', tender, 8, '必须提交营业执照。'), evidence: [] },
      { requirement_id: 'R-SCORE', category: 'SCORING', criticality: 'NORMAL', label: '售后服务评分',
        title: '售后响应承诺', status: 'PASS',
        source: reference('TENDER-001', tender, 15, '售后响应时间可获得评分。'),
        evidence: [reference('EVD-001', evidence, 6, '售后响应承诺为二小时。')] },
    ],
  };
}

const response = (payload, status = 200) => Promise.resolve(new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } }));
globalThis.fetch = (url, options = {}) => {
  const request = { url: String(url), method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null };
  requests.push(request);
  if (request.url === '/api/runs/dom-qa-run/review' && request.method === 'POST') {
    if (failureNext) { failureNext = false; return response({ detail: '本次未保存，请重试。' }, 503); }
    if (conflictNext) {
      conflictNext = false;
      serverRun.revision += 1;
      serverRun.requirements[0].title = '其他成员更新后的条款';
      return response({ detail: '任务版本冲突' }, 409);
    }
    const item = serverRun.requirements.find((entry) => entry.requirement_id === request.body.requirement_id);
    assert.ok(item, 'The review must refer to an existing requirement.');
    assert.equal(request.body.revision, serverRun.revision, 'The review must use the current server revision.');
    item.status = request.body.decision === 'CONFIRM' ? request.body.new_status : 'NEEDS_REVIEW';
    serverRun.review.items.push({ ...request.body, new_status: item.status });
    serverRun.revision += 1;
    return response(serverRun);
  }
  if (request.url === '/api/runs/dom-qa-run/comments' && request.method === 'POST') {
    return response({ comment_id: 'qa-comment', body: request.body.body });
  }
  if (request.url === '/api/runs/dom-qa-run' && request.method === 'GET') return response(serverRun);
  unexpectedRequests.push(request);
  throw new Error(`No network is allowed: unexpected ${request.method} ${request.url}`);
};

const pause = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
async function waitFor(condition, message, timeout = 1500) {
  const deadline = Date.now() + timeout;
  while (!condition() && Date.now() < deadline) await pause(10);
  assert.ok(condition(), message);
}
function query(selector) {
  const node = window.document.querySelector(selector);
  assert.ok(node, `Expected DOM node: ${selector}`);
  return node;
}
const requirement = (id, selector = '') => query(`#requirements [data-requirement-id="${id}"] ${selector}`.trim());
const submit = (form) => form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
function dismissToasts() {
  let toast;
  while ((toast = window.document.querySelector('.toast-region .toast'))) toast.click();
}
function reset() {
  assert.deepEqual(unexpectedRequests, [], 'Only explicitly stubbed API paths are allowed.');
  dismissToasts(); resetMatrixView();
  requests = []; unexpectedRequests = []; conflictNext = false; failureNext = false;
  serverRun = fixture();
  store.set({ currentRun: structuredClone(serverRun), currentUser: { user_id: 'qa-reviewer', role: 'REVIEWER' } });
  renderMatrixSection();
}

mountMatrix();
// Re-entry should not register a second set of delegated listeners.
mountMatrix();

try {
  await test('workbench DOM interaction contract (stubbed HTTP, no browser)', async (suite) => {
    await suite.test('initial cards separate priority risk from compact complete matrix', () => {
      reset();
      assert.equal(window.document.querySelectorAll('#risk-list .review-card').length, 2);
      assert.equal(window.document.querySelectorAll('#requirements .review-card').length, 3);
      assert.equal(query('#risk-list .review-card').dataset.requirementId, 'R-FATAL', 'Unresolved fatal clauses must precede other categories.');
      assert.ok(query('#risk-list [data-requirement-id="R-FATAL"]').open);
      assert.equal(requirement('R-SCORE').open, false);
      assert.equal(requirement('R-MISSING', '[data-review="CONFIRM"]').disabled, true);
      requirement('R-MISSING', '[data-review="CONFIRM"]').click();
      assert.equal(requests.length, 0, 'Missing evidence cannot be confirmed.');
      assert.equal(query('#matrix-count').textContent, '共 3 项');
    });

    await suite.test('malicious quotation remains literal text, including highlighted fragments', () => {
      reset();
      const excerpt = requirement('R-FATAL', 'blockquote');
      assert.equal(excerpt.textContent, maliciousQuote);
      assert.equal(excerpt.querySelector('img'), null);
      assert.equal(window.document.querySelector('img[src="evil.invalid"]'), null);
      assert.equal(window.document.querySelector('[onerror]'), null);
      assert.ok(excerpt.querySelector('mark'), 'Meaningful source keywords remain highlighted.');
      requirement('R-FATAL', '[data-source="tender"]').click();
      const reader = query('#evidence-reader');
      assert.ok(reader.textContent.includes(maliciousQuote));
      assert.equal(reader.querySelector('img:not([data-source-page])'), null);
    });

    await suite.test('confirm sends one explicit PASS with revision and collapses the saved card', async () => {
      reset();
      requirement('R-FATAL', '[data-review="CONFIRM"]').click();
      await waitFor(() => store.get().currentRun.revision === 8, 'Confirmed run should replace the client state.');
      assert.equal(requests.length, 1, 'Mounting twice must not double-submit.');
      assert.deepEqual(requests[0], { url: '/api/runs/dom-qa-run/review', method: 'POST', body: {
        note: '', requirement_id: 'R-FATAL', decision: 'CONFIRM', revision: 7, new_status: 'PASS',
      } });
      assert.equal(requirement('R-FATAL').dataset.status, 'PASS');
      assert.equal(requirement('R-FATAL').open, false);
      assert.equal(requirement('R-FATAL', '[data-review="CONFIRM"]').disabled, true);
      assert.match(requirement('R-FATAL').textContent, /已核销通过/);
      assert.equal(window.document.querySelector('#risk-list [data-requirement-id="R-FATAL"]'), null);
      assert.equal(getReviewProgress(store.get().currentRun).reviewed, 1);
    });

    await suite.test('reject requires a nonblank reason and preserves it in the review request', async () => {
      reset();
      requirement('R-SCORE', '[data-review="REJECT"]').click();
      const form = requirement('R-SCORE', '[data-review-form]');
      const text = form.querySelector('textarea');
      assert.equal(text.required, true);
      submit(form); await pause(0);
      assert.equal(requests.length, 0);
      text.value = '  ';
      submit(form); await pause(0);
      assert.equal(requests.length, 0, 'Whitespace is not a valid rejection reason.');
      text.value = '证书到期时间需要进一步核验';
      text.dispatchEvent(new window.Event('input', { bubbles: true }));
      submit(form);
      await waitFor(() => store.get().currentRun.revision === 8, 'Reject should return the updated run.');
      assert.equal(requests.length, 1);
      assert.equal(requests[0].body.decision, 'REJECT');
      assert.equal(requests[0].body.revision, 7);
      assert.equal(requests[0].body.note, text.value);
      assert.equal('new_status' in requests[0].body, false);
      assert.equal(requirement('R-SCORE').dataset.status, 'NEEDS_REVIEW');
      assert.match(requirement('R-SCORE').textContent, /证书到期时间需要进一步核验/);
    });

    await suite.test('adding a note uses the comments endpoint and changes neither status nor human progress', async () => {
      reset();
      const before = store.get().currentRun;
      const note = '核对备注 <img src="note.invalid" onerror="alert(1)">';
      let saved = false;
      window.addEventListener('bidproof:comments-changed', () => { saved = true; }, { once: true });
      requirement('R-FATAL', '[data-note]').click();
      const form = requirement('R-FATAL', '[data-review-form]');
      form.querySelector('textarea').value = note;
      submit(form);
      await waitFor(() => saved, 'A successful note should publish the comments update event.');
      assert.equal(requests.length, 1);
      assert.equal(requests[0].url, '/api/runs/dom-qa-run/comments');
      assert.equal(requests[0].body.body, `【条款 R-FATAL】${note}`);
      assert.equal(store.get().currentRun, before);
      assert.equal(getReviewProgress(store.get().currentRun).reviewed, 0);
      assert.equal(requirement('R-FATAL').dataset.status, 'NEEDS_REVIEW');
      assert.equal(window.document.querySelector('img[src="note.invalid"]'), null);
    });

    await suite.test('category filter and debounced search narrow the matrix and can be cleared', async () => {
      reset();
      query('#matrix-filters [data-category="SCORING"]').click();
      assert.equal(window.document.querySelectorAll('#requirements .review-card').length, 1);
      assert.equal(requirement('R-SCORE').dataset.category, 'SCORING');
      assert.equal(query('#matrix-filters [data-category="SCORING"]').getAttribute('aria-pressed'), 'true');
      query('#matrix-filters [data-category="ALL"]').click();
      const input = query('#requirement-search');
      input.value = '营业执照'; input.dispatchEvent(new window.Event('input', { bubbles: true }));
      await waitFor(() => query('#matrix-count').textContent === '共 1 项', 'Search should match actual source quotation text.');
      assert.equal(window.document.querySelectorAll('#requirements .review-card').length, 1);
      assert.ok(requirement('R-MISSING'));
      input.value = '不存在的条款'; input.dispatchEvent(new window.Event('input', { bubbles: true }));
      await waitFor(() => query('#matrix-count').textContent === '共 0 项', 'No match should show an explicit empty state.');
      assert.match(query('#requirements').textContent, /没有符合条件的条款/);
      input.value = ''; input.dispatchEvent(new window.Event('input', { bubbles: true }));
      await waitFor(() => query('#matrix-count').textContent === '共 3 项', 'Clearing search should recover all cards.');
    });

    await suite.test('source selection updates both reader sides and exposes only real page URLs', () => {
      reset();
      requirement('R-SCORE', '[data-source="evidence"]').click();
      const reader = query('#evidence-reader');
      assert.match(reader.querySelector('.evidence-reader__context').textContent, /售后服务评分/);
      assert.ok(requirement('R-SCORE').classList.contains('review-card--selected'));
      assert.ok(reader.contains(window.document.activeElement), 'Focus should enter the chosen reader side.');
      const pages = [...reader.querySelectorAll('img[data-source-page]')].map((image) => image.getAttribute('src'));
      assert.deepEqual(pages, ['/api/runs/dom-qa-run/files/TENDER-001/pages/15', '/api/runs/dom-qa-run/files/EVD-001/pages/6']);
      reader.querySelector('img[data-source-page]').dispatchEvent(new window.Event('error'));
      assert.match(reader.textContent, /原页暂时无法显示/);
      assert.match(reader.textContent, /售后响应时间可获得评分/);
      requirement('R-MISSING', '[data-source="evidence"]').click();
      assert.match(query('#evidence-reader').textContent, /暂未匹配到证据/);
      assert.equal(query('#evidence-reader').querySelectorAll('img[data-source-page]').length, 1);
    });

    await suite.test('source buttons focus their respective reader sides and return focuses the current card', () => {
      reset();
      requirement('R-SCORE', '[data-source="evidence"]').click();
      assert.equal(window.document.activeElement.dataset.readerRole, 'evidence');
      requirement('R-SCORE', '[data-source="tender"]').click();
      assert.equal(window.document.activeElement.dataset.readerRole, 'tender');
      query('#evidence-reader [data-reader-return]').click();
      assert.equal(window.document.activeElement, requirement('R-SCORE', 'summary'));
    });

    await suite.test('page zoom toggles accessibly and becomes unavailable when the original page fails', () => {
      reset();
      requirement('R-FATAL', '[data-source="tender"]').click();
      const side = query('#evidence-reader [data-reader-role="tender"]');
      const button = side.querySelector('[data-page-zoom]');
      const page = side.querySelector('.reader-page');
      assert.equal(button.getAttribute('aria-pressed'), 'false');
      button.click();
      assert.equal(button.getAttribute('aria-pressed'), 'true');
      assert.equal(button.textContent, '适应宽度');
      assert.ok(page.classList.contains('reader-page--zoom'));
      assert.equal(window.document.activeElement, page);
      button.click();
      assert.equal(button.getAttribute('aria-pressed'), 'false');
      assert.equal(page.classList.contains('reader-page--zoom'), false);
      page.querySelector('img').dispatchEvent(new window.Event('error'));
      assert.equal(button.hidden, true);
      assert.match(page.textContent, /原页暂时无法显示/);
    });

    await suite.test('failed rejection keeps its typed reason available for an intentional retry', async () => {
      reset(); failureNext = true;
      requirement('R-SCORE', '[data-review="REJECT"]').click();
      const form = requirement('R-SCORE', '[data-review-form]');
      const text = form.querySelector('textarea');
      text.value = '证明材料与实际项目不一致';
      text.dispatchEvent(new window.Event('input', { bubbles: true }));
      submit(form);
      await waitFor(() => window.document.querySelector('.toast--error'), 'Failed rejection should report an error.');
      assert.equal(requirement('R-SCORE', 'textarea').value, '证明材料与实际项目不一致');
      assert.equal(form.querySelector('button[type="submit"]').disabled, false);
      assert.equal(requirement('R-SCORE').dataset.status, 'PASS');
      submit(form);
      await waitFor(() => store.get().currentRun.revision === 8, 'The retained rejection can be retried.');
      assert.equal(requests.length, 2);
      assert.equal(requests[1].body.note, '证明材料与实际项目不一致');
      assert.equal(requirement('R-SCORE').dataset.status, 'NEEDS_REVIEW');
    });

    await suite.test('server failure keeps the original verdict and allows an intentional retry', async () => {
      reset(); failureNext = true;
      requirement('R-FATAL', '[data-review="CONFIRM"]').click();
      await waitFor(() => window.document.querySelector('.toast--error'), 'Server failure should be visible.');
      assert.equal(store.get().currentRun.revision, 7);
      assert.equal(requirement('R-FATAL').dataset.status, 'NEEDS_REVIEW');
      assert.equal(requirement('R-FATAL', '[data-review="CONFIRM"]').disabled, false);
      assert.equal(requests.length, 1, 'Mutation requests must not retry themselves.');
      requirement('R-FATAL', '[data-review="CONFIRM"]').click();
      await waitFor(() => store.get().currentRun.revision === 8, 'Explicit retry should remain usable.');
      assert.equal(requests.length, 2);
    });

    await suite.test('a conflict refreshes the latest run without resubmitting or claiming success', async () => {
      reset(); conflictNext = true;
      requirement('R-FATAL', '[data-review="CONFIRM"]').click();
      await waitFor(() => store.get().currentRun.revision === 8, 'Version conflict should refresh the newest run.');
      assert.deepEqual(requests.map(({ method, url }) => ({ method, url })), [
        { method: 'POST', url: '/api/runs/dom-qa-run/review' },
        { method: 'GET', url: '/api/runs/dom-qa-run' },
      ]);
      assert.equal(requirement('R-FATAL').dataset.status, 'NEEDS_REVIEW');
      assert.match(requirement('R-FATAL').textContent, /其他成员更新后的条款/);
      assert.match(query('.toast--error').textContent, /本次操作未保存/);
      assert.equal(requirement('R-FATAL', '[data-review="CONFIRM"]').disabled, false);
    });

    await suite.test('read-only role keeps every review and note action disabled', () => {
      reset();
      store.set({ currentUser: { user_id: 'qa-viewer', role: 'VIEWER' } });
      renderMatrixSection();
      for (const button of window.document.querySelectorAll('.review-actions button')) assert.equal(button.disabled, true);
      assert.equal(requests.length, 0);
      assert.deepEqual(unexpectedRequests, [], 'No test may perform real or unstubbed network activity.');
    });
  });
} finally {
  unmountMatrix(); dismissToasts(); store.reset(initialState); dom.window.close();
  globalThis.fetch = originalFetch;
  for (const [key, descriptor] of originalGlobals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
}
