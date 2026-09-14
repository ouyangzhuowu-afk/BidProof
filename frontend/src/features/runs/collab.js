/**
 * 详情页协作区：评论、审计记录、整改项。
 *
 * 从 app.js 搬出时修掉的主要问题：
 *
 *   1. 三个面板用一个 Promise.all 拉取，共用一个 try/catch。
 *      任何一个接口挂掉，三个面板一起变成错误态 —— 而且旧实现的
 *      catch 分支只写了评论和整改两个面板，审计面板会永远停在骨架屏。
 *      现在三条链路彼此独立，一个失败不影响另外两个。
 *
 *   2. 整改项的状态下拉在每次渲染后逐个 addEventListener。改为委托。
 *
 *   3. 审计记录直接显示 user_id（一串 UUID）。现在映射成用户名，
 *      映射不到才回退显示 id —— 审计记录的读者是人，不是数据库。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { toastSuccess, toastFromError } from '../../core/toast.js';
import { formatRelative, formatDate } from '../../core/format.js';
import { runsApi } from '../../api/index.js';

/** @type {(() => void)[]} */
let teardown = [];

export function mountCollab() {
  if (teardown.length) return;
  teardown = [
    bind('#comment-form', 'submit', (event) => { void postComment(event); }),
    bind('#remediation-form', 'submit', (event) => { void createRemediation(event); }),
    delegate('#remediations-list', 'change', '[data-remediation-status]', (event, node) => {
      void patchRemediation(
        /** @type {HTMLElement} */ (node).dataset.remediationStatus,
        { status: /** @type {HTMLSelectElement} */ (event.target).value },
        node,
      );
    }),
  ];
}

export function unmountCollab() {
  for (const off of teardown) off();
  teardown = [];
}

/**
 * 加载三个面板。**刻意不用 Promise.all** ——
 * 它们之间没有依赖关系，没有理由一起失败。
 */
export function loadCollab() {
  void loadComments();
  void loadAudit();
  void loadRemediations();
}

/* ═══════════════════════════════════════════════════════════════════════════
   评论
   ═══════════════════════════════════════════════════════════════════════ */

async function loadComments() {
  const target = el('#comments-list');
  const run = store.get().currentRun;
  if (!target || !run) return;

  mount(target, skeleton('line', 2));
  try {
    const { comments } = await runsApi.listComments(run.run_id);
    if (!comments.length) {
      mount(target, emptyState({
        icon: 'message-square',
        title: '暂无评论',
        body: '用评论记录与法务、商务之间的往来，它们不会进入审计链。',
      }));
      return;
    }
    mount(target, comments.map((item) => html`
      <article class="activity">
        <span class="avatar avatar--sm">${initial(displayName(item.user_id))}</span>
        <div class="activity__body">
          <p class="activity__head">
            <strong>${displayName(item.user_id)}</strong>
            <time datetime="${item.created_at}" title="${formatDate(item.created_at)}">
              ${formatRelative(item.created_at)}
            </time>
          </p>
          <p class="activity__text">${item.body}</p>
        </div>
      </article>
    `));
  } catch (error) {
    mount(target, errorState({ title: '评论加载失败', error }));
  }
}

