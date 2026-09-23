import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { mountDemo } from '../src/demo';
import { confirm, initialState } from '../src/demo-model';
import { mountTracking } from '../src/tracking';

const markup = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
function fixture() {
  const dom = new JSDOM(markup, { url: 'https://example.test/' });
  const document = dom.window.document;
  const cleanup = mountDemo(document);
  function get<T extends HTMLElement>(selector: string): T {
    const element = document.querySelector<T>(selector);
    assert.ok(element, selector);
    return element;
  }
  function click(selector: string): void { get<HTMLButtonElement>(selector).click(); }
  return { dom, document, get, click, close() { cleanup(); dom.window.close(); }, cleanup };
}

test('missing evidence and an expiry conflict cannot be confirmed through direct events', () => {
  const f = fixture();
  try {
    for (const id of ['missing', 'expiry']) {
      f.click(`[data-case="${id}"]`);
      assert.equal(f.get<HTMLButtonElement>('[data-demo-confirm]').disabled, true);
      f.get('[data-demo-confirm]').dispatchEvent(new f.dom.window.MouseEvent('click', { bubbles: true }));
      assert.equal(f.get('[data-demo-count]').textContent, '0 / 3');
      assert.notEqual(f.get('[data-demo-verdict]').textContent, '已核销通过');
    }
  } finally { f.close(); }
});

test('the matched example has both citations and can be confirmed exactly once', () => {
  const f = fixture();
  try {
    f.click('[data-case="matched"]');
    assert.equal(f.get('[data-tender-page]').textContent, 'P.9');
    assert.equal(f.get('[data-evidence-page]').textContent, 'P.3');
    assert.equal(f.get<HTMLButtonElement>('[data-demo-confirm]').disabled, false);
    f.click('[data-demo-confirm]');
    assert.equal(f.get('[data-demo-verdict]').textContent, '已核销通过');
    assert.equal(f.get<HTMLProgressElement>('[data-demo-progress]').value, 1);
    f.get('[data-demo-confirm]').dispatchEvent(new f.dom.window.MouseEvent('click', { bubbles: true }));
    assert.equal(f.get('[data-demo-count]').textContent, '1 / 3');
    f.click('[data-case="missing"]');
    assert.equal(f.get('[data-demo-verdict]').textContent, '废标风险');
    assert.equal(f.get('[data-demo-count]').textContent, '1 / 3');
  } finally { f.close(); }
});

test('a doubtful review reverses the confirmed progress and focuses the note editor', () => {
  const f = fixture();
  try {
    f.click('[data-case="matched"]'); f.click('[data-demo-confirm]'); f.click('[data-demo-reject]');
    assert.equal(f.get('[data-demo-count]').textContent, '0 / 3');
    assert.equal(f.get('[data-demo-verdict]').textContent, '存疑待复核');
    assert.equal(f.get('[data-note-editor]').hidden, false);
    assert.equal(f.document.activeElement, f.get('#demo-note'));
    assert.match(f.get('[data-demo-status]').textContent ?? '', /仍保留在待处理/);
    f.click('[data-case="missing"]'); f.click('[data-case="matched"]');
    assert.equal(f.get('[data-demo-verdict]').textContent, '存疑待复核');
  } finally { f.close(); }
});

test('notes remain scoped to each case and untrusted markup stays plain text', () => {
  const f = fixture();
  try {
    const payload = '<img src=x onerror="window.__xss = true">';
    f.click('[data-demo-note]');
    f.get<HTMLTextAreaElement>('#demo-note').value = payload;
    f.get('#demo-note').dispatchEvent(new f.dom.window.Event('input', { bubbles: true }));
    f.click('[data-case="matched"]'); f.click('[data-demo-note]');
    assert.equal(f.get<HTMLTextAreaElement>('#demo-note').value, '');
    f.get<HTMLTextAreaElement>('#demo-note').value = '待负责人复核';
    f.click('[data-note-save]');
    assert.equal(f.get('[data-demo-count]').textContent, '0 / 3');
    f.click('[data-case="missing"]'); f.click('[data-demo-note]');
    assert.equal(f.get<HTMLTextAreaElement>('#demo-note').value, payload);
    assert.equal(f.document.querySelector('img'), null);
    f.click('[data-note-save]');
    assert.match(f.get('[data-demo-status]').textContent ?? '', /不会发送或保存到服务器/);
    assert.equal(f.document.activeElement, f.get('[data-demo-note]'));
  } finally { f.close(); }
});

