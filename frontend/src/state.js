import { store as sharedStore } from './core/store.js';

/**
 * Mutable UI state lives here instead of as module-level `let` bindings in app.js.
 * Views read and write through this object so there is a single mutation surface.
 *
 * @typedef {object} AppStore
 * @property {object | null} currentRun
 * @property {string} activeCategory
 * @property {number} matrixPage
 * @property {string} searchTerm
 * @property {ReturnType<typeof setTimeout> | null} toastTimer
 * @property {string} runScope
 * @property {string | null} rescanParentId
 * @property {Set<string>} selectedRunIds
 * @property {boolean} authSetupRequired
 * @property {string} authMode
 * @property {object | null} authStatus
 * @property {object | null} accountAction
 * @property {object | null} currentUser
 * @property {string} pendingMfaToken
 * @property {string} memberCreateMode
 * @property {object[]} membersCache
 * @property {object[]} projectsCache
 * @property {string} projectFilter
 * @property {string} runSearch
 * @property {string} runTagFilter
 * @property {string} runAssigneeFilter
 * @property {string} runReviewerFilter
 * @property {boolean} runFavoriteOnly
 * @property {string} runSort
 * @property {ReturnType<typeof setTimeout> | null} runSearchTimer
 */

/** @returns {AppStore} */
const initialLegacyState = () => ({
  currentRun: null,
  // ⚠️ 以下字段已随任务列表与要求项矩阵迁出，仅为兼容尚未迁移的代码保留。
  // 真正在用的是 core/store.js。app.js 清空后整组删除。
  activeCategory: 'ALL',
  matrixPage: 1,
  searchTerm: '',
  toastTimer: null,
  runScope: 'ACTIVE',
  rescanParentId: null,
  selectedRunIds: new Set(),
  authSetupRequired: false,
  authMode: 'login',
  authStatus: null,
  accountAction: null,
  currentUser: null,
  pendingMfaToken: '',
  memberCreateMode: 'invite',
  membersCache: [],
  projectsCache: [],
  projectFilter: '',
  runSearch: '',
  runTagFilter: '',
  runAssigneeFilter: '',
  runReviewerFilter: '',
  runFavoriteOnly: false,
  runSort: 'updated_desc',
  runSearchTimer: null,
});

export const store = initialLegacyState();

/** Reset compatibility fields along with core/store; never retain old filters or timers. */
export function clearLegacySessionState() {
  clearTimeout(store.toastTimer); clearTimeout(store.runSearchTimer);
  Object.assign(store, initialLegacyState());
}

// Compatibility accessors keep migrated and legacy views on one source of truth.
for (const key of ['currentRun', 'currentUser']) {
  Object.defineProperty(store, key, {
    enumerable: true,
    configurable: false,
    get: () => sharedStore.get()[key],
    set: (value) => sharedStore.set({ [key]: value }),
  });
}
