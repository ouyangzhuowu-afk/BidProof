/**
 * 人工决策页。
 *
 * 这是整个产品唯一一处「人对结果负责」的地方：系统给证据，人做判断，
 * 判断写进审计链。所以这一页的设计原则和别处不同 ——
 * **宁可多一步，不可少一步**。
 *
 * 从 app.js 搬出时改的：
 *
 *   1. 未解决要求项原本是 <select multiple size="7">，提示「按 Ctrl / Cmd 可多选」。
 *      这是整个产品最重要的一次输入，却用了 Web 上最容易误操作的控件：
 *      点一下就会清空之前所有选择，触屏上几乎无法多选，读屏支持也差。
 *      改为复选框列表 —— 多占一点竖向空间，换来不会选错。
 *
 *   2. 「停止投标」原本和其它两项一样，点一下直接保存。
 *      它意味着放弃一个投标机会，现在加二次确认。
 *
 *   3. 保存成功后原本直接跳回详情页，用户看不到自己刚存了什么。
 *      现在留在原页并给出明确成功反馈，跳转交给用户自己决定。
 *
 *   4. 错误只写在一个 <span> 里，读屏虽有 aria-live 但视觉上极不显眼。
 *      改为 callout，并把焦点移到错误处。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount } from '../../ui/render.js';
import { toastSuccess, toastFromError } from '../../core/toast.js';
import { statusLabel, decisionLabel, formatDate } from '../../core/format.js';
import { runsApi } from '../../api/index.js';
import { confirmAction } from '../../ui/confirm.js';

/** @typedef {import('../../../types/api.js').Run} Run */

/** @type {(() => void)[]} */
let teardown = [];

export function mountDecisionView() {
  if (teardown.length) return;
  teardown = [
    bind('#decision-form', 'submit', (event) => { void submit(event); }),
    // 选中数量要实时反映在标题上，否则用户滚到下面就忘了勾了几个。
    delegate('#unresolved-items', 'change', 'input[type="checkbox"]', updateSelectedCount),
  ];
  render();
}

export function unmountDecisionView() {
  for (const off of teardown) off();
  teardown = [];
}

/* ═══════════════════════════════════════════════════════════════════════════
   渲染
   ═══════════════════════════════════════════════════════════════════════ */

export function render() {
  const run = store.get().currentRun;
  if (!run) return;

  renderContext(run);
  renderUnresolved(run);

  // 回填已有决策。没有决策时默认落在 HOLD ——
  // 默认值不该是 CONTINUE（等于替用户做了乐观判断），也不该是 STOP。
  const current = run.decision?.decision || 'HOLD';
  const radio = /** @type {HTMLInputElement | null} */ (
    el(`#decision-form input[name="decision"][value="${current}"]`)
  );
  if (radio) radio.checked = true;

  const note = /** @type {HTMLTextAreaElement | null} */ (el('#decision-note'));
  if (note) note.value = run.decision?.note || '';

  clearError();
}

/** @param {Run} run */
function renderContext(run) {
  const target = el('#decision-context-content');
  if (!target) return;

  mount(target, html`
    <div class="decision-context">
      <div class="context-metric" data-tone="danger" data-nonzero="${String(run.blocker_count > 0)}">
        <strong>${run.blocker_count}</strong><span>资格 / 废标风险</span>
      </div>
      <div class="context-metric" data-tone="warning" data-nonzero="${String(run.unresolved_count > 0)}">
        <strong>${run.unresolved_count}</strong><span>未解决要求</span>
      </div>
      <div class="context-metric">
        <strong>${run.requirement_count}</strong><span>全部要求项</span>
      </div>
    </div>

    ${run.blocker_count > 0
      ? html`
        <p class="callout" data-tone="danger">
          <i data-lucide="shield-alert"></i>
          <span>存在 ${run.blocker_count} 项资格或废标风险尚未满足。
                选择「继续投标」前请确认这些风险已有处置方案。</span>
        </p>`
      : ''}

    ${run.decision?.decision
      ? html`
        <p class="callout" data-tone="info">
          <i data-lucide="history"></i>
          <span>上次决策：<strong>${decisionLabel(run.decision.decision)}</strong>
                ${run.decision.decided_at ? ` · ${formatDate(run.decision.decided_at)}` : ''}
                ${run.decision.decided_by ? ` · ${run.decision.decided_by}` : ''}<br>
                保存新决策会覆盖它，但两次记录都会留在审计链中。</span>
        </p>`
      : html`
        <p class="hint">尚未记录人工决定。请先核对高风险项与证据缺口。</p>`}
  `);
}

