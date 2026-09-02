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
 * @property {boolean} authTrialMode
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

/** @type {AppStore} */
export const store = {
  currentRun: null,
  activeCategory: 'ALL',
  matrixPage: 1,
  searchTerm: '',
  toastTimer: null,
  runScope: 'ACTIVE',
  rescanParentId: null,
  selectedRunIds: new Set(),
  authSetupRequired: false,
  authTrialMode: false,
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
};
