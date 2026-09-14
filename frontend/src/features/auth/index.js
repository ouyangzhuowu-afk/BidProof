/**
 * 鉴权入口。
 *
 * 负责三件事：装配监听、提交、以及从 URL 进入的账号动作（激活 / 重置）。
 * 所有分支判断都在 state.js，所有 DOM 写入都在 view.js。
 *
 * 从 app.js 搬出时修掉的：
 *
 *   1. **MFA 挂起时提交按钮被禁用**，而验证码正是通过同一个表单提交的。
 *      用户只能靠在输入框里按回车，点按钮毫无反应。见 state.js 的 submitDisabled。
 *
 *   2. **MFA 挂起没有取消路径。** 换了手机、拿不到验证码时，
 *      唯一的出路是刷新整页。现在有「返回登录」。
 *
 *   3. **登录成功的判据是 `mfa_required`，不是 `mfa_token` 是否存在**
 *      （见 api/auth.js 的 toOutcome）。后者当前能工作只是因为后端两个字段
 *      同时回传。
 *
 *   4. 模式钳制逻辑此前在 setAuthMode() 与 showAuth() 各写了一遍。
 */

import { bind, delegate, el, withLoading, openDialog, closeDialog } from '../../core/dom.js';
import { mount, html } from '../../ui/render.js';
import { authApi } from '../../api/index.js';
import {
  renderAuth, openAuthDialog, closeAuthDialog, setMessage,
  togglePasswordVisibility, clearAuthForm,
} from './view.js';
import { MODE_ENDPOINT, buildPayload, needsConfirm, clampMode } from './state.js';
import { assertPasswordPolicy } from '../../core/password.js';

/** @typedef {import('../../../types/api.js').AuthStatus} AuthStatus */
/** @typedef {import('../../../types/api.js').CurrentUser} CurrentUser */

/** @type {AuthStatus | null} */
let status = null;
let mode = 'login';
let pendingMfaToken = '';
/** @type {{ token: string, action: string } | null} */
let accountAction = null;
/** @type {(user: CurrentUser) => void} */
let onAuthenticated = () => {};
let bound = false;

/* ═══════════════════════════════════════════════════════════════════════════
   装配
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * @param {{ onAuthenticated: (user: CurrentUser) => void }} handlers
 */
export function configureAuth(handlers) {
  onAuthenticated = handlers.onAuthenticated;
  if (bound) return;
  bound = true;

  bind('#auth-form', 'submit', (event) => { void submit(event); });
  delegate('#auth-mode-wrap', 'click', '[data-auth-mode]', (_e, node) => {
    setMode(/** @type {HTMLElement} */ (node).dataset.authMode);
  });
  bind('#auth-mfa-cancel', 'click', cancelMfa);
  bind('#account-action-form', 'submit', (event) => { void submitAccountAction(event); });
  bind('#logout-button', 'click', () => { void logout(); });

  // 密码显隐按钮在两个对话框里都有，用文档级委托一次绑完。
  delegate(document.body, 'click', '[data-password-toggle]', (_e, node) => {
    togglePasswordVisibility(/** @type {HTMLElement} */ (node));
  });

  // 这两个对话框不允许 Esc 关闭：背后没有可用的界面，
  // 关掉只会留下一个空壳。既有行为，保留。
  for (const selector of ['#auth-panel', '#account-action-panel']) {
    bind(selector, 'cancel', (event) => event.preventDefault());
  }

  // 401。core/http.js 不认识任何视图模块，它只派发这个事件；
  // 此前没有任何地方监听 —— 会话过期后用户会看到一连串请求失败，
  // 而不是一个登录框。
  bind(window, 'bidproof:unauthorized', () => { void reopenAfterExpiry(); });
}

/**
 * 会话过期后重新打开登录。
 *
 * 重新拉一次 status 而不是直接开框：过期期间管理员可能改过开关
 * （关掉了个人注册、启用了 OIDC），用旧的 status 渲染会给出已经不存在的入口。
 */
async function reopenAfterExpiry() {
  if (/** @type {HTMLDialogElement | null} */ (el('#auth-panel'))?.open) return;
  pendingMfaToken = '';
  try {
    status = await authApi.getStatus();
  } catch { /* 拿不到就用上一次的 status 兜底 */ }
  open('login', '登录状态已过期，请重新登录。');
}

/* ═══════════════════════════════════════════════════════════════════════════
   启动
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 鉴权启动流程。返回 true 表示已登录、调用方可以继续初始化；
 * 返回 false 表示已经打开了某个对话框，调用方应当停下。
 *
 * @returns {Promise<boolean>}
 */
