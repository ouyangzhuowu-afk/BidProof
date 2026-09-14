/**
 * 极小的可订阅状态容器（约 60 行，零依赖）。
 *
 * 旧实现是一个裸的 mutable object：写入不通知任何人，每处修改都要手动
 * 记得再调用对应的 renderX()。渲染遗漏是旧版最常见的一类 bug——
 * 例如 updateMember() 改完角色后 membersCache 仍是旧值，筛选下拉不刷新。
 *
 * 这里保留同样的字段名，让迁移是机械的，但把「谁依赖哪部分状态」
 * 变成显式订阅。选择器返回值用 Object.is 比较，不相等才触发回调，
 * 因此订阅一个 slice 不会被无关字段的写入惊动。
 */

/**
 * @template S
 * @param {S} initialState
 */
export function createStore(initialState) {
  let state = initialState;
  /** @type {Set<{ select: (s: S) => unknown, run: (v: any, prev: any) => void, last: unknown }>} */
  const watchers = new Set();
  let notifying = false;
  /** 批量写入时合并通知，避免一次交互触发 N 次重渲染。 */
  let pending = false;

  const notify = () => {
    if (notifying) { pending = true; return; }
    notifying = true;
    try {
      // 复制一份：回调里允许新增/移除订阅。
      for (const watcher of [...watchers]) {
        const next = watcher.select(state);
        if (Object.is(next, watcher.last)) continue;
        const prev = watcher.last;
        watcher.last = next;
        watcher.run(next, prev);
      }
    } finally {
      notifying = false;
      if (pending) { pending = false; notify(); }
    }
  };

  return {
    /** @returns {Readonly<S>} */
    get: () => state,

    /**
     * 局部更新。传函数可基于当前值计算。
     * @param {Partial<S> | ((current: Readonly<S>) => Partial<S>)} patch
     */
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : patch;
      let changed = false;
      for (const key of /** @type {(keyof S)[]} */ (Object.keys(next))) {
        if (!Object.is(state[key], next[key])) { changed = true; break; }
      }
      if (!changed) return;
      state = { ...state, ...next };
      notify();
    },

    /**
     * 订阅一个切片。返回取消订阅函数。
     * @template V
     * @param {(s: Readonly<S>) => V} select
     * @param {(value: V, previous: V) => void} run
     * @param {{ immediate?: boolean }} [options]
     * @returns {() => void}
     */
    watch(select, run, options = {}) {
      const watcher = { select, run, last: select(state) };
      watchers.add(watcher);
      if (options.immediate) run(/** @type {any} */ (watcher.last), undefined);
      return () => watchers.delete(watcher);
    },

    /** 测试与热重载用。 */
    reset(next) { state = next; notify(); },
  };
}

/**
 * @typedef {object} RunFilters
 * @property {string} scope          ACTIVE | ARCHIVED | ALL
 * @property {string} projectId
 * @property {string} search
 * @property {string} tag
 * @property {string} assigneeId
 * @property {string} reviewerId
 * @property {boolean} favoriteOnly
 * @property {string} sort           updated_desc | filename
 */

/**
 * @typedef {object} AppState
 * @property {import('../../types/api.js').Run | null} currentRun
 * @property {string} activeCategory
 * @property {number} matrixPage
 * @property {string} requirementSearch
 * @property {ReadonlySet<string>} selectedRunIds
 * @property {RunFilters} runFilters
 * @property {string | null} rescanParentId
 * @property {import('../../types/api.js').AuthStatus | null} authStatus
 * @property {import('../../types/api.js').CurrentUser | null} currentUser
 * @property {'login'|'setup'|'register'|'trial'} authMode
 * @property {string} pendingMfaToken
 * @property {import('../../types/api.js').Member[]} members
 * @property {import('../../types/api.js').Project[]} projects
 * @property {number} membersFetchedAt
 * @property {number} projectsFetchedAt
 */

/** @type {AppState} */
const initial = {
  currentRun: null,
  activeCategory: 'ALL',
  matrixPage: 1,
  requirementSearch: '',
  selectedRunIds: new Set(),
  runFilters: {
    scope: 'ACTIVE',
    projectId: '',
    search: '',
    tag: '',
    assigneeId: '',
    reviewerId: '',
    favoriteOnly: false,
    sort: 'updated_desc',
  },
  rescanParentId: null,
  authStatus: null,
  currentUser: null,
  authMode: 'login',
  pendingMfaToken: '',
  members: [],
  projects: [],
  membersFetchedAt: 0,
  projectsFetchedAt: 0,
};

export const store = createStore(initial);

/** 成员/项目缓存的有效期。旧实现是「取过就永不再取」，改名后下拉框一直是旧值。 */
export const CACHE_TTL_MS = 60_000;

/** @param {number} fetchedAt */
export const isStale = (fetchedAt) => Date.now() - fetchedAt > CACHE_TTL_MS;

/** 选择器。集中放这里，避免各视图各写一份过滤逻辑。 */
export const selectors = {
  canManageWorkspace: (/** @type {AppState} */ s) =>
    ['OWNER', 'ADMIN'].includes(s.currentUser?.role ?? ''),

  activeMembers: (/** @type {AppState} */ s) => s.members.filter((m) => m.active),

  activeProjects: (/** @type {AppState} */ s) => s.projects.filter((p) => !p.archived_at),

  hasRunFilters: (/** @type {AppState} */ s) => {
    const f = s.runFilters;
    return Boolean(f.search || f.tag || f.assigneeId || f.reviewerId || f.favoriteOnly || f.projectId);
  },
};
