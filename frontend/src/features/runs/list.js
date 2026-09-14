/**
 * 任务列表视图。
 *
 * 这是第一个从 app.js 搬出来的视图，也是后续视图的模板。约定：
 *
 *   1. 模块导出 mount() / unmount()，自己管理全部订阅与监听。
 *      路由离开时 unmount() 必须把一切收干净 —— 旧实现从不解绑，
 *      来回切五次视图，同一个筛选框上就挂了五个 input 监听器。
 *   2. 事件一律走委托（core/dom.js 的 delegate），
 *      列表重渲染后不需要重新绑定。旧实现每次 loadRuns() 都要
 *      遍历几十行逐个 addEventListener。
 *   3. 请求状态（loading / empty / error / ok）是显式的四态机，
 *      不是「先塞骨架屏、出错再覆盖」的隐式流程。
 *   4. 本模块不直接拼 URL，也不直接碰 fetch —— 只用 api 层。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { store, isStale, selectors } from '../../core/store.js';
import { html, mount, mountNodes, emptyState, errorState, skeleton } from '../../ui/render.js';
import { toast, toastFromError } from '../../core/toast.js';
import { formatRelative, shortId, decisionLabel, formatPercent } from '../../core/format.js';
import { runsApi, workspaceApi, ApiError } from '../../api/index.js';
import { confirmWithWord } from '../../ui/confirm.js';
import { navigate } from '../../core/router.js';

/** @typedef {import('../../../types/api.js').RunSummary} RunSummary */
/** @typedef {import('../../../types/api.js').RunScope} RunScope */

/** 输入防抖。250ms 是「打字停顿」与「感觉卡顿」之间的经验分界。 */
const SEARCH_DEBOUNCE_MS = 250;

/** @type {(() => void)[]} */
let teardown = [];
/** 正在飞行的列表请求。新请求发出前中止旧的，避免慢响应覆盖快响应。 */
let inflight = /** @type {AbortController | null} */ (null);
/** @type {ReturnType<typeof setTimeout> | null} */
let searchTimer = null;

/* ═══════════════════════════════════════════════════════════════════════════
   生命周期
   ═══════════════════════════════════════════════════════════════════════ */

export function mountRunsView() {
  if (teardown.length) return; // 幂等：重复进入同一路由不重复绑定

  teardown = [
    ...bindToolbar(),
    ...bindList(),
    ...bindBulkBar(),
    // 筛选条件变了就重新取数。订阅切片而不是整个 store，
    // 因此详情页写 currentRun 不会触发列表刷新。
    store.watch((s) => s.runFilters, () => { void load(); }),
    store.watch((s) => s.selectedRunIds, renderBulkBar),
  ];

  syncControlsFromState();
  void load();
  void loadSidePanels();
}

export function unmountRunsView() {
  inflight?.abort();
  inflight = null;
  if (searchTimer) clearTimeout(searchTimer);
  for (const off of teardown) off();
  teardown = [];
}

/* ═══════════════════════════════════════════════════════════════════════════
   取数
   ═══════════════════════════════════════════════════════════════════════ */

async function load() {
  const list = el('#runs-list');
  if (!list) return;

  // 竞态：用户快速改筛选会连发多个请求，返回顺序不保证。
  // 旧实现没有中止，最后显示的是「最慢的那次」的结果。
  inflight?.abort();
  const controller = new AbortController();
  inflight = controller;

  mount(list, skeleton('row', 4));
  setBusy(true);

  try {
    const filters = store.get().runFilters;
    const runs = await runsApi.listRuns(filters, { signal: controller.signal });
    if (controller.signal.aborted) return;

    const visible = runsApi.filterByScope(runs, /** @type {RunScope} */ (filters.scope));
    renderMetrics(visible);
    pruneSelection(visible);

    if (!visible.length) {
      renderEmpty(list);
      return;
    }
    mountNodes(list, visible.map(renderRow));
  } catch (error) {
    if (error instanceof ApiError && error.isAborted) return;
    mount(list, errorState({
      title: '任务列表加载失败',
      error,
      retryId: 'runs-retry',
    }));
  } finally {
    if (inflight === controller) inflight = null;
    setBusy(false);
  }
}

