/**
 * 账号安全：修改密码、登录设备、二次验证、API 令牌。
 *
 * 这四块的共同点是**每一块都在处理凭据**，所以规则比别处严：
 *
 *   - 一次性秘密（MFA 恢复码、API 令牌明文）必须走 ui/secret-reveal.js，
 *     不能再像旧实现那样 `element.textContent = '请立即保存令牌：' + token`。
 *     丢令牌是重建集成，丢恢复码是**账号锁死**。
 *   - 撤销类动作按确认阶梯分级：踢单个设备 T2、踢全部其他设备 T3、
 *     撤销令牌 T3 且确认词用令牌名本身。
 *   - 关闭 MFA **不额外套确认对话框** —— 它已经要求输入一个 TOTP 码，
 *     那个码本身就是确认。再叠一层只是噪音。
 *
 * 另外修掉的：
 *   - `getMfaStatus()` 此前对 `/api/auth/mfa/enroll` 发 GET。那个端点只接受
 *     POST，而且 POST 会**轮换密钥**。现在读 `/api/auth/status` 的 mfa_enabled。
 *   - 会话列表直接把 `created_at` / `expires_at` 原样打印，界面上是一串 ISO
 *     时间戳。现在走 format.js。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { confirmAction, confirmWithWord } from '../../ui/confirm.js';
import { revealSecret } from '../../ui/secret-reveal.js';
import { toastSuccess, toastFromError } from '../../core/toast.js';
import { formatDate, formatRelative } from '../../core/format.js';
import { isPermissionError } from '../../core/permissions.js';
import { authApi } from '../../api/index.js';
import { assertPasswordPolicy } from '../../core/password.js';

/** @type {(() => void)[]} */
let teardown = [];
/** 本地记住 MFA 开关状态，避免提交时再多发一次 status 请求。 */
let mfaEnabled = false;

export function mountAccount() {
  if (teardown.length) return;
  teardown = [
    bind('#password-form', 'submit', (event) => { void changePassword(event); }),
    bind('#revoke-other-sessions', 'click', (event) => { void revokeOthers(event.currentTarget); }),
    delegate('#sessions-list', 'click', '[data-revoke-session]', (_e, node) => {
      void revokeSession(/** @type {HTMLButtonElement} */ (node));
    }),
    bind('#mfa-enroll', 'click', (event) => { void enroll(event.currentTarget); }),
    bind('#mfa-form', 'submit', (event) => { void submitMfa(event); }),
    bind('#token-form', 'submit', (event) => { void createToken(event); }),
    delegate('#tokens-list', 'click', '[data-revoke-token]', (_e, node) => {
      void revokeToken(/** @type {HTMLButtonElement} */ (node));
    }),
  ];
  load();
}

export function unmountAccount() {
  for (const off of teardown) off();
  teardown = [];
  // 恢复码与令牌明文不留在 DOM 里。
  mount(el('#mfa-secret'), '');
  el('#mfa-secret')?.setAttribute('hidden', '');
  mount(el('#token-message'), '');
}

export function load() {
  void loadSessions();
  void loadMfa();
  void loadTokens();
}

