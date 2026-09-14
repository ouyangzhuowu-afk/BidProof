/**
 * 轻提示。
 *
 * 旧实现的问题不在样式，在于它对辅助技术完全不存在：
 * 一个普通 div 改 textContent，屏幕阅读器不会播报任何内容 ——
 * 「决策已保存」这种关键确认，键盘/读屏用户根本收不到。
 * 同时它只有一个共享计时器，连续两次操作会让第一条提示被吞掉。
 *
 * 这里：
 *   - 用 role="status" + aria-live 的持久化 live region，内容变更被播报；
 *   - 错误用 assertive，成功用 polite，不抢断用户正在听的内容；
 *   - 每条提示各自计时，最多同时显示 3 条，超出的排队；
 *   - 尊重 prefers-reduced-motion（动画在 CSS 层关掉，这里不需要判断）。
 */

/** @typedef {'info' | 'success' | 'error' | 'undo'} ToastTone */

const MAX_VISIBLE = 3;
// 撤销窗口比普通提示长：用户要先意识到「点错了」，再去找那个按钮。
const DURATION = { info: 4000, success: 4000, error: 8000, undo: 8000 };

/** @type {HTMLElement | null} */
let region = null;
/** @typedef {{ label: string, run: () => void } | null} ToastAction */

/** @type {{ message: string, tone: ToastTone, action: ToastAction }[]} */
const queue = [];
let visible = 0;

function ensureRegion() {
  if (region?.isConnected) return region;
  region = document.createElement('div');
  region.className = 'toast-region';
  // polite：不打断读屏当前朗读。错误项单独用 assertive 的子节点覆盖。
  region.setAttribute('role', 'status');
  region.setAttribute('aria-live', 'polite');
  region.setAttribute('aria-atomic', 'false');
  document.body.append(region);
  return region;
}

/**
 * @param {string} message
 * @param {ToastTone} [tone]
 */
export function toast(message, tone = 'info') {
  push(String(message ?? '').trim(), tone, null);
}

/**
 * 带撤销动作的提示（确认阶梯的 T1）。
 *
 * 用于**完全可逆、且撤销窗口内无副作用**的操作：归档 / 恢复项目。
 * 这类动作用确认对话框是过度设计——它打断的频率远高于它挽回的错误；
 * 但完全不给反馈又会让人不确定自己点没点中。事后撤销是两者之间的正解。
 *
 * 撤销按钮的存在时间就是提示的存在时间（8 秒），
 * 所以调用方的 onUndo 必须是一次幂等的反向请求，不能依赖任何中间状态。
 *
 * @param {string} message
 * @param {{ label?: string, onUndo: () => void }} options
 */
export function toastWithUndo(message, { label = '撤销', onUndo }) {
  push(String(message ?? '').trim(), 'undo', { label, run: onUndo });
}

/**
 * @param {string} text
 * @param {ToastTone} tone
 * @param {ToastAction} action
 */
function push(text, tone, action) {
  if (!text) return;
  if (visible >= MAX_VISIBLE) {
    queue.push({ message: text, tone, action });
    return;
  }
  show(text, tone, action);
}

export const toastSuccess = (/** @type {string} */ m) => toast(m, 'success');
export const toastError = (/** @type {string} */ m) => toast(m, 'error');

/**
 * 从任意 error 生成提示。ApiError 的 message 已是面向用户的文案，
 * 其它异常一律降级为通用文案 —— 不把 `undefined is not a function`
 * 这类内部信息推到用户面前。
 *
 * @param {unknown} error
 * @param {string} [fallback]
 */
export function toastFromError(error, fallback = '操作未完成，请重试。') {
  const message = error instanceof Error && error.name === 'ApiError'
    ? error.message
    : fallback;
  toast(message, 'error');
}

/**
 * @param {string} message
 * @param {ToastTone} tone
 * @param {ToastAction} [action]
 */
function show(message, tone, action = null) {
  visible += 1;
  const node = document.createElement('div');
  node.className = `toast toast--${tone}`;
  // 错误需要立刻被播报，否则用户会以为操作成功了。
  node.setAttribute('aria-live', tone === 'error' ? 'assertive' : 'polite');
  node.setAttribute('aria-atomic', 'true');
  node.textContent = message;

  // 撤销按钮必须是真 <button>：整条提示本来就绑了「点击即关」，
  // 如果把撤销做成点整条，用户想关掉反而会触发撤销。
  if (action) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'toast__action';
    button.textContent = action.label;
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      action.run();
      node.click();
    });
    node.append(button);
  }

  ensureRegion().append(node);

  const dismiss = () => {
    if (!node.isConnected) return;
    node.remove();
    visible -= 1;
    const next = queue.shift();
    if (next) show(next.message, next.tone, next.action);
  };

  const timer = setTimeout(dismiss, DURATION[tone] ?? DURATION.info);
  // 点击即关。长文案的错误提示用户可能来不及读完，也可能想马上清掉。
  node.addEventListener('click', () => { clearTimeout(timer); dismiss(); });
}

/** 路由切换时清空，避免上一页的提示叠在新页面上。 */
export function clearToasts() {
  queue.length = 0;
  region?.replaceChildren();
  visible = 0;
}