/**
 * 侧栏两块（提醒、准确率）独立加载。
 * 旧实现把它们塞在 loadRuns() 的 try 里，任何一块失败都会让整个列表显示错误态。
 */
async function loadSidePanels() {
  void loadNotices();
  void loadAccuracy();
}

async function loadNotices() {
  const target = el('#runs-notices-body');
  if (!target) return;
  try {
    const { notifications, count } = await workspaceApi.listNotifications();
    if (!notifications.length) {
      mount(target, emptyState({
        icon: 'check-check',
        title: '暂无待处理提醒',
        body: '有作业失败或节点临近时会出现在这里。',
      }));
      return;
    }
    const shown = notifications.slice(0, 6);
    mount(target, html`
      ${shown.map((item) => html`
        <article class="notice" data-severity="${item.severity}">
          <span class="notice__icon">
            <i data-lucide="${item.type === 'SCAN_JOB_FAILED' ? 'triangle-alert' : 'calendar-clock'}"></i>
          </span>
          <span class="notice__body">
            <strong>${item.title}</strong>
            <small>${item.message}${item.run_id ? ` · 任务 ${shortId(item.run_id)}` : ''}</small>
          </span>
        </article>
      `)}
      ${count > shown.length
        ? html`<p class="hint" style="padding: var(--space-3) var(--space-4)">另有 ${count - shown.length} 条提醒，请在对应任务或作业中查看。</p>`
        : ''}
    `);
  } catch (error) {
    mount(target, errorState({ title: '提醒加载失败', error }));
  }
}

/**
 * 准确率。
 *
 * 合规约束（不得移除）：review_population_complete 为 false 时，
 * precision / recall 只是抽样估计，界面必须显式声明，不能呈现为已验证指标。
 */
