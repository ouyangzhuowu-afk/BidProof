/**
 * 展示层格式化。
 *
 * 旧实现把七张枚举→中文的映射表以 `({ A: 'x', B: 'y' })[value] || value`
 * 的形式内联在 app.js 末尾，并且在渲染函数里又各写了一遍同样的三元判断。
 * 结果是同一个 `NEEDS_REVIEW` 在列表页叫「待复核」，在详情页叫「需人工确认」。
 *
 * 规则：任何面向用户的枚举文案只能从这里取。
 * 语言切换在 i18n 层，这里只负责「哪个键对应哪条文案」这件确定的事。
 */

/** @typedef {import('../../types/api.js').RequirementStatus} RequirementStatus */

/* ── 日期与数字 ─────────────────────────────────────────────────────────── */

const dateTime = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false,
});

const dateOnly = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit',
});

const relative = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });

/**
 * 绝对时间。无效值返回占位符而不是 "Invalid Date" ——
 * 旧实现直接 `new Date(x).toLocaleString()`，字段缺失时页面上会出现
 * 一行醒目的 Invalid Date，看起来像系统故障。
 *
 * @param {string | number | Date | null | undefined} value
 * @param {{ withTime?: boolean }} [options]
 */
export function formatDate(value, options = {}) {
  const date = toDate(value);
  if (!date) return '—';
  return (options.withTime === false ? dateOnly : dateTime).format(date);
}

/**
 * 相对时间，用于列表里的「更新于」。超过 30 天退回绝对日期 ——
 * 「87 天前」对排期没有帮助，用户真正想看的是具体哪天。
 *
 * @param {string | number | Date | null | undefined} value
 */
export function formatRelative(value) {
  const date = toDate(value);
  if (!date) return '—';
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minute = 60_000, hour = 60 * minute, day = 24 * hour;

  if (abs < minute) return '刚刚';
  if (abs < hour) return relative.format(Math.round(diffMs / minute), 'minute');
  if (abs < day) return relative.format(Math.round(diffMs / hour), 'hour');
  if (abs < 30 * day) return relative.format(Math.round(diffMs / day), 'day');
  return dateOnly.format(date);
}

/** @param {unknown} value @returns {Date | null} */
function toDate(value) {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'string' || typeof value === 'number') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}

/**
 * 任务号缩写。全长 UUID 在列表里既读不出来也对不上，
 * 统一取前 12 位 —— 旧实现有 .slice(0, 8) 和 .slice(0, 12) 两种，
 * 于是同一个任务在两个页面显示成不同的编号。
 *
 * @param {string | null | undefined} id
 */
export function shortId(id) {
  return id ? String(id).slice(0, 12) : '—';
}

/**
 * 百分比。null/undefined 与 0 必须区分：
 * 「还没测」和「命中率 0%」是完全不同的事实。
 *
 * @param {number | null | undefined} ratio 0–1
 * @param {number} [digits]
 */
export function formatPercent(ratio, digits = 1) {
  if (typeof ratio !== 'number' || Number.isNaN(ratio)) return '未测量';
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** @param {number | null | undefined} bytes */
export function formatBytes(bytes) {
  if (typeof bytes !== 'number' || bytes < 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

/* ── 枚举文案 ───────────────────────────────────────────────────────────── */

/**
 * 生成「查表 + 原样兜底」的映射函数。
 * 兜底是刻意的：后端新增枚举值时，界面显示原始值总好过显示空白。
 *
 * @template {string} K
 * @param {Record<K, string>} table
 */
function labeller(table) {
  return (/** @type {string | null | undefined} */ value) =>
    (value && /** @type {Record<string, string>} */ (table)[value]) || value || '—';
}

/** 要求项判定。UNKNOWN 与 NEEDS_REVIEW 的文案必须互不相似。 */
export const statusLabel = labeller({
  PASS: '已满足',
  FAIL: '不满足',
  NEEDS_REVIEW: '待人工确认',
  UNKNOWN: '未找到证据',
});

export const categoryLabel = labeller({
  FATAL: '废标风险',
  QUALIFICATION: '资格条件',
  CREDENTIAL: '资质证明',
  BOND: '保证金',
  SIGNATURE: '签署盖章',
  DEADLINE: '时间节点',
  FORMAT: '格式要求',
  SCORING: '评分项',
  OTHER: '其他',
});

export const criticalityLabel = labeller({
  BLOCKER: '阻断',
  REVIEW: '需复核',
  INFO: '参考',
});

export const detectionLabel = labeller({
  deterministic: '规则命中',
  heuristic: '启发式',
  model: '模型辅助',
});

/**
 * 人工决策。取值以 app.js 旧实现为准（CONTINUE / HOLD / STOP），
 * 不是直觉上的 GO / NO_GO —— 这是契约，改文案可以，改键不行。
 */
export const decisionLabel = labeller({
  CONTINUE: '继续投标',
  HOLD: '暂缓',
  STOP: '停止投标',
});

export const jobStatusLabel = labeller({
  PENDING: '排队中',
  RUNNING: '扫描中',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  DEAD: '已终止',
});

export const roleLabel = labeller({
  OWNER: '所有者',
  ADMIN: '管理员',
  REVIEWER: '复核人',
  VIEWER: '只读成员',
});

export const backupStatusLabel = labeller({
  verified: '已验证',
  unverified: '未验证',
  missing: '无备份',
});

/**
 * 证据定位。没有定位时必须说出来 ——
 * 这条是产品可信度的底线：未标注来源的结论一律显性标记为缺失。
 *
 * @param {{ locator?: { label?: string } } | null | undefined} target
 */
export function locatorLabel(target) {
  return target?.locator?.label || '定位缺失';
}

/**
 * 判定的排序权重。用于「风险优先」排序。
 * 集中定义，避免列表页与详情页排出两种顺序。
 *
 * @param {{ status?: RequirementStatus, category?: string }} item
 */
export function riskRank(item) {
  const byStatus = { FAIL: 0, UNKNOWN: 1, NEEDS_REVIEW: 2, PASS: 3 };
  const byCategory = { FATAL: 0, QUALIFICATION: 1, DEADLINE: 2, BOND: 3 };
  const status = byStatus[/** @type {keyof typeof byStatus} */ (item.status)] ?? 9;
  const category = byCategory[/** @type {keyof typeof byCategory} */ (item.category)] ?? 9;
  return status * 10 + category;
}
