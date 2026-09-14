/**
 * 确认对话框原语。
 *
 * 取代 app.js 里的 confirmDanger()，并把散在各处的 window.confirm 收进来。
 *
 * 旧实现（app.js:432）有三个问题，这里逐一修掉：
 *
 *   1. **按 Esc 会让 Promise 永不 settle。** <dialog> 原生支持 Esc 关闭，
 *      但那条路径不经过 done()，于是 `await confirmDanger(...)` 永久挂起，
 *      调用方的按钮 loading 态永远不消失，两个监听器也留在 DOM 上。
 *      用户看到的是「点了取消，按钮卡住了」。
 *      现在唯一的 settle 出口是 dialog 的 close 事件 —— Esc、点背景、
 *      点按钮全都会触发它，不存在漏网路径。
 *
 *   2. **确认词输错等同于取消。** 旧实现是 `done(input.value === confirmWord)`，
 *      输错直接把对话框关掉且不给反馈。用户会以为确认成功了，实际什么都没发生。
 *      现在改为实时校验：不匹配时确认按钮 disabled，根本无法提交。
 *
 *   3. **关闭后焦点掉回文档开头。** 改用 core/dom.js 的 openDialog()，
 *      它会把焦点还给触发元素。
 *
 * 另外：对话框 DOM 由本模块自己创建，不再依赖 static/index.html 里的
 * #confirm-panel。理由是这个原语要能被任意视图调用，包括那些还没迁移、
 * 甚至将来不存在的页面 —— 依赖外部标记等于给它绑了一个隐式前置条件。
 */

import { openDialog } from '../core/dom.js';
import { html, mount } from './render.js';

/** @type {HTMLDialogElement | null} */
let dialog = null;

/**
 * 一次确认（T2）。用于「有后果但可恢复，或影响他人」的操作：
 * 停用成员、踢会话、取消作业、记录停止投标。
 *
 * @param {object} options
 * @param {string} options.title
 * @param {string} options.body            说明。必须写清后果，且**带上数字**
 * @param {string} [options.confirmLabel]  确认按钮文案。用动词，不要用「确定」
 * @param {string} [options.cancelLabel]
 * @param {'danger' | 'neutral'} [options.tone]
 * @returns {Promise<boolean>}
 */
export function confirmAction({
  title, body, confirmLabel = '确认', cancelLabel = '取消', tone = 'neutral',
}) {
  return open({ title, body, confirmLabel, cancelLabel, tone, word: null });
}

/**
 * 确认词确认（T3）。用于**不可逆且销毁数据**的操作：
 * 批量删除、留存清理、撤销全部会话、撤销 API 令牌。
 *
 * 关于 word 取什么值：**不要一律用 DELETE。**
 * 确认词的全部意义是打断肌肉记忆，统一成一个词之后用户第三次就闭着眼睛敲了。
 * 删对象时就用对象的名字（令牌名、项目名），批量操作用一个描述动作的词（PURGE）。
 *
 * @param {object} options
 * @param {string} options.title
 * @param {string} options.body
 * @param {string} options.word            要求用户逐字输入的词
 * @param {string} [options.confirmLabel]
 * @param {string} [options.cancelLabel]
 * @returns {Promise<boolean>}
 */
export function confirmWithWord({
  title, body, word, confirmLabel = '永久删除', cancelLabel = '取消',
}) {
  return open({ title, body, confirmLabel, cancelLabel, tone: 'danger', word });
}

/* ═══════════════════════════════════════════════════════════════════════════
   实现
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * @param {{ title: string, body: string, confirmLabel: string,
 *           cancelLabel: string, tone: 'danger' | 'neutral', word: string | null }} options
 * @returns {Promise<boolean>}
 */
function open(options) {
  const node = ensureDialog();
  // 同一时刻只允许一个确认。并发调用直接拒绝，
  // 而不是把上一个挤掉 —— 后者会让上一个调用方拿到一个它没等到的答案。
  if (node.open) return Promise.resolve(false);

  node.dataset.tone = options.tone;
  mount(node, body(options));

  const confirmButton = /** @type {HTMLButtonElement} */ (node.querySelector('[data-confirm-ok]'));
  const cancelButton = /** @type {HTMLButtonElement} */ (node.querySelector('[data-confirm-cancel]'));
  const input = /** @type {HTMLInputElement | null} */ (node.querySelector('[data-confirm-word]'));

  // 需要确认词时，按钮起始就是禁用的 —— 用户看得到「还差一步」。
  if (input) confirmButton.disabled = true;

  return new Promise((resolve) => {
    let answer = false;

    const validate = () => {
      // 允许首尾空白：从密码管理器或聊天窗口粘贴几乎必然带空格，
      // 因为一个看不见的字符而拒绝用户，只会让人以为功能坏了。
      confirmButton.disabled = input.value.trim() !== options.word;
    };

    const onConfirm = () => {
      if (confirmButton.disabled) return;
      answer = true;
      node.close();
    };

    input?.addEventListener('input', validate);
    confirmButton.addEventListener('click', onConfirm);
    cancelButton.addEventListener('click', () => node.close());

    // 唯一的 settle 出口。Esc、点背景、点任意按钮最终都走到这里，
    // 所以不存在「Promise 永不 settle」的路径 —— 这正是旧实现的 bug。
    node.addEventListener('close', () => {
      input?.removeEventListener('input', validate);
      confirmButton.removeEventListener('click', onConfirm);
      mount(node, '');
      resolve(answer);
    }, { once: true });

    // 有确认词时聚焦输入框，否则聚焦取消 ——
    // 危险操作的默认焦点不该落在「确认」上。
    openDialog(node, input ? '[data-confirm-word]' : '[data-confirm-cancel]');
  });
}

/** @param {{ title: string, body: string, confirmLabel: string, cancelLabel: string, word: string | null }} o */
function body(o) {
  return html`
    <form method="dialog" class="confirm">
      <div class="confirm__head">
        <span class="confirm__icon"><i data-lucide="triangle-alert" aria-hidden="true"></i></span>
        <div class="confirm__text">
          <h2 class="title-section" id="confirm-title">${o.title}</h2>
          <p>${o.body}</p>
        </div>
      </div>

      ${o.word
        ? html`
          <p class="field">
            <label for="confirm-word-input">
              输入 <strong class="confirm__word">${o.word}</strong> 以确认
            </label>
            <input class="input" id="confirm-word-input" data-confirm-word type="text"
                   autocomplete="off" autocapitalize="off" spellcheck="false"
                   aria-describedby="confirm-title">
          </p>`
        : ''}

      <div class="confirm__actions">
        <button class="btn btn--ghost" type="button" data-confirm-cancel>${o.cancelLabel}</button>
        <button class="btn btn--danger" type="button" data-confirm-ok>${o.confirmLabel}</button>
      </div>
    </form>
  `;
}

function ensureDialog() {
  if (dialog?.isConnected) return dialog;
  dialog = document.createElement('dialog');
  // 复用 base.css 的 .dialog 原语（尺寸、圆角、阴影、backdrop、入场动画），
  // .confirm-dialog 只收窄宽度。浮层样式不该有第二套实现。
  dialog.className = 'dialog confirm-dialog';
  dialog.setAttribute('aria-labelledby', 'confirm-title');
  document.body.append(dialog);
  return dialog;
}