export async function startAuth() {
  // 账号动作（激活 / 重置）从 URL 进入，优先级最高：
  // 用户是点着一条一次性链接来的，不该先看到登录框。
  if (await tryAccountAction()) return false;

  try {
    status = await authApi.getStatus();
  } catch (error) {
    status = null;
    open('login', error instanceof Error ? error.message : '无法连接服务');
    return false;
  }

  // 从 OIDC 回跳时可能带着 mfa_token：直接进第二步，不要求重新输密码。
  const fromUrl = new URLSearchParams(window.location.search).get('mfa_token');
  if (fromUrl && !status.authenticated) {
    pendingMfaToken = fromUrl;
    open('login');
    return false;
  }

  if (status.setup_required) {
    open('setup', status.bootstrap_locked
      ? '生产环境尚未配置初始化令牌，请联系运维人员。'
      : '');
    return false;
  }
  if (!status.authenticated) {
    open('login');
    return false;
  }

  onAuthenticated(/** @type {CurrentUser} */ (status.user));
  return true;
}

/** @param {string} requested @param {string} [message] */
function open(requested, message = '') {
  mode = clampMode(status, requested);
  const view = renderAuth(status, mode, Boolean(pendingMfaToken), message);
  openAuthDialog(view.focus);
}

/** @param {string} requested */
function setMode(requested) {
  mode = clampMode(status, requested);
  const view = renderAuth(status, mode, Boolean(pendingMfaToken));
  requestAnimationFrame(() => /** @type {HTMLElement | null} */ (el(view.focus))?.focus());
}

/**
 * 退出 MFA 第二步，回到登录。
 *
 * 这个出口旧实现完全没有 —— 换了手机、拿不到验证码时只能刷新整页。
 * 清掉 pendingMfaToken 的同时也清表单：上一次的密码不该留在 DOM 里。
 */
function cancelMfa() {
  pendingMfaToken = '';
  clearAuthForm();
  const view = renderAuth(status, mode, false);
  requestAnimationFrame(() => /** @type {HTMLElement | null} */ (el(view.focus))?.focus());
}

/* ═══════════════════════════════════════════════════════════════════════════
   提交
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {Event} event */
async function submit(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const button = form.querySelector('button[type="submit"]');
  setMessage('');

  await withLoading(button, async () => {
    try {
      const outcome = pendingMfaToken
        ? await authApi.verifyMfa({
          mfa_token: pendingMfaToken,
          code: value('#auth-mfa-code'),
        })
        : await submitCredentials();

      if (outcome.kind === 'mfa_required') {
        pendingMfaToken = outcome.mfaToken;
        const view = renderAuth(status, mode, true, '');
        setMessage('');
        mount(el('#auth-message'), html`
          <p class="callout" data-tone="info">
            <i data-lucide="shield-check" aria-hidden="true"></i>
            <span>请输入身份验证器中的 6 位验证码，或一次性恢复码。</span>
          </p>`);
        requestAnimationFrame(() => /** @type {HTMLElement | null} */ (el(view.focus))?.focus());
        return;
      }

      pendingMfaToken = '';
      clearAuthForm();
      closeAuthDialog();
      onAuthenticated(outcome.user);
    } catch (error) {
      fail(error);
    }
  });
}

/** @returns {Promise<import('../../api/auth.js').LoginOutcome>} */
async function submitCredentials() {
  const password = value('#auth-password');
  if (needsConfirm(mode) && password !== value('#auth-password-confirm')) {
    // 本地校验，不发请求 —— 这不是服务端能判断的事。
    const mismatch = new Error('两次输入的密码不一致');
    mismatch.name = 'ConfirmMismatch';
    throw mismatch;
  }
  if (needsConfirm(mode)) assertPasswordPolicy(password);

  const payload = buildPayload(mode, {
    username: value('#auth-username'),
    password,
    workspace: value('#auth-workspace'),
    bootstrapToken: value('#auth-bootstrap-token'),
    joinCode: value('#auth-join-code'),
    displayName: value('#auth-display-name'),
  });

  const call = authApi[MODE_ENDPOINT[mode]];
  const result = await call(payload);
  // login/verifyMfa 已归一成 LoginOutcome；其余三个端点直接返回用户对象。
  return result?.kind ? result : { kind: 'authenticated', user: result };
}

/**
 * 失败处理。焦点落点很重要：这个表单最多有六个输入框，
 * 用户需要立刻知道是哪一个出了问题。
 *
 * @param {unknown} error
 */
