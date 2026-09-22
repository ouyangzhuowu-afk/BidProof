/**
 * Dependency-free regression checks for the review workbench's trust boundaries.
 * Run with: node scripts/test-review-workbench.mjs
 * These are pure-logic checks; browser interaction and visual QA remain separate.
 */
import assert from 'node:assert/strict';
import { File } from 'node:buffer';
import test from 'node:test';
import { html, toHtml } from '../src/ui/render.js';
import { store as legacyStore } from '../src/state.js';
import { store as sharedStore } from '../src/core/store.js';
import { formatFileSize, validateFiles } from '../src/features/scan/intake.js';
import { getReviewProgress, hasCompleteCitation } from '../src/features/runs/review-model.js';

test('untrusted quotations and filenames remain text in SafeHtml templates', () => {
  const quote = '</blockquote><img src=x onerror="alert(1)"> & \'原文\'';
  const filename = '" autofocus onfocus="alert(2).pdf';
  const rendered = toHtml(html`<blockquote title="${filename}">${quote}</blockquote>`);
  assert.equal(rendered, '<blockquote title="&quot; autofocus onfocus=&quot;alert(2).pdf">'
    + '&lt;/blockquote&gt;&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &#039;原文&#039;</blockquote>');
  assert.equal(rendered.includes('<img'), false);
  assert.equal(rendered.includes('title=""'), false);
});

test('nested safe highlights retain markup while every dynamic fragment is escaped', () => {
  const rendered = toHtml(html`<p>${[
    '资质 <script>unsafe()</script>',
    html`<mark>${'<svg/onload=alert(1)>'}</mark>`,
  ]}</p>`);
  assert.equal(rendered, '<p>资质 &lt;script&gt;unsafe()&lt;/script&gt;'
    + '<mark>&lt;svg/onload=alert(1)&gt;</mark></p>');
  assert.equal(toHtml(false), '');
  assert.equal(toHtml(null), '');
});

test('untrusted API objects cannot forge a SafeHtml capability or mutate minted markup', () => {
  const forged = { __safe: true, value: '<img src=x onerror="alert(1)">' };
  const rendered = toHtml(html`<blockquote>${forged}</blockquote>`);
  assert.equal(rendered, '<blockquote>[object Object]</blockquote>');
  assert.equal(rendered.includes('<img'), false);
  const minted = html`<mark>${'有效期'}</mark>`;
  assert.ok(Object.isFrozen(minted));
  assert.throws(() => { minted.value = forged.value; }, TypeError);
  assert.equal(toHtml(html`<p>${minted}</p>`), '<p><mark>有效期</mark></p>');
});

test('legacy run writes notify migrated views once and migrated review writes remain visible', () => {
  const initial = sharedStore.get();
  const events = [];
  const stop = sharedStore.watch((state) => state.currentRun, (next, previous) => events.push({ next, previous }));
  try {
    const run = { run_id: 'qa-run', requirements: [], review: { items: [] } };
    legacyStore.currentRun = run;
    assert.equal(sharedStore.get().currentRun, run);
    assert.equal(events.length, 1);
    legacyStore.currentRun = run;
    assert.equal(events.length, 1, 'Reassigning an identical run must not duplicate notifications.');

    const reviewed = { ...run, review: { items: [{ requirement_id: 'req-1', decision: 'CONFIRM' }] } };
    sharedStore.set({ currentRun: reviewed });
    assert.equal(legacyStore.currentRun, reviewed);
    assert.equal(events.length, 2);
    assert.equal(events[1].previous, run);
  } finally {
    stop();
    sharedStore.reset(initial);
  }
});

test('current user and logout changes propagate in both state interfaces', () => {
  const initial = sharedStore.get();
  try {
    const user = { user_id: 'qa-reviewer', role: 'REVIEWER' };
    legacyStore.currentUser = user;
    assert.equal(sharedStore.get().currentUser, user);
    sharedStore.set({ currentUser: null, currentRun: null });
    assert.equal(legacyStore.currentUser, null);
    assert.equal(legacyStore.currentRun, null);
  } finally {
    sharedStore.reset(initial);
  }
});

const file = (name, contents = 'document') => new File([contents], name, { lastModified: 1 });

test('upload preflight accepts the six actual server formats, case insensitively', () => {
  for (const extension of ['pdf', 'docx', 'xlsx', 'pptx', 'txt', 'md']) {
    assert.deepEqual(validateFiles([file(`材料.${extension}`)]), []);
    assert.deepEqual(validateFiles([file(`材料.${extension.toUpperCase()}`)]), []);
  }
});

