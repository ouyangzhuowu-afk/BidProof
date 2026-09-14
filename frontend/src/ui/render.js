/**
 * 渲染层。由 escape.js 演进而来，保留原有的 html / raw / toHtml 契约
 * （标签模板默认转义，只有 raw() 标记过的内容才原样输出），并补上两件事：
 *
 *   1. mount() 在插入 DOM 后只对**刚插入的子树**渲染图标，
 *      取代旧版 24 处全文档 lucide.createIcons() 扫描。
 *   2. 空 / 加载 / 失败三态有各自的结构化渲染函数，
 *      而不是到处拼 `<div class="empty-state error-text">${e.message}，xxx失败</div>`。
 */

import { renderIcons } from '../core/icons.js';
import { t } from '../i18n/index.js';

/**
 * @typedef {object} SafeHtml
 * @property {true} __safe
 * @property {string} value
 */

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };

/** @param {unknown} value */
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[/** @type {keyof ESCAPES} */ (ch)]);
}

/**
 * 标记一段字符串为「已经是安全 HTML」。
 * 只应传入本模块自己生成的内容，绝不能传入 element.innerHTML 读回来的值。
 * @param {unknown} value
 * @returns {SafeHtml}
 */
export function raw(value) {
  return { __safe: true, value: String(value ?? '') };
}

/** @param {unknown} value */
export function toHtml(value) {
  if (value == null || value === false) return '';
  if (Array.isArray(value)) return value.map(toHtml).join('');
  if (typeof value === 'object' && /** @type {SafeHtml} */ (value).__safe) {
    return /** @type {SafeHtml} */ (value).value;
  }
  return escapeHtml(value);
}

/**
 * @param {TemplateStringsArray} strings
 * @param {...unknown} values
 * @returns {SafeHtml}
 */
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i += 1) out += toHtml(values[i]) + strings[i + 1];
  return raw(out);
}

/**
 * 写入内容并渲染该子树内的图标。
 * 业务代码只调用这个函数，永远不直接碰 innerHTML（eslint 会拦）。
 * @param {Element | null} element
 * @param {unknown} content
 */
export function mount(element, content) {
  if (!element) return;
  element.innerHTML = toHtml(content);
  renderIcons(element);
}

/**
 * 替换子节点（保留已构造好的 DOM，不走字符串）。
 * @param {Element | null} element
 * @param {Node[]} nodes
 */
export function mountNodes(element, nodes) {
  if (!element) return;
  element.replaceChildren(...nodes);
  renderIcons(element);
}

/** 拒绝 javascript: / data: / vbscript: 等协议。 */
export function safeUrl(value) {
  const text = String(value ?? '').trim();
  if (!text) return '#';
  const lowered = text.toLowerCase();
  if (/^(javascript|data|vbscript|file):/.test(lowered)) return '#';
  return text;
}

// ---------------------------------------------------------------- 三态

/**
 * 空状态：一句说明 + 一个动作。空屏是邀请，不是讣告。
 * @param {object} spec
 * @param {string} spec.icon
 * @param {string} spec.title
 * @param {string} [spec.body]
 * @param {{ label: string, id: string }} [spec.action]
 */
export function emptyState({ icon, title, body = '', action }) {
  return html`<div class="state">
    <span class="state__icon" data-lucide="${icon}" data-icon-size="20"></span>
    <p class="state__title">${title}</p>
    <p class="state__body">${body}</p>
    ${action ? html`<button class="btn btn--secondary" type="button" id="${action.id}">${action.label}</button>` : ''}
  </div>`;
}

/**
 * 失败状态：说清楚发生了什么、下一步做什么，并给一个重试入口。
 * 保留服务端原文（error.message 来自后端 detail），不改写、不吞掉。
 * @param {object} spec
 * @param {string} spec.title
 * @param {Error} spec.error
 * @param {string} [spec.retryId]
 */
export function errorState({ title, error, retryId }) {
  return html`<div class="state state--error" role="alert">
    <span class="state__icon" data-lucide="triangle-alert" data-icon-size="20"></span>
    <p class="state__title">${title}</p>
    <p class="state__body">${error.message}</p>
    ${retryId ? html`<button class="btn btn--secondary" type="button" id="${retryId}">${t('error.retry')}</button>` : ''}
  </div>`;
}

/**
 * 加载状态：骨架的形状要像即将出现的内容，否则内容一到就是一次布局跳动（CLS）。
 * @param {'row' | 'card' | 'line'} shape
 * @param {number} count
 */
export function skeleton(shape, count = 3) {
  return raw(`<div class="skeleton skeleton--${shape}"></div>`.repeat(count));
}
