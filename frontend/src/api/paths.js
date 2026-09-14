/**
 * 所有 API 路径的唯一定义处。
 *
 * 旧实现把 41 个路径以模板字符串的形式散在 app.js 的 60 多个函数里，
 * 每处各自调用一次 encodeURIComponent —— 其中 3 处漏掉了。
 * 把路径集中之后：
 *   - 路径拼接与转义只有一份实现，漏转义在结构上不可能发生；
 *   - 后端改路径时，diff 只落在这一个文件上，review 能一眼看完；
 *   - grep 这个文件就是一份准确的「前端用到了哪些接口」清单。
 *
 * 硬约束：本文件里的每一条路径都必须与旧实现逐字一致。
 * 这是契约，不是实现细节，重构不得顺手「优化」。
 */

const enc = encodeURIComponent;

/**
 * 构造查询串。空值、空字符串、false 一律不进 URL ——
 * 旧实现会发出 `?tag=&assignee_id=` 这种参数，后端按「有值」处理，
 * 导致清除筛选后列表仍然是空的。
 *
 * @param {Record<string, string | number | boolean | null | undefined>} params
 * @returns {string} 形如 `?a=1&b=2`，无参数时返回空串
 */
export function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export const paths = {
  /* ── 鉴权 ───────────────────────────────────────────────────────────── */
  auth: {
    status: '/api/auth/status',
    login: '/api/auth/login',
    logout: '/api/auth/logout',
    register: '/api/auth/register',
    bootstrap: '/api/auth/bootstrap',
    trialJoin: '/api/auth/trial-join',
    activate: '/api/auth/activate',
    resetPassword: '/api/auth/reset-password',
    invitations: '/api/auth/invitations',
    password: '/api/auth/password',
    /** 邀请 / 重置链接落地时用 token 换取动作详情。 */
    action: (/** @type {string} */ token) => `/api/auth/action?token=${enc(token)}`,
    mfa: {
      enroll: '/api/auth/mfa/enroll',
      confirm: '/api/auth/mfa/confirm',
      disable: '/api/auth/mfa/disable',
      /** 登录第二步，携带 pendingMfaToken。 */
      verify: '/api/auth/mfa/verify',
    },
    sessions: '/api/auth/sessions',
    session: (/** @type {string} */ id) => `/api/auth/sessions/${enc(id)}`,
    revokeOtherSessions: '/api/auth/sessions/revoke-others',
    tokens: '/api/auth/tokens',
    token: (/** @type {string} */ id) => `/api/auth/tokens/${enc(id)}`,
  },

  /* ── 扫描任务 ───────────────────────────────────────────────────────── */
  runs: {
    /** @param {Record<string, any>} filters */
    list: (filters = {}) => `/api/runs${query(filters)}`,
    detail: (/** @type {string} */ id) => `/api/runs/${enc(id)}`,
    /** 批量归档 / 恢复 / 删除。body: { action, run_ids }。 */
    bulk: '/api/runs/bulk',
    bulkReport: '/api/runs/bulk/report.zip',
    rescan: (/** @type {string} */ id) => `/api/runs/${enc(id)}/rescan`,
    decision: (/** @type {string} */ id) => `/api/runs/${enc(id)}/decision`,
    metadata: (/** @type {string} */ id) => `/api/runs/${enc(id)}/metadata`,
    review: (/** @type {string} */ id) => `/api/runs/${enc(id)}/review`,
    comments: (/** @type {string} */ id) => `/api/runs/${enc(id)}/comments`,
    audit: (/** @type {string} */ id) => `/api/runs/${enc(id)}/audit`,
    remediations: (/** @type {string} */ id) => `/api/runs/${enc(id)}/remediations`,
    accuracyFeedback: (/** @type {string} */ id) => `/api/runs/${enc(id)}/accuracy-feedback`,
    /** 与父版本的差异。调用前必须确认 parent_run_id 非空。 */
    diff: (/** @type {string} */ id, /** @type {string} */ parentId) =>
      `/api/runs/${enc(id)}/diff/${enc(parentId)}`,
    /** 原始归档件下载。source_id 来自 Run.source_documents。 */
    file: (/** @type {string} */ id, /** @type {string} */ sourceId) =>
      `/api/runs/${enc(id)}/files/${enc(sourceId)}`,
    /** @param {import('../../types/api.js').ReportFormat} format */
    report: (/** @type {string} */ id, format) => `/api/runs/${enc(id)}/report.${format}`,
  },

  /** 整改项状态更新走独立顶层资源，不挂在 run 下。 */
  remediation: (/** @type {string} */ id) => `/api/remediations/${enc(id)}`,

  /* ── 后台作业 ───────────────────────────────────────────────────────── */
  jobs: {
    /** @param {{ limit?: number }} params */
    list: (params = {}) => `/api/jobs${query(params)}`,
    detail: (/** @type {string} */ id) => `/api/jobs/${enc(id)}`,
    /** SSE 端点。EventSource 不走 fetch 封装，超时/重试策略也不同。 */
    events: (/** @type {string} */ id) => `/api/jobs/${enc(id)}/events`,
    retry: (/** @type {string} */ id) => `/api/jobs/${enc(id)}/retry`,
    cancel: (/** @type {string} */ id) => `/api/jobs/${enc(id)}/cancel`,
  },

  /* ── 工作区管理 ─────────────────────────────────────────────────────── */
  members: '/api/members',
  member: (/** @type {string} */ id) => `/api/members/${enc(id)}`,
  memberPasswordReset: (/** @type {string} */ id) => `/api/members/${enc(id)}/password-reset`,

  /** @param {{ include_archived?: boolean }} params */
  projects: (params = {}) => `/api/projects${query(params)}`,
  project: (/** @type {string} */ id) => `/api/projects/${enc(id)}`,

  notifications: '/api/notifications',
  accuracyMetrics: '/api/accuracy/metrics',
  sampleTender: '/api/sample-tender',

  workspace: {
    settings: '/api/workspace/settings',
    privacy: '/api/workspace/privacy',
    usage: '/api/workspace/usage',
  },

  retention: {
    preview: '/api/retention/preview',
    purge: '/api/retention/purge',
  },

  backups: '/api/backups',

  /**
   * 服务健康。**唯一一个不在 /api/ 前缀下的端点**，此前完全没有收录，
   * 管理页直接内联了字符串。
   * 返回 { database, backup_status, failed_jobs, last_verified_backup_at, degraded_reasons[] }。
   */
  health: '/healthz?detail=true',
};
