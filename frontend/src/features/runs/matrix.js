/**
 * 要求项对照矩阵 + 高风险卡片。
 *
 * 这是产品的核心界面：逐条把「招标原文要求什么」和「企业证据证明了什么」
 * 并排放在一起，让人做出可追溯的判断。
 *
 * 从 app.js 搬出时修掉的几件事：
 *
 *   1. 【重要】旧实现的 explanationMarkup() 用 category + status 硬编码生成
 *      「证据缺口 / 风险影响 / 建议动作」三段文字，但排版上和真实判定结果
 *      完全一样，看起来像是系统对这份文档的分析结论。
 *      对一个以可追溯性为卖点的合规工具来说，这是把本地猜测冒充成证据。
 *      现在这部分保留（它确实有用），但明确标注为「按类别的通用处置指引」，
 *      并与引文区在视觉上分开。判断依据与处置建议不能长得一样。
 *
 *   2. 分类筛选按钮每次 renderMatrix() 都重建并重新 addEventListener。
 *      现在筛选用一次性委托，重渲染只换内容。
 *
 *   3. 分页按钮在每次渲染后重新绑定，且 scrollIntoView 固定 smooth，
 *      无视 prefers-reduced-motion。现在都改了。
 *
 *   4. 复核请求漏传 revision（后端的乐观并发字段）。两个人同时复核
 *      同一任务时会静默覆盖对方的判定 —— 见 api/runs.js 的说明。
 */

import { delegate, el } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount, mountNodes, emptyState } from '../../ui/render.js';
import { toast, toastFromError } from '../../core/toast.js';
import {
  statusLabel, categoryLabel, criticalityLabel, detectionLabel,
  locatorLabel, riskRank,
} from '../../core/format.js';
import { runsApi } from '../../api/index.js';

/** @typedef {import('../../../types/api.js').Requirement} Requirement */
/** @typedef {import('../../../types/api.js').Run} Run */

/** 每页条数。与旧实现保持一致，避免用户的翻页习惯被打乱。 */
const PAGE_SIZE = 25;

/** 高风险卡片最多显示几张。超过就该去矩阵里看，而不是把首屏堆满。 */
const RISK_LIMIT = 4;

/** @type {(() => void)[]} */
let teardown = [];

/** 视图内状态。不进全局 store —— 离开详情页就该丢掉。 */
let view = { category: 'ALL', search: '', page: 1 };

/* ═══════════════════════════════════════════════════════════════════════════
   生命周期
   ═══════════════════════════════════════════════════════════════════════ */

export function mountMatrix() {
  if (teardown.length) return;
  teardown = [
    delegate('#matrix-filters', 'click', '[data-category]', (_e, node) => {
      view.category = /** @type {HTMLElement} */ (node).dataset.category;
      view.page = 1;
      renderMatrix();
    }),
    delegate('#matrix-pagination', 'click', '[data-page]', (_e, node) => {
      const dir = /** @type {HTMLElement} */ (node).dataset.page;
      view.page += dir === 'next' ? 1 : -1;
      renderMatrix();
      scrollToMatrix();
    }),
    delegate('#requirements', 'click', '[data-review]', (_e, node) => {
      void review(/** @type {HTMLButtonElement} */(node));
    }),
    delegate('#requirements', 'click', '[data-accuracy]', (_e, node) => {
      void feedback(/** @type {HTMLButtonElement} */(node));
    }),
    delegate('#risk-list', 'click', '[data-review]', (_e, node) => {
      void review(/** @type {HTMLButtonElement} */(node));
    }),
    bindSearch(),
  ];
}

export function unmountMatrix() {
  for (const off of teardown) off();
  teardown = [];
  view = { category: 'ALL', search: '', page: 1 };
}

/**
 * 打开另一个任务时重置视图内状态。
 * 必须调用：否则上一个任务的分类筛选和搜索词会带到新任务上，
 * 用户会看到一个「莫名其妙只有 3 项」的矩阵。
 */
