import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';
import { mountDemo } from '../src/demo';
import { COMPLETE_MESSAGE, DEMO_DURATION_MS } from '../src/demo-model';
import { mountTracking } from '../src/tracking';

const markup = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
function fixture(reducedMotion = false) {
  const dom = new JSDOM(markup, { url: 'https://example.test/', pretendToBeVisual: true });
  const document = dom.window.document;
  let now = 0;
  let nextId = 0;
  const timers = new Map<number, { callback: () => void; at: number }>();
  const motionListeners = new Set<() => void>();
  const motion = {
    matches: reducedMotion,
    addEventListener(_type: string, listener: EventListenerOrEventListenerObject | null) { if (typeof listener === 'function') motionListeners.add(listener as () => void); },
    removeEventListener(_type: string, listener: EventListenerOrEventListenerObject | null) { if (typeof listener === 'function') motionListeners.delete(listener as () => void); },
  };
  const options = {
    motion,
    schedule(callback: () => void, delay: number) { const id = ++nextId; timers.set(id, { callback, at: now + delay }); return id; },
    cancel(id: number) { timers.delete(id); },
  };
  const cleanup = mountDemo(document, options);
  function get<T extends HTMLElement>(selector: string): T {
    const element = document.querySelector<T>(selector);
    assert.ok(element, selector);
    return element;
  }
  function advance(ms: number): void {
    const end = now + ms;
    for (;;) {
      const [next] = [...timers.entries()].filter(([, task]) => task.at <= end).sort((a, b) => a[1].at - b[1].at);
      if (!next) break;
      timers.delete(next[0]); now = next[1].at; next[1].callback();
    }
    now = end;
  }
  return { dom, document, get, advance, timers, motion, motionListeners, options, cleanup,
    play() { get<HTMLButtonElement>('[data-demo-play]').click(); },
    close() { cleanup(); dom.window.close(); },
  };
}

test('the no-script page explains input and output and offers a real app destination', () => {
  const dom = new JSDOM(markup);
  const document = dom.window.document;
  try {
    assert.equal(document.querySelectorAll('h1').length, 1);
    assert.equal(document.querySelectorAll('.primary-cta').length, 1);
    assert.equal(document.querySelector('.primary-cta')?.getAttribute('href'), '/app');
    assert.equal(document.querySelectorAll('.feature-card').length, 3);
    assert.ok((document.querySelector('.hero-description')?.textContent?.length ?? 100) <= 30);
    assert.equal(document.querySelectorAll('.result-row').length, 3);
    assert.equal(document.querySelector<HTMLElement>('[data-demo-results]')?.hidden, false);
    assert.equal(document.querySelectorAll('#pricing, #faq, [role="tablist"]').length, 0);
    assert.match(document.querySelector('[data-demo]')?.textContent ?? '', /示例/);
    assert.ok(document.querySelector('noscript'));
  } finally { dom.window.close(); }
});

test('one click produces a result and returns the control within three seconds', () => {
  const f = fixture();
  try {
    f.play();
    assert.equal(f.get('[data-demo-play]').getAttribute('aria-disabled'), 'true');
    assert.equal(f.get<HTMLButtonElement>('[data-demo-play]').disabled, false);
    assert.equal(f.get('#demo-results').getAttribute('aria-busy'), 'true');
    assert.equal(f.get('[data-demo-skeleton]').hidden, false);
    assert.equal(f.get('[data-demo-results]').hidden, true);
    f.advance(DEMO_DURATION_MS);
    assert.ok(DEMO_DURATION_MS <= 3000);
    assert.equal(f.get('#demo-results').getAttribute('aria-busy'), 'false');
    assert.equal(f.get('[data-demo-results]').hidden, false);
    assert.equal(f.get('[data-demo-skeleton]').hidden, true);
    assert.equal(f.get('[data-demo-status]').textContent, COMPLETE_MESSAGE);
    assert.equal(f.get<HTMLButtonElement>('[data-demo-play]').disabled, false);
    assert.equal(f.timers.size, 0);
    assert.equal(f.document.querySelectorAll('.result-state.review').length, 2);
    assert.doesNotMatch(f.get('[data-demo-results]').textContent ?? '', /已通过|核销通过/);
  } finally { f.close(); }
});

test('rapid synthetic clicks cannot start overlapping demo timelines', () => {
  const f = fixture();
  try {
    f.play();
    const pending = f.timers.size;
    for (let i = 0; i < 10; i++) f.get('[data-demo-play]').dispatchEvent(new f.dom.window.MouseEvent('click', { bubbles: true }));
    assert.equal(f.timers.size, pending);
    f.advance(DEMO_DURATION_MS);
    f.play();
    assert.equal(f.get('[data-demo]').dataset.phase, 'running');
    f.advance(DEMO_DURATION_MS);
    assert.equal(f.get('[data-demo]').dataset.phase, 'complete');
    assert.equal(f.timers.size, 0);
  } finally { f.close(); }
});