function fail(error) {
  const message = error instanceof Error ? error.message : '登录失败，请重试。';
  setMessage(message);

  const target = pendingMfaToken
    ? '#auth-mfa-code'
    : (error instanceof Error && error.name === 'ConfirmMismatch')
      ? '#auth-password-confirm'
      : (mode === 'trial' ? '#auth-join-code' : '#auth-password');
  const node = /** @type {HTMLInputElement | null} */ (el(target));
  node?.focus();
  node?.select?.();
}

/* ═══════════════════════════════════════════════════════════════════════════
   账号动作：激活 / 重置
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 从 URL 的一次性 token 进入。
 * @returns {Promise<boolean>} 是否接管了本次启动
 */
async function tryAccountAction() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const requested = params.get('auth_action');
  if (!token || !['activate', 'reset'].includes(requested)) return false;

  const dialog = /** @type {HTMLDialogElement | null} */ (el('#account-action-panel'));
  try {
    const inspected = await authApi.describeAction(token);
    accountAction = { token, action: inspected.action };
    // 取值是 'INVITE'，不是 'activate'。分支写错不会报错，
    // 只会把邀请当成密码重置处理 —— 文案和后续端点都会错。
    const invite = inspected.action === 'INVITE';
    text('#account-action-title', invite ? '激活企业账号' : '重置账号密码');
    text('#account-action-subtitle', invite
      ? `接受邀请并为「${inspected.username}」设置密码。`
      : '设置新密码后，该账号的旧会话将全部失效。');
    setValue('#account-action-username', inspected.username);
    text('#account-action-submit', invite ? '激活并进入' : '重置并进入');
  } catch (error) {
    accountAction = null;
    accountMessage(error instanceof Error ? error.message : '链接无效', 'danger');
    const submitButton = /** @type {HTMLButtonElement | null} */ (
      el('#account-action-form button[type="submit"]')
    );
    // token 失效时禁用提交。旧实现这一点做对了，保留。
    if (submitButton) submitButton.disabled = true;
  }
  if (dialog) openDialog(dialog, '#account-action-password');
  return true;
}

/** @param {Event} event */
async function submitAccountAction(event) {
  event.preventDefault();
  if (!accountAction) return;

  const password = value('#account-action-password');
  if (password !== value('#account-action-confirm')) {
    accountMessage('两次输入的密码不一致。', 'danger');
    /** @type {HTMLInputElement | null} */ (el('#account-action-confirm'))?.focus();
    return;
  }
  try {
    assertPasswordPolicy(password);
  } catch (error) {
    accountMessage(error instanceof Error ? error.message : '密码不符合要求。', 'danger');
    /** @type {HTMLInputElement | null} */ (el('#account-action-password'))?.focus();
    return;
  }

  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  accountMessage('');

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      const body = { token: accountAction.token, password };
      const user = accountAction.action === 'INVITE'
        ? await authApi.activate(body)
        : await authApi.resetPassword(body);

      // 把一次性 token 从 URL 与浏览器历史里抹掉。
      // 这是安全行为不是清洁工作：否则 token 会留在历史记录、
      // 以及用户之后可能分享出去的地址里。
      window.history.replaceState({}, '', '/app');
      form.reset();
      closeDialog(/** @type {HTMLDialogElement | null} */ (el('#account-action-panel')));
      onAuthenticated(user);
    } catch (error) {
      accountMessage(error instanceof Error ? error.message : '设置失败，请重试。', 'danger');
    }
  });
}

/** @param {string} message @param {'danger'} [tone] */
function accountMessage(message, tone = 'danger') {
  const target = el('#account-action-message');
  if (!target) return;
  mount(target, message
    ? html`<p class="callout" data-tone="${tone}">
             <i data-lucide="triangle-alert" aria-hidden="true"></i><span>${message}</span></p>`
    : '');
}

/* ═══════════════════════════════════════════════════════════════════════════
   登出
   ═══════════════════════════════════════════════════════════════════════ */

async function logout() {
  try {
    await authApi.logout();
  } finally {
    // 整页跳转而不是切视图：这是最省心的会话清理方式，
    // 内存里残留的任何任务数据、证据引文都会随之丢掉。
    window.location.replace('/app');
  }
}

/* ── 小工具 ─────────────────────────────────────────────────────────────── */

/** @param {string} selector */
function value(selector) {
  return /** @type {HTMLInputElement | null} */ (el(selector))?.value ?? '';
}

/** @param {string} selector @param {string} v */
function setValue(selector, v) {
  const node = /** @type {HTMLInputElement | null} */ (el(selector));
  if (node) node.value = v;
}

/** @param {string} selector @param {string} v */
function text(selector, v) {
  const node = el(selector);
  if (node) node.textContent = v;
}