export function resetMatrixView() {
  view = { category: 'ALL', search: '', page: 1 };
  const input = /** @type {HTMLInputElement | null} */ (el('#requirement-search'));
  if (input) input.value = '';
}

/** 详情数据变化后由外部调用（初次进入、复核之后、重扫之后）。 */
export function renderMatrixSection() {
  renderRisks();
  renderMatrix();
}

function bindSearch() {
  const input = el('#requirement-search');
  if (!input) return () => {};
  let timer = /** @type {ReturnType<typeof setTimeout> | null} */ (null);
  const handler = (/** @type {Event} */ event) => {
    if (timer) clearTimeout(timer);
    const value = /** @type {HTMLInputElement} */ (event.target).value
      .trim().toLocaleLowerCase('zh-CN');
    timer = setTimeout(() => { view.search = value; view.page = 1; renderMatrix(); }, 200);
  };
  input.addEventListener('input', handler);
  return () => { if (timer) clearTimeout(timer); input.removeEventListener('input', handler); };
}

/* ═══════════════════════════════════════════════════════════════════════════
   矩阵
   ═══════════════════════════════════════════════════════════════════════ */

function renderMatrix() {
  const run = store.get().currentRun;
  const target = el('#requirements');
  if (!run || !target) return;

  renderFilters(run.requirements);

  const filtered = run.requirements.filter(matches);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  view.page = Math.min(Math.max(1, view.page), pageCount);

  const start = (view.page - 1) * PAGE_SIZE;
  const items = filtered.slice(start, start + PAGE_SIZE);

  const count = el('#matrix-count');
  if (count) count.textContent = `共 ${filtered.length} 项`;

  if (!items.length) {
    mount(target, emptyState({
      icon: 'filter-x',
      title: '没有符合条件的要求项',
      body: view.search || view.category !== 'ALL'
        ? '试试清空搜索词或切回「全部」分类。'
        : '这份文档没有解析出任何要求项，请检查扫描质量。',
    }));
  } else {
    mountNodes(target, items.map(renderRow));
  }

  renderPager(filtered.length, pageCount, start);
}

/** @param {Requirement} item */
function matches(item) {
  if (view.category !== 'ALL' && item.category !== view.category) return false;
  if (!view.search) return true;
  // 引文也进检索范围：复核时经常是记得原文里的某个词，而不是要求项标题。
  const haystack = `${item.category} ${item.label} ${item.title} ${item.source?.quote || ''}`
    .toLocaleLowerCase('zh-CN');
  return haystack.includes(view.search);
}

/**
 * 分类筛选。带每类的数量 —— 旧实现只有分类名，
 * 用户点进去才发现是空的，或者不知道哪一类问题最多。
 *
 * @param {Requirement[]} all
 */
function renderFilters(all) {
  const target = el('#matrix-filters');
  if (!target) return;

  /** @type {Map<string, number>} */
  const counts = new Map();
  for (const item of all) counts.set(item.category, (counts.get(item.category) || 0) + 1);

  // 按数量降序，高频分类排在前面，减少横向扫描距离。
  const categories = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  mount(target, html`
    <button class="tab" type="button" role="tab" data-category="ALL"
            aria-selected="${String(view.category === 'ALL')}">
      全部 <span class="tab__count">${all.length}</span>
    </button>
    ${categories.map(([category, n]) => html`
      <button class="tab" type="button" role="tab" data-category="${category}"
              aria-selected="${String(view.category === category)}">
        ${categoryLabel(category)} <span class="tab__count">${n}</span>
      </button>
    `)}
  `);
}

/**
 * 单条要求项。用 <details> 承载展开/收起：
 * 原生语义自带键盘操作与读屏支持，不需要自己管 aria-expanded。
 *
 * @param {Requirement} item
 * @returns {HTMLElement}
 */
