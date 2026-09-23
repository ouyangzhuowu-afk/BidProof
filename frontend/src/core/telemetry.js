// @ts-check
import { isRecord } from './validators.js';

/** @type {import('./contracts.js').DiagnosticSink | null} */
let sink = null;
let release = 'local';
/** @type {Map<string, number>} */
const recent = new Map();
let sent = 0;
let windowStart = Date.now();
const MAX_PER_MINUTE = 10;

/** Only trusted deployment code may install a sink. No vendor SDK/network is enabled by default.
 * @param {import('./contracts.js').DiagnosticSink | null} next
 * @param {{ release?: string }} [options]
 */
export function configureTelemetry(next, options = {}) {
  sink = next;
  release = /^[a-zA-Z0-9._-]{1,64}$/.test(options.release || '') ? String(options.release) : 'local';
  recent.clear(); sent = 0; windowStart = Date.now();
}

/** @param {unknown} error
 * @param {{ module?: import('./contracts.js').TelemetryModule, code?: import('./contracts.js').TelemetryCode, status?: number, requestId?: string }} [context]
 * @returns {Readonly<import('./contracts.js').DiagnosticEvent> | null}
 */
export function reportDiagnostic(error, context = {}) {
  const name = error instanceof Error ? error.name : '';
  const errorType = name === 'TypeError' || name === 'RangeError' || name === 'SyntaxError' || name === 'ApiError' || name === 'Error' ? name : 'Unknown';
  const routes = ['home', 'detail', 'decision', 'jobs', 'admin'];
  const routeName = typeof location === 'undefined' ? '' : location.hash.slice(1).split('/')[0] || 'home';
  const route = routes.includes(routeName) ? /** @type {import('./contracts.js').DiagnosticEvent['route']} */ (routeName) : 'unknown';
  const modules = ['boot', 'runtime', 'network', 'decision', 'collaboration', 'jobs'];
  const codes = ['UNEXPECTED', 'BOOT_FAILED', 'NETWORK', 'TIMEOUT', 'INVALID_RESPONSE', 'SERVER_ERROR'];
  const module = context.module && modules.includes(context.module) ? context.module : 'runtime';
  const code = context.code && codes.includes(context.code) ? context.code : 'UNEXPECTED';
  const status = Number.isInteger(context.status) && Number(context.status) >= 100 && Number(context.status) <= 599 ? Number(context.status) : 0;
  // No message, stack, breadcrumb, URL, user, input, source quote, or filename crosses this boundary.
  const event = /** @type {import('./contracts.js').DiagnosticEvent} */ ({ schema: 1, module, code, error_type: errorType, release, route, status, occurred_at: new Date().toISOString() });
  if (typeof context.requestId === 'string' && /^[a-f0-9-]{16,64}$/i.test(context.requestId)) event.request_id = context.requestId;
  const now = Date.now();
  if (now - windowStart >= 60_000) { sent = 0; recent.clear(); windowStart = now; }
  const fingerprint = `${module}:${code}:${errorType}:${status}:${route}`;
  if (recent.has(fingerprint) || sent >= MAX_PER_MINUTE) return null;
  recent.set(fingerprint, now); sent += 1;
  const safeEvent = Object.freeze(event);
  if (sink) {
    try { Promise.resolve(sink(safeEvent)).catch(() => {}); }
    catch { /* Monitoring must never break the product or recursively report itself. */ }
  }
  return safeEvent;
}

/** Optional same-origin transport, enabled only after deploying a receiving endpoint.
 * @param {string} endpoint @returns {import('./contracts.js').DiagnosticSink}
 */
export function sameOriginSink(endpoint) {
  const url = new URL(endpoint, location.origin);
  if (url.origin !== location.origin || url.username || url.password || url.search || url.hash) throw new Error('监控地址必须为不含查询参数的同源路径。');
  return async (event) => {
    const body = JSON.stringify(event);
    if (body.length > 2048 || !isRecord(event)) return;
    await fetch(url.pathname, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body, keepalive: true, signal: AbortSignal.timeout(3000) });
  };
}
