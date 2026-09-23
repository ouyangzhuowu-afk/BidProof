// @ts-check
import { reportDiagnostic } from './telemetry.js';
import { isRecord } from './validators.js';

/** @type {(() => void) | null} */
let dispose = null;

/** Application-wide last resort. Module-level catches remain responsible for write results. */
export function installRuntimeBoundary() {
  if (dispose) return dispose;
  const notices = document.createElement('section');
  notices.className = 'runtime-notices';
  notices.setAttribute('aria-label', '连接与运行状态');
  const offline = document.createElement('p');
  offline.className = 'runtime-notice';
  offline.setAttribute('role', 'status');
  offline.textContent = '网络已断开。已显示的内容仍可查看；保存和扫描需要恢复连接。恢复后不会自动重发操作。';
  const failure = document.createElement('div');
  failure.className = 'runtime-notice runtime-notice--error';
  failure.setAttribute('role', 'alert');
  failure.hidden = true;
  const message = document.createElement('span');
  message.textContent = '界面部分内容未能更新。请先复制未保存的输入，再刷新核实操作结果。';
  const reload = document.createElement('button');
  reload.className = 'btn btn--secondary'; reload.type = 'button'; reload.textContent = '刷新页面';
  reload.addEventListener('click', () => window.location.reload());
  const dismiss = document.createElement('button');
  dismiss.className = 'btn btn--ghost'; dismiss.type = 'button'; dismiss.textContent = '收起提示';
  dismiss.addEventListener('click', () => { failure.hidden = true; });
  failure.append(message, reload, dismiss);
  notices.append(offline, failure);
  document.body.prepend(notices);
  const connectivity = () => { offline.hidden = navigator.onLine !== false; };
  /** @param {unknown} error */
  const unexpected = (error) => {
    if (isRecord(error) && (error.code === 'ABORTED' || error.name === 'AbortError')) return;
    reportDiagnostic(error, { module: 'runtime' });
    failure.hidden = false;
  };
  /** @param {ErrorEvent} event */
  const onError = (event) => { if (event.error) unexpected(event.error); };
  /** @param {PromiseRejectionEvent} event */
  const onRejection = (event) => unexpected(event.reason);
  window.addEventListener('error', onError);
  window.addEventListener('unhandledrejection', onRejection);
  window.addEventListener('online', connectivity);
  window.addEventListener('offline', connectivity);
  connectivity();
  dispose = () => {
    window.removeEventListener('error', onError);
    window.removeEventListener('unhandledrejection', onRejection);
    window.removeEventListener('online', connectivity);
    window.removeEventListener('offline', connectivity);
    notices.remove(); dispose = null;
  };
  return dispose;
}