test('restoring examples clears notes and confirmation without persistent storage', () => {
  const f = fixture();
  try {
    f.click('[data-case="matched"]'); f.click('[data-demo-confirm]'); f.click('[data-demo-note]');
    f.get<HTMLTextAreaElement>('#demo-note').value = 'temporary';
    f.click('[data-note-save]'); f.click('[data-demo-reset]');
    assert.equal(f.get('[data-demo-count]').textContent, '0 / 3');
    assert.equal(f.get('[data-case="missing"]').getAttribute('aria-selected'), 'true');
    f.click('[data-case="matched"]'); f.click('[data-demo-note]');
    assert.equal(f.get<HTMLTextAreaElement>('#demo-note').value, '');
    assert.equal(f.dom.window.localStorage.length, 0);
    assert.equal(f.dom.window.sessionStorage.length, 0);
  } finally { f.close(); }
});

test('keyboard arrows wrap scenarios with one roving tab stop', () => {
  const f = fixture();
  try {
    const first = f.get<HTMLButtonElement>('[data-case="missing"]'); first.focus();
    first.dispatchEvent(new f.dom.window.KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    assert.equal(f.document.activeElement, f.get('[data-case="matched"]'));
    assert.equal(f.get('#demo-panel').getAttribute('aria-labelledby'), 'demo-tab-matched');
    assert.equal([...f.document.querySelectorAll<HTMLButtonElement>('[data-case]')].filter((button) => button.tabIndex === 0).length, 1);
    f.get('[data-case="matched"]').dispatchEvent(new f.dom.window.KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
    assert.equal(f.document.activeElement, first);
  } finally { f.close(); }
});

test('teardown removes listeners so a fresh mount does not duplicate review actions', () => {
  const f = fixture();
  try {
    f.cleanup(); f.click('[data-case="matched"]');
    assert.equal(f.get('[data-case="missing"]').getAttribute('aria-selected'), 'true');
    const stop = mountDemo(f.document);
    f.click('[data-case="matched"]'); f.click('[data-demo-confirm]');
    assert.equal(f.get('[data-demo-count]').textContent, '1 / 3'); stop();
  } finally { f.close(); }
});

test('marketing events contain only enumerated placement/action without note content', () => {
  const f = fixture(); const events: unknown[] = []; const stop = mountTracking(f.document);
  try {
    f.dom.window.addEventListener('bidproof:marketing', (event) => events.push((event as CustomEvent).detail));
    f.get('[data-track="hero:demo"]').dispatchEvent(new f.dom.window.MouseEvent('click', { bubbles: true, cancelable: true }));
    f.click('[data-case="matched"]'); f.click('[data-demo-note]');
    f.get<HTMLTextAreaElement>('#demo-note').value = 'private company note'; f.click('[data-note-save]');
    assert.deepEqual(events, [{ placement: 'hero', action: 'demo' }, { placement: 'demo', action: 'select' }, { placement: 'demo', action: 'note' }]);
    assert.equal(JSON.stringify(events).includes('private'), false);
    const unsafe = f.document.createElement('button'); unsafe.dataset.track = 'private@example.test:workspace'; f.document.body.append(unsafe); unsafe.click();
    assert.equal(events.length, 3);
  } finally { stop(); f.close(); }
});

test('domain model guards conflicts and duplicate confirmations independently from UI', () => {
  const state = initialState(); assert.equal(confirm(state), false);
  state.selected = 'expiry'; assert.equal(confirm(state), false);
  state.selected = 'matched'; assert.equal(confirm(state), true); assert.equal(confirm(state), false);
});

test('all anchors resolve and FAQ/CTAs work without inline script or an email detour', () => {
  const dom = new JSDOM(markup);
  try {
    const document = dom.window.document;
    for (const anchor of document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]')) assert.ok(document.getElementById(anchor.getAttribute('href')!.slice(1)));
    assert.ok(document.querySelectorAll('a[href="/app"]').length >= 8);
    assert.equal(document.querySelectorAll('#faq details').length, 6);
    assert.ok(document.querySelector('noscript'));
    assert.equal(document.querySelectorAll('script:not([src]),[onclick],[onerror]').length, 0);
    assert.equal(document.querySelectorAll('a[href*="mail.qq.com"]').length, 0);
  } finally { dom.window.close(); }
});
