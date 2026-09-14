/**
 * 主题。
 *
 * 从 i18n.js 里拆出来：语言和主题是两件不相干的事，旧文件把它们放在一起，
 * 导致任何改主题的提交都要碰 i18n 文件。
 *
 * 新增「跟随系统」档位。旧实现只有 light/dark 二选一，默认 light——
 * 系统已是深色的用户每次打开工作台都会被闪一下。
 */

const STORAGE_KEY = 'bidproof-theme';

/** @typedef {'light' | 'dark' | 'system'} ThemePreference */

const media = window.matchMedia('(prefers-color-scheme: dark)');

/** @returns {ThemePreference} */
export function preference() {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === 'dark' || stored === 'light' ? stored : 'system';
}

/** 实际生效的主题。 @returns {'light' | 'dark'} */
export function resolved() {
  const pref = preference();
  if (pref === 'system') return media.matches ? 'dark' : 'light';
  return pref;
}

export function apply() {
  const theme = resolved();
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  // 与 tokens.css 中的 --canvas 保持一致。
  meta?.setAttribute('content', theme === 'dark' ? '#0e151c' : '#eceef1');
}

/** @param {ThemePreference} next */
export function set(next) {
  if (next === 'system') localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, next);
  apply();
}

/** light → dark → system → light */
export function cycle() {
  const order = /** @type {ThemePreference[]} */ (['light', 'dark', 'system']);
  const next = order[(order.indexOf(preference()) + 1) % order.length];
  set(next);
  return next;
}

/** 用户选了「跟随系统」时，系统变了界面要跟着变。 */
export function start() {
  apply();
  media.addEventListener('change', () => {
    if (preference() === 'system') apply();
  });
}
