/**
 * DOM 访问层。
 *
 * 解决旧实现的 P0：app.js 在模块顶层直接执行 293 处
 * `document.querySelector('#x').addEventListener(...)`。任何一个 id 在 HTML 里
 * 被改名或删除，整个脚本在第一条语句就抛 TypeError，用户看到的是白屏，
 * 控制台里只有一行 "Cannot read properties of null"。
 *
 * 这里的规则：
 *   - el()   找不到返回 null，开发期打一条明确警告，生产期静默。
 *   - must() 用于确实缺了就没法继续的骨架节点，抛出可读错误。
 *   - bind() 找不到元素时跳过绑定而不是崩溃，其它功能继续可用。
 */

const isDev = import.meta.env?.DEV ?? false;

/** @type {Map<string, Element>} */
const cache = new Map();

/**
 * 按选择器取元素，带缓存。
 * @template {Element} T
 * @param {string} selector
 * @param {ParentNode} [root]
 * @returns {T | null}
 */
export function el(selector, root) {
  if (root) return /** @type {T | null} */ (root.querySelector(selector));
  const cached = cache.get(selector);
  if (cached?.isConnected) return /** @type {T} */ (cached);
  const found = document.querySelector(selector);
  if (found) cache.set(selector, found);
  else if (isDev) console.warn(`[dom] 未找到元素：${selector}`);
  return /** @type {T | null} */ (found);
}

/**
 * @template {Element} T
 * @param {string} selector
 * @param {ParentNode} [root]
 * @returns {T}
 */
export function must(selector, root) {
  const found = el(selector, root);
  if (!found) throw new Error(`[dom] 缺少必需节点：${selector}`);
  return /** @type {T} */ (found);
}

/**
 * @param {string} selector
 * @param {ParentNode} [root]
 * @returns {Element[]}
 */
export function all(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

/**
 * 绑定事件。元素不存在时跳过，不中断后续绑定。
 * @param {string | EventTarget | null} target
 * @param {string} type
 * @param {(event: any) => void} handler
 * @param {AddEventListenerOptions} [options]
 * @returns {() => void} 解绑
 */
export function bind(target, type, handler, options) {
  const node = typeof target === 'string' ? el(target) : target;
  if (!node || typeof node.addEventListener !== 'function') return () => {};
  node.addEventListener(type, handler, options);
  return () => node.removeEventListener(type, handler, options);
}

/**
 * 事件委托。列表渲染后不再需要逐行 addEventListener——
 * 旧实现每次 loadJobs()/loadMembers() 都会重新遍历绑定几十个监听器。
 *
 * @param {string | Element | null} container
 * @param {string} type
 * @param {string} selector
 * @param {(event: Event, matched: Element) => void} handler
 * @returns {() => void}
 */
export function delegate(container, type, selector, handler) {
  return bind(container, type, (event) => {
    const target = /** @type {Element | null} */ (event.target);
    const matched = target?.closest(selector);
    if (matched && (typeof container === 'string' ? el(container) : container)?.contains(matched)) {
      handler(event, matched);
    }
  });
}

/**
 * 按钮加载态。
 *
 * 旧实现把 button.innerHTML 存进 dataset 再用 raw() 还原，等于把一段已渲染的
 * DOM 字符串当作可信 HTML 重新注入——只要按钮里曾经渲染过用户提供的文本
 * （成员名、项目名、文件名），就是一条自我 XSS 通道。
 * 这里改成纯 CSS 驱动：只切 data-loading，DOM 结构一个字都不动。
 *
 * @param {Element | null} button
 * @param {boolean} loading
 */
export function setLoading(button, loading) {
  if (!(button instanceof HTMLButtonElement)) return;
  button.dataset.loading = String(loading);
  button.disabled = loading;
  button.setAttribute('aria-busy', String(loading));
}

/**
 * 执行一次带按钮加载态的异步动作。把 try/finally 收敛到一处——
 * 旧实现有 18 处结构完全相同的 setButtonLoading(true) … finally(false)。
 *
 * @template T
 * @param {Element | null} button
 * @param {() => Promise<T>} action
 * @returns {Promise<T>}
 */
export async function withLoading(button, action) {
  setLoading(button, true);
  try {
    return await action();
  } finally {
    setLoading(button, false);
  }
}

/**
 * 把 dialog 的焦点管理补齐：打开时聚焦首个可聚焦控件，关闭后归还焦点。
 * 原生 <dialog> 会做焦点陷阱，但不会把焦点还给触发者，
 * 键盘用户关闭弹窗后会掉回文档开头。
 *
 * @param {HTMLDialogElement | null} dialog
 * @param {string} [initialFocus] 选择器
 */
export function openDialog(dialog, initialFocus) {
  if (!dialog || dialog.open) return;
  const opener = /** @type {HTMLElement | null} */ (document.activeElement);
  dialog.showModal();
  const focusTarget = initialFocus
    ? el(initialFocus, dialog)
    : el('input:not([type=hidden]), select, textarea, button', dialog);
  /** @type {HTMLElement | null} */ (focusTarget)?.focus();
  dialog.addEventListener('close', () => opener?.focus?.(), { once: true });
}

/** @param {HTMLDialogElement | null} dialog */
export function closeDialog(dialog) {
  if (dialog?.open) dialog.close();
}

/**
 * 缓存失效。HTML 骨架被整段替换时调用（目前只有主题/语言切换会触发）。
 */
export function resetDomCache() {
  cache.clear();
}
