/* eslint-disable require-await -- Async test doubles intentionally retain the real API Promise contract. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';
import { createCountdown, identifierError, normalizeCode, normalizeIdentifier, remainingSeconds, safeProviders } from '../src/features/auth/passwordless-state.js';

await test('email, international phone and autofill are normalized without weakening code validation', () => {
  assert.equal(normalizeIdentifier('email', ' Test @ Example.com '), 'test@example.com');
  assert.equal(identifierError('email', 'broken@'), '请输入完整邮箱，例如 name@company.com。');
  assert.notEqual(identifierError('email', 'a..b@example.com'), '');
  assert.equal(normalizeIdentifier('sms', '138 0013 8000'), '+8613800138000');
  assert.equal(identifierError('sms', '+1 (415) 555-0123'), '');
  assert.notEqual(identifierError('sms', '123'), '');
  assert.equal(normalizeCode('１２３ ４５６'), '123456');
  assert.equal(normalizeCode('123456abc'), '123456abc', 'Pasted garbage must be rejected, not silently converted into a valid code.');
});

await test('countdown uses a deadline after tab suspension and releases every scheduled timer', () => {
  let now = 1000; let next = 0;
  const scheduled = new Map(); const ticks = [];
  const timer = createCountdown((value) => ticks.push(value), {
    now: () => now,
    schedule: (fn) => { scheduled.set(++next, fn); return next; },
    cancel: (id) => scheduled.delete(id),
  });
  const fire = () => { const [id, fn] = scheduled.entries().next().value; scheduled.delete(id); fn(); };
  timer.start(60); assert.deepEqual(ticks, [60]); assert.equal(scheduled.size, 1);
  now += 100; fire(); assert.deepEqual(ticks, [60], 'No repeated screen-reader updates in the same second.');
  now += 49000; fire(); assert.equal(ticks.at(-1), 11);
  timer.start(20); assert.equal(scheduled.size, 1, 'Resend owns only one timer.');
  timer.stop(); assert.equal(scheduled.size, 0);
  timer.start(1); now += 1200; fire(); assert.equal(ticks.at(-1), 0); assert.equal(scheduled.size, 0);
  assert.equal(remainingSeconds(1000, 2000), 0);
});

await test('OAuth links only accept supported same-origin provider endpoints', () => {
  assert.deepEqual(safeProviders([
    { id: 'google', label: '<script>x</script>', url: '/api/auth/oauth/google/start' },
    { id: 'github', url: 'javascript:alert(1)' }, { id: 'google', url: 'https://evil.invalid' },
  ]), [{ id: 'google', label: 'Google', url: '/api/auth/oauth/google/start' }]);
});

const dom = new JSDOM(await readFile(new URL('../../static/index.html', import.meta.url), 'utf8'), { url: 'https://bidproof.invalid/app', pretendToBeVisual: true });
const w = dom.window;
const originals = new Map();
for (const key of ['window', 'document', 'location', 'history', 'navigator', 'localStorage', 'Element', 'HTMLElement', 'HTMLInputElement', 'HTMLButtonElement', 'HTMLFormElement', 'HTMLDialogElement', 'Event', 'CustomEvent', 'MouseEvent', 'FormData']) {
  originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key));
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === 'window' ? w : w[key] });
}
const previousRaf = globalThis.requestAnimationFrame;
globalThis.requestAnimationFrame = (fn) => { fn(); return 0; };
w.HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
w.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); this.dispatchEvent(new w.Event('close')); };
w.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
const oldFetch = globalThis.fetch;
const { createAuthModal } = await import('../src/features/auth/unified.js');
const { request, resetSessionTransport } = await import('../src/core/http.js');
const query = (selector) => document.querySelector(selector);
const input = (selector, value) => { query(selector).value = value; query(selector).dispatchEvent(new w.Event('input', { bubbles: true })); };
const submit = (selector = '#auth-unified-form') => query(selector).dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
const pause = () => new Promise((resolve) => { setImmediate(resolve); });
const both = { authenticated: false, setup_required: false, personal_signup_enabled: true, passwordless: { email: true, phone: true, oauth: [] } };
const sent = { challenge_id: 'challenge-1', masked_identifier: 't***@example.com', channel: 'email', expires_in: 300, resend_after: 60 };
const user = { user_id: 'user', username: 'verified', role: 'OWNER', workspace_id: 'one' };
let modal;
const open = (api, status = both, extra = {}) => {
  modal?.destroy();
  modal = createAuthModal({ dialog: query('#auth-panel'), root: query('#auth-unified-root'), legacyForm: query('#auth-form'), api, onOutcome: () => {}, onLegacy: () => {}, ...extra });
  modal.open(status); return modal;
};

try {
  await test('first view is one identifier, no profile fields, and invalid input never contacts delivery', async () => {
    let calls = 0;
    open({ requestChallenge: async () => { calls++; return sent; } });
    assert.equal(document.activeElement.id, 'auth-identifier');
    assert.equal(query('#auth-form').hidden, true);
    assert.equal(query('#auth-unified-root').querySelectorAll('input').length, 1);
    input('#auth-identifier', 'not an email'); submit(); await pause();
    assert.equal(calls, 0); assert.equal(query('#auth-identifier').getAttribute('aria-invalid'), 'true');
    assert.match(query('#auth-inline-error').textContent, /完整邮箱/);
    query('[data-auth-channel="sms"]').click();
    input('#auth-identifier', '138 0013 8000'); submit(); await pause();
    assert.equal(calls, 1); assert.ok(query('#auth-one-time-code'));
    assert.equal(query('[data-auth-action="resend"]').disabled, true);
    assert.equal(document.activeElement.id, 'auth-one-time-code');
  });
  await test('pasted 6-digit code reaches verification and MFA outcome is preserved', async () => {
    let requestBody; let verifyBody; let outcome;
    open({
      requestChallenge: async (body) => { requestBody = body; return sent; },
      verifyChallenge: async (body) => { verifyBody = body; return { kind: 'mfa_required', mfaToken: 'mfa-once' }; },
    }, both, { onOutcome: (value) => { outcome = value; } });
    input('#auth-identifier', ' Person @ Example.com '); submit(); await pause();
    assert.deepEqual(requestBody, { channel: 'email', identifier: 'person@example.com' });
    assert.equal(outcome, undefined, 'Delivery is not authentication.');
    input('#auth-one-time-code', '１２３ ４５６'); submit(); await pause();
    assert.deepEqual(verifyBody, { challenge_id: 'challenge-1', code: '123456' });
    assert.deepEqual(outcome, { kind: 'mfa_required', mfaToken: 'mfa-once' });
    assert.equal(query('#auth-unified-root').textContent, '', 'One-time code is erased at handoff.');
  });
  await test('wrong code remains recoverable without resending or losing the recipient', async () => {
    let calls = 0; let outcome;
    open({ requestChallenge: async () => sent, verifyChallenge: async () => {
      calls++; if (calls === 1) throw Object.assign(new Error('验证码不正确，请重试。'), { status: 401 });
      return { kind: 'authenticated', user };
    } }, both, { onOutcome: (value) => { outcome = value; } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    input('#auth-one-time-code', '123'); submit(); await pause(); assert.equal(calls, 0);
    input('#auth-one-time-code', '000000'); submit(); await pause();
    assert.match(query('#auth-inline-error').textContent, /不正确/);
    assert.match(query('#auth-unified-description').textContent, /t\*\*\*@example.com/);
    input('#auth-one-time-code', '123456'); submit(); await pause();
    assert.equal(calls, 2); assert.equal(outcome.user.user_id, 'user');
  });
  await test('server cooldown blocks rapid resend, expiration asks for a new code', async () => {
    let deliveries = 0;
    open({ requestChallenge: async () => {
      deliveries++; if (deliveries === 1) throw Object.assign(new Error('请稍后重试。'), { status: 429, retryAfter: 45 });
      return { ...sent, resend_after: 0 };
    } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    assert.match(query('#auth-unified-form [type="submit"]').textContent, /45 秒/);
    submit(); await pause(); assert.equal(deliveries, 1);
    open({ requestChallenge: async () => ({ ...sent, resend_after: 0 }), verifyChallenge: async () => { throw Object.assign(new Error('验证码已过期。'), { status: 410 }); } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    input('#auth-one-time-code', '123456'); submit(); await pause();
    assert.equal(query('#auth-unified-form [type="submit"]').disabled, true);
    assert.match(query('#auth-code-expiry').textContent, /已过期/);
    assert.equal(query('[data-auth-action="resend"]').disabled, false);
  });
  await test('delivery outage stays on identifier screen and supports an explicit retry', async () => {
    let calls = 0;
    open({ requestChallenge: async () => { calls++; if (calls === 1) throw Object.assign(new Error('邮件暂时发送失败，请重试。'), { status: 503 }); return sent; } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    assert.ok(query('#auth-identifier')); assert.equal(query('#auth-one-time-code'), null);
    assert.match(query('#auth-inline-error').textContent, /发送失败/);
    submit(); await pause(); assert.equal(calls, 2); assert.ok(query('#auth-one-time-code'));
  });
  await test('closing the modal aborts requests and discards a late successful response', async () => {
    let resolve; let signal; let outcomes = 0;
    open({ requestChallenge: (_body, options) => { signal = options.signal; return new Promise((done) => { resolve = done; }); } }, both, { onOutcome: () => { outcomes++; } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    query('#auth-panel').close(); assert.equal(signal.aborted, true);
    resolve(sent); await pause(); assert.equal(query('#auth-unified-root').textContent, ''); assert.equal(outcomes, 0);
  });
  await test('unconfigured delivery preserves a usable legacy password entry and omits unavailable providers', async () => {
    let sentBody;
    open({ login: async (body) => { sentBody = body; return { kind: 'authenticated', user }; } }, { ...both, passwordless: { email: false, phone: false, oauth: [] } });
    assert.ok(query('#auth-unified-password')); assert.equal(query('[data-auth-channel]'), null);
    assert.equal(query('.auth-simple__providers'), null);
    input('#auth-identifier', ' legacy-owner '); input('#auth-unified-password', ' spaces retained ');
    submit(); await pause(); assert.deepEqual(sentBody, { username: 'legacy-owner', password: ' spaces retained ' });
  });
  await test('server recipient/error strings cannot create elements, and accessible status remains inline', async () => {
    open({ requestChallenge: async () => ({ ...sent, masked_identifier: '<img src=x onerror=alert(1)>' }) });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    assert.equal(query('#auth-unified-root img'), null);
    assert.match(query('#auth-unified-description').textContent, /<img/);
    assert.equal(query('#auth-one-time-code').getAttribute('autocomplete'), 'one-time-code');
    assert.equal(query('#auth-inline-error').getAttribute('role'), 'alert');
    assert.equal(query('#auth-panel').getAttribute('aria-describedby'), 'auth-unified-description');
  });
  await test('auth HTTP errors retain nested messages and Retry-After without replaying delivery', async () => {
    let calls = 0;
    globalThis.fetch = () => { calls++; return Promise.resolve(new Response(JSON.stringify({ detail: { code: 'OTP_COOLDOWN', message: '请等待后重新发送。' } }), { status: 429, headers: { 'content-type': 'application/json', 'retry-after': '37' } })); };
    await assert.rejects(request('/api/auth/challenges', { method: 'POST', body: '{}' }), (error) => error.retryAfter === 37 && error.code === 'OTP_COOLDOWN' && error.message === '请等待后重新发送。');
    assert.equal(calls, 1);
  });
  await test('persisted page restoration rechecks auth and never resurrects the previous OTP challenge', async () => {
    let statusReads = 0;
    open({ requestChallenge: async () => sent, getStatus: async () => { statusReads++; return both; } });
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    input('#auth-one-time-code', '123456');
    window.dispatchEvent(new w.PageTransitionEvent('pagehide', { persisted: true }));
    assert.equal(query('#auth-unified-root').textContent, '');
    window.dispatchEvent(new w.PageTransitionEvent('pageshow', { persisted: true }));
    await pause();
    assert.equal(statusReads, 1);
    assert.equal(query('#auth-unified-root').hidden, false);
    assert.equal(query('#auth-one-time-code'), null);
    assert.equal(query('#auth-identifier').value, '');
    assert.equal(document.activeElement.id, 'auth-identifier');
  });
  await test('configured first-run OTP bypasses admin bootstrap and authenticates only after retained MFA', async () => {
    modal.destroy(); modal = null;
    let authenticated = 0;
    const requests = [];
    globalThis.fetch = (url, options = {}) => {
      requests.push(url);
      let response;
      if (url === '/api/auth/status') response = { ...both, setup_required: true };
      else if (url === '/api/auth/challenges') response = sent;
      else if (url === '/api/auth/challenges/verify') response = { mfa_required: true, mfa_token: 'mfa-token' };
      else if (url === '/api/auth/mfa/verify') { assert.deepEqual(JSON.parse(options.body), { mfa_token: 'mfa-token', code: '654321' }); response = user; }
      else throw new Error(`Unstubbed: ${url}`);
      return Promise.resolve(new Response(JSON.stringify(response), { headers: { 'content-type': 'application/json' } }));
    };
    resetSessionTransport();
    const { configureAuth, startAuth } = await import('../src/features/auth/index.js');
    configureAuth({ onAuthenticated: () => { authenticated++; } });
    assert.equal(await startAuth(), false); assert.ok(query('#auth-identifier'));
    const beforeRestore = requests.filter((url) => url === '/api/auth/status').length;
    window.dispatchEvent(new w.PageTransitionEvent('pagehide', { persisted: true }));
    window.dispatchEvent(new w.PageTransitionEvent('pageshow', { persisted: true }));
    await pause();
    assert.equal(requests.filter((url) => url === '/api/auth/status').length, beforeRestore + 1,
      'Modal and session-channel restoration must share a single status refresh.');
    assert.ok(query('#auth-identifier'), 'The restored auth dialog must not be blank.');
    input('#auth-identifier', 'p@example.com'); submit(); await pause();
    input('#auth-one-time-code', '123456'); submit(); await pause();
    assert.equal(authenticated, 0); assert.equal(query('#mfa-fields').hidden, false);
    assert.equal(query('#auth-username-field').hidden, true);
    input('#auth-mfa-code', '654321');
    assert.equal(query('#auth-form').checkValidity(), true, 'Hidden setup fields must not block native MFA submission.');
    submit('#auth-form'); await pause();
    assert.equal(authenticated, 1); assert.equal(query('#auth-panel').open, false);
    assert.equal(requests.includes('/api/auth/bootstrap'), false);
  });
} finally {
  modal?.destroy(); query('#auth-panel')?.close();
  globalThis.fetch = oldFetch;
  if (previousRaf) globalThis.requestAnimationFrame = previousRaf; else delete globalThis.requestAnimationFrame;
  for (const [key, original] of originals) {
    if (original) Object.defineProperty(globalThis, key, original); else delete globalThis[key];
  }
  dom.window.close();
}
