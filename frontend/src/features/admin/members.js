/**
 * 企业成员。
 *
 * 从 app.js 搬出时改的四件事：
 *
 *   1. **改角色与停用现在要二次确认。** 旧实现是 `<select>` 一 change 就提交、
 *      按钮一点就停用，没有任何确认。改的是别人的权限，降级或停用对对方是
 *      立即生效的，而对方不在场 —— 这类操作属于确认阶梯的 T2。
 *      取消确认时把下拉还原，否则界面显示的角色和服务端不一致。
 *
 *   2. **重置密码链接改用一次性凭据组件。** 旧实现的 showSecureLink 只有
 *      链接和复制按钮，没有「仅显示一次」的视觉提示，也没有保存确认。
 *
 *   3. **可见性走角色矩阵前置**（core/permissions.js），不再靠内联的
 *      `['OWNER','ADMIN'].includes(...)` 各写一遍。
 *
 *   4. **列表改用真 `<table>` 且事件走委托。** 旧实现每次渲染后遍历三种
 *      控件逐个 addEventListener，刷新一次就多挂一轮。
 *
 * 保留不动的既有行为：**OWNER 自身没有角色与停用控件**
 * （原 app.js 的条件是 `member.role !== 'OWNER'`）。这不是疏漏。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { confirmAction } from '../../ui/confirm.js';
import { revealSecret } from '../../ui/secret-reveal.js';
import { toastSuccess, toastFromError } from '../../core/toast.js';
import { shortId, roleLabel } from '../../core/format.js';
import { can, isMemberMutable, isPermissionError } from '../../core/permissions.js';
import { workspaceApi, authApi } from '../../api/index.js';
import { MIN_PASSWORD_LENGTH, PASSWORD_POLICY_MESSAGE, passwordMeetsPolicy } from '../../core/password.js';

/** @typedef {import('../../../types/api.js').Member} Member */
/** @typedef {import('../../../types/api.js').Role} Role */

/** @type {(() => void)[]} */
let teardown = [];
/** 'invite' = 生成一次性链接；'direct' = 管理员设定初始密码。 */
let createMode = 'invite';

export function mountMembers() {
  if (teardown.length) return;
  teardown = [
    bind('#member-form', 'submit', (event) => { void submitCreate(event); }),
    delegate('#member-mode', 'click', '[data-member-mode]', (_e, node) => {
      setCreateMode(/** @type {HTMLElement} */ (node).dataset.memberMode);
    }),
    delegate('#members-list', 'change', '[data-member-role]', (event, node) => {
      void changeRole(/** @type {HTMLSelectElement} */ (event.target),
        /** @type {HTMLElement} */ (node).dataset.memberRole);
    }),
    delegate('#members-list', 'click', '[data-member-active]', (_e, node) => {
      void toggleActive(/** @type {HTMLButtonElement} */ (node));
    }),
    delegate('#members-list', 'click', '[data-member-reset]', (_e, node) => {
      void resetPassword(/** @type {HTMLButtonElement} */ (node));
    }),
    delegate('#members-list', 'click', '#members-retry', () => { void load(); }),
  ];
  setCreateMode('invite');
  void load();
}

export function unmountMembers() {
  for (const off of teardown) off();
  teardown = [];
  // 邀请链接、重置链接都是秘密，离开页面时不留在 DOM 里。
  mount(el('#member-message'), '');
}

/* ═══════════════════════════════════════════════════════════════════════════
   取数与渲染
   ═══════════════════════════════════════════════════════════════════════ */

export async function load() {
  const target = el('#members-list');
  if (!target) return;

  const manage = can('members.manage');
  el('#member-form')?.toggleAttribute('hidden', !manage);

  mount(target, skeleton('row', 3));
  try {
    const { members } = await workspaceApi.listMembers();
    // 顺手刷新全局缓存：任务列表的负责人/复核人下拉用的是同一份数据，
    // 改完角色回到任务页应当立刻看到新值。
    store.set({ members, membersFetchedAt: Date.now() });
    render(members, manage);
  } catch (error) {
    mount(target, errorState({
      title: isPermissionError(error) ? '没有查看成员的权限' : '成员加载失败',
      error,
      // 权限问题重试也没用，只有其它错误才给重试按钮。
      retryId: isPermissionError(error) ? undefined : 'members-retry',
    }));
  }
}

