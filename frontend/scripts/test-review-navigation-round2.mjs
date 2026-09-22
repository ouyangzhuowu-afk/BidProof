/** Round-two navigation regression: real DOM + stubbed HTTP; no browser or network. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const runtime = process.env.JSDOM_MODULE || 'jsdom';
const { JSDOM } = await import(isAbsolute(runtime) ? pathToFileURL(runtime).href : runtime);
const source = await readFile(new URL('../../static/index.html', import.meta.url), 'utf8');
const dom = new JSDOM(source, { url: 'https://bidproof.invalid/app', pretendToBeVisual: true });
const { window } = dom;
const previous = new Map();
for (const key of ['window', 'document', 'localStorage', 'Element', 'HTMLElement', 'HTMLInputElement', 'HTMLButtonElement', 'HTMLFormElement', 'Event', 'CustomEvent', 'MouseEvent', 'FormData']) {
  previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? window : window[key] });
}
window.matchMedia = (query) => ({ matches: query.includes('prefers-reduced-motion'), media: query, addEventListener() {}, removeEventListener() {} });
window.HTMLElement.prototype.scrollIntoView = function () {};
window.document.querySelector('#detail-view').hidden = false;
assert.ok(window.document.querySelector('#review-navigation'), 'The shipped HTML must include the real navigation anchor.');
const { store } = await import('../src/core/store.js');
const { mountMatrix, unmountMatrix, resetMatrixView, renderMatrixSection } = await import('../src/features/runs/matrix.js');
const { getReviewQueueCounts, isHumanConfirmed, getReviewProgress } = await import('../src/features/runs/review-model.js');
const { riskRank } = await import('../src/core/format.js');
const initial = store.get();
const originalFetch = globalThis.fetch;
let run;
let requests = [];
let deferReview = false;
let deferComment = false;
let releaseResponse = null;
const ref = (id, filename, quote) => ({ source_id: id, filename, quote, page: 1, locator: { kind: 'page', label: '第 1 页', index: 1 } });
const makeRun = () => ({
  run_id: 'navigation-qa', revision: 3, tender_filename: '招标.pdf',
  source_documents: [{ source_id: 'TENDER-001', role: 'tender', filename: '招标.pdf', file_type: 'pdf' },
    { source_id: 'EVD-001', role: 'enterprise_evidence', filename: '证明.pdf', file_type: 'pdf' }],
  review: { items: [
    { requirement_id: 'R-09', decision: 'CONFIRM', new_status: 'PASS' },
    { requirement_id: 'R-09', decision: 'REJECT', new_status: 'NEEDS_REVIEW' },
    { requirement_id: 'R-09', decision: 'CONFIRM', new_status: 'PASS' },
    { requirement_id: 'R-10', decision: 'REJECT', new_status: 'NEEDS_REVIEW' },
    { requirement_id: 'R-11', decision: 'PASS', new_status: 'PASS' },
  ] },
  requirements: Array.from({ length: 30 }, (_, index) => ({
    requirement_id: `R-${String(index + 1).padStart(2, '0')}`, label: `条款 ${index + 1}`, title: `要求 ${index + 1} 的可核验原文`,
    category: index < 7 ? 'FATAL' : 'SCORING', criticality: index < 7 ? 'BLOCKER' : 'INFO',
    status: [7, 8, 10].includes(index) ? 'PASS' : 'NEEDS_REVIEW',
    source: ref('TENDER-001', '招标.pdf', '必须核对企业证明材料。'), evidence: [ref('EVD-001', '证明.pdf', '企业已提交可核验的证明。')],
  })),
});
globalThis.fetch = (url, options = {}) => {
  const body = options.body ? JSON.parse(options.body) : null;
  requests.push({ url: String(url), method: options.method || 'GET', body });
  if (String(url) === '/api/runs/navigation-qa/comments') {
    assert.equal(options.method, 'POST');
    const response = () => new Response(JSON.stringify({ body: body.body }), { status: 200, headers: { 'content-type': 'application/json' } });
    return deferComment ? new Promise((resolve) => { releaseResponse = () => resolve(response()); }) : Promise.resolve(response());
  }
  assert.equal(String(url), '/api/runs/navigation-qa/review', 'Only the explicit confirm test may write.');
  assert.equal(options.method, 'POST');
  assert.equal(body.revision, run.revision);
  const item = run.requirements.find((entry) => entry.requirement_id === body.requirement_id);
  item.status = body.new_status;
  run.review.items.push({ ...body }); run.revision += 1;
  const snapshot = JSON.stringify(run);
  const response = () => new Response(snapshot, { status: 200, headers: { 'content-type': 'application/json' } });
  return deferReview ? new Promise((resolve) => { releaseResponse = () => resolve(response()); }) : Promise.resolve(response());
};
function q(selector) { const node = window.document.querySelector(selector); assert.ok(node, `Missing ${selector}`); return node; }
const row = (id, child = '') => q(`#requirements [data-requirement-id="${id}"] ${child}`.trim());
const visibleIds = () => [...window.document.querySelectorAll('#requirements [data-requirement-id]')].map((node) => node.dataset.requirementId);
const priorityIds = () => [...window.document.querySelectorAll('#risk-list [data-requirement-id]')].map((node) => node.dataset.requirementId);
const state = (value) => q(`[data-review-status="${value}"]`).click();
function input(node, value) { node.value = value; node.dispatchEvent(new window.Event('input', { bubbles: true })); }
function dismiss() { for (const toast of window.document.querySelectorAll('.toast')) toast.click(); }
function reset() {
  dismiss(); resetMatrixView(); requests = []; run = makeRun(); deferReview = false; deferComment = false; releaseResponse = null;
  store.set({ currentRun: structuredClone(run), currentUser: { user_id: 'reviewer', role: 'REVIEWER' } });
  renderMatrixSection();
}
const pause = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
async function waitFor(predicate) { for (let n = 0; n < 100 && !predicate(); n += 1) await pause(10); assert.ok(predicate()); }
mountMatrix();
try {
  await test('round-two review navigation and draft retention', async (suite) => {
    await suite.test('human confirmation is distinct from machine PASS and rejected reviews', () => {
      reset();
      assert.deepEqual(getReviewQueueCounts(run), { total: 30, confirmed: 2, pending: 28 });
      assert.equal(isHumanConfirmed(run, run.requirements[7]), false);
      assert.equal(isHumanConfirmed(run, run.requirements[8]), true);
      assert.equal(isHumanConfirmed(run, run.requirements[9]), false);
      assert.equal(getReviewProgress(run).reviewed, 3, 'Human progress remains unique reviewed clauses, not resolved clauses.');
      state('CONFIRMED'); assert.deepEqual(new Set(visibleIds()), new Set(['R-09', 'R-11']));
      state('PENDING');
      assert.ok(!visibleIds().includes('R-09')); assert.ok(visibleIds().includes('R-10'));
      q('#matrix-pagination [data-page="next"]').click();
      assert.match(row('R-08', '.review-status').textContent, /系统已满足.*待核销/);
      assert.equal(requests.length, 0);
    });
    await suite.test('priority batches expose every risk and preserve source navigation', () => {
      reset(); assert.deepEqual(priorityIds(), ['R-01', 'R-02', 'R-03']);
      q('[data-risk-page="next"]').click(); assert.deepEqual(priorityIds(), ['R-04', 'R-05', 'R-06']);
      assert.match(q('#review-navigation').textContent, /条款 4/);
      assert.equal(window.document.activeElement.closest('[data-requirement-id]').dataset.requirementId, 'R-04');
      q('[data-risk-page="next"]').click(); assert.deepEqual(priorityIds(), ['R-07']);
      assert.equal(q('[data-risk-page="next"]').disabled, true);
      q('[data-risk-page="prev"]').click(); assert.deepEqual(priorityIds(), ['R-04', 'R-05', 'R-06']);
      assert.equal(requests.length, 0);
    });
    await suite.test('task-wide next to-do crosses pages and focuses an open target without confirming', () => {
      reset(); const ordered = [...run.requirements].sort((a, b) => riskRank(a) - riskRank(b));
      const origin = ordered[24]; const expected = ordered.slice(25).find((entry) => !isHumanConfirmed(run, entry));
      row(origin.requirement_id, '[data-source="tender"]').click();
      q('[data-review-nav="next"]').click();
      assert.equal(row(expected.requirement_id).open, true);
      assert.equal(q('#matrix-pagination [aria-current="page"]').textContent, '2');
      assert.equal(window.document.activeElement.closest('[data-requirement-id]').dataset.requirementId, expected.requirement_id);
      assert.equal(requests.length, 0);
    });
    await suite.test('previous respects task ordering and can reveal a target hidden by filters', () => {
      reset(); row('R-03', '[data-source="tender"]').click();
      state('CONFIRMED'); assert.ok(!visibleIds().includes('R-02'));
      q('[data-review-nav="previous"]').click();
      assert.equal(row('R-02').open, true);
      assert.equal(q('[data-review-status="ALL"]').getAttribute('aria-pressed'), 'true');
      assert.equal(requests.length, 0);
    });
    await suite.test('unsaved note survives next/previous navigation and hidden status filters', () => {
      reset(); row('R-01', '[data-note]').click(); input(row('R-01', 'textarea'), '待核对 <img onerror=1> 原件');
      assert.equal(row('R-01', '[data-draft-for]').hidden, false);
      row('R-01', '[data-source="tender"]').click();
      q('[data-review-nav="next"]').click(); q('[data-review-nav="previous"]').click();
      assert.equal(row('R-01', 'textarea').value, '待核对 <img onerror=1> 原件');
      state('CONFIRMED'); state('PENDING');
      assert.equal(row('R-01', 'textarea').value, '待核对 <img onerror=1> 原件');
      assert.equal(row('R-01').querySelector('[onerror]'), null);
      assert.equal(requests.length, 0);
    });
    await suite.test('note and rejection drafts survive switching editor modes independently', () => {
      reset(); row('R-01', '[data-note]').click(); input(row('R-01', 'textarea'), '人工备注草稿');
      row('R-01', '[data-review="REJECT"]').click(); input(row('R-01', 'textarea'), '驳回原因草稿');
      row('R-01', '[data-note]').click(); assert.equal(row('R-01', 'textarea').value, '人工备注草稿');
      row('R-01', '[data-review="REJECT"]').click(); assert.equal(row('R-01', 'textarea').value, '驳回原因草稿');
      q('#requirements [data-requirement-id="R-01"] [data-editor-cancel]').click();
      assert.equal(row('R-01', 'textarea').value, '人工备注草稿', 'Discarding a rejection must not discard a separate note.');
      assert.equal(requests.length, 0);
    });
    await suite.test('confirm updates human filters while retaining a separate unsaved note', async () => {
      reset(); row('R-01', '[data-note]').click(); input(row('R-01', 'textarea'), '尚未保存到评论的备注');
      row('R-01', '[data-review="CONFIRM"]').click();
      await waitFor(() => store.get().currentRun.revision === 4);
      assert.equal(requests.length, 1); assert.equal(requests[0].body.new_status, 'PASS');
      state('CONFIRMED'); assert.ok(visibleIds().includes('R-01'));
      assert.equal(row('R-01', 'textarea').value, '尚未保存到评论的备注');
      assert.equal(row('R-01', '[data-draft-for]').hidden, false);
      state('PENDING'); assert.ok(!visibleIds().includes('R-01'));
      assert.equal(getReviewQueueCounts(store.get().currentRun).confirmed, 3);
    });
    await suite.test('a delayed review response cannot overwrite a newer revision already displayed', async () => {
      reset(); deferReview = true;
      row('R-01', '[data-review="CONFIRM"]').click();
      await waitFor(() => Boolean(releaseResponse));
      const newer = { ...structuredClone(run), revision: 5, tags: ['刚保存的协作信息'] };
      store.set({ currentRun: newer });
      releaseResponse();
      await waitFor(() => [...window.document.querySelectorAll('.toast')].some((node) => node.textContent.includes('较新版本')));
      assert.equal(store.get().currentRun.revision, 5);
      assert.deepEqual(store.get().currentRun.tags, ['刚保存的协作信息']);
      assert.equal(store.get().currentRun.requirements[0].status, 'PASS');
      assert.equal(requests.length, 1);
    });
    await suite.test('an in-flight note locks both copies of its editor while preserving other drafts', async () => {
      reset(); deferComment = true;
      row('R-01', '[data-note]').click(); input(row('R-01', 'textarea'), '实际提交的备注 A');
      renderMatrixSection();
      row('R-01', 'form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
      await waitFor(() => Boolean(releaseResponse));
      for (const area of window.document.querySelectorAll('[data-requirement-id="R-01"] textarea')) assert.equal(area.readOnly, true);
      for (const button of window.document.querySelectorAll('[data-requirement-id="R-01"] [data-note], [data-requirement-id="R-01"] [type="submit"], [data-requirement-id="R-01"] [data-editor-cancel]')) assert.equal(button.disabled, true);
      q('#risk-list [data-requirement-id="R-01"] form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
      assert.equal(requests.length, 1, 'The second presentation cannot submit the same pending comment twice.');
      row('R-02', '[data-note]').click(); input(row('R-02', 'textarea'), '另一个条款的未保存备注 B');
      releaseResponse();
      await waitFor(() => row('R-01').querySelector('textarea') === null);
      assert.equal(row('R-02', 'textarea').value, '另一个条款的未保存备注 B');
      assert.equal(row('R-02', '[data-draft-for]').hidden, false);
      assert.equal(row('R-01', '[data-note]').disabled, false);
      assert.equal(q('#risk-list [data-requirement-id="R-01"]').querySelector('textarea'), null);
      assert.equal(requests[0].body.body, '【条款 R-01】实际提交的备注 A');
    });
    await suite.test('read-only users can navigate but cannot acquire editable review controls', () => {
      reset(); row('R-01', '[data-note]').click(); input(row('R-01', 'textarea'), '角色变更前的未保存备注');
      store.set({ currentUser: { user_id: 'viewer', role: 'VIEWER' } }); renderMatrixSection();
      assert.equal(row('R-01', 'textarea').readOnly, true);
      assert.equal(row('R-01', '[type="submit"]').disabled, true);
      row('R-01', 'form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
      q('[data-review-nav="next"]').click();
      for (const button of window.document.querySelectorAll('.review-actions button')) assert.equal(button.disabled, true);
      state('CONFIRMED'); assert.equal(requests.length, 0);
    });
    await suite.test('empty runs disable navigation without declaring human completion', () => {
      reset(); run.requirements = []; run.review.items = []; store.set({ currentRun: structuredClone(run) }); resetMatrixView(); renderMatrixSection();
      assert.equal(q('[data-review-nav="next"]').disabled, true); assert.equal(q('[data-review-nav="previous"]').disabled, true);
      assert.match(q('#review-navigation').textContent, /尚未提取到要求项/);
      assert.ok(!q('#review-navigation').textContent.includes('全部条款已人工核销'));
    });
  });
} finally {
  unmountMatrix(); dismiss(); store.reset(initial); dom.window.close(); globalThis.fetch = originalFetch;
  for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
}