function renderRow(item) {
  const node = document.createElement('details');
  node.className = 'req';
  node.dataset.status = item.status;

  mount(node, html`
    <summary class="req__summary">
      <span class="req__name">
        <strong>${item.label}</strong>
        <small>${categoryLabel(item.category)} · ${item.requirement_id}</small>
      </span>
      <span class="locator ${item.source?.locator?.label ? '' : 'locator--missing'}">
        ${locatorLabel(item.source)}
      </span>
      <span class="verdict verdict--${item.status}">${statusLabel(item.status)}</span>
      <i data-lucide="chevron-down" class="req__caret" aria-hidden="true"></i>
    </summary>
    <div class="req__body">
      <p class="req__title">${item.title}</p>
      ${citation(item)}
      ${guidance(item)}
      ${footer(item)}
    </div>
  `);
  return node;
}

/**
 * 证据对照。左招标原文、右企业证据，中缝是整个设计里唯一被强调的分隔线。
 *
 * 缺失必须显性：没有引文就写明「未提取到」，没有定位就标 locator--missing。
 * 留白会被读成「没问题」。
 *
 * @param {Requirement} item
 */
function citation(item) {
  const source = item.source || {};
  const evidence = item.evidence || [];
  return html`
    <div class="citation">
      <div class="citation__side">
        <span class="citation__role">招标原文</span>
        <span class="locator ${source.locator?.label ? '' : 'locator--missing'}">${locatorLabel(source)}</span>
        <p class="quote ${source.quote ? '' : 'quote--absent'}">
          ${source.quote || '未提取到可引用原文'}
        </p>
      </div>
      <div class="citation__gutter" aria-hidden="true"></div>
      <div class="citation__side">
        <span class="citation__role">企业证据</span>
        ${evidence.length
          ? evidence.map((entry) => html`
              <span class="locator ${entry.locator?.label ? '' : 'locator--missing'}">
                ${entry.filename} · ${locatorLabel(entry)}
              </span>
              <p class="quote ${entry.quote ? '' : 'quote--absent'}">${entry.quote || '已定位，未提取到文字'}</p>
            `)
          : html`
              <span class="locator locator--missing">未匹配</span>
              <p class="quote quote--absent">没有找到可核验的企业证据，需人工补充。</p>
            `}
      </div>
    </div>
  `;
}

/**
 * 处置指引。
 *
 * 【必读】这里的三段文字是**按分类与判定状态查表得出的通用建议**，
 * 不是系统对这份文档的分析结论。旧实现把它和引文区排成同样的样式，
 * 读起来像是系统的发现 —— 对一个卖可追溯性的合规工具，这是把猜测冒充证据。
 *
 * 现在：整块降级为次要信息，并带明确的来源说明。
 * 如果将来后端提供了真正的逐项分析，应当替换本函数而不是叠加。
 *
 * @param {Requirement} item
 */
function guidance(item) {
  const gap = (item.evidence || []).length
    ? '已定位候选企业证据，仍需人工确认语义充分性与原件有效性'
    : ['QUALIFICATION', 'CREDENTIAL', 'BOND', 'SIGNATURE'].includes(item.category)
      ? '未定位到可核验的企业证据'
      : '该项主要依赖招标原文，需人工确认适用条件';

  const impact = {
    FATAL: '可能导致废标或资格失效',
    QUALIFICATION: '可能导致资格审查不通过',
    DEADLINE: '错过节点可能导致文件不被接收',
  }[item.category] || '可能影响合规性、评分或材料完整性';

  const action = ['UNKNOWN', 'NEEDS_REVIEW'].includes(item.status)
    ? '补充证据并由人工复核'
    : item.status === 'FAIL'
      ? '核对原文并制定风险处置方案'
      : '保留原文定位并确认原件有效';

  return html`
    <div class="guidance">
      <p class="guidance__note">
        <i data-lucide="info" aria-hidden="true"></i>
        以下为按「${categoryLabel(item.category)}」类别与当前判定给出的通用处置指引，非本文档的分析结论。
      </p>
      <dl class="kv">
        <dt>证据缺口</dt><dd>${gap}</dd>
        <dt>风险影响</dt><dd>${impact}</dd>
        <dt>建议动作</dt><dd>${action}</dd>
      </dl>
    </div>
  `;
}