test('unsupported and empty inputs are rejected before upload', () => {
  for (const name of ['材料.doc', '材料.exe', '文件无后缀', '材料.pdf.exe']) {
    assert.equal(validateFiles([file(name)]).length, 1, name);
  }
  assert.equal(validateFiles([new File([], '空文件.pdf')]).length, 1);
  // Optional enterprise evidence may be empty; required tender is validated by its input.
  assert.deepEqual(validateFiles([], { multiple: true }), []);
});

test('one tender and multiple evidence documents follow different selection contracts', () => {
  const documents = [file('招标.pdf'), file('资质.pdf')];
  assert.equal(validateFiles(documents).length, 1);
  assert.deepEqual(validateFiles(documents, { multiple: true }), []);
});

test('server-provided size cap is exact, per-file, and not fabricated when unknown', () => {
  const fourBytes = file('四字节.pdf', '1234');
  const fiveBytes = file('五字节.pdf', '12345');
  assert.deepEqual(validateFiles([fourBytes], { maxBytes: 4 }), []);
  assert.equal(validateFiles([fiveBytes], { maxBytes: 4 }).length, 1);
  assert.deepEqual(validateFiles([fourBytes, fourBytes], { multiple: true, maxBytes: 4 }), []);
  assert.deepEqual(validateFiles([fiveBytes], { maxBytes: null }), []);
  assert.deepEqual(validateFiles([fiveBytes], { maxBytes: undefined }), []);
  assert.equal(formatFileSize(4), '4 B');
  assert.equal(formatFileSize(1024), '1.0 KB');
  assert.equal(formatFileSize(50 * 1024 * 1024), '50.0 MB');
});

test('machine PASS and ordinary comments do not increment human review progress', () => {
  const run = {
    requirements: [{ requirement_id: 'a', status: 'PASS' }, { requirement_id: 'b', status: 'FAIL' }],
    comments: [{ requirement_id: 'a', text: '已看到' }],
    review: { items: [] },
  };
  assert.deepEqual(getReviewProgress(run), { reviewed: 0, total: 2, pending: 2, percent: 0 });
});

test('progress counts each current requirement once and ignores obsolete review events', () => {
  const run = {
    requirements: ['a', 'b', 'c'].map((requirement_id) => ({ requirement_id })),
    review: { items: [
      { requirement_id: 'a', decision: 'PASS' },
      { requirement_id: 'a', decision: 'REJECT' },
      { requirement_id: 'b', decision: 'NEEDS_REVIEW' },
      { requirement_id: 'removed-item', decision: 'CONFIRM' },
    ] },
  };
  assert.deepEqual(getReviewProgress(run), { reviewed: 2, total: 3, pending: 1, percent: 67 });
});

test('empty and fully reviewed runs produce bounded, finite progress', () => {
  assert.deepEqual(getReviewProgress({ requirements: [] }), { reviewed: 0, total: 0, pending: 0, percent: 0 });
  assert.deepEqual(getReviewProgress({
    requirements: [{ requirement_id: 'a' }],
    review: { items: [{ requirement_id: 'a' }, { requirement_id: 'a' }] },
  }), { reviewed: 1, total: 1, pending: 0, percent: 100 });
});

const citation = (label = '第 12 页', quote = '提供有效的企业资质证明') => ({ locator: { label }, quote });

test('PASS needs both locatable tender text and at least one locatable evidence quotation', () => {
  const source = citation();
  const evidence = citation('第 3 页', '有效期至 2027 年');
  assert.equal(hasCompleteCitation({ source, evidence: [evidence] }), true);
  assert.equal(hasCompleteCitation({ source, evidence: [citation('', '候选'), evidence] }), true);
  assert.equal(hasCompleteCitation({ source, evidence: [] }), false);
  assert.equal(hasCompleteCitation({ source }), false);
  assert.equal(hasCompleteCitation({ evidence: [evidence] }), false);
  assert.equal(hasCompleteCitation({}), false);
});

test('a filename, source id, or page number alone cannot bypass the dual quotation gate', () => {
  const source = citation();
  const evidence = citation('第 3 页', '企业证据原文');
  for (const incomplete of [
    { filename: '资质.pdf', source_id: 'EVD-001', page: 3 },
    citation('第 3 页', ''),
    citation('', '有文字，但没有可定位出处'),
  ]) {
    assert.equal(hasCompleteCitation({ source, evidence: [incomplete] }), false);
    assert.equal(hasCompleteCitation({ source: incomplete, evidence: [evidence] }), false);
  }
});
