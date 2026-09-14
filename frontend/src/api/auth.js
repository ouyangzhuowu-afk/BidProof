/**
 * 鉴权与账号安全。
 *
 * 硬约束区：登录流程、MFA 两步、会话与令牌的语义一律不动。
 * 这一层只是把旧实现里散落的 fetch 收进来，并把「两步登录」
 * 这个隐式状态机写成显式返回值 —— 旧实现靠检查响应里有没有
 * `mfa_token` 字段来决定下一步，判断散在 3 个地方。
 */

import { request, json } from '../core/http.js';
import { paths } from './paths.js';

/** @typedef {import('../../types/api.js').AuthStatus} AuthStatus */
/** @typedef {import('../../types/api.js').CurrentUser} CurrentUser */
/** @typedef {import('../../types/api.js').Session} Session */
/** @typedef {import('../../types/api.js').ApiTokenSummary} ApiToken */

/**
 * 登录结果。两种终态之一，调用方必须显式处理两支 ——
 * 返回联合类型正是为了让漏处理在类型检查时就暴露。
 *
 * @typedef {{ kind: 'authenticated', user: CurrentUser }
 *         | { kind: 'mfa_required', mfaToken: string }} LoginOutcome
 */

/** @returns {Promise<AuthStatus>} */
export function getStatus() {
  return request(paths.auth.status);
}

/**
 * 第一步登录。服务端返回 mfa_token 表示还需要第二步。
 * @param {{ username: string, password: string }} body
 * @returns {Promise<LoginOutcome>}
 */
export async function login(body) {
  const payload = await json(paths.auth.login, 'POST', body);
  return toOutcome(payload);
}

/**
 * 第二步：提交 TOTP。
 * @param {{ mfa_token: string, code: string }} body
 * @returns {Promise<LoginOutcome>}
 */
export async function verifyMfa(body) {
  return toOutcome(await json(paths.auth.mfa.verify, 'POST', body));
}

/**
 * 把服务端响应归一成两种终态之一。
 *
 * **判据是 `mfa_required`，不是 `mfa_token` 是否存在。**
 * 此前用后者，当前能工作只是因为后端两个字段同时回传；
 * 哪天后端只保留 `mfa_required`（或在不需要二次验证时也回一个空 token），
 * 判断就会静默反向 —— 用户要么被卡在验证码界面，要么直接跳过二次验证。
 *
 * @param {any} payload
 * @returns {LoginOutcome}
 */
function toOutcome(payload) {
  if (payload?.mfa_required) {
    return { kind: 'mfa_required', mfaToken: payload.mfa_token };
  }
  // 登录成功时后端直接返回用户对象本身，没有 user 包装层。
  return { kind: 'authenticated', user: payload?.user ?? payload };
}

/**
 * 首次部署创建 OWNER。仅在 status.setup_required 为真时可用。
 *
 * `workspace_name` 必填 —— bootstrap 同时创建工作区和所有者账号，
 * 此前的类型只写了 username/password，照着实现必然 422。
 * `bootstrap_token` 仅当 status.bootstrap_token_required 为真时需要；
 * status.bootstrap_locked 为真时整个表单应禁用提交。
 *
 * @param {object} body
 * @param {string} body.username
 * @param {string} body.password
 * @param {string} body.workspace_name
 * @param {string | null} [body.bootstrap_token]
 */
export function bootstrap(body) {
  return json(paths.auth.bootstrap, 'POST', body);
}

export function register(/** @type {Record<string, unknown>} */ body) {
  return json(paths.auth.register, 'POST', body);
}

export function trialJoin(/** @type {Record<string, unknown>} */ body) {
  return json(paths.auth.trialJoin, 'POST', body);
}

export function logout() {
  return json(paths.auth.logout, 'POST');
}

/** 修改自己的密码。旧密码错误时服务端返回 400 + detail。 */
export function changePassword(/** @type {{ current_password: string, new_password: string }} */ body) {
  return json(paths.auth.password, 'POST', body);
}

/* ── 邀请 / 重置链接 ─────────────────────────────────────────────────────── */

