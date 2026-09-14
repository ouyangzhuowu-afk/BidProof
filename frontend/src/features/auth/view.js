/**
 * 鉴权对话框的渲染层。
 *
 * 规则：**这个文件里不允许出现业务条件判断。**
 * 所有分支都在 state.js 的 resolveAuthView() 里算完了，这里只负责把
 * 视图模型刷到 DOM 上。一旦这里开始出现 `if (mode === ...)`，
 * 就说明状态机漏了一个字段，应该回去补 —— 而不是在这里补一个 if。
 */

import { el, openDialog, closeDialog } from '../../core/dom.js';
import { mount, html } from '../../ui/render.js';
import { resolveAuthView } from './state.js';

/** @typedef {import('./state.js').AuthMode} AuthMode */
/** @typedef {import('../../../types/api.js').AuthStatus} AuthStatus */

/** 字段块 → 选择器。visible/required 的键与这里一一对应。 */
const BLOCKS = {
  setupFields: '#setup-fields',
  bootstrapToken: '#bootstrap-token-wrap',
  trialFields: '#trial-join-fields',
  registerFields: '#register-fields',
  confirmField: '#auth-confirm-wrap',
  passwordHint: '#auth-password-hint',
  mfaFields: '#mfa-fields',
  oidc: '#oidc-login-wrap',
};

const REQUIRED_INPUTS = {
  workspace: '#auth-workspace',
  bootstrapToken: '#auth-bootstrap-token',
  joinCode: '#auth-join-code',
  confirm: '#auth-password-confirm',
  mfaCode: '#auth-mfa-code',
};

/**
 * @param {AuthStatus | null} status
 * @param {AuthMode | string} mode
 * @param {boolean} pendingMfa
 * @param {string} [message]
 * @returns {import('./state.js').AuthView}
 */
export function renderAuth(status, mode, pendingMfa, message = '') {
  const view = resolveAuthView(status, mode, pendingMfa);

  text('#auth-title', view.title);
  text('#auth-subtitle', view.subtitle);
  text('#auth-submit-label', view.submitLabel);
  text('#auth-help', view.helpText);
  toggle('#auth-help', view.helpVisible);

  for (const [key, selector] of Object.entries(BLOCKS)) {
    toggle(selector, view.visible[key]);
  }
  for (const [key, selector] of Object.entries(REQUIRED_INPUTS)) {
    const input = /** @type {HTMLInputElement | null} */ (el(selector));
    if (input) input.required = Boolean(view.required[key]);
  }

  // 模式切换器
  toggle('#auth-mode-wrap', view.modeSwitcherVisible);
  for (const node of document.querySelectorAll('[data-auth-mode]')) {
    const key = /** @type {HTMLElement} */ (node).dataset.authMode;
    node.toggleAttribute('hidden', !view.modeButtons[key]);
    // aria-pressed 而不是 class：切换器语义上是一组开关按钮，
    // 读屏需要知道哪一个是当前选中的。旧实现只加了 is-active 类。
    node.setAttribute('aria-pressed', String(key === view.mode && !view.pendingMfa));
  }

  const password = /** @type {HTMLInputElement | null} */ (el('#auth-password'));
  if (password) {
    password.minLength = view.passwordMinLength;
    password.autocomplete = view.passwordAutocomplete;
    password.disabled = view.credentialsDisabled;
  }
  const username = /** @type {HTMLInputElement | null} */ (el('#auth-username'));
  if (username) username.disabled = view.credentialsDisabled;

  const submit = /** @type {HTMLButtonElement | null} */ (el('#auth-form button[type="submit"]'));
  if (submit) submit.disabled = view.submitDisabled;

  setMessage(message, view.submitDisabled ? 'warning' : 'danger');
  return view;
}

/**
 * 打开对话框并把焦点放到该放的地方。
 * 用 requestAnimationFrame 而不是 setTimeout(0)：showModal() 之后
 * 浏览器还要做一次焦点初始化，抢在它前面聚焦会被覆盖。
 *
 * @param {string} focusSelector
 */
export function openAuthDialog(focusSelector) {
  const dialog = /** @type {HTMLDialogElement | null} */ (el('#auth-panel'));
  if (!dialog) return;
  if (!dialog.open) openDialog(dialog, focusSelector);
  else requestAnimationFrame(() => /** @type {HTMLElement | null} */ (el(focusSelector))?.focus());
}

export function closeAuthDialog() {
  closeDialog(/** @type {HTMLDialogElement | null} */ (el('#auth-panel')));
}

/**
 * 错误与提示。
 *
 * 旧实现是 `#auth-message` 的 textContent —— 有 aria-live，
 * 但视觉上就是一行小字，在一个有六个输入框的表单里几乎看不见。
 *
 * @param {string} message
 * @param {'danger' | 'warning'} [tone]
 */
export function setMessage(message, tone = 'danger') {
  const target = el('#auth-message');
  if (!target) return;
  if (!message) { mount(target, ''); return; }
  mount(target, html`
    <p class="callout" data-tone="${tone}">
      <i data-lucide="triangle-alert" aria-hidden="true"></i>
      <span>${message}</span>
    </p>`);
}

/**
 * 密码显隐切换。
 * 注意 aria-label 的方向：按钮描述的是**点下去会发生什么**，
 * 不是当前状态。旧实现把两者写反了一半。
 *
 * @param {HTMLElement} button
 */
export function togglePasswordVisibility(button) {
  const input = /** @type {HTMLInputElement | null} */ (
    document.getElementById(button.dataset.passwordToggle || '')
  );
  if (!input) return;
  const revealing = input.type === 'password';
  input.type = revealing ? 'text' : 'password';
  button.setAttribute('aria-label', revealing ? '隐藏密码' : '显示密码');
  button.setAttribute('aria-pressed', String(revealing));
  mount(button, html`<i data-lucide="${revealing ? 'eye-off' : 'eye'}"></i>`);
}

/** 关闭对话框前清空密码字段，别把明文留在 DOM 里。 */
export function clearAuthForm() {
  const form = /** @type {HTMLFormElement | null} */ (el('#auth-form'));
  form?.reset();
  setMessage('');
}

/* ── 小工具 ─────────────────────────────────────────────────────────────── */

/** @param {string} selector @param {string} value */
function text(selector, value) {
  const node = el(selector);
  if (node) node.textContent = value;
}

/** @param {string} selector @param {boolean} visible */
function toggle(selector, visible) {
  el(selector)?.toggleAttribute('hidden', !visible);
}
