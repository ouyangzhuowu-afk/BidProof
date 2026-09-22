/**
 * Reader navigation DOM checks. No browser layout or real network is exercised.
 * JSDOM_MODULE=/absolute/path/to/jsdom/lib/api.js node frontend/scripts/test-reader-navigation-dom.mjs
 */
import assert from 'node:assert/strict';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const dependency = process.env.JSDOM_MODULE || 'jsdom';
const { JSDOM } = await import(isAbsolute(dependency) ? pathToFileURL(dependency).href : dependency);
const dom = new JSDOM('<section id="detail-view"><aside id="evidence-reader"></aside></section>', {
  url: 'https://bidproof.invalid/app', pretendToBeVisual: true,
});
const originals = new Map();
for (const key of ['window', 'document', 'localStorage', 'Element', 'HTMLElement', 'Event', 'CustomEvent']) {
  originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? dom.window : dom.window[key] });
}
const originalFetch = globalThis.fetch;
globalThis.fetch = () => { throw new Error('Reader DOM tests must never perform network requests.'); };
const { renderEvidenceReader } = await import('../src/features/runs/evidence-reader.js');

function fixture(count = 1) {
  const refs = Array.from({ length: count }, (_, index) => ({ source_id: `EVD-${index + 1}`, filename: `证明-${index + 1}.pdf`,
    page: 1, locator: { kind: 'page', index: 1, label: '第 1 页' }, quote: `企业证明 ${index + 1} 的摘录。` }));
  const item = { requirement_id: 'R-1', label: '有效资质', category: 'QUALIFICATION',
    source: { source_id: 'TENDER-001', page: 2, locator: { kind: 'page', index: 2, label: '第 2 页' }, quote: '必须提供有效资质；这段摘录来自引用第 2 页。' },
    evidence: refs };
  const run = { run_id: 'reader-test', tender_filename: '招标.pdf', requirements: [item], source_documents: [
    { source_id: 'TENDER-001', filename: '招标.pdf', file_type: 'pdf', role: 'tender', pages: 3 },
    ...refs.map((reference) => ({ source_id: reference.source_id, filename: reference.filename,
      file_type: 'pdf', role: 'enterprise_evidence', pages: 4 })),
  ] };
  return { run, item };
}

function query(selector, context = document) {
  const result = context.querySelector(selector);
  assert.ok(result, `Missing ${selector}`);
  return result;
}
const side = (role = 'tender') => query(`[data-reader-role="${role}"]`);
const img = (role = 'tender') => query('img[data-source-page]', side(role));
const action = (name, role = 'tender') => query(`[data-reader-page="${name}"]`, side(role));
const select = (index) => {
  const picker = query('[data-evidence-select]'); picker.value = String(index);
  picker.dispatchEvent(new window.Event('change', { bubbles: true }));
};
function render(data = fixture()) {
  renderEvidenceReader(data.run, null);
  renderEvidenceReader(data.run, data.item);
  return data;
}

