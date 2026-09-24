import { html, mount } from '../../ui/render.js';
import { openDialog } from '../../core/dom.js';
import { createCountdown, identifierError, normalizeCode, normalizeIdentifier, remainingSeconds, safeProviders } from './passwordless-state.js';

/**
 * Unified entry. Account creation happens only after server-side verification.
 * The native modal owns focus containment/restoration; this controller owns every
 * listener, pending request and timer so switching flows cannot leak a session.
 */
export function createAuthModal({ dialog, root, legacyForm, api, onOutcome, onLegacy, onResume }) {
  let status = null;
  let channel = 'email';
  let step = 'identify';
  let identifier = '';
  let password = '';
  let code = '';
  let challenge = null;
  let expiresAt = 0;
  let resendAt = 0;
  let busy = false;
  let active = false;
  let message = '';
  let invalid = '';
  let generation = 0;
  let requestController = null;
  let needsResume = false;
  let destroyed = false;
  const listeners = [];
  const select = (selector) => root.querySelector(selector);
  const focus = () => select(step === 'code' ? '#auth-one-time-code' : '#auth-identifier')?.focus();
  const cooldown = createCountdown(() => updateTiming());

  function listen(target, event, handler) {
    target.addEventListener(event, handler);
    listeners.push(() => target.removeEventListener(event, handler));
  }

  function tick() {
    cooldown.start(Math.max(remainingSeconds(resendAt), remainingSeconds(expiresAt)));
  }

  function updateTiming() {
    if (!active) return;
    const resend = select('[data-auth-action="resend"]');
    const remaining = remainingSeconds(resendAt);
    if (resend) {
      resend.disabled = busy || remaining > 0;
      resend.textContent = remaining > 0 ? `${remaining} 秒后重新发送` : '重新发送验证码';
    }
    const expired = step === 'code' && remainingSeconds(expiresAt) === 0;
    const expiry = select('#auth-code-expiry');
    if (expiry) expiry.textContent = expired ? '验证码已过期，请重新发送。' : '验证码仅用于本次进入，请勿转发。';
    const submit = select('[type="submit"]');
    if (submit) {
      submit.disabled = busy || expired || (step === 'identify' && channel !== 'password' && remaining > 0);
      submit.textContent = busy ? (step === 'code' || channel === 'password' ? '正在验证…' : '正在发送…')
        : step === 'code' ? '验证并进入' : channel === 'password' ? '进入工作台'
          : remaining > 0 ? `${remaining} 秒后重试` : '获取验证码';
    }
  }

  function render(shouldFocus = true) {
    const hasEmail = Boolean(status?.passwordless?.email);
    const hasPhone = Boolean(status?.passwordless?.phone);
    const providers = safeProviders(status?.passwordless?.oauth);
    const otpAvailable = hasEmail || hasPhone;
    mount(root, html`
      <div class="auth-simple__top"><a href="/" class="auth-simple__brand" aria-label="BidProof 首页">BidProof<span>投标材料检查</span></a><a class="auth-simple__home" href="/" aria-label="返回首页">返回首页</a></div>
      <header class="auth-simple__heading"><h2 id="auth-unified-title">${step === 'code' ? '查看你的验证码' : '开始检查投标材料'}</h2>
        <p id="auth-unified-description">${step === 'code'
          ? `验证码已发送至 ${challenge?.masked_identifier || ''}`
          : channel === 'password' ? '使用邮箱或已有账号进入。' : '验证后直接进入，首次使用自动创建账号。'}</p></header>
      ${step === 'identify' && providers.length ? html`<div class="auth-simple__providers">${providers.map((provider) => html`
        <a class="btn btn--secondary" href="${provider.url}"><span class="auth-simple__provider-mark" aria-hidden="true">${provider.id === 'google' ? 'G' : 'GH'}</span>使用 ${provider.label} 继续</a>`)}</div><div class="auth-simple__divider"><span>或</span></div>` : ''}
      <form id="auth-unified-form" class="auth-simple__form" novalidate aria-busy="${busy}">
        ${step === 'identify' && channel !== 'password' && hasEmail && hasPhone ? html`
          <div class="auth-simple__switch" role="group" aria-label="验证码接收方式">
            <button type="button" data-auth-channel="email" aria-pressed="${channel === 'email'}">邮箱</button>
            <button type="button" data-auth-channel="sms" aria-pressed="${channel === 'sms'}">手机号</button>
          </div>` : ''}
        ${step === 'identify' ? html`<div class="field">
          <label for="auth-identifier">${channel === 'email' ? '邮箱' : channel === 'sms' ? '手机号' : '邮箱或现有账号'}</label>
          <input class="input" id="auth-identifier" name="username" type="${channel === 'email' ? 'email' : channel === 'sms' ? 'tel' : 'text'}"
            inputmode="${channel === 'email' ? 'email' : channel === 'sms' ? 'tel' : 'text'}" autocomplete="${channel === 'sms' ? 'tel' : channel === 'email' ? 'email' : 'username'}"
            autocapitalize="none" spellcheck="false" maxlength="254" placeholder="${channel === 'email' ? 'name@company.com' : channel === 'sms' ? '手机号，境外号码请加区号' : '你的邮箱或账号'}"
            value="${identifier}" required aria-invalid="${invalid === 'identifier'}" aria-describedby="auth-inline-error">
        </div>${channel === 'password' ? html`<div class="field"><label for="auth-unified-password">密码</label>
          <span class="password-field"><input class="input" id="auth-unified-password" name="password" type="password" autocomplete="current-password" required
            value="${password}" aria-invalid="${invalid === 'password'}" aria-describedby="auth-inline-error">
            <button class="icon-btn password-toggle" type="button" data-auth-action="password-visibility" aria-label="显示密码" aria-pressed="false"><i data-lucide="eye" aria-hidden="true"></i></button></span></div>` : ''}`
          : html`<div class="field"><label for="auth-one-time-code">6 位验证码</label>
            <input class="input auth-simple__code" id="auth-one-time-code" name="code" type="text" inputmode="numeric" autocomplete="one-time-code"
              pattern="[0-9]{6}" maxlength="12" value="${code}" required aria-invalid="${invalid === 'code'}" aria-describedby="auth-inline-error auth-code-expiry">
            <p class="hint" id="auth-code-expiry" role="status" aria-live="polite"></p></div>`}
        <p id="auth-inline-error" class="auth-simple__error" role="alert" aria-live="assertive">${message}</p>
        <p id="auth-offline" class="auth-simple__error" role="status" ${navigator.onLine === false ? '' : html`hidden`}>当前网络已断开，连接恢复后可重试。</p>
        <button type="submit" class="btn btn--primary"></button>
      </form>
      <div class="auth-simple__alternatives">
        ${step === 'code' ? html`<button type="button" class="auth-simple__link" data-auth-action="resend"></button><button type="button" class="auth-simple__link" data-auth-action="back">修改${channel === 'email' ? '邮箱' : '手机号'}</button>`
          : html`${channel === 'password' && otpAvailable ? html`<button type="button" class="auth-simple__link" data-auth-action="otp">使用验证码进入</button>` : channel !== 'password' ? html`<button type="button" class="auth-simple__link" data-auth-action="password">使用密码进入</button>` : ''}
            ${status?.oidc_enabled ? html`<a class="auth-simple__link" href="/api/auth/oidc/start">企业统一登录</a>` : ''}
            ${!otpAvailable && status?.personal_signup_enabled ? html`<button type="button" class="auth-simple__link" data-auth-action="register">首次使用，创建账号</button>` : ''}
            ${!otpAvailable && status?.trial_join_enabled ? html`<button type="button" class="auth-simple__link" data-auth-action="trial">使用企业邀请信息</button>` : ''}`}
      </div>
      <p class="auth-simple__privacy">${channel === 'password' && !otpAvailable ? '忘记密码可联系管理员获取重置链接。' : '不需要填写公司或职位。'} <a href="/privacy" target="_blank" rel="noopener">隐私说明</a></p>`);
    for (const control of root.querySelectorAll('input, button')) control.disabled = busy;
    updateTiming();
    if (shouldFocus) focus();
  }

  function displayError(text, field = '') {
    message = text;
    invalid = field;
    select('#auth-inline-error').textContent = text;
    for (const [key, selector] of [['identifier', '#auth-identifier'], ['password', '#auth-unified-password'], ['code', '#auth-one-time-code']]) {
      const input = select(selector);
      input?.setAttribute('aria-invalid', String(key === field));
      if (key === field) input?.focus();
    }
  }

  async function run(action) {
    if (busy || !active) return;
    busy = true;
    message = ''; invalid = '';
    const owner = ++generation;
    requestController = new AbortController();
    render(false);
    try {
      await action(requestController.signal, owner);
    } catch (error) {
      if (owner !== generation || !active) return;
      if (error?.status === 429 || (error?.status === 503 && error.retryAfter > 0)) {
        resendAt = Date.now() + Math.max(1, error.retryAfter || 60) * 1000;
        tick();
      }
      if (error?.status === 410 || (error?.status === 429 && step === 'code')) expiresAt = Date.now();
      message = error instanceof Error ? error.message : '暂时无法完成，请重试。';
      invalid = step === 'code' ? 'code' : channel === 'password' ? 'password' : 'identifier';
    } finally {
      if (owner === generation && active) {
        busy = false;
        requestController = null;
        render();
      }
    }
  }

  async function send(signal, owner) {
    const next = await api.requestChallenge({ channel, identifier }, { signal });
    if (owner !== generation || !active) return;
    challenge = next;
    code = '';
    expiresAt = Date.now() + next.expires_in * 1000;
    resendAt = Date.now() + next.resend_after * 1000;
    step = 'code';
    tick();
  }

  listen(root, 'submit', (event) => {
    if (event.target.id !== 'auth-unified-form') return;
    event.preventDefault();
    if (busy) return;
    if (step === 'identify') {
      identifier = normalizeIdentifier(channel, select('#auth-identifier').value);
      select('#auth-identifier').value = identifier;
      const error = identifierError(channel, identifier);
      if (error) { displayError(error, 'identifier'); return; }
      if (channel === 'password') {
        password = select('#auth-unified-password').value;
        if (!password) { displayError('请输入密码。', 'password'); return; }
        void run(async (signal, owner) => {
          const outcome = await api.login({ username: identifier, password }, { signal });
          if (owner !== generation || !active) return;
          deactivate();
          await onOutcome(outcome);
        });
      } else if (!remainingSeconds(resendAt)) void run(send);
      return;
    }
    code = normalizeCode(select('#auth-one-time-code').value);
    select('#auth-one-time-code').value = code;
    if (!/^\d{6}$/.test(code)) { displayError('请输入收到的 6 位数字验证码。', 'code'); return; }
    if (!remainingSeconds(expiresAt)) { displayError('验证码已过期，请重新发送。', 'code'); return; }
    void run(async (signal, owner) => {
      const outcome = await api.verifyChallenge({ challenge_id: challenge.challenge_id, code }, { signal });
      if (owner !== generation || !active) return;
      deactivate();
      await onOutcome(outcome);
    });
  });

  listen(root, 'input', (event) => {
    if (event.target.id === 'auth-identifier') identifier = event.target.value;
    if (event.target.id === 'auth-unified-password') password = event.target.value;
    if (event.target.id === 'auth-one-time-code') {
      code = normalizeCode(event.target.value);
      event.target.value = code;
    }
    if (message) displayError('');
  });
  listen(root, 'focusout', (event) => {
    if (event.target.id !== 'auth-identifier' || busy) return;
    identifier = normalizeIdentifier(channel, event.target.value);
    event.target.value = identifier;
    // Blur validation must not pull focus away from a channel-switch button.
    const error = identifier ? identifierError(channel, identifier) : '';
    select('#auth-inline-error').textContent = error;
    event.target.setAttribute('aria-invalid', String(Boolean(error)));
  });
  listen(root, 'click', (event) => {
    const button = event.target.closest('button');
    if (!button || busy) return;
    const nextChannel = button.dataset.authChannel;
    const action = button.dataset.authAction;
    if (action === 'resend') {
      if (!remainingSeconds(resendAt)) void run(send);
      return;
    }
    if (action === 'password-visibility') {
      const input = select('#auth-unified-password');
      const revealing = input.type === 'password';
      input.type = revealing ? 'text' : 'password';
      button.setAttribute('aria-label', revealing ? '隐藏密码' : '显示密码');
      button.setAttribute('aria-pressed', String(revealing));
      return;
    }
    if (action === 'register' || action === 'trial') {
      deactivate(); onLegacy(action); return;
    }
    if (nextChannel || ['password', 'otp', 'back'].includes(action)) {
      cooldown.stop();
      step = 'identify';
      if (action !== 'back') {
        channel = nextChannel || (action === 'password' ? 'password' : status?.passwordless?.email ? 'email' : 'sms');
        identifier = ''; resendAt = 0;
      }
      password = ''; code = ''; challenge = null; message = ''; invalid = ''; expiresAt = 0;
      render(); tick();
    }
  });

  const updateOffline = () => select('#auth-offline')?.toggleAttribute('hidden', navigator.onLine !== false);
  listen(window, 'online', updateOffline);
  listen(window, 'offline', updateOffline);
  listen(dialog, 'close', () => deactivate());
  listen(window, 'pagehide', () => { needsResume = active; deactivate(); });
  listen(window, 'pageshow', (event) => {
    if (!event.persisted || !needsResume) return;
    needsResume = false;
    // The shared session channel also revalidates restored pages. Let that
    // synchronous listener run first, then recover only if it has not done so.
    // This prevents duplicate status requests from cancelling one another.
    queueMicrotask(() => {
      if (destroyed || active) return;
      if (onResume) { void onResume(); return; }
      // Standalone embedders without a session owner must recheck the server,
      // rather than resurrecting an expired challenge from the bfcache.
      const owner = ++generation;
      Promise.resolve().then(() => api.getStatus()).then((fresh) => {
        if (destroyed || generation !== owner) return;
        if (fresh.authenticated) return onOutcome({ kind: 'authenticated', user: fresh.user });
        if (fresh.setup_required && !fresh.personal_signup_enabled) return onLegacy('setup');
        open(fresh, '请重新验证身份。');
      }).catch(() => {
        if (!destroyed && generation === owner) open(null, '连接暂未恢复，请重试或刷新页面。');
      });
    });
  });

  function deactivate() {
    active = false; generation += 1; busy = false;
    requestController?.abort(); requestController = null; cooldown.stop();
    password = ''; code = ''; challenge = null; identifier = '';
    mount(root, ''); root.hidden = true;
  }

  function open(nextStatus, initialMessage = '') {
    deactivate();
    status = nextStatus;
    channel = status?.passwordless?.email ? 'email' : status?.passwordless?.phone ? 'sms' : 'password';
    step = 'identify'; message = initialMessage; invalid = ''; resendAt = 0; expiresAt = 0; active = true;
    legacyForm.hidden = true; root.hidden = false;
    dialog.setAttribute('aria-labelledby', 'auth-unified-title');
    dialog.setAttribute('aria-describedby', 'auth-unified-description');
    render(false);
    if (!dialog.open) openDialog(dialog, '#auth-identifier');
    else focus();
  }

  return {
    open,
    deactivate,
    destroy() { destroyed = true; deactivate(); listeners.splice(0).forEach((remove) => remove()); },
  };
}
