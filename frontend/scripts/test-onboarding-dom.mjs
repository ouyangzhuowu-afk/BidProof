import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<div id="first-run-guide"></div>', { url: 'https://bidproof.invalid/app' });
for (const key of ['document', 'window', 'localStorage', 'Element', 'HTMLElement']) globalThis[key] = dom.window[key];
const { startOnboarding, advanceOnboarding, stopOnboarding } = await import('../src/features/runs/onboarding.js');
const count = () => document.querySelector('.first-run__count')?.textContent.trim();
const user = (id) => ({ user_id: id, workspace_id: 'test', role: 'OWNER' });

test('first-run steps survive reload without crossing account boundaries', () => {
  startOnboarding(user('a'));
  assert.match(count(), /^0 \/ 3/);
  assert.equal(document.querySelector('[aria-current="step"]').textContent.includes('选择场景'), true);
  advanceOnboarding(1); advanceOnboarding(2);
  assert.match(count(), /^2 \/ 3/);
  advanceOnboarding(1); advanceOnboarding(99);
  assert.match(count(), /^2 \/ 3/);
  stopOnboarding();
  assert.equal(document.querySelector('#first-run-guide').textContent, '');
  startOnboarding(user('b')); assert.match(count(), /^0 \/ 3/);
  startOnboarding(user('a')); assert.match(count(), /^2 \/ 3/);
  advanceOnboarding(3);
  assert.equal(document.querySelector('details').open, false);
  assert.match(document.body.textContent, /已完成首次体验/);
  assert.equal(document.querySelectorAll('[aria-current="step"]').length, 0);
});

test('guide can collapse and restore while storage failure remains nonblocking', () => {
  startOnboarding(user('c'));
  const details = document.querySelector('details');
  details.open = false;
  details.dispatchEvent(new window.Event('toggle'));
  startOnboarding(user('c'));
  assert.equal(document.querySelector('details').open, false);
  const storage = globalThis.localStorage;
  globalThis.localStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  startOnboarding(user('d')); advanceOnboarding(1);
  assert.match(count(), /^1 \/ 3/);
  globalThis.localStorage = storage;
  startOnboarding({ ...user('viewer'), role: 'VIEWER' });
  assert.equal(document.querySelector('#first-run-guide').textContent, '');
});

test.after(() => { stopOnboarding(); dom.window.close(); });