test('reduced motion returns the result immediately without starting a timer', () => {
  const f = fixture(true);
  try {
    f.play();
    assert.equal(f.timers.size, 0);
    assert.equal(f.get('[data-demo-status]').textContent, COMPLETE_MESSAGE);
    assert.equal(f.get<HTMLButtonElement>('[data-demo-play]').disabled, false);
  } finally { f.close(); }
});

test('changing reduced motion during a playback reveals results and cancels timers', () => {
  const f = fixture();
  try {
    f.play(); f.advance(500);
    f.motion.matches = true;
    f.motionListeners.forEach((listener) => listener());
    assert.equal(f.timers.size, 0);
    assert.equal(f.get('[data-demo]').dataset.phase, 'complete');
  } finally { f.close(); }
});

test('a hidden page finishes once and does not leave a running timer behind', () => {
  const f = fixture();
  try {
    f.play();
    Object.defineProperty(f.document, 'hidden', { configurable: true, value: true });
    f.document.dispatchEvent(new f.dom.window.Event('visibilitychange'));
    assert.equal(f.timers.size, 0);
    assert.equal(f.get('[data-demo]').dataset.phase, 'complete');
    const message = f.get('[data-demo-status]').textContent;
    f.advance(5000);
    assert.equal(f.get('[data-demo-status]').textContent, message);
  } finally { f.close(); }
});

test('pagehide clears active timing while allowing a back-cache visit to play again', () => {
  const f = fixture();
  try {
    f.play(); f.dom.window.dispatchEvent(new f.dom.window.PageTransitionEvent('pagehide', { persisted: true }));
    assert.equal(f.timers.size, 0);
    assert.equal(f.get('[data-demo]').dataset.phase, 'complete');
    f.play();
    assert.equal(f.get('[data-demo]').dataset.phase, 'running');
  } finally { f.close(); }
});

test('unmount removes listeners and restores the static result', () => {
  const f = fixture();
  try {
    f.play(); f.cleanup();
    assert.equal(f.timers.size, 0);
    assert.equal(f.motionListeners.size, 0);
    assert.equal(f.get('[data-demo-results]').hidden, false);
    assert.equal(f.get('#demo-results').getAttribute('aria-busy'), 'false');
    f.get('[data-demo-play]').dispatchEvent(new f.dom.window.MouseEvent('click', { bubbles: true }));
    f.advance(5000);
    assert.equal(f.timers.size, 0);
    assert.equal(f.get('[data-demo]').dataset.phase, 'ready');
  } finally { f.close(); }
});

test('mounting again disposes the prior controller rather than doubling actions', () => {
  const f = fixture();
  const events: unknown[] = [];
  f.dom.window.addEventListener('bidproof:marketing', (event) => events.push((event as CustomEvent).detail));
  const secondCleanup = mountDemo(f.document, f.options);
  try {
    f.play(); f.advance(DEMO_DURATION_MS);
    assert.deepEqual(events, [{ placement: 'demo', action: 'play' }, { placement: 'demo', action: 'complete' }]);
    assert.equal(f.motionListeners.size, 1);
  } finally { secondCleanup(); f.close(); }
});

test('controls use native keyboard semantics and polite result announcements', () => {
  const f = fixture();
  try {
    const button = f.get<HTMLButtonElement>('[data-demo-play]');
    assert.equal(button.tagName, 'BUTTON');
    assert.equal(button.type, 'button');
    assert.equal(button.getAttribute('aria-controls'), 'demo-results');
    button.focus();
    assert.equal(f.document.activeElement, button);
    f.play(); f.advance(DEMO_DURATION_MS);
    assert.equal(f.document.activeElement, button);
    assert.equal(f.get('[data-demo-status]').getAttribute('role'), 'status');
    assert.equal(f.get('[data-demo-status]').getAttribute('aria-live'), 'polite');
  } finally { f.close(); }
});

test('marketing tracking discards arbitrary actions and sends only fixed fields', () => {
  const f = fixture();
  const events: unknown[] = [];
  f.dom.window.addEventListener('bidproof:marketing', (event) => events.push((event as CustomEvent).detail));
  const cleanupTracking = mountTracking(f.document);
  try {
    const control = f.document.createElement('button');
    control.textContent = 'person@example.com';
    control.dataset.track = 'hero:workspace';
    control.dataset.email = 'person@example.com';
    f.document.body.append(control);
    control.click();
    control.dataset.track = 'hero:workspace:person@example.com'; control.click();
    control.dataset.track = 'hero:<img src=x onerror=alert(1)>'; control.click();
    assert.deepEqual(events, [{ placement: 'hero', action: 'workspace' }]);
    assert.equal(f.document.querySelector('img'), null);
    cleanupTracking();
    control.dataset.track = 'hero:workspace'; control.click();
    assert.equal(events.length, 1);
    assert.equal(f.dom.window.localStorage.length, 0);
  } finally { cleanupTracking(); f.close(); }
});