try {
  await test('original evidence reader navigation', async (suite) => {
    await suite.test('previous / next respect recorded bounds and return to the real citation', () => {
      render();
      const otherImage = img('evidence');
      assert.match(img().getAttribute('src'), /\/TENDER-001\/pages\/2$/);
      assert.equal(action('citation').disabled, true);
      action('previous').click();
      assert.match(img().getAttribute('src'), /\/pages\/1$/);
      assert.equal(action('previous').disabled, true);
      assert.match(side().textContent, /正在浏览第 1 页/);
      assert.match(side().textContent, /引用第 2 页/);
      assert.match(side().textContent, /摘录仍来自引用第 2 页/);
      action('next').click(); action('next').click();
      assert.match(img().getAttribute('src'), /\/pages\/3$/);
      assert.equal(action('next').disabled, true);
      assert.equal(document.activeElement, query('[data-reader-position]', side()), 'Disabled navigation moves focus to the visible page position.');
      action('citation').click();
      assert.match(img().getAttribute('src'), /\/pages\/2$/);
      assert.equal(img('evidence'), otherImage, 'Browsing tender pages must not reload enterprise evidence.');
      assert.match(side().textContent, /文件记录共 3 页/);
    });

    await suite.test('unknown total stays unknown, including after a page-load failure', () => {
      const data = fixture(); delete data.run.source_documents[0].pages; render(data);
      assert.match(side().textContent, /总页数未记录/);
      assert.doesNotMatch(side().textContent, /文件记录共/);
      action('next').click();
      img().dispatchEvent(new window.Event('error'));
      assert.match(side().textContent, /原页暂时无法显示/);
      assert.match(side().textContent, /总页数未记录/);
      assert.doesNotMatch(side().textContent, /最后一页/);
      assert.equal(action('next').disabled, false, 'An image error is not proof of the last page.');
      assert.match(query('.reader-excerpt', side()).textContent, /必须提供有效资质/);
      assert.equal(query('[data-page-zoom]', side()).hidden, true);
      action('retry').click();
      assert.match(img().getAttribute('src'), /\/pages\/3$/);
      assert.equal(query('.reader-page', side()).getAttribute('aria-busy'), 'true');
      img().dispatchEvent(new window.Event('load'));
      assert.equal(query('.reader-page', side()).getAttribute('aria-busy'), 'false');
      assert.match(query('[data-page-status]', side()).textContent, /已显示第 3 页/);
      assert.equal(query('[data-page-zoom]', side()).hidden, false);
    });

    await suite.test('conflicting recorded total never relocates the citation or invents a page count', () => {
      const data = fixture(); data.run.source_documents[0].pages = 1; render(data);
      assert.match(side().textContent, /页数记录与引用不一致/);
      assert.doesNotMatch(side().textContent, /文件记录共 1 页/);
      assert.match(img().getAttribute('src'), /\/pages\/2$/);
      action('next').click();
      assert.match(img().getAttribute('src'), /\/pages\/3$/);
      action('citation').click();
      assert.match(img().getAttribute('src'), /\/pages\/2$/);
    });

    await suite.test('invalid total metadata is not promoted to a document page count', () => {
      for (const value of [0, -1, 2.5, Infinity, 'invalid']) {
        const data = fixture(); data.run.source_documents[0].pages = value; render(data);
        assert.match(side().textContent, /总页数未记录/);
        assert.doesNotMatch(side().textContent, /文件记录共/);
      }
    });

    await suite.test('many evidence entries render only the selected original and preserve each reading position', () => {
      render(fixture(35));
      assert.equal(document.querySelectorAll('img[data-source-page]').length, 2);
      const picker = query('[data-evidence-select]');
      assert.equal(picker.options.length, 35);
      assert.equal(query(`label[for="${picker.id}"]`).textContent, '匹配证据 · 共 35 份');
      action('next').click();
      const tenderImage = img();
      select(34);
      assert.equal(img(), tenderImage);
      assert.match(img('evidence').getAttribute('src'), /\/EVD-35\/pages\/1$/);
      assert.match(side('evidence').textContent, /企业证明 35 的摘录/);
      assert.equal(document.querySelectorAll('img[data-source-page]').length, 2);
      action('next', 'evidence').click();
      select(0); select(34);
      assert.match(img('evidence').getAttribute('src'), /\/EVD-35\/pages\/2$/);
      assert.match(query('[data-evidence-selection-status]').textContent, /第 35 份.*共 35 份/);
    });

    await suite.test('stale image events cannot replace a newly selected page with a false failure', () => {
      render();
      const stale = img();
      action('next').click();
      const current = img();
      stale.dispatchEvent(new window.Event('error'));
      stale.dispatchEvent(new window.Event('load'));
      assert.equal(img(), current);
      assert.equal(query('.reader-page', side()).getAttribute('aria-busy'), 'true');
      current.dispatchEvent(new window.Event('load'));
      assert.match(query('[data-page-status]', side()).textContent, /已显示第 3 页/);
    });

    await suite.test('same-clause rerender retains the page while a different clause opens its citation', () => {
      const data = render();
      action('next').click();
      query('[data-page-zoom]', side()).click();
      renderEvidenceReader(data.run, data.item);
      assert.match(img().getAttribute('src'), /\/pages\/3$/);
      assert.equal(query('[data-page-zoom]', side()).getAttribute('aria-pressed'), 'true');
      renderEvidenceReader(data.run, { ...data.item, requirement_id: 'R-2' });
      assert.match(img().getAttribute('src'), /\/pages\/2$/);
      assert.equal(query('[data-page-zoom]', side()).getAttribute('aria-pressed'), 'false');
    });

    await suite.test('text-only and missing-page references do not invent image locations', () => {
      const data = fixture();
      data.run.source_documents[1].file_type = 'txt';
      data.run.source_documents[1].filename = 'proof.txt';
      data.item.source.page = null; data.item.source.locator = { kind: 'paragraph', label: '段落 7', index: 7 };
      render(data);
      assert.equal(document.querySelectorAll('img[data-source-page]').length, 0);
      assert.equal(document.querySelectorAll('[data-reader-page]').length, 0);
      assert.equal(document.querySelectorAll('.reader-source__download').length, 2);
      assert.match(side().textContent, /段落 7/);
    });

    await suite.test('ambiguous sources keep their quotation without guessing which original to browse', () => {
      const data = fixture(); delete data.item.evidence[0].source_id;
      data.run.source_documents.push({ ...data.run.source_documents[1], source_id: 'EVD-DUPLICATE' });
      render(data);
      assert.equal(side('evidence').querySelector('img'), null);
      assert.equal(side('evidence').querySelector('.reader-source__download'), null);
      assert.match(side('evidence').textContent, /未记录可唯一匹配的原件/);
    });

    await suite.test('filenames, option labels and excerpts stay escaped during navigation and selection', () => {
      const data = fixture(2);
      const malicious = '<img src="https://evil.invalid" onerror="alert(1)">';
      data.item.evidence[1].filename = malicious;
      data.run.source_documents[2].filename = malicious;
      data.item.evidence[1].quote = `必须 ${malicious}`;
      render(data); select(1); action('next', 'evidence').click();
      assert.equal(document.querySelectorAll('img').length, 2);
      assert.equal(document.querySelector('[onerror]'), null);
      assert.equal(document.querySelector('script'), null);
      assert.match(side('evidence').textContent, /<img src=/);
      assert.match(img('evidence').getAttribute('src'), /^\/api\/runs\/reader-test\/files\/EVD-2\/pages\/2$/);
    });
  });
} finally {
  dom.window.close(); globalThis.fetch = originalFetch;
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
}
