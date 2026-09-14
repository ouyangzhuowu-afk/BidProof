/**
 * 角色能力矩阵。
 *
 * 管理页现在用两套机制决定「这个控件给不给看」：
 *
 *   A. 角色前置 —— `['OWNER','ADMIN'].includes(store.currentUser?.role)`
 *      控制 #member-form、#project-form、#purge-retention
 *
 *   B. 403 后置 —— 先发请求，catch 里把表单藏起来（备份、API 令牌）：
 *
 *        } catch (error) {
 *          setHtml(target, html`<div class="empty-state">当前角色无备份管理权限。</div>`);
 *          document.querySelector('#create-backup').hidden = true;
 *        }
 *
 * B 的问题不是多发一次请求，是**它把所有失败都说成权限问题**。
 * 网络断了、后端 500、超时 —— 用户看到的都是「当前角色无备份管理权限」，
 * 一个管理员会因此以为自己权限被改了。这和「整改项保存失败却不还原下拉」
 * 是同一类问题：界面在撒谎。
 *
 * 这个模块把可见性判定统一到 A。B 只作为兜底，且**必须按状态码分支** ——
 * 403 才说权限，其余走正常错误态并给重试（见 isPermissionError）。
 */

/** @typedef {import('../../types/api.js').Role} Role */

/**
 * 能力清单。取名按「动作」而不是「页面」，
 * 这样界面重排时不需要动这张表。
 *
 * @typedef {'members.manage' | 'projects.manage' | 'retention.purge'
 *         | 'retention.configure' | 'backups.manage' | 'tokens.manage'
 *         | 'account.self'} Capability
 */

/**
 * 角色 → 能力。
 *
 * **前四行有代码依据**（原 app.js 的角色数组）：
 *   members.manage / projects.manage / retention.*  → OWNER, ADMIN
 *
 * **后两行是假设**：备份与 API 令牌在旧实现里没有角色判断，
 * 只有 403 兜底，所以这里按「与其它管理能力同级」推定。
 * 拿到后端权限表后必须核对 —— 推错的方向是「该显示的没显示」，
 * 比「不该显示的显示了」安全，但仍然是推定。
 *
 * @type {Record<Role, Capability[]>}
 */
const MATRIX = {
  OWNER: [
    'members.manage', 'projects.manage', 'retention.purge', 'retention.configure',
    'backups.manage', 'tokens.manage', 'account.self',
  ],
  ADMIN: [
    'members.manage', 'projects.manage', 'retention.purge', 'retention.configure',
    'backups.manage', 'tokens.manage', 'account.self',
  ],
  REVIEWER: ['account.self'],
  VIEWER: ['account.self'],
};

/** @type {Role | null} */
let currentRole = null;

/**
 * 登录成功或身份变化后调用一次。
 *
 * 之所以不直接读 store：目前 app.js 用 state.js、features/* 用 core/store.js，
 * 两套并存。等 app.js 清空、只剩一个 store 之后，这里可以改成订阅。
 *
 * @param {Role | null | undefined} role
 */
export function setCurrentRole(role) {
  currentRole = role || null;
}

/** @returns {Role | null} */
export function getCurrentRole() {
  return currentRole;
}

/**
 * @param {Capability} capability
 * @param {Role | null} [role] 不传则用当前身份
 * @returns {boolean}
 */
export function can(capability, role = currentRole) {
  if (!role) return false;
  return (MATRIX[role] || []).includes(capability);
}

/**
 * 按能力切换控件可见性。返回是否可见，方便调用方接着做别的事。
 *
 * @param {Element | null} node
 * @param {Capability} capability
 * @returns {boolean}
 */
export function gate(node, capability) {
  const allowed = can(capability);
  if (node) node.toggleAttribute('hidden', !allowed);
  return allowed;
}

/**
 * 判断一个错误是不是「权限不足」。
 *
 * 这是 403 兜底路径的唯一正确入口：**只有 403 才能说权限**。
 * 其余错误必须按错误态处理并提供重试，否则就是在对用户撒谎。
 *
 * @param {unknown} error
 * @returns {boolean}
 */
export function isPermissionError(error) {
  return Boolean(error) && /** @type {any} */ (error).status === 403;
}

/**
 * OWNER 自身在成员列表里没有角色与停用控件 —— 这是既有行为（原 app.js:802
 * 的条件是 `member.role !== 'OWNER'`），不是疏漏，迁移时必须保留。
 *
 * @param {{ role: Role }} member
 * @returns {boolean}
 */
export function isMemberMutable(member) {
  return member.role !== 'OWNER';
}

/**
 * 默认项目不允许归档（原 app.js:833）。这条业务规则此前只存在于一个
 * 内联三元里，类型与 API 层都没有体现。
 *
 * @param {{ code?: string }} project
 * @returns {boolean}
 */
export function isProjectArchivable(project) {
  return project.code !== 'DEFAULT';
}