/** @param {Member[]} members @param {boolean} manage */
function render(members, manage) {
  const target = el('#members-list');
  if (!target) return;
  if (!members.length) {
    mount(target, emptyState({ icon: 'users', title: '还没有成员' }));
    return;
  }

  mount(target, html`
    <div class="table-wrap">
      <table class="table table--responsive">
        <thead>
          <tr>
            <th scope="col">成员</th>
            <th scope="col">角色</th>
            <th scope="col">状态</th>
            <th scope="col" class="td--actions"><span class="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>${members.map((member) => row(member, manage))}</tbody>
      </table>
    </div>
  `);
}

/** @param {Member} member @param {boolean} manage */
function row(member, manage) {
  // OWNER 行没有角色与停用控件 —— 既有行为，不是疏漏。
  const mutable = manage && isMemberMutable(member);

  return html`
    <tr data-active="${String(member.active)}">
      <td data-label="成员">
        <span class="member-cell">
          <span class="avatar avatar--sm">${initial(member.username)}</span>
          <span class="member-cell__text">
            <strong>${member.username}</strong>
            <small class="chip chip--mono">${shortId(member.user_id)}</small>
          </span>
        </span>
      </td>
      <td data-label="角色">
        ${mutable
          ? html`
            <select class="select" data-member-role="${member.user_id}"
                    data-previous="${member.role}"
                    aria-label="${member.username} 的角色">
              ${['ADMIN', 'REVIEWER', 'VIEWER'].map((value) => html`
                <option value="${value}" ${member.role === value ? 'selected' : ''}>
                  ${roleLabel(value)}
                </option>`)}
            </select>`
          : html`<span class="chip">${roleLabel(member.role)}</span>`}
      </td>
      <td data-label="状态">
        <span class="chip ${member.active ? 'chip--info' : ''}">
          ${member.active ? '可登录' : '已停用'}
        </span>
      </td>
      <td data-label="操作" class="td--actions">
        ${mutable
          ? html`
            <button class="btn btn--sm btn--ghost" type="button"
                    data-member-active="${member.user_id}"
                    data-active="${String(member.active)}"
                    data-username="${member.username}">
              ${member.active ? '停用' : '启用'}
            </button>`
          : ''}
        ${mutable && member.active
          ? html`
            <button class="btn btn--sm btn--ghost" type="button"
                    data-member-reset="${member.user_id}"
                    data-username="${member.username}">
              重置密码
            </button>`
          : ''}
      </td>
    </tr>
  `;
}

/* ═══════════════════════════════════════════════════════════════════════════
   动作
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 改角色。T2 —— 权限变更对被改的人立即生效，而对方不在场。
 *
 * @param {HTMLSelectElement} select
 * @param {string} userId
 */
async function changeRole(select, userId) {
  const previous = select.dataset.previous || '';
  const next = /** @type {Role} */ (select.value);
  if (next === previous) return;

  const name = select.getAttribute('aria-label')?.replace(' 的角色', '') || '该成员';
  const ok = await confirmAction({
    title: '修改成员角色',
    body: `将「${name}」从${roleLabel(previous)}改为${roleLabel(next)}。`
      + '权限变更立即生效，对方当前的会话不会断开但可访问范围会变。',
    confirmLabel: `改为${roleLabel(next)}`,
  });
  if (!ok) {
    // 取消就还原下拉。不还原的话界面显示的角色和服务端不一致，
    // 而用户会以为已经改了。
    select.value = previous;
    return;
  }

  select.disabled = true;
  try {
    await workspaceApi.updateMember(userId, { role: next });
    select.dataset.previous = next;
    toastSuccess('成员角色已更新。');
    await load();
  } catch (error) {
    select.value = previous;
    toastFromError(error, '角色未更新。');
  } finally {
    select.disabled = false;
  }
}

/**
 * 停用 / 启用。停用要确认（把人挡在工作区外），启用不用。
 * @param {HTMLButtonElement} button
 */