/**
 * 未解决要求项清单。
 *
 * 语义：勾选 = 「我知道这一项还没解决，并且我的决策已经把它考虑在内」。
 * 不是「要处理它」，所以默认不全选。
 *
 * @param {Run} run
 */
function renderUnresolved(run) {
  const target = el('#unresolved-items');
  if (!target) return;

  const items = run.requirements.filter((item) => ['UNKNOWN', 'NEEDS_REVIEW'].includes(item.status));
  const acknowledged = new Set(run.decision?.unresolved_requirement_ids || []);

  if (!items.length) {
    mount(target, html`
      <p class="callout" data-tone="ok">
        <i data-lucide="check-check"></i>
        <span>所有要求项都已有确定结论，无需在此勾选。</span>
      </p>
    `);
    updateSelectedCount();
    return;
  }

  mount(target, html`
    <div class="ack-list" role="group" aria-labelledby="unresolved-label">
      ${items.map((item) => html`
        <label class="ack" data-status="${item.status}">
          <input type="checkbox" name="unresolved_requirement_ids"
                 value="${item.requirement_id}" ${acknowledged.has(item.requirement_id) ? 'checked' : ''}>
          <span class="ack__body">
            <span class="ack__head">
              <strong>${item.label}</strong>
              <span class="verdict verdict--${item.status}">${statusLabel(item.status)}</span>
            </span>
            <small>${item.title}</small>
          </span>
        </label>
      `)}
    </div>
  `);
  updateSelectedCount();
}

function updateSelectedCount() {
  const badge = el('#unresolved-count');
  if (!badge) return;
  const total = document.querySelectorAll('#unresolved-items input[type="checkbox"]').length;
  const picked = document.querySelectorAll('#unresolved-items input:checked').length;
  badge.textContent = total ? `已确认 ${picked} / ${total} 项` : '';
}

/* ═══════════════════════════════════════════════════════════════════════════
   提交
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {Event} event */
async function submit(event) {
  event.preventDefault();
  const run = store.get().currentRun;
  if (!run) return;

  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const data = new FormData(form);
  const decision = String(data.get('decision') || '');
  const note = String(data.get('note') || '').trim();
  const unresolved = data.getAll('unresolved_requirement_ids').map(String);

  // 停止投标意味着放弃一个机会。它和另外两项不是同一量级的动作。
  if (decision === 'STOP') {
    const ok = await confirmAction({
      title: '记录「停止投标」',
      body: '这会作为正式结论写入审计链。如果只是需要更多时间或材料，'
        + '应当选择「暂缓处理」而不是停止。',
      confirmLabel: '记录停止投标',
      cancelLabel: '再想想',
      tone: 'danger',
    });
    if (!ok) return;
  }

  // 说明不是必填字段（后端不要求），但空说明的决策在审计上没有价值。
  // 用提示而非阻断 —— 强制填写只会催生「同意」两个字。
  if (!note && decision !== 'HOLD') {
    const ok = await confirmAction({
      title: '决策说明为空',
      body: '审计时无法还原这次判断的依据。仍然保存吗？',
      confirmLabel: '不填写，直接保存',
      cancelLabel: '返回填写',
    });
    if (!ok) {
      /** @type {HTMLTextAreaElement | null} */ (el('#decision-note'))?.focus();
      return;
    }
  }

  const button = form.querySelector('button[type="submit"]');
  clearError();

  await withLoading(button, async () => {
    try {
      const updated = await runsApi.saveDecision(run.run_id, {
        decision,
        note,
        unresolved_requirement_ids: unresolved,
      });
      store.set({ currentRun: updated });
      // 停在本页并重渲染，用户能看见自己刚存进去的东西。
      // 旧实现直接跳回详情页，保存结果不可见，只能靠一句 toast。
      render();
      toastSuccess(`已记录「${decisionLabel(decision)}」。`);
    } catch (error) {
      showError(error);
    }
  });
}

/** @param {unknown} error */
function showError(error) {
  const target = el('#decision-message');
  if (!target) { toastFromError(error, '决策未保存。'); return; }
  mount(target, html`
    <p class="callout" data-tone="danger" tabindex="-1" id="decision-error">
      <i data-lucide="triangle-alert"></i>
      <span>${error instanceof Error ? error.message : '未知错误'}，决策未保存，请重试。</span>
    </p>
  `);
  // 把焦点移到错误处：表单很长，提交按钮在底部，
  // 错误若渲染在别处，键盘与读屏用户不会知道发生了什么。
  /** @type {HTMLElement | null} */ (el('#decision-error'))?.focus();
}

function clearError() {
  const target = el('#decision-message');
  if (target) mount(target, '');
}