async function loadAccuracy() {
  const target = el('#runs-accuracy-body');
  if (!target) return;
  try {
    const summary = await workspaceApi.getAccuracyMetrics();
    const verified = Boolean(summary.review_population_complete);
    mount(target, html`
      <div class="accuracy stack stack--tight" data-verified="${String(verified)}" style="padding: var(--space-4)">
        <div class="row row--between">
          <span class="hint">检出准确率</span>
          <span class="accuracy__value">${formatPercent(summary.precision ?? null)}</span>
        </div>
        <div class="row row--between">
          <span class="hint">召回率</span>
          <span class="accuracy__value">${formatPercent(summary.recall ?? null)}</span>
        </div>
        <p class="accuracy__caveat">
          ${verified
            ? `基于 ${summary.sample_size ?? 0} 条已完成全量复核的样本。`
            : '复核样本尚未覆盖全量，以上为抽样估计，不能作为对外承诺的指标。'}
        </p>
      </div>
    `);
  } catch (error) {
    mount(target, errorState({ title: '准确率加载失败', error }));
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   渲染
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {RunSummary[]} runs */
function renderMetrics(runs) {
  const target = el('#runs-metrics');
  if (!target) return;

  const blockers = sum(runs, (r) => r.blocker_count);
  const unresolved = sum(runs, (r) => r.unresolved_count);
  const decided = runs.filter((r) => r.decision?.decision).length;
  const coverage = runs.length ? Math.round((decided / runs.length) * 100) : 0;

  /** @type {[string, number, string, string, string][]} */
  const cards = [
    ['扫描任务', runs.length, '当前范围内', 'files', 'neutral'],
    ['高风险项', blockers, '优先核对资格与废标项', 'shield-alert', 'danger'],
    ['待复核项', unresolved, '尚未形成确定证据链', 'circle-help', 'warning'],
    ['已做决策', decided, `覆盖 ${coverage}% 任务`, 'clipboard-check', 'ok'],
  ];

  mount(target, cards.map(([label, value, note, icon, tone]) => html`
    <div class="metric" data-tone="${tone}" data-zero="${String(value === 0)}">
      <div class="metric__head"><span>${label}</span><i data-lucide="${icon}"></i></div>
      <strong class="metric__value">${value}</strong>
      <small class="metric__note">${note}</small>
    </div>
  `));
}

/**
 * 单行。整行可点（.run-row__link 的 ::after 铺满），
 * 但复选框与收藏按钮通过 z-index 浮在热区之上。
 *
 * @param {RunSummary} run
 * @returns {HTMLElement}
 */
function renderRow(run) {
  const row = document.createElement('article');
  row.className = 'run-row';
  row.dataset.runId = run.run_id;
  row.dataset.risk = run.blocker_count > 0 ? 'blocked'
    : run.unresolved_count > 0 ? 'review'
      : 'clear';
  if (store.get().selectedRunIds.has(run.run_id)) row.dataset.selected = 'true';

  const decision = run.decision?.decision ?? '';
  const favorite = Boolean(run.favorite);

  mount(row, html`
    <label class="run-row__select">
      <input type="checkbox" data-run-select="${run.run_id}"
             ${store.get().selectedRunIds.has(run.run_id) ? 'checked' : ''}
             aria-label="选择 ${run.tender_filename}">
    </label>

    <div class="run-row__main">
      <a class="run-row__link" href="#detail/${run.run_id}" data-run-open="${run.run_id}">
        ${run.tender_filename}
      </a>
      <p class="run-row__meta">
        <span class="chip chip--mono">${shortId(run.run_id)}</span>
        <span>${formatRelative(run.updated_at || run.created_at)}</span>
        ${run.archived_at ? html`<span class="chip">已归档</span>` : ''}
        ${(run.tags || []).slice(0, 3).map((tag) => html`<span class="chip">${tag}</span>`)}
      </p>
    </div>

    <div class="run-row__aside">
      <span class="run-count" data-tone="danger" data-nonzero="${String(run.blocker_count > 0)}">
        <b>${run.blocker_count}</b><span>高风险</span>
      </span>
      <span class="run-count" data-tone="warning" data-nonzero="${String(run.unresolved_count > 0)}">
        <b>${run.unresolved_count}</b><span>待复核</span>
      </span>
      <span class="decision-pill" data-decision="${decision}">
        ${decision ? decisionLabel(decision) : '未决策'}
      </span>
      <button class="icon-btn run-star" type="button"
              data-run-favorite="${run.run_id}"
              aria-pressed="${String(favorite)}"
              aria-label="${favorite ? '取消收藏' : '收藏'} ${run.tender_filename}">
        <i data-lucide="star"></i>
      </button>
    </div>
  `);
  return row;
}

/** @param {Element} list */
function renderEmpty(list) {
  // 「一条都没有」和「筛选之后没有」是两种完全不同的处境，
  // 给同一句话会让新用户以为产品坏了。
  if (selectors.hasRunFilters(store.get())) {
    mount(list, emptyState({
      icon: 'filter-x',
      title: '没有符合条件的任务',
      body: '当前筛选条件下没有任何任务。清除筛选即可看到全部。',
      action: { id: 'runs-clear-filters', label: '清除筛选' },
    }));
    return;
  }
  mount(list, html`
    <div class="runs-onboarding">
      <p class="title-section">还没有扫描任务</p>
      <ol class="runs-onboarding__steps">
        <li>新建扫描，选择要核查的招标文件</li>
        <li>一并上传已有的企业资质与业绩材料</li>
        <li>在作业页查看进度，完成后逐条复核证据</li>
      </ol>
      <button class="btn btn--primary" type="button" id="runs-try-sample">
        <i data-lucide="file-plus-2"></i><span>用一份示例招标文件试跑</span>
      </button>
    </div>
  `);
}

function renderBulkBar() {
  const bar = el('#runs-bulkbar');
  if (!bar) return;
  const selected = store.get().selectedRunIds;
  bar.hidden = selected.size === 0;
  if (bar.hidden) return;

  const scope = store.get().runFilters.scope;
  mount(bar, html`
    <span class="bulkbar__count">已选 ${selected.size} 项</span>
    ${scope === 'ARCHIVED'
      ? html`<button class="btn btn--sm btn--secondary" type="button" data-bulk="RESTORE">恢复</button>`
      : html`<button class="btn btn--sm btn--secondary" type="button" data-bulk="ARCHIVE">归档</button>`}
    <button class="btn btn--sm btn--secondary" type="button" data-bulk="EXPORT">导出报告</button>
    <button class="btn btn--sm btn--danger" type="button" data-bulk="DELETE">删除</button>
    <button class="btn btn--sm btn--ghost" type="button" data-bulk="CLEAR">取消选择</button>
  `);
}

/* ═══════════════════════════════════════════════════════════════════════════
   事件
   ═══════════════════════════════════════════════════════════════════════ */

function bindToolbar() {
  return [
    bind('#runs-search', 'input', (event) => {
      // 防抖只作用于「发请求」，输入框本身立刻响应。
      if (searchTimer) clearTimeout(searchTimer);
      const value = event.target.value.trim();
      searchTimer = setTimeout(() => patchFilters({ search: value }), SEARCH_DEBOUNCE_MS);
    }),

    // 分段控件：role="radiogroup"，点击与方向键都要能切。
    delegate('#runs-scope', 'click', '[data-scope]', (_event, node) => {
      patchFilters({ scope: /** @type {HTMLElement} */ (node).dataset.scope });
    }),
    bind('#runs-scope', 'keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault();
      const options = [...event.currentTarget.querySelectorAll('[data-scope]')];
      const index = options.findIndex((n) => n.getAttribute('aria-checked') === 'true');
      const next = options[(index + (event.key === 'ArrowRight' ? 1 : -1) + options.length) % options.length];
      /** @type {HTMLElement} */ (next).focus();
      patchFilters({ scope: /** @type {HTMLElement} */ (next).dataset.scope });
    }),

    bind('#runs-refresh', 'click', (event) => withLoading(event.currentTarget, load)),

    // 其余筛选控件统一走委托，新增一个筛选项不需要再加一条绑定。
    delegate('#runs-filters', 'change', '[data-filter]', (event, node) => {
      const key = /** @type {HTMLElement} */ (node).dataset.filter;
      const input = /** @type {HTMLInputElement} */ (event.target);
      patchFilters({ [key]: input.type === 'checkbox' ? input.checked : input.value });
    }),

    bind('#runs-clear-filters-btn', 'click', clearFilters),
  ];
}

function bindList() {
  return [
    delegate('#runs-list', 'change', '[data-run-select]', (event, node) => {
      toggleSelection(
        /** @type {HTMLElement} */ (node).dataset.runSelect,
        /** @type {HTMLInputElement} */ (event.target).checked,
      );
    }),

    delegate('#runs-list', 'click', '[data-run-favorite]', (event, node) => {
      event.preventDefault();
      void toggleFavorite(/** @type {HTMLElement} */ (node));
    }),

    // 用真实 <a href="#detail/..."> 承载跳转：中键、Ctrl+点击、
    // 复制链接地址都能用。这里只是拦下左键走 SPA 路由。
    delegate('#runs-list', 'click', '[data-run-open]', (event, node) => {
      const mouse = /** @type {MouseEvent} */ (event);
      if (mouse.metaKey || mouse.ctrlKey || mouse.shiftKey || mouse.button !== 0) return;
      event.preventDefault();
      void navigate('detail', /** @type {HTMLElement} */ (node).dataset.runOpen);
    }),

    // 空状态与错误态里的按钮是渲染出来的，只能用委托。
    delegate('#runs-list', 'click', '#runs-clear-filters', clearFilters),
    delegate('#runs-list', 'click', '#runs-retry', () => { void load(); }),
    delegate('#runs-list', 'click', '#runs-try-sample', (event) => {
      void withLoading(/** @type {Element} */ (event.target).closest('button'), startSample);
    }),
  ];
}

function bindBulkBar() {
  return [
    delegate('#runs-bulkbar', 'click', '[data-bulk]', (_event, node) => {
      void runBulk(/** @type {HTMLElement} */ (node).dataset.bulk, node);
    }),
  ];
}

/* ═══════════════════════════════════════════════════════════════════════════
   动作
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {Record<string, unknown>} patch */
function patchFilters(patch) {
  store.set((current) => ({
    runFilters: { ...current.runFilters, ...patch },
    // 改筛选后旧的选中项可能已经不在列表里，先清空比逐个校验更可预期。
    selectedRunIds: new Set(),
  }));
  syncControlsFromState();
}

function clearFilters() {
  store.set({
    runFilters: {
      scope: 'ACTIVE', projectId: '', search: '', tag: '',
      assigneeId: '', reviewerId: '', favoriteOnly: false, sort: 'updated_desc',
    },
    selectedRunIds: new Set(),
  });
  syncControlsFromState();
}

/** 把 store 的值写回控件。刷新、后退、清除筛选都依赖这一步。 */
function syncControlsFromState() {
  const f = store.get().runFilters;
  setValue('#runs-search', f.search);
  setValue('[data-filter="tag"]', f.tag);
  setValue('[data-filter="projectId"]', f.projectId);
  setValue('[data-filter="assigneeId"]', f.assigneeId);
  setValue('[data-filter="reviewerId"]', f.reviewerId);
  setValue('[data-filter="sort"]', f.sort);
  const favorite = /** @type {HTMLInputElement | null} */ (el('[data-filter="favoriteOnly"]'));
  if (favorite) favorite.checked = f.favoriteOnly;

  for (const node of document.querySelectorAll('#runs-scope [data-scope]')) {
    node.setAttribute('aria-checked', String(/** @type {HTMLElement} */ (node).dataset.scope === f.scope));
  }

  // 让「有几个筛选生效」可见，否则空列表看起来像加载失败。
  const badge = el('#runs-filter-count');
  if (badge) {
    const active = [f.search, f.tag, f.projectId, f.assigneeId, f.reviewerId]
      .filter(Boolean).length + (f.favoriteOnly ? 1 : 0);
    badge.textContent = String(active);
    badge.toggleAttribute('hidden', active === 0);
  }
}

/** @param {string} runId @param {boolean} selected */
function toggleSelection(runId, selected) {
  store.set((current) => {
    const next = new Set(current.selectedRunIds);
    if (selected) next.add(runId); else next.delete(runId);
    return { selectedRunIds: next };
  });
  const row = el(`.run-row[data-run-id="${CSS.escape(runId)}"]`);
  if (row) row.toggleAttribute('data-selected', selected);
}

/** @param {RunSummary[]} visible */
function pruneSelection(visible) {
  const ids = new Set(visible.map((r) => r.run_id));
  const current = store.get().selectedRunIds;
  const kept = new Set([...current].filter((id) => ids.has(id)));
  if (kept.size !== current.size) store.set({ selectedRunIds: kept });
}

/**
 * 收藏。乐观更新：先翻转 UI，失败再翻回来。
 * 这是全站唯一做乐观更新的地方 —— 它没有副作用、失败可逆、
 * 且用户会连续点很多次。判定与决策类操作一律不做乐观更新。
 *
 * @param {HTMLElement} button
 */
async function toggleFavorite(button) {
  const runId = button.dataset.runFavorite;
  const next = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(next));
  try {
    await runsApi.saveMetadata(runId, { favorite: next });
  } catch (error) {
    button.setAttribute('aria-pressed', String(!next));
    toastFromError(error, '收藏状态未能保存。');
  }
}