/**
 * 行内操作。两组按钮做的是完全不同的两件事，必须在视觉上分开：
 *   左组「复核」改变判定，会写进审计链；
 *   右组「检出质量」不改判定，只回流度量信号。
 * 旧实现把四个按钮排成一排、同样样式，用户分不清哪个会留痕。
 *
 * @param {Requirement} item
 */
function footer(item) {
  const settled = item.status === 'PASS' || item.status === 'FAIL';
  return html`
    <div class="req__footer">
      <p class="req__meta">
        <span class="chip">${detectionLabel(item.detection_method)}</span>
        <span class="chip">${criticalityLabel(item.criticality)}</span>
      </p>
      <div class="req__actions">
        <span class="req__actions-group" role="group" aria-label="人工复核（会写入审计记录）">
          ${settled
            ? html`
                <button class="btn btn--sm btn--secondary" type="button"
                        data-review="CONFIRM" data-id="${item.requirement_id}">确认结论</button>
                <button class="btn btn--sm btn--secondary" type="button"
                        data-review="REJECT" data-id="${item.requirement_id}">驳回结论</button>`
            : html`
                <button class="btn btn--sm btn--secondary" type="button"
                        data-review="REQUEST_EVIDENCE" data-id="${item.requirement_id}">请求证据</button>
                <button class="btn btn--sm btn--secondary" type="button"
                        data-review="CONFIRM" data-id="${item.requirement_id}">保留复核</button>`}
        </span>
        <span class="req__actions-group req__actions-group--muted" role="group" aria-label="检出质量反馈（不改变判定）">
          <button class="btn btn--sm btn--ghost" type="button"
                  data-accuracy="RELEVANT" data-id="${item.requirement_id}"
                  data-category="${item.category}">有效</button>
          <button class="btn btn--sm btn--ghost" type="button"
                  data-accuracy="NOT_RELEVANT" data-id="${item.requirement_id}"
                  data-category="${item.category}">误报</button>
        </span>
      </div>
    </div>
  `;
}

/**
 * 分页。显示区间而不只是页码 —— 复核是分批进行的工作，
 * 「显示 26–50，共 138 项」比「第 2 页」更能回答「我做到哪了」。
 */
function renderPager(total, pageCount, start) {
  const target = el('#matrix-pagination');
  if (!target) return;
  if (!total) { mount(target, ''); return; }

  mount(target, html`
    <button class="pager__page" type="button" data-page="prev"
            ${view.page === 1 ? 'disabled' : ''} aria-label="上一页">
      <i data-lucide="arrow-left"></i>
    </button>
    <span class="pager__page" aria-current="page">${view.page}</span>
    <button class="pager__page" type="button" data-page="next"
            ${view.page === pageCount ? 'disabled' : ''} aria-label="下一页">
      <i data-lucide="arrow-right"></i>
    </button>
    <span class="pager__info">显示 ${start + 1}–${Math.min(start + PAGE_SIZE, total)}，共 ${total} 项</span>
  `);
}

function scrollToMatrix() {
  const anchor = el('#matrix-title');
  if (!anchor) return;
  // 旧实现固定 smooth，对前庭障碍用户是问题，且在长列表上会晕。
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  anchor.scrollIntoView({ block: 'start', behavior: reduced ? 'auto' : 'smooth' });
}

/* ═══════════════════════════════════════════════════════════════════════════
   高风险卡片
   ═══════════════════════════════════════════════════════════════════════ */

