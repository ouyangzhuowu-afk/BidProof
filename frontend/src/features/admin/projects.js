/**
 * 投标项目。
 *
 * 归档 / 恢复是确认阶梯里唯一落在 **T1（事后撤销）** 的动作：
 * 它完全可逆，撤销窗口内也没有副作用。给它套确认对话框是过度设计 ——
 * 打断的频率远高于挽回的错误；但完全不给反馈又会让人不确定点没点中。
 * 所以做成「立即执行 + 8 秒内可撤销」。
 *
 * 另外两处从 app.js 带过来的修正：
 *
 *   - 旧实现的 loadProjects() 同时负责三件事：渲染管理页列表、填任务列表的
 *     项目下拉、填扫描弹窗的项目下拉。于是管理页的一次刷新会顺手重置
 *     用户在别处选好的筛选。这里只管自己那一份，下拉数据走全局 store。
 *   - `code === 'DEFAULT'` 的项目不给归档按钮。这条规则此前藏在一个内联
 *     三元里，现在是 core/permissions.js 的 isProjectArchivable()。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { toastSuccess, toastWithUndo, toastFromError } from '../../core/toast.js';
import { can, isProjectArchivable, isPermissionError } from '../../core/permissions.js';
import { workspaceApi } from '../../api/index.js';

/** @typedef {import('../../../types/api.js').Project} Project */

/** @type {(() => void)[]} */
let teardown = [];

export function mountProjects() {
  if (teardown.length) return;
  teardown = [
    bind('#project-form', 'submit', (event) => { void submitCreate(event); }),
    delegate('#projects-list', 'click', '[data-project-archive]', (_e, node) => {
      void setArchived(/** @type {HTMLButtonElement} */ (node));
    }),
    delegate('#projects-list', 'click', '#projects-retry', () => { void load(); }),
  ];
  void load();
}

export function unmountProjects() {
  for (const off of teardown) off();
  teardown = [];
}

export async function load() {
  const target = el('#projects-list');
  if (!target) return;

  const manage = can('projects.manage');
  el('#project-form')?.toggleAttribute('hidden', !manage);

  mount(target, skeleton('row', 2));
  try {
    const { projects } = await workspaceApi.listProjects({ includeArchived: true });
    // 别处的项目下拉读这份缓存。写进去而不是各自再拉一次，
    // 是为了让「刚创建的项目」在扫描弹窗里立刻可选。
    store.set({ projects, projectsFetchedAt: Date.now() });
    render(projects, manage);
  } catch (error) {
    mount(target, errorState({
      title: isPermissionError(error) ? '没有查看项目的权限' : '项目加载失败',
      error,
      retryId: isPermissionError(error) ? undefined : 'projects-retry',
    }));
  }
}

/** @param {Project[]} projects @param {boolean} manage */
function render(projects, manage) {
  const target = el('#projects-list');
  if (!target) return;
  if (!projects.length) {
    mount(target, emptyState({
      icon: 'folder-plus',
      title: '还没有项目',
      body: '项目用来把扫描任务分组，也是筛选与权限的边界。',
    }));
    return;
  }

  // 归档的排在后面：它们是历史，不该和在用的项目混在一起按字母排。
  const sorted = [...projects].sort((a, b) =>
    Number(Boolean(a.archived_at)) - Number(Boolean(b.archived_at)));

  mount(target, sorted.map((project) => html`
    <article class="admin-row" data-archived="${String(Boolean(project.archived_at))}">
      <span class="admin-row__icon"><i data-lucide="folder"></i></span>
      <span class="admin-row__main">
        <strong>${project.name}</strong>
        <small>
          <span class="chip chip--mono">${project.code}</span>
          ${project.archived_at ? '已归档，不能新建扫描' : '可创建扫描'}
        </small>
      </span>
      ${manage && isProjectArchivable(project)
        ? html`
          <button class="btn btn--sm btn--ghost" type="button"
                  data-project-archive="${project.project_id}"
                  data-archived="${String(Boolean(project.archived_at))}"
                  data-name="${project.name}">
            ${project.archived_at ? '恢复' : '归档'}
          </button>`
        : html`<span class="chip">${isProjectArchivable(project) ? '' : '默认项目'}</span>`}
    </article>
  `));
}

/* ═══════════════════════════════════════════════════════════════════════════
   动作
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 归档 / 恢复。T1：立即执行，8 秒内可撤销。
 * @param {HTMLButtonElement} button
 */
async function setArchived(button) {
  const projectId = button.dataset.projectArchive;
  const name = button.dataset.name || '项目';
  const next = button.dataset.archived !== 'true';

  await withLoading(button, async () => {
    try {
      await workspaceApi.updateProject(projectId, { archived: next });
      await load();
      toastWithUndo(
        next ? `已归档「${name}」。` : `已恢复「${name}」。`,
        { onUndo: () => { void undo(projectId, !next, name); } },
      );
    } catch (error) {
      toastFromError(error, '项目状态未更新。');
    }
  });
}

/**
 * 撤销必须是一次幂等的反向请求 —— 提示只存在 8 秒，
 * 这期间页面上的任何中间状态都可能已经变了，不能依赖它们。
 *
 * @param {string} projectId @param {boolean} archived @param {string} name
 */
async function undo(projectId, archived, name) {
  try {
    await workspaceApi.updateProject(projectId, { archived });
    await load();
    toastSuccess(`已撤销对「${name}」的更改。`);
  } catch (error) {
    toastFromError(error, '撤销未成功，请手动改回。');
  }
}

/** @param {Event} event */
async function submitCreate(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const data = new FormData(form);
  const name = String(data.get('name') || '').trim();
  if (!name) return;
  // code 留空时传 null 让后端生成，不要传空字符串 ——
  // 后端会把 '' 当成一个合法的空编号存下来。
  const code = String(data.get('code') || '').trim() || null;

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      await workspaceApi.createProject({ name, code });
      form.reset();
      toastSuccess('项目已创建。');
      await load();
    } catch (error) {
      toastFromError(error, '项目未创建。');
    }
  });
}
