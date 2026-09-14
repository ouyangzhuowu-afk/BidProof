/**
 * 工作区管理：成员、项目、提醒、留存策略、备份、准确率。
 *
 * 这些接口的共同点是「读多写少、且写完必须让所有下拉框看到新值」。
 * 旧实现把结果缓存在 store.membersCache 里且永不失效，
 * 于是改了成员角色之后，筛选下拉仍然是旧的，直到刷新整页。
 * 缓存策略现在归 core/store.js 的 TTL 管，这一层只负责取数。
 */

import { request, json } from '../core/http.js';
import { paths } from './paths.js';

/** @typedef {import('../../types/api.js').Member} Member */
/** @typedef {import('../../types/api.js').Project} Project */
/** @typedef {import('../../types/api.js').Notification} Notification */
/** @typedef {import('../../types/api.js').AccuracySummary} AccuracyMetrics */

/* ── 成员 ───────────────────────────────────────────────────────────────── */

/** @returns {Promise<{ members: Member[] }>} */
export function listMembers() {
  return request(paths.members);
}

/**
 * 直接创建成员（管理员设定初始密码）。
 * 与 auth.createInvitation 是两条并存的路径，产品上由「创建方式」开关决定。
 */
export function createMember(/** @type {Record<string, unknown>} */ body) {
  return json(paths.members, 'POST', body);
}

/**
 * 改角色或停用。停用不是删除 —— 历史记录里仍要能显示这个人。
 * @param {string} userId
 * @param {{ role?: import('../../types/api.js').Role, active?: boolean }} body
 */
export function updateMember(userId, body) {
  return json(paths.member(userId), 'PATCH', body);
}

/**
 * 生成一次性重置链接。
 *
 * 字段名是 `reset_path`（相对路径），不是 url/token。有效期 1 小时，
 * 只出现这一次 —— 交给 ui/secret-reveal.js 呈现。
 *
 * @param {string} userId
 * @returns {Promise<{ reset_path: string }>}
 */
export function resetMemberPassword(userId) {
  return json(paths.memberPasswordReset(userId), 'POST');
}

/* ── 项目 ───────────────────────────────────────────────────────────────── */

/**
 * @param {{ includeArchived?: boolean }} [options]
 * @returns {Promise<{ projects: Project[] }>}
 */
export function listProjects(options = {}) {
  return request(paths.projects(
    options.includeArchived ? { include_archived: true } : {},
  ));
}

/**
 * 新建项目。`code` 由用户填写，留空时传 null 让后端生成。
 *
 * 相关业务规则：`code === 'DEFAULT'` 的项目不允许归档
 * （见 core/permissions.js 的 isProjectArchivable）。
 *
 * @param {{ name: string, code: string | null }} body
 * @returns {Promise<import('../../types/api.js').Project>}
 */
export function createProject(body) {
  return json(paths.projects(), 'POST', body);
}

/**
 * 归档 / 恢复项目。契约是 PATCH + archived 布尔。
 * @param {string} projectId
 * @param {{ archived: boolean }} body
 */
export function updateProject(projectId, body) {
  return json(paths.project(projectId), 'PATCH', body);
}

/* ── 提醒与指标 ─────────────────────────────────────────────────────────── */

/** @returns {Promise<{ notifications: Notification[], count: number }>} */
export function listNotifications() {
  return request(paths.notifications);
}

/**
 * 检出准确率。
 *
 * 合规提示：review_population_complete 为 false 时，precision/recall
 * 只是抽样估计，**不得**在界面上呈现为已验证指标。旧实现直接展示百分比，
 * 这是对外宣称口径的风险点，UI 层必须据此降级文案。
 *
 * @returns {Promise<AccuracyMetrics>}
 */
export function getAccuracyMetrics() {
  return request(paths.accuracyMetrics);
}

/** 示例招标文件，用于空状态的一键试跑。 */
export function getSampleTender() {
  return request(paths.sampleTender);
}

/* ── 工作区设置 ─────────────────────────────────────────────────────────── */

export function getWorkspaceSettings() {
  return request(paths.workspace.settings);
}

/**
 * 保留期设置写在 workspace/settings 上，不是独立资源。
 *
 * **方法是 PATCH**。此前写的是 POST，会直接 405。
 *
 * @param {{ retention_days: number }} body
 */
export function saveWorkspaceSettings(body) {
  return json(paths.workspace.settings, 'PATCH', body);
}

/** 隐私与数据处理声明，合规展示用，不得删除。 */
export function getPrivacy() {
  return request(paths.workspace.privacy);
}

export function getUsage() {
  return request(paths.workspace.usage);
}

/* ── 留存与备份 ─────────────────────────────────────────────────────────── */

/** 先预览将被清除的数据量，再执行。UI 必须强制走这两步。 */
export function previewRetention() {
  return request(paths.retention.preview);
}

/** 不可逆。调用方必须已完成输入确认词的二次确认。 */
export function purgeRetention() {
  return json(paths.retention.purge, 'POST');
}

/**
 * 服务健康。管理页的运行状态面板用。
 * 此前 app.js 内联了 '/healthz?detail=true' 字符串，没有走 API 层。
 *
 * @returns {Promise<{ database?: string, backup_status?: string, failed_jobs?: number,
 *                     last_verified_backup_at?: string | null, degraded_reasons?: string[] }>}
 */
export function getHealth() {
  return request(paths.health);
}

export function listBackups() {
  return request(paths.backups);
}

export function createBackup() {
  return json(paths.backups, 'POST');
}
