/**
 * 扫描任务接口。
 *
 * 这一层只做三件事：拼参数、标类型、给出可被 UI 直接使用的返回值。
 * 不做 DOM 操作，不弹 toast，不读全局 store —— 这样它可以被测试，
 * 也可以在未来换成 SSR/BFF 时整体搬走。
 *
 * 旧实现里这些调用是内联在事件处理函数中间的，于是「请求」和「渲染」
 * 共享同一个 try/catch，任何一处渲染异常都会被当成网络错误提示给用户。
 */

import { request, json, requestBlob, saveBlob, UPLOAD_TIMEOUT_MS, EXPORT_TIMEOUT_MS } from '../core/http.js';
import { paths } from './paths.js';

/** @typedef {import('../../types/api.js').Run} Run */
/** @typedef {import('../../types/api.js').RunSummary} RunSummary */
/** @typedef {import('../../types/api.js').RunScope} RunScope */
/** @typedef {import('../../types/api.js').ReportFormat} ExportFormat */

/**
 * 列表筛选条件。字段名与后端查询参数一一对应，不做别名映射 ——
 * 映射层是这类项目里最容易腐化的东西。
 *
 * @typedef {object} RunQuery
 * @property {RunScope} [scope]        仅前端概念，转成 include_archived 后不再出现
 * @property {string} [projectId]
 * @property {string} [search]
 * @property {string} [tag]
 * @property {string} [assigneeId]
 * @property {string} [reviewerId]
 * @property {boolean} [favoriteOnly]
 * @property {string} [sort]
 */

/**
 * 列表查询。
 *
 * 注意 scope 的处理：后端只认 include_archived 布尔值，
 * ARCHIVED 与 ALL 都要带上归档数据，差别在前端过滤（见 filterByScope）。
 * 旧实现在这里和渲染处各判断了一次，两处逻辑一度不一致。
 *
 * @param {RunQuery} [filters]
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<RunSummary[]>}
 */
export function listRuns(filters = {}, options = {}) {
  const scope = filters.scope ?? 'ACTIVE';
  return request(paths.runs.list({
    include_archived: String(scope !== 'ACTIVE'),
    sort: filters.sort || 'updated_desc',
    project_id: filters.projectId,
    search: filters.search,
    tag: filters.tag,
    assignee_id: filters.assigneeId,
    reviewer_id: filters.reviewerId,
    favorite: filters.favoriteOnly ? 'true' : undefined,
  }), options);
}

/**
 * 按 scope 收敛列表。后端返回的是「包含/不包含归档」，
 * 而 UI 的三档语义更细，所以最后一步在前端完成。
 *
 * @template {{ archived_at?: string | null }} T
 * @param {T[]} runs
 * @param {RunScope} scope
 * @returns {T[]}
 */
export function filterByScope(runs, scope) {
  if (scope === 'ARCHIVED') return runs.filter((run) => Boolean(run.archived_at));
  if (scope === 'ACTIVE') return runs.filter((run) => !run.archived_at);
  return runs;
}

/**
 * @param {string} runId
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<Run>}
 */
export function getRun(runId, options = {}) {
  return request(paths.runs.detail(runId), options);
}

/**
 * 基于已有任务重新扫描，生成新版本。
 *
 * 注意与「新建扫描」的不同：新建走 POST /api/jobs（异步作业，见 api/jobs.js），
 * 重扫是同步返回 Run 的。这个不对称是既有契约，前端不做统一。
 *
 * 超时单独放大到 10 分钟：后端要做 PDF 解析和 OCR，
 * 默认 30s 会在用户什么都没做错的情况下把请求掐断。
 * @param {string} parentRunId
 * @param {FormData} form
 * @returns {Promise<Run>}
 */
export function rescan(parentRunId, form) {
  return request(paths.runs.rescan(parentRunId), {
    method: 'POST',
    body: form,
    timeoutMs: UPLOAD_TIMEOUT_MS,
  });
}

/**
 * 记录人工决策。这是产品里唯一不可撤销的写操作，
 * 调用方必须已经做过二次确认。
 *
 * @param {string} runId
 * @param {{ decision: string, note: string, unresolved_requirement_ids: string[] }} body
 * @returns {Promise<Run>}
 */
export function saveDecision(runId, body) {
  return json(paths.runs.decision(runId), 'POST', body);
}

/**
 * @param {string} runId
 * @param {{ tags?: string[], favorite?: boolean, assignee_id?: string | null, reviewer_id?: string | null, project_id?: string | null }} body
 * @returns {Promise<Run>}
 */
export function saveMetadata(runId, body) {
  return json(paths.runs.metadata(runId), 'POST', body);
}

/**
 * 单条要求项的人工复核。
 *
 * **`revision` 必传**：后端用它做乐观并发控制。两个人同时复核同一任务时，
 * 后提交的一方会拿到冲突错误而不是静默覆盖对方的判定。
 * 调用方必须传入当前 Run 的 revision，不要省略、不要传 0。
 *
 * @param {string} runId
 * @param {object} body
 * @param {string} body.requirement_id
 * @param {import('../../types/api.js').ReviewDecision} body.decision
 * @param {number} [body.revision] 当前 Run.revision
 * @param {string} [body.note]
 * @returns {Promise<Run>} 返回整个 Run，不是单条要求项
 */