/* ═══════════════════════════════════════════════════════════════════════════
   密码
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {Event} event */
async function changePassword(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const data = new FormData(form);
  const message = el('#password-message');
  mount(message, '');

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      const newPassword = String(data.get('new_password') || '');
      assertPasswordPolicy(newPassword);
      await authApi.changePassword({
        current_password: String(data.get('current_password') || ''),
        new_password: newPassword,
      });
      form.reset();
      // 「当前会话继续有效」是必须说的一句：改完密码之后
      // 用户最担心的就是自己会不会被踢出去。
      mount(message, html`
        <p class="callout" data-tone="ok">
          <i data-lucide="check"></i>
          <span>密码已更新，当前会话继续有效。其它设备不受影响，如需一并踢出请用下方的按钮。</span>
        </p>`);
      await loadSessions();
    } catch (error) {
      mount(message, html`
        <p class="callout" data-tone="danger">
          <i data-lucide="triangle-alert"></i>
          <span>${error instanceof Error ? error.message : '密码未更新'}。</span>
        </p>`);
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   登录设备
   ═══════════════════════════════════════════════════════════════════════ */

async function loadSessions() {
  const target = el('#sessions-list');
  if (!target) return;
  mount(target, skeleton('row', 2));
  try {
    const { sessions } = await authApi.listSessions();
    if (!sessions.length) {
      mount(target, emptyState({ icon: 'monitor-smartphone', title: '没有有效会话' }));
      return;
    }
    // 当前设备排最前，且不给撤销按钮 —— 踢掉自己等于登出，
    // 那是另一个入口该做的事。
    const sorted = [...sessions].sort((a, b) => Number(b.current) - Number(a.current));
    mount(target, sorted.map((session) => html`
      <article class="admin-row" data-current="${String(Boolean(session.current))}">
        <span class="admin-row__icon"><i data-lucide="monitor"></i></span>
        <span class="admin-row__main">
          <strong>${session.current ? '当前设备' : '其他设备'}</strong>
          <small>
            登录于 ${formatDate(session.created_at)}
            · 有效至 ${formatRelative(session.expires_at)}
          </small>
        </span>
        ${session.current
          ? html`<span class="chip chip--info">使用中</span>`
          : html`<button class="btn btn--sm btn--ghost" type="button"
                         data-revoke-session="${session.session_id}">踢出</button>`}
      </article>
    `));
    // 只有一台设备时「踢出其他设备」没有意义，藏起来。
    el('#revoke-other-sessions')?.toggleAttribute('hidden', sessions.length <= 1);
  } catch (error) {
    mount(target, errorState({ title: '会话列表加载失败', error }));
  }
}

/** @param {HTMLButtonElement} button */
async function revokeSession(button) {
  const ok = await confirmAction({
    title: '踢出该设备',
    body: '该设备的登录会话将立即失效，需要重新登录。',
    confirmLabel: '踢出',
  });
  if (!ok) return;

  await withLoading(button, async () => {
    try {
      await authApi.revokeSession(button.dataset.revokeSession);
      toastSuccess('已踢出该设备。');
      await loadSessions();
    } catch (error) {
      toastFromError(error, '未能踢出该设备。');
    }
  });
}

/**
 * T3。批量、影响所有设备、登录态无法恢复。
 *
 * 产品上有过一次讨论：这个功能的典型场景是「我怀疑账号被盗」，
 * 此时让用户先打字是有成本的。结论是仍用确认词 ——
 * 误触的代价（全公司设备被踢）比多打六个字母高得多。
 *
 * @param {Element} button
 */
async function revokeOthers(button) {
  const ok = await confirmWithWord({
    title: '踢出全部其他设备',
    body: '除当前设备外的所有登录会话将立即失效，其他设备需要重新登录。此操作无法撤销。',
    word: 'REVOKE',
    confirmLabel: '全部踢出',
  });
  if (!ok) return;

  await withLoading(button, async () => {
    try {
      const result = await authApi.revokeOtherSessions();
      toastSuccess(`已踢出 ${result.revoked} 台其他设备。`);
      await loadSessions();
    } catch (error) {
      toastFromError(error, '未能踢出其他设备。');
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   二次验证
   ═══════════════════════════════════════════════════════════════════════ */

async function loadMfa() {
  const target = el('#mfa-status');
  if (!target) return;
  try {
    const { enabled } = await authApi.getMfaStatus();
    mfaEnabled = enabled;
    mount(target, enabled
      ? html`<p class="callout" data-tone="ok">
               <i data-lucide="shield-check"></i>
               <span>二次验证已启用。登录时需要验证器验证码或一条恢复码。</span></p>`
      : html`<p class="callout" data-tone="warning">
               <i data-lucide="shield-alert"></i>
               <span>尚未启用二次验证。启用后，仅凭密码无法登录本账号。</span></p>`);

    const label = el('#mfa-submit-label');
    if (label) label.textContent = enabled ? '关闭二次验证' : '确认并启用';
    // 已启用时不该再显示「开始绑定」—— 那个按钮会轮换密钥，
    // 让已绑定的验证器立刻失效。
    el('#mfa-enroll')?.toggleAttribute('hidden', enabled);
  } catch (error) {
    mount(target, errorState({ title: '二次验证状态加载失败', error }));
  }
}

/**
 * 生成密钥与恢复码。
 *
 * **调用即轮换密钥**：用户没确认就离开，旧密钥已失效。这是既有后端行为，
 * 所以按钮之前先确认一次 —— 旧实现点一下就发请求。
 *
 * @param {Element} button
 */
async function enroll(button) {
  const ok = await confirmAction({
    title: '开始绑定验证器',
    body: '会生成一组新的密钥与恢复码。此前生成过的密钥与恢复码将立即失效，'
      + '即使你这次没有完成绑定。',
    confirmLabel: '生成新密钥',
  });
  if (!ok) return;

  await withLoading(button, async () => {
    try {
      const payload = await authApi.enrollMfa();
      const secret = el('#mfa-secret');
      secret?.removeAttribute('hidden');
      // 恢复码是这里唯一不可再生的东西：验证器可以重新绑定，
      // 恢复码丢了就只能找管理员重置账号。
      revealSecret(secret, {
        title: 'MFA 密钥与恢复码',
        note: '恢复码只显示这一次。丢失后，一旦失去验证器就无法自行登录。'
          + '请立即存入密码管理器。',
        values: [`密钥：${payload.secret}`, '', '恢复码：', ...(payload.recovery_codes || [])],
        filename: 'bidproof-mfa-recovery-codes.txt',
      });
      mount(el('#mfa-message'), html`
        <p class="hint">用验证器扫描或录入上面的密钥，然后在下方输入一个验证码完成绑定。</p>`);
    } catch (error) {
      toastFromError(error, '密钥未生成。');
    }
  });
}

/**
 * 启用或关闭。关闭**不额外套确认对话框** ——
 * 它已经要求输入一个 TOTP 码，那个码本身就是确认。
 *
 * @param {Event} event
 */
async function submitMfa(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const input = /** @type {HTMLInputElement} */ (form.querySelector('#mfa-code'));
  const code = input.value.trim();
  if (!code) { input.focus(); return; }
  mount(el('#mfa-message'), '');

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      if (mfaEnabled) {
        await authApi.disableMfa({ code });
        toastSuccess('二次验证已关闭。');
      } else {
        await authApi.confirmMfa({ code });
        toastSuccess('二次验证已启用。');
      }
      input.value = '';
      mount(el('#mfa-secret'), '');
      el('#mfa-secret')?.setAttribute('hidden', '');
      await loadMfa();
    } catch (error) {
      mount(el('#mfa-message'), html`
        <p class="callout" data-tone="danger">
          <i data-lucide="triangle-alert"></i>
          <span>${error instanceof Error ? error.message : '操作未完成'}。
                验证码只有 30 秒有效期，过期后请用新的一个。</span>
        </p>`);
      input.select();
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   API 令牌
   ═══════════════════════════════════════════════════════════════════════ */

async function loadTokens() {
  const target = el('#tokens-list');
  if (!target) return;
  mount(target, skeleton('row', 2));
  try {
    const { tokens } = await authApi.listTokens();
    el('#token-form')?.removeAttribute('hidden');
    if (!tokens.length) {
      mount(target, emptyState({
        icon: 'key',
        title: '还没有 API 令牌',
        body: '令牌用于让外部系统读取扫描结果，权限与创建者相同。',
      }));
      return;
    }
    mount(target, tokens.map((token) => html`
      <article class="admin-row" data-revoked="${String(Boolean(token.revoked_at))}">
        <span class="admin-row__icon"><i data-lucide="key"></i></span>
        <span class="admin-row__main">
          <strong>${token.name}</strong>
          <small>
            <span class="chip chip--mono">${token.token_prefix}…</span>
            ${token.revoked_at ? `已于 ${formatDate(token.revoked_at)} 撤销` : '有效'}
          </small>
        </span>
        ${token.revoked_at
          ? html`<span class="chip">已撤销</span>`
          : html`<button class="btn btn--sm btn--ghost" type="button"
                         data-revoke-token="${token.token_id}"
                         data-token-name="${token.name}">撤销</button>`}
      </article>
    `));
  } catch (error) {
    el('#token-form')?.toggleAttribute('hidden', true);
    mount(target, isPermissionError(error)
      ? emptyState({ icon: 'lock', title: '当前角色不能管理 API 令牌' })
      : errorState({ title: '令牌列表加载失败', error }));
  }
}

/** @param {Event} event */
async function createToken(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const input = /** @type {HTMLInputElement} */ (form.querySelector('#token-name'));
  const name = input.value.trim();
  if (!name) return;

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      const created = await authApi.createToken({ name });
      input.value = '';
      revealSecret(el('#token-message'), {
        title: `API 令牌 · ${created.name}`,
        note: '服务端只保存哈希，这是唯一一次能看到明文的机会。',
        values: [created.token],
        filename: `bidproof-token-${created.token_prefix || 'new'}.txt`,
      });
      await loadTokens();
    } catch (error) {
      toastFromError(error, '令牌未创建。');
    }
  });
}

/**
 * T3，确认词用令牌名本身。
 *
 * 用名字而不是统一的 DELETE 有两个理由：确认词统一之后会变成肌肉记忆；
 * 而列表里多个令牌长得很像，输入名字同时也是一次「你选对那一条了吗」的校验。
 *
 * @param {HTMLButtonElement} button
 */
async function revokeToken(button) {
  const name = button.dataset.tokenName || '';
  const ok = await confirmWithWord({
    title: '撤销 API 令牌',
    body: `使用「${name}」的集成会立即开始收到 401。令牌无法恢复，只能重新创建。`,
    word: name,
    confirmLabel: '撤销令牌',
  });
  if (!ok) return;

  await withLoading(button, async () => {
    try {
      await authApi.revokeToken(button.dataset.revokeToken);
      toastSuccess('令牌已撤销。');
      await loadTokens();
    } catch (error) {
      toastFromError(error, '令牌未撤销。');
    }
  });
}