/**
 * 批量操作。删除走不可逆路径，必须二次确认。
 * @param {string} action
 * @param {Element} button
 */
async function runBulk(action, button) {
  const ids = [...store.get().selectedRunIds];
  if (!ids.length) return;

  if (action === 'CLEAR') {
    store.set({ selectedRunIds: new Set() });
    return;
  }

  if (action === 'DELETE') {
    // T3：不可逆且销毁证据链，必须逐字输入确认词。
    // 批次 4 迁移时这里一度降级成 window.confirm（回车即过），
    // 比旧实现的 confirmDanger 还弱 —— 现在补回。
    const ok = await confirmWithWord({
      title: '永久删除任务',
      body: `将删除 ${ids.length} 个任务及其上传文件与证据链，删除后无法恢复，`
        + '导出过的报告也不再能追溯到原始材料。',
      word: 'DELETE',
      confirmLabel: `永久删除 ${ids.length} 项`,
    });
    if (!ok) return;
  }

  await withLoading(button, async () => {
    try {
      if (action === 'EXPORT') {
        await runsApi.bulkExport(ids);
        toast(`已导出 ${ids.length} 份报告。`, 'success');
        return;
      }
      await runsApi.bulkManage(/** @type {any} */ (action), ids);
      store.set({ selectedRunIds: new Set() });
      toast({
        ARCHIVE: `已归档 ${ids.length} 个任务。`,
        RESTORE: `已恢复 ${ids.length} 个任务。`,
        DELETE: `已删除 ${ids.length} 个任务。`,
      }[action], 'success');
      await load();
    } catch (error) {
      toastFromError(error);
    }
  });
}