/**
 * 用链接里的 token 换取动作详情（是激活还是重置、给哪个用户）。
 *
 * 注意取值：**`'INVITE'` 表示邀请激活**，不是 'activate'。
 * 分支写错的后果不是报错，是把邀请当成密码重置处理 —— 文案和后续端点都会错。
 *
 * @param {string} token
 * @returns {Promise<{ action: 'INVITE' | 'RESET', username: string, role: import('../../types/api.js').Role }>}
 */
export function describeAction(token) {
  return request(paths.auth.action(token));
}

/** @param {{ token: string, password: string }} body */
export function activate(body) {
  return json(paths.auth.activate, 'POST', body);
}

/** @param {{ token: string, password: string }} body */
export function resetPassword(body) {
  return json(paths.auth.resetPassword, 'POST', body);
}

/**
 * 管理员为成员创建邀请。
 *
 * 返回的 `activation_path` 是相对路径，**只出现这一次**，
 * 必须当场交给用户（见 ui/secret-reveal.js）。有效期 72 小时。
 *
 * @param {{ username: string, role: import('../../types/api.js').Role }} body
 * @returns {Promise<{ activation_path: string }>}
 */
export function createInvitation(body) {
  return json(paths.auth.invitations, 'POST', body);
}

/* ── MFA ────────────────────────────────────────────────────────────────── */

/**
 * 当前账号是否已启用二次验证。
 *
 * **从 /api/auth/status 读 `mfa_enabled`**，不要对 mfa/enroll 发 GET ——
 * 那个端点只接受 POST，而且 POST 它会**轮换密钥**。
 * 此前的实现是 `request(paths.auth.mfa.enroll)`，既拿不到结果（大概率 405），
 * 万一后端把 GET 也路由过去还会把用户已有的验证器搞失效。
 *
 * @returns {Promise<{ enabled: boolean }>}
 */
export async function getMfaStatus() {
  const status = await request(paths.auth.status);
  return { enabled: Boolean(status?.mfa_enabled) };
}

/**
 * 生成密钥与恢复码。
 *
 * 两件事调用方必须知道：
 *   1. **调用即轮换密钥。** 用户没确认就离开，旧密钥已失效 —— 既有后端行为。
 *   2. **`recovery_codes` 只回传这一次。** 丢了等于账号锁死，
 *      必须用 ui/secret-reveal.js 呈现并要求用户确认已保存。
 *      此前这里标的是 otpauth_url，照着实现会直接漏掉恢复码。
 *
 * @returns {Promise<{ secret: string, recovery_codes: string[] }>}
 */
export function enrollMfa() {
  return json(paths.auth.mfa.enroll, 'POST');
}

export function confirmMfa(/** @type {{ code: string }} */ body) {
  return json(paths.auth.mfa.confirm, 'POST', body);
}

export function disableMfa(/** @type {{ code: string }} */ body) {
  return json(paths.auth.mfa.disable, 'POST', body);
}

/* ── 会话 ───────────────────────────────────────────────────────────────── */

/** @returns {Promise<{ sessions: Session[] }>} */
export function listSessions() {
  return request(paths.auth.sessions);
}

/** @param {string} sessionId */
export function revokeSession(sessionId) {
  return json(paths.auth.session(sessionId), 'DELETE');
}

/** 踢掉除当前之外的全部会话。安全事件响应用，需二次确认。 */
export function revokeOtherSessions() {
  return json(paths.auth.revokeOtherSessions, 'POST');
}

/* ── API 令牌 ───────────────────────────────────────────────────────────── */

/** @returns {Promise<{ tokens: ApiToken[] }>} */
export function listTokens() {
  return request(paths.auth.tokens);
}

/**
 * 明文令牌只在这次响应里出现，之后服务端只存哈希。
 * UI 必须在这一刻让用户复制走，不能指望之后再查。
 * @returns {Promise<ApiToken>}
 */
export function createToken(/** @type {{ name: string }} */ body) {
  return json(paths.auth.tokens, 'POST', body);
}

/** @param {string} tokenId */
export function revokeToken(tokenId) {
  return json(paths.auth.token(tokenId), 'DELETE');
}