export function reviewRequirement(runId, body) {
  return json(paths.runs.review(runId), 'POST', { note: '', ...body });
}

/**
 * 检出准确性反馈。与 review 不同：这条不改变判定，只回流度量信号。
 *
 * 契约要点（从旧实现逐字核对，不得简化）：
 *   predicted        'DETECTED' = 系统报了这一项；'MISSED' = 系统漏了
 *   actual           'RELEVANT' = 确实该报；'NOT_RELEVANT' = 误报
 *   dataset_scope    固定 'PILOT'
 *   review_complete  本任务是否已完成全量复核。**它直接决定
 *                    /api/accuracy/metrics 的 review_population_complete**，
 *                    进而决定准确率能不能对外引用。不能默认填 true。
 *
 * 漏项反馈（predicted: 'MISSED'）额外带 locator_label 与 quote。
 *
 * @param {string} runId
 * @param {object} body
 * @param {string} body.category
 * @param {'DETECTED' | 'MISSED'} body.predicted
 * @param {import('../../types/api.js').AccuracyVerdict} body.actual
 * @param {boolean} body.review_complete
 * @param {string} [body.requirement_id]
 * @param {string} [body.locator_label]
 * @param {string} [body.quote]
 * @param {string} [body.note]
 */
export function submitAccuracyFeedback(runId, body) {
  return json(paths.runs.accuracyFeedback(runId), 'POST', {
    dataset_scope: 'PILOT',
    note: '界面人工反馈',
    ...body,
  });
}

/**
 * @param {string} runId
 * @returns {Promise<{ comments: import('../../types/api.js').Comment[] }>}
 */
export function listComments(runId) {
  return request(paths.runs.comments(runId));
}

/** @param {string} runId @param {{ body: string }} body */
export function addComment(runId, body) {
  return json(paths.runs.comments(runId), 'POST', body);
}

/**
 * @param {string} runId
 * @returns {Promise<{ events: import('../../types/api.js').AuditEvent[] }>}
 */
export function listAudit(runId) {
  return request(paths.runs.audit(runId));
}

/**
 * @param {string} runId
 * @returns {Promise<{ remediations: import('../../types/api.js').Remediation[] }>}
 */
export function listRemediations(runId) {
  return request(paths.runs.remediations(runId));
}

/** @param {string} runId @param {Record<string, unknown>} body */
export function createRemediation(runId, body) {
  return json(paths.runs.remediations(runId), 'POST', body);
}

/** @param {string} remediationId @param {Record<string, unknown>} body */
export function updateRemediation(remediationId, body) {
  return json(paths.remediation(remediationId), 'PATCH', body);
}

/**
 * 版本差异。parentRunId 为空时不应调用 —— 这里显式抛错而不是发一个必然 404 的请求。
 * @param {string} runId
 * @param {string} parentRunId
 */
export function getDiff(runId, parentRunId) {
  if (!parentRunId) throw new Error('当前任务没有父版本，无法比较差异。');
  return request(paths.runs.diff(runId, parentRunId));
}

/* ── 批量操作 ───────────────────────────────────────────────────────────── */

/**
 * @param {import('../../types/api.js').BulkAction} action
 * @param {string[]} runIds
 * @returns {Promise<{ updated: number }>}
 */
export function bulkManage(action, runIds) {
  return json(paths.runs.bulk, 'POST', { action, run_ids: runIds });
}

/**
 * 批量导出为 zip。直接落盘，不返回内容。
 * @param {string[]} runIds
 */
export async function bulkExport(runIds) {
  const response = await requestBlob(paths.runs.bulkReport, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_ids: runIds }),
    timeoutMs: EXPORT_TIMEOUT_MS,
  });
  saveBlob(await response.blob(), filenameFrom(response, 'bidproof-reports.zip'));
}

/**
 * 单任务导出。
 * @param {string} runId
 * @param {ExportFormat} format
 */
export async function exportRun(runId, format) {
  const response = await requestBlob(paths.runs.report(runId, format));
  saveBlob(await response.blob(), filenameFrom(response, `bidproof-${runId.slice(0, 12)}.${format}`));
}

/**
 * 优先用服务端给的文件名 —— 报告文件名里带着版本号和时间戳，
 * 是归档链路的一部分，前端自己拼会丢掉这些信息。
 *
 * @param {Response} response
 * @param {string} fallback
 */
function filenameFrom(response, fallback) {
  const header = response.headers.get('content-disposition') || '';
  const utf8 = header.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8) { try { return decodeURIComponent(utf8[1]); } catch { /* 落到下一分支 */ } }
  const plain = header.match(/filename="?([^";]+)"?/i);
  return plain ? plain[1] : fallback;
}