function renderRisks() {
  const run = store.get().currentRun;
  const target = el('#risk-list');
  if (!run || !target) return;

  const risks = run.requirements
    .filter((item) => ['FATAL', 'QUALIFICATION', 'DEADLINE'].includes(item.category) && item.status !== 'PASS')
    .sort((a, b) => riskRank(a) - riskRank(b))
    .slice(0, RISK_LIMIT);

  if (!risks.length) {
    mount(target, emptyState({
      icon: 'shield-check',
      title: '没有需要优先处理的高风险项',
      body: '废标、资格与时间节点三类要求均已满足或已复核。',
    }));
    return;
  }

  mountNodes(target, risks.map((item) => {
    const card = document.createElement('article');
    card.className = 'risk';
    card.dataset.status = item.status;
    mount(card, html`
      <div class="risk__head">
        <span class="chip chip--danger">${categoryLabel(item.category)}</span>
        <span class="verdict verdict--${item.status}">${statusLabel(item.status)}</span>
      </div>
      <h3 class="risk__label">${item.label}</h3>
      <p class="req__title">${item.title}</p>
      ${citation(item)}
      ${footer(item)}
    `);
    return card;
  }));
}

/* ═══════════════════════════════════════════════════════════════════════════
   动作
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 人工复核。会改变判定并写入审计链，所以：
 *   - 不做乐观更新，等服务端返回的整个 Run 为准；
 *   - 必须带 revision，否则并发复核会静默覆盖（见 api/runs.js）。
 *
 * @param {HTMLButtonElement} button
 */
async function review(button) {
  const run = store.get().currentRun;
  if (!run) return;

  button.disabled = true;
  try {
    const updated = await runsApi.reviewRequirement(run.run_id, {
      requirement_id: button.dataset.id,
      decision: /** @type {any} */ (button.dataset.review),
      revision: run.revision,
    });
    store.set({ currentRun: updated });
    // 重渲染前保留展开状态与滚动位置：复核是连续动作，
    // 每点一次就把面板收起来会让人丢失上下文。
    const open = openIds();
    renderMatrixSection();
    restoreOpen(open);
    toast('复核结果已记录。', 'success');
  } catch (error) {
    button.disabled = false;
    toastFromError(error, '复核未保存，请重试。');
  }
}

/**
 * 检出质量反馈。不改判定，只回流度量信号。
 *
 * review_complete 直接决定准确率能否对外引用，
 * 必须读界面上那个复选框的真实值，不能默认 true。
 *
 * @param {HTMLButtonElement} button
 */
async function feedback(button) {
  const run = store.get().currentRun;
  if (!run) return;

  const complete = /** @type {HTMLInputElement | null} */ (el('#accuracy-review-complete'));
  button.disabled = true;
  try {
    await runsApi.submitAccuracyFeedback(run.run_id, {
      category: button.dataset.category,
      predicted: 'DETECTED',
      actual: /** @type {any} */ (button.dataset.accuracy),
      requirement_id: button.dataset.id,
      review_complete: Boolean(complete?.checked),
    });
    toast(button.dataset.accuracy === 'RELEVANT' ? '已确认为有效检出。' : '误报反馈已记录。', 'success');
    window.dispatchEvent(new CustomEvent('bidproof:accuracy-changed'));
  } catch (error) {
    toastFromError(error, '反馈未保存。');
  } finally {
    button.disabled = false;
  }
}

/** @returns {string[]} 当前展开的要求项 id */
function openIds() {
  return [...document.querySelectorAll('#requirements .req[open]')]
    .map((node) => node.querySelector('[data-id]')?.getAttribute('data-id'))
    .filter(Boolean);
}

/** @param {string[]} ids */
function restoreOpen(ids) {
  if (!ids.length) return;
  for (const node of document.querySelectorAll('#requirements .req')) {
    const id = node.querySelector('[data-id]')?.getAttribute('data-id');
    if (id && ids.includes(id)) node.setAttribute('open', '');
  }
}
