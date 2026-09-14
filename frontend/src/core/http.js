/**
 * BidProof API 客户端。
 *
 * 对外契约完全不变（这是硬约束）：
 *   - 路径、方法、请求体字段、查询参数一律沿用旧实现。
 *   - 凭证：credentials: 'same-origin'。
 *   - CSRF：从 cookie `bidproof_csrf` 读取，写入 `X-CSRF-Token` 头。
 *   - 错误：服务端在 JSON 里返回 `detail`，非 JSON 时用响应文本。
 *   - 401（非 /api/auth/ 路径）触发重新登录。
 *
 * 相对旧实现新增的能力：
 *   - ApiError 保留 status / code / detail / url，调用方不再靠中文字符串判断错误类型。
 *   - 超时与取消（AbortSignal），默认 30s；上传与导出单独配置。
 *   - 幂等请求（GET/HEAD）在网络错误与 502/503/504 上指数退避重试。
 *   - 并发去重：同一 GET 在飞行中不会发第二次。
 *   - 401 处理通过 onUnauthorized 注入，http 层不认识 UI。
 */

/** @typedef {import('../../types/api.js').ApiErrorShape} ApiErrorShape */

const CSRF_COOKIE = 'bidproof_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const AUTH_PATH_PREFIX = '/api/auth/';

const DEFAULT_TIMEOUT_MS = 30_000;
/** 上传要走文件解析，后端本身就慢，不能用默认超时掐断。 */
export const UPLOAD_TIMEOUT_MS = 10 * 60_000;
export const EXPORT_TIMEOUT_MS = 3 * 60_000;

const RETRYABLE_STATUS = new Set([502, 503, 504]);
const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD']);

/** 业务错误。带上状态码后，调用方可以按错误类型而不是按文案分支。 */
export class ApiError extends Error {
  /**
   * @param {object} init
   * @param {string} init.message  面向用户的文案（服务端 detail 优先）
   * @param {number} init.status   HTTP 状态码；0 表示请求根本没发出去
   * @param {string} init.url
   * @param {string} [init.code]   服务端业务错误码（若返回）
   * @param {unknown} [init.payload]
   */
  constructor({ message, status, url, code, payload }) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
    this.code = code ?? '';
    this.payload = payload;
  }

  /** 网络不可达 / 超时 / 被取消，而不是服务端拒绝。 */
  get isNetwork() { return this.status === 0; }
  get isTimeout() { return this.code === 'TIMEOUT'; }
  get isAborted() { return this.code === 'ABORTED'; }
  get isUnauthorized() { return this.status === 401; }
  get isForbidden() { return this.status === 403; }
  get isConflict() { return this.status === 409; }
  get isServer() { return this.status >= 500; }
}

/** @type {(() => void) | null} */
let unauthorizedHandler = null;

/**
 * 注册 401 回调。UI 层在启动时注入一次，http 层因此不需要 import 任何视图。
 * @param {() => void} handler
 */
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