/** 空状态的一键试跑。取回示例文件后交给扫描弹窗。 */
async function startSample() {
  try {
    const sample = await workspaceApi.getSampleTender();
    window.dispatchEvent(new CustomEvent('bidproof:start-sample-scan', { detail: sample }));
  } catch (error) {
    toastFromError(error, '示例文件暂不可用。');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   给尚未迁移的 app.js 用的接缝
   -----------------------------------------------------------------------
   过渡期专用。app.js 里还有几处「做完某件事后刷新列表」的调用
   （提交扫描、打开任务、重试作业、提交准确率反馈）。
   这两个导出让它不必知道本模块的内部结构。
   app.js 清空之后，这两个函数连同本节一起删除。
   ═══════════════════════════════════════════════════════════════════════ */

/** 重新拉取任务列表。视图未挂载时是空操作。 */
export async function reloadRuns() {
  if (!el('#runs-list')) return;
  await load();
}

/** 重新拉取准确率面板。提交准确率反馈后调用。 */
export async function reloadAccuracy() {
  await loadAccuracy();
}

/* ═══════════════════════════════════════════════════════════════════════════
   工具
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {boolean} busy */
function setBusy(busy) {
  const list = el('#runs-list');
  // aria-busy 让读屏在加载期间不去朗读半成品内容。
  list?.setAttribute('aria-busy', String(busy));
  const refresh = /** @type {HTMLButtonElement | null} */ (el('#runs-refresh'));
  if (refresh) refresh.disabled = busy;
}

/** @param {string} selector @param {string} value */
function setValue(selector, value) {
  const node = /** @type {HTMLInputElement | null} */ (el(selector));
  if (node && node.value !== value) node.value = value ?? '';
}

/**
 * @template T
 * @param {T[]} items
 * @param {(item: T) => number | undefined} pick
 */
function sum(items, pick) {
  return items.reduce((total, item) => total + Number(pick(item) || 0), 0);
}

/**
 * 成员与项目下拉的选项。缓存有 TTL（core/store.js），
 * 过期才重新拉 —— 旧实现是「取过就永不再取」，改完成员角色后下拉一直是旧值。
 */
export async function ensureFilterOptions() {
  const state = store.get();
  const jobs = [];
  if (!state.members.length || isStale(state.membersFetchedAt)) {
    jobs.push(workspaceApi.listMembers().then(({ members }) =>
      store.set({ members, membersFetchedAt: Date.now() })));
  }
  if (!state.projects.length || isStale(state.projectsFetchedAt)) {
    jobs.push(workspaceApi.listProjects().then(({ projects }) =>
      store.set({ projects, projectsFetchedAt: Date.now() })));
  }
  // 下拉选项取不回来不该阻塞列表，失败静默降级为「全部」。
  await Promise.allSettled(jobs);
}