async function toggleActive(button) {
  const userId = button.dataset.memberActive;
  const name = button.dataset.username || '该成员';
  const next = button.dataset.active !== 'true';

  if (!next) {
    const ok = await confirmAction({
      title: '停用成员',
      body: `「${name}」将无法登录工作台。历史记录与审计事件仍会保留其署名，`
        + '需要时可以再启用。',
      confirmLabel: '停用',
      tone: 'danger',
    });
    if (!ok) return;
  }

  await withLoading(button, async () => {
    try {
      await workspaceApi.updateMember(userId, { active: next });
      toastSuccess(next ? '成员已启用。' : '成员已停用。');
      await load();
    } catch (error) {
      toastFromError(error, '成员状态未更新。');
    }
  });
}

/**
 * 生成一次性重置链接。T2 —— 会使对方现有凭据失效。
 * @param {HTMLButtonElement} button
 */
async function resetPassword(button) {
  const name = button.dataset.username || '该成员';
  const ok = await confirmAction({
    title: '重置成员密码',
    body: `将为「${name}」生成一条一小时内有效的重置链接。`
      + '对方用它设置新密码后，其现有会话全部失效。',
    confirmLabel: '生成重置链接',
  });
  if (!ok) return;

  await withLoading(button, async () => {
    try {
      const reset = await workspaceApi.resetMemberPassword(button.dataset.memberReset);
      revealSecret(el('#member-message'), {
        title: `密码重置链接 · ${name}`,
        note: '1 小时内有效，只显示这一次。请通过可信渠道发给对方。',
        link: absolute(reset.reset_path),
      });
    } catch (error) {
      showFormError(error, '重置链接未生成。');
    }
  });
}

/* ── 新建成员 ─────────────────────────────────────────────────────────────── */

/** @param {string} mode */
function setCreateMode(mode) {
  createMode = mode === 'direct' ? 'direct' : 'invite';
  const direct = createMode === 'direct';
  for (const node of document.querySelectorAll('#member-mode [data-member-mode]')) {
    node.setAttribute('aria-pressed',
      String(/** @type {HTMLElement} */ (node).dataset.memberMode === createMode));
  }
  el('#member-password-wrap')?.toggleAttribute('hidden', !direct);
  const password = /** @type {HTMLInputElement | null} */ (el('#member-password'));
  if (password) {
    password.required = direct;
    password.minLength = MIN_PASSWORD_LENGTH;
  }
  const label = el('#member-submit-label');
  if (label) label.textContent = direct ? '直接开户' : '生成邀请链接';
}

/** @param {Event} event */
async function submitCreate(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const data = new FormData(form);
  const username = String(data.get('username') || '').trim();
  const role = /** @type {Role} */ (String(data.get('role') || 'REVIEWER'));
  if (!username) return;

  mount(el('#member-message'), '');

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      if (createMode === 'direct') {
        const password = String(data.get('password') || '');
        if (!passwordMeetsPolicy(password)) {
          throw new Error(PASSWORD_POLICY_MESSAGE);
        }
        await workspaceApi.createMember({ username, password, role });
        form.reset();
        setCreateMode('direct');
        // 密码是管理员自己设的，不需要一次性凭据组件；
        // 但仍要提醒线下转交，不要贴在聊天窗口里。
        mount(el('#member-message'), html`
          <p class="callout" data-tone="ok">
            <i data-lucide="check"></i>
            <span>已为 ${username} 开户。请通过可信渠道线下转交初始密码。</span>
          </p>`);
      } else {
        const invitation = await authApi.createInvitation({ username, role });
        form.reset();
        setCreateMode('invite');
        revealSecret(el('#member-message'), {
          title: `邀请链接 · ${username}`,
          note: '72 小时内有效，只显示这一次。对方通过它设置密码并激活账号。',
          link: absolute(invitation.activation_path),
        });
      }
      await load();
    } catch (error) {
      showFormError(error, '成员未创建。');
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   工具
   ═══════════════════════════════════════════════════════════════════════ */

/** 后端返回的是相对路径，链接要能直接发给别人，必须补上来源。 */
function absolute(/** @type {string} */ path) {
  return new URL(path, window.location.origin).toString();
}

/** @param {unknown} error @param {string} fallback */
function showFormError(error, fallback) {
  const message = error instanceof Error ? error.message : fallback;
  mount(el('#member-message'), html`
    <p class="callout" data-tone="danger">
      <i data-lucide="triangle-alert"></i><span>${message}</span>
    </p>`);
}

/** @param {string} name */
function initial(name) {
  return String(name || '?').slice(0, 1).toLocaleUpperCase('zh-CN');
}