function csrfToken() {
  const row = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${CSRF_COOKIE}=`));
  return row ? decodeURIComponent(row.slice(CSRF_COOKIE.length + 1)) : '';
}

/**
 * @param {RequestInit} [options]
 * @returns {RequestInit}
 */
function withCredentials(options = {}) {
  const token = csrfToken();
  return {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(token ? { [CSRF_HEADER]: token } : {}),
      ...(options.headers || {}),
    },
  };
}

/**
 * 组合外部 signal 与超时 signal。AbortSignal.any 在 Safari 17 以下缺失，
 * 所以这里做了显式回退，避免旧 Mac 上整条链路静默失效。
 * @param {AbortSignal | undefined} external
 * @param {number} timeoutMs
 */
function buildSignal(external, timeoutMs) {
  const timeout = AbortSignal.timeout(timeoutMs);
  if (!external) return { signal: timeout, dispose: () => {} };
  if (typeof AbortSignal.any === 'function') {
    return { signal: AbortSignal.any([external, timeout]), dispose: () => {} };
  }
  const controller = new AbortController();
  const forward = (/** @type {Event} */ event) => {
    controller.abort(/** @type {AbortSignal} */ (event.target).reason);
  };
  external.addEventListener('abort', forward, { once: true });
  timeout.addEventListener('abort', forward, { once: true });
  return {
    signal: controller.signal,
    dispose: () => external.removeEventListener('abort', forward),
  };
}

/**
 * @param {Response} response
 * @returns {Promise<{ detail?: string, code?: string, [k: string]: unknown }>}
 */
async function readPayload(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    try {
      return await response.json();
    } catch {
      return { detail: '' };
    }
  }
  return { detail: await response.text() };
}

/** FastAPI / Pydantic 校验字段 → 中文标签。 */
const VALIDATION_FIELD_LABELS = {
  username: '用户名',
  password: '密码',
  workspace_name: '企业名称',
  bootstrap_token: '初始化令牌',
  join_code: '试用加入码',
  display_name: '空间名称',
  current_password: '当前密码',
  new_password: '新密码',
  mfa_token: '二次验证令牌',
  code: '验证码',
};

/**
 * 把 FastAPI 的 detail（字符串或校验错误数组）收成一句可读中文。
 * 旧实现只认 string，校验失败时用户只能看到「请求失败（422）」。
 *
 * @param {unknown} detail
 * @returns {string}
 */
export function formatErrorDetail(detail) {
  if (typeof detail === 'string' && detail.trim()) return detail.trim();
  if (!Array.isArray(detail) || detail.length === 0) return '';

  const messages = [];
  for (const item of detail) {
    if (typeof item === 'string' && item.trim()) {
      messages.push(item.trim());
      continue;
    }
    if (!item || typeof item !== 'object') continue;
    const entry = /** @type {{ loc?: unknown[], msg?: string, type?: string, ctx?: { min_length?: number, max_length?: number } }} */ (item);
    const field = Array.isArray(entry.loc)
      ? entry.loc.filter((part) => part !== 'body' && typeof part === 'string').at(-1)
      : '';
    const label = (typeof field === 'string' && VALIDATION_FIELD_LABELS[field]) || field || '';
    let msg = typeof entry.msg === 'string' ? entry.msg.replace(/^Value error,\s*/i, '').trim() : '';

    if (entry.type === 'string_too_short' && entry.ctx?.min_length) {
      msg = `至少 ${entry.ctx.min_length} 个字符`;
    } else if (entry.type === 'string_too_long' && entry.ctx?.max_length) {
      msg = `最多 ${entry.ctx.max_length} 个字符`;
    } else if (entry.type === 'missing') {
      msg = '不能为空';
    }

    if (!msg) continue;
    messages.push(label ? `${label}：${msg}` : msg);
  }

  // 去重：同一字段偶发重复条目
  return [...new Set(messages)].join('；');
}

/**
 * @param {Response} response
 * @param {string} url
 * @param {unknown} payload
 */
function toApiError(response, url, payload) {
  const body = /** @type {Record<string, unknown>} */ (payload || {});
  const detail = formatErrorDetail(body.detail) || `请求失败（${response.status}）`;
  return new ApiError({
    message: detail,
    status: response.status,
    url,
    code: typeof body.code === 'string' ? body.code : '',
    payload,
  });
}

function handleUnauthorized(url, status) {
  if (status === 401 && !url.startsWith(AUTH_PATH_PREFIX) && unauthorizedHandler) {
    unauthorizedHandler();
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** @type {Map<string, Promise<unknown>>} */
const inFlight = new Map();

/**
 * @typedef {object} RequestOptions
 * @property {string} [method]
 * @property {BodyInit | null} [body]
 * @property {Record<string, string>} [headers]
 * @property {AbortSignal} [signal]
 * @property {number} [timeoutMs]
 * @property {number} [retries]   仅对幂等方法生效
 * @property {boolean} [dedupe]   同一 GET 并发去重，默认 true
 */

/**
 * 发送请求并解析 JSON。契约与旧的 request() 一致：成功返回 payload，失败抛错。
 *
 * @template T
 * @param {string} url
 * @param {RequestOptions} [options]
 * @returns {Promise<T>}
 */
export async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const idempotent = IDEMPOTENT_METHODS.has(method);
  const dedupe = options.dedupe !== false && idempotent && !options.signal;

  if (dedupe && inFlight.has(url)) {
    return /** @type {Promise<T>} */ (inFlight.get(url));
  }

  const run = executeJson(url, method, idempotent, options);
  if (dedupe) {
    inFlight.set(url, run);
    run.finally(() => inFlight.delete(url));
  }
  return /** @type {Promise<T>} */ (run);
}

/**
 * @param {string} url
 * @param {string} method
 * @param {boolean} idempotent
 * @param {RequestOptions} options
 */
async function executeJson(url, method, idempotent, options) {
  const maxAttempts = idempotent ? (options.retries ?? 2) + 1 : 1;
  let lastError;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const response = await send(url, method, options);
      if (response.ok) return await readPayload(response);

      const payload = await readPayload(response);
      handleUnauthorized(url, response.status);
      const error = toApiError(response, url, payload);

      if (idempotent && RETRYABLE_STATUS.has(response.status) && attempt < maxAttempts - 1) {
        lastError = error;
        await sleep(backoff(attempt));
        continue;
      }
      throw error;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.isAborted) throw error;
        lastError = error;
        if (!idempotent || attempt === maxAttempts - 1) throw error;
        await sleep(backoff(attempt));
        continue;
      }
      throw error;
    }
  }
  throw lastError;
}

const backoff = (attempt) => Math.min(4000, 400 * 2 ** attempt) + Math.random() * 200;

/**
 * @param {string} url
 * @param {string} method
 * @param {RequestOptions} options
 * @returns {Promise<Response>}
 */
async function send(url, method, options) {
  const { signal, dispose } = buildSignal(
    options.signal,
    options.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );
  try {
    return await fetch(url, withCredentials({
      method,
      body: options.body,
      headers: options.headers,
      signal,
    }));
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError';
    const timedOut = error instanceof DOMException && error.name === 'TimeoutError';
    throw new ApiError({
      message: timedOut
        ? '请求超时，服务可能仍在处理。稍后刷新查看结果。'
        : aborted
          ? '请求已取消。'
          : '无法连接服务，请检查网络后重试。',
      status: 0,
      url,
      code: timedOut ? 'TIMEOUT' : aborted ? 'ABORTED' : 'NETWORK',
    });
  } finally {
    dispose();
  }
}

/**
 * JSON body 的语法糖。仅此一处设置 Content-Type，
 * 旧实现里这一行被复制了 30 多遍。
 *
 * @template T
 * @param {string} url
 * @param {'POST'|'PATCH'|'PUT'|'DELETE'} method
 * @param {unknown} [body]
 * @param {RequestOptions} [options]
 * @returns {Promise<T>}
 */
export function json(url, method, body, options = {}) {
  return request(url, {
    ...options,
    method,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/**
 * 成功路径是二进制下载的接口。鉴权与错误处理与 request() 完全一致。
 * @param {string} url
 * @param {RequestOptions} [options]
 * @returns {Promise<Response>}
 */
export async function requestBlob(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const response = await send(url, method, {
    ...options,
    timeoutMs: options.timeoutMs ?? EXPORT_TIMEOUT_MS,
  });
  if (!response.ok) {
    const payload = await readPayload(response);
    handleUnauthorized(url, response.status);
    throw toApiError(response, url, payload);
  }
  return response;
}

/**
 * 触发一次浏览器下载并清理 object URL。
 * 旧实现有三处重复的 createElement('a') 片段，其中两处漏了 revokeObjectURL。
 * @param {Blob} blob
 * @param {string} filename
 */
export function saveBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  link.rel = 'noopener';
  document.body.append(link);
  link.click();
  link.remove();
  // Safari 需要等一帧再释放，否则下载会被中断。
  setTimeout(() => URL.revokeObjectURL(href), 0);
}

/**
 * 后台扫描作业的进度订阅。优先 SSE，连接失败回退轮询。
 *
 * 与旧实现的差别：
 *   - 返回 cancel()，离开页面时能真正断开（旧版 EventSource 泄漏到页面卸载）。
 *   - 区分「连接错误」与「服务端正常结束」，不再把正常收尾误判为失败后重新轮询。
 *
 * @param {string} jobId
 * @param {object} handlers
 * @param {(job: any) => void} handlers.onProgress
 * @param {(job: any) => void} handlers.onDone
 * @param {(error: Error) => void} handlers.onError
 * @returns {() => void} cancel
 */
export function watchJob(jobId, { onProgress, onDone, onError }) {
  const encoded = encodeURIComponent(jobId);
  const terminal = new Set(['FAILED', 'CANCELLED', 'DEAD']);
  let closed = false;
  let source = /** @type {EventSource | null} */ (null);
  let pollTimer = /** @type {ReturnType<typeof setTimeout> | null} */ (null);

  const cancel = () => {
    closed = true;
    source?.close();
    if (pollTimer) clearTimeout(pollTimer);
  };

  const settle = (job) => {
    if (closed) return;
    if (job.status === 'COMPLETED' && job.run_id) { cancel(); onDone(job); return true; }
    if (terminal.has(job.status)) {
      cancel();
      onError(new ApiError({
        message: job.progress_message || '后台扫描失败，可在作业记录中重试。',
        status: 0,
        url: `/api/jobs/${encoded}`,
        code: job.status,
      }));
      return true;
    }
    onProgress(job);
    return false;
  };

  const poll = async () => {
    let delay = 750;
    for (let attempt = 0; attempt < 240 && !closed; attempt += 1) {
      try {
        const job = await request(`/api/jobs/${encoded}`);
        if (settle(job)) return;
      } catch (error) {
        if (closed) return;
        if (error instanceof ApiError && error.isUnauthorized) { cancel(); onError(error); return; }
        // 单次轮询失败不终止，网络抖动比作业失败常见得多。
      }
      await new Promise((resolve) => { pollTimer = setTimeout(resolve, delay); });
      delay = Math.min(5000, Math.round(delay * 1.4));
    }
    if (!closed) {
      cancel();
      onError(new ApiError({
        message: '扫描仍在后台执行。可以离开本页，完成后在任务列表查看；刷新不会重复提交。',
        status: 0,
        url: `/api/jobs/${encoded}`,
        code: 'STILL_RUNNING',
      }));
    }
  };

  try {
    source = new EventSource(`/api/jobs/${encoded}/events`);
    source.onmessage = (event) => {
      let job;
      try { job = JSON.parse(event.data); } catch { return; }
      settle(job);
    };
    source.onerror = () => {
      if (closed) return;
      source?.close();
      source = null;
      poll();
    };
  } catch {
    poll();
  }

  return cancel;
}
