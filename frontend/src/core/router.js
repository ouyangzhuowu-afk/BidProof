/**
 * Hash 路由。
 *
 * 保持与旧实现完全相同的 URL 形态（#home / #jobs / #admin / #detail/{runId}
 * / #decision/{runId}），因为用户可能已经把详情页链接贴在了工单和邮件里。
 *
 * 相对旧实现的修正：
 *   - 旧版 showView() 里 history.pushState 与 popstate 处理互相触发：
 *     后退 → navigateFromHash() → showHome() → showView() → pushState，
 *     于是「后退」实际上又压入了一条历史记录，连按两次才退得回去。
 *     这里明确区分 navigate()（用户主动跳转，写历史）与 apply()（响应历史，不写）。
 *   - 支持按需加载视图模块，为代码分割留出接口。
 */

/**
 * @typedef {object} Route
 * @property {string} name
 * @property {string} title          页面上下文文案（写入面包屑）
 * @property {(id?: string) => void | Promise<void>} enter
 * @property {boolean} [takesId]
 */

/** @type {Map<string, Route>} */
const routes = new Map();
let fallback = 'home';
/** @type {(route: Route, id?: string) => void} */
let onEnter = () => {};
let applying = false;

/** @param {Route} route */
export function register(route) {
  routes.set(route.name, route);
}

/**
 * @param {object} options
 * @param {string} options.fallback
 * @param {(route: Route, id?: string) => void} options.onEnter 每次进入路由后的公共副作用（高亮导航、滚动、焦点）
 */
export function configure(options) {
  fallback = options.fallback;
  onEnter = options.onEnter;
}

function parse(hash) {
  const clean = hash.replace(/^#/, '');
  if (!clean) return { name: fallback, id: undefined };
  const [name, id] = clean.split('/');
  return { name: routes.has(name) ? name : fallback, id: id || undefined };
}

/**
 * 响应地址栏当前状态。不写历史。
 */
export async function apply() {
  const { name, id } = parse(location.hash);
  const route = routes.get(name);
  if (!route) return;
  applying = true;
  try {
    onEnter(route, id);
    await route.enter(id);
  } finally {
    applying = false;
  }
}

/**
 * 用户主动跳转。写入一条历史记录（相同地址不重复写）。
 * @param {string} name
 * @param {string} [id]
 */
export async function navigate(name, id) {
  const route = routes.get(name);
  if (!route) return;
  const hash = route.takesId && id ? `#${name}/${id}` : `#${name}`;
  if (location.hash !== hash) {
    history.pushState(null, '', hash);
  }
  if (applying) return;
  onEnter(route, id);
  await route.enter(id);
}

export function start() {
  window.addEventListener('popstate', () => { apply(); });
  window.addEventListener('hashchange', () => { if (!applying) apply(); });
  return apply();
}
