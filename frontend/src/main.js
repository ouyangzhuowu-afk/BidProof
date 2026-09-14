/**
 * 应用入口。
 *
 * 批次 1 的原则是「地基先换、房子不动」：这里只负责启动核心设施，
 * 随后仍然加载现有的 app.js。app.js 内部的视图逻辑会在批次 3、4 里
 * 按视图逐个搬进 features/，每搬走一块就从 app.js 里删掉对应的一块。
 *
 * 之所以要有这个入口，而不是继续让 app.js 当入口：
 * 旧的 app.js 在模块顶层就开始 `document.querySelector('#x').addEventListener(...)`，
 * 任何一个 id 缺失都会让整个脚本在第一条语句崩掉、页面全白。
 * 现在启动被包在 try 里，核心设施（主题、图标、鉴权跳转）先就位，
 * 即使业务初始化失败，用户至少能看到一个说明而不是空白页。
 */

import * as theme from './core/theme.js';
import { renderIcons } from './core/icons.js';
import { onUnauthorized } from './core/http.js';
import { setLang, currentLang } from './i18n/index.js';

// 主题必须在首帧之前生效，否则深色用户会被白屏闪一下。
theme.start();
setLang(currentLang());

/** app.js 在被导入时会挂载所有事件与初始化逻辑。 */
async function boot() {
  // 401 处理注入：http 层因此不需要认识任何视图模块。
  onUnauthorized(() => {
    window.dispatchEvent(new CustomEvent('bidproof:unauthorized'));
  });

  renderIcons(document);

  try {
    await import('./app.js');
  } catch (error) {
    console.error('[bidproof] 工作台初始化失败', error);
    showBootFailure(error);
  }
}

/**
 * 启动失败时的兜底界面。没有它，用户看到的是白屏加一行控制台报错。
 * @param {unknown} error
 */
function showBootFailure(error) {
  const main = document.querySelector('#app-main');
  if (!main) return;
  const detail = error instanceof Error ? error.message : String(error);
  main.innerHTML = '';
  const block = document.createElement('div');
  block.className = 'state state--error';
  block.setAttribute('role', 'alert');

  const title = document.createElement('p');
  title.className = 'state__title';
  title.textContent = '工作台没能启动';

  const body = document.createElement('p');
  body.className = 'state__body';
  // textContent：错误信息可能包含来自响应体的内容，不走 HTML 解析。
  body.textContent = `${detail}。请刷新页面重试；若反复出现，请把这条信息提供给管理员。`;

  const retry = document.createElement('button');
  retry.className = 'btn btn--secondary';
  retry.type = 'button';
  retry.textContent = '刷新页面';
  retry.addEventListener('click', () => window.location.reload());

  block.append(title, body, retry);
  main.append(block);
}

boot();