/** @param {Event} event */
async function postComment(event) {
  event.preventDefault();
  const run = store.get().currentRun;
  if (!run) return;

  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const input = /** @type {HTMLTextAreaElement} */ (form.querySelector('[name="body"]'));
  const body = input.value.trim();
  if (!body) { input.focus(); return; }

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      await runsApi.addComment(run.run_id, { body });
      input.value = '';
      await loadComments();
    } catch (error) {
      toastFromError(error, '评论未发送。');
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   审计
   ═══════════════════════════════════════════════════════════════════════ */

/** 审计事件类型 → 中文。未知类型原样显示，不吞掉。 */
const AUDIT_LABELS = {
  RUN_CREATED: '创建扫描',
  RUN_RESCANNED: '重新扫描',
  REQUIREMENT_REVIEWED: '复核要求项',
  DECISION_RECORDED: '记录决策',
  METADATA_UPDATED: '更新任务信息',
  RUN_ARCHIVED: '归档',
  RUN_RESTORED: '恢复',
  REMEDIATION_CREATED: '创建整改项',
  REMEDIATION_UPDATED: '更新整改项',
};

async function loadAudit() {
  const target = el('#audit-events');
  const run = store.get().currentRun;
  if (!target || !run) return;

  mount(target, skeleton('line', 3));
  try {
    const { events } = await runsApi.listAudit(run.run_id);
    if (!events.length) {
      mount(target, emptyState({ icon: 'scroll-text', title: '暂无审计记录' }));
      return;
    }
    // 只显示最近 30 条。审计全量导出走报告，不在这里翻页 ——
    // 这个面板的用途是「最近发生了什么」，不是合规归档。
    mount(target, html`
      <ol class="timeline">
        ${events.slice(0, 30).map((item) => html`
          <li class="timeline__item">
            <p class="timeline__head">
              <strong>${AUDIT_LABELS[item.event_type] || item.event_type}</strong>
              <time datetime="${item.created_at}" title="${formatDate(item.created_at)}">
                ${formatRelative(item.created_at)}
              </time>
            </p>
            <small>${displayName(item.user_id)}${item.note ? ` · ${item.note}` : ''}</small>
          </li>
        `)}
      </ol>
      ${events.length > 30
        ? html`<p class="hint" style="padding: var(--space-3) var(--space-4)">
                 另有 ${events.length - 30} 条较早记录，可在导出报告中查看完整审计链。</p>`
        : ''}
    `);
  } catch (error) {
    mount(target, errorState({ title: '审计记录加载失败', error }));
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   整改项
   ═══════════════════════════════════════════════════════════════════════ */

const REMEDIATION_STATUSES = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'WAIVED'];
const REMEDIATION_LABELS = {
  OPEN: '待处理', IN_PROGRESS: '进行中', RESOLVED: '已解决', WAIVED: '已豁免',
};

async function loadRemediations() {
  const target = el('#remediations-list');
  const run = store.get().currentRun;
  if (!target || !run) return;

  mount(target, skeleton('row', 2));
  try {
    const { remediations } = await runsApi.listRemediations(run.run_id);
    renderRemediations(remediations || []);
    fillRequirementOptions(run);
  } catch (error) {
    mount(target, errorState({ title: '整改项加载失败', error }));
  }
}

/** @param {import('../../../types/api.js').Remediation[]} items */
function renderRemediations(items) {
  const target = el('#remediations-list');
  if (!target) return;

  if (!items.length) {
    mount(target, emptyState({
      icon: 'list-todo',
      title: '暂无整改项',
      body: '把需要补材料、找人确认的事项登记在这里，它们会出现在导出报告中。',
    }));
    return;
  }

  mount(target, items.map((item) => html`
    <article class="remediation" data-status="${item.status}">
      <div class="remediation__main">
        <strong>${item.title}</strong>
        <small>
          ${item.requirement_id ? `要求项 ${item.requirement_id} · ` : ''}
          ${item.owner_id ? displayName(item.owner_id) : '未指派'}
          ${item.due_date ? ` · 截止 ${formatDate(item.due_date, { withTime: false })}` : ''}
        </small>
      </div>
      <select class="select" data-remediation-status="${item.remediation_id}"
              aria-label="修改「${item.title}」的状态">
        ${REMEDIATION_STATUSES.map((value) => html`
          <option value="${value}" ${item.status === value ? 'selected' : ''}>
            ${REMEDIATION_LABELS[value]}
          </option>
        `)}
      </select>
    </article>
  `));
}

/**
 * 整改项可以挂在某条要求项上。只列出非 PASS 的 ——
 * 给已满足的要求项建整改项没有意义，把它们放进下拉只会让列表变长。
 *
 * @param {import('../../../types/api.js').Run} run
 */
function fillRequirementOptions(run) {
  const select = el('#remediation-requirement');
  if (!select) return;
  const open = run.requirements.filter((item) => item.status !== 'PASS');
  mount(select, html`
    <option value="">不关联要求项</option>
    ${open.map((item) => html`
      <option value="${item.requirement_id}">${item.label} · ${item.requirement_id}</option>
    `)}
  `);
}

/** @param {Event} event */
async function createRemediation(event) {
  event.preventDefault();
  const run = store.get().currentRun;
  if (!run) return;

  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const data = new FormData(form);
  const title = String(data.get('title') || '').trim();
  if (!title) return;

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      await runsApi.createRemediation(run.run_id, {
        title,
        requirement_id: data.get('requirement_id') || null,
        owner_id: data.get('owner_id') || null,
        due_date: data.get('due_date') || null,
      });
      form.reset();
      await loadRemediations();
      toastSuccess('整改项已创建。');
    } catch (error) {
      toastFromError(error, '整改项未创建。');
    }
  });
}

/**
 * @param {string} remediationId
 * @param {Record<string, unknown>} payload
 * @param {Element} control
 */
async function patchRemediation(remediationId, payload, control) {
  const select = /** @type {HTMLSelectElement} */ (control);
  const previous = select.dataset.previous || '';
  select.disabled = true;
  try {
    await runsApi.updateRemediation(remediationId, payload);
    select.closest('.remediation')?.setAttribute('data-status', String(payload.status));
    select.dataset.previous = select.value;
    toastSuccess('整改项已更新。');
  } catch (error) {
    // 状态没存上就把下拉还原，否则界面在说谎。
    if (previous) select.value = previous;
    toastFromError(error, '状态未更新。');
  } finally {
    select.disabled = false;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   工具
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * user_id → 用户名。审计记录的读者是人，不该看一串 UUID。
 * 成员列表取不到时回退显示 id，不显示空白。
 *
 * @param {string | undefined} userId
 */
function displayName(userId) {
  if (!userId) return '系统';
  const member = store.get().members.find((m) => m.user_id === userId);
  return member?.username || userId;
}

/** @param {string} name */
function initial(name) {
  return name.slice(0, 1).toLocaleUpperCase('zh-CN');
}
