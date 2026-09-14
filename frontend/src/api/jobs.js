/**
 * 后台扫描作业。
 *
 * 「新建扫描」在契约上是异步的：POST /api/jobs 只返回一个 job_id，
 * 真正的 Run 要等作业跑完。旧实现把提交、订阅进度、轮询兜底、
 * 拉取结果四件事写在同一个 submitScan() 里，其中的 EventSource
 * 从来没有被关闭过 —— 用户连开五个任务，页面上就挂着五条长连接。
 *
 * 这里把生命周期显式化：submitScan() 返回 job，watch() 返回 cancel()。
 * 谁开的谁负责关，路由切换时统一调用。
 */

import { request, json, watchJob, UPLOAD_TIMEOUT_MS } from '../core/http.js';
import { paths } from './paths.js';
import { getRun } from './runs.js';

/** @typedef {import('../../types/api.js').ScanJob} Job */
/** @typedef {import('../../types/api.js').Run} Run */

/**
 * 提交一次扫描。FormData 直传，**不要**设置 Content-Type：
 * 手动设置会丢掉 multipart boundary，后端只会看到一个空 body。
 *
 * @param {FormData} form
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<Job>}
 */
export function submitScan(form, options = {}) {
  return request(paths.jobs.list({}), {
    ...options,
    method: 'POST',
    body: form,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
}

/**
 * @param {{ limit?: number }} [params]
 * @returns {Promise<{ jobs: Job[] }>}
 */
export function listJobs(params = { limit: 200 }) {
  return request(paths.jobs.list(params));
}

/** @param {string} jobId @returns {Promise<Job>} */
export function getJob(jobId) {
  return request(paths.jobs.detail(jobId));
}

/** @param {string} jobId */
export function retryJob(jobId) {
  return json(paths.jobs.retry(jobId), 'POST');
}

/** @param {string} jobId */
export function cancelJob(jobId) {
  return json(paths.jobs.cancel(jobId), 'POST');
}

/**
 * 订阅作业直到终态，完成后自动取回 Run。
 *
 * 返回的 cancel() 必须在离开页面时调用。传播机制（SSE 优先、
 * 失败退化为指数退避轮询）在 core/http.js 的 watchJob 里，
 * 这一层只负责「拿到结果」这件业务事实。
 *
 * @param {string} jobId
 * @param {object} handlers
 * @param {(job: Job) => void} [handlers.onProgress]
 * @param {(run: Run, job: Job) => void} handlers.onDone
 * @param {(error: Error) => void} handlers.onError
 * @returns {() => void} cancel
 */
export function watchScan(jobId, { onProgress = () => {}, onDone, onError }) {
  let cancelled = false;
  const stop = watchJob(jobId, {
    onProgress,
    onDone: async (job) => {
      if (cancelled) return;
      try {
        const run = await getRun(job.run_id);
        if (!cancelled) onDone(run, job);
      } catch (error) {
        // 作业成功但详情取不回来是两件事，不要合并成「扫描失败」。
        if (!cancelled) onError(/** @type {Error} */ (error));
      }
    },
    onError: (error) => { if (!cancelled) onError(error); },
  });
  return () => { cancelled = true; stop(); };
}
