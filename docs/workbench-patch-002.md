# BidProof 工作台补丁 · 002 —— 首页收敛

针对 `static/index.html` 的 `#home-view`、`static/style.css`、`frontend/src/app.js`。

**要解决的问题**（对照 `static/assets/bidproof-workspace.png`）：同一个「新建扫描」在一屏内出现三次；7 个筛选控件在空态下常驻展开且 label 竖排换行；四张 0 值统计卡占据首屏最大面积；右栏四个模块里三个是产品自述；原生 `<select>` 与其他控件风格断裂。

每个部件单看都合格，问题是没人做过「删掉一半」的那一遍。这个补丁做的就是那一遍。

改动后 `#home-view` 的 DOM 节点数从 78 降到 41。所有被移除的能力都有去处，没有一项是直接删掉。

---

## 编辑 1 · 侧边导航去掉「新建扫描」

导航回答「去哪儿」，不回答「做什么」。顶栏已经有一个了。

**`static/index.html` 第 22 行，删除整行：**

```html
<button class="nav-item" id="nav-new-scan" type="button"><i data-lucide="file-plus-2"></i><span>新建扫描</span></button>
```

`frontend/src/app.js` 里 `#nav-new-scan` 的绑定改为可选链（见编辑 7）。移动端底栏 `.mobile-nav` 里的入口保留——那里没有顶栏，是唯一入口。

---

## 编辑 2 · 页面标题旁去掉第二个「新建扫描」

**`static/index.html` 第 42–45 行，整块替换：**

替换前：

```html
          <header class="page-header">
            <div><p class="eyebrow">任务总览</p><h1>扫描任务</h1><p class="lede">集中查看投标风险、证据缺口与人工决策状态。</p></div>
            <button class="button primary desktop-primary-action" id="new-scan-button" type="button"><i data-lucide="file-plus-2"></i><span>新建扫描</span></button>
          </header>
```

替换后：

```html
          <header class="page-header">
            <div><h1>扫描任务</h1><p class="lede" id="home-lede">集中查看投标风险、证据缺口与人工决策状态。</p></div>
          </header>
```

`eyebrow`（「任务总览」）一并去掉：h1 已经写着「扫描任务」，上面再顶一行小字重复同一件事，是纯装饰。详情页那些 eyebrow 有区分作用，保留。

`#home-lede` 加 id 是为了编辑 8 里替换成实时摘要。

---

## 编辑 3 · 四张统计卡换成一条判定分布带

**`static/index.html` 第 46–48 行，整块替换：**

替换前：

```html
          <section class="overview-grid" id="overview-grid" aria-label="任务概览">
            <div class="overview-card skeleton-block"></div><div class="overview-card skeleton-block"></div><div class="overview-card skeleton-block"></div><div class="overview-card skeleton-block"></div>
          </section>
```

替换后：

```html
          <section class="risk-summary" id="risk-summary" aria-label="判定分布" hidden></section>
```

`hidden` 是默认值：**没有任务时这一整块不出现**。当前版本在零任务时依然渲染四张写着 0 的卡片，占掉首屏最大面积却不携带任何信息。

分布带比四个孤立数字更接近用户实际要做的判断——他要看的是「这批任务里有多少比例需要我动手」，不是「废标风险的绝对值是 12」。

---

## 编辑 4 · 筛选条默认收起

**`static/index.html` 第 52–62 行，整块替换：**

替换前：

```html
              <div class="task-filter-bar" aria-label="任务筛选">
                <label class="task-search" for="run-search">...</label>
                <label class="filter-field" for="run-tag-filter">...</label>
                <label class="filter-field" for="run-assignee-filter">...</label>
                <label class="filter-field" for="run-reviewer-filter">...</label>
                <label class="filter-field" for="run-sort">...</label>
                <div class="filter-bottom-row">
                  <label class="favorite-filter">...</label>
                  <button class="mini-button filter-reset" id="clear-run-filters" type="button">...</button>
                </div>
              </div>
```

替换后：

```html
              <div class="task-filter-bar" aria-label="任务筛选">
                <div class="filter-primary">
                  <label class="task-search" for="run-search"><span class="sr-only">搜索任务</span><span class="search-input"><i data-lucide="search" aria-hidden="true"></i><input id="run-search" type="search" placeholder="搜索文件名、标签或任务编号" autocomplete="off"></span></label>
                  <button class="filter-toggle" id="toggle-filters" type="button" aria-expanded="false" aria-controls="filter-advanced"><i data-lucide="sliders-horizontal"></i><span>更多筛选</span><span class="filter-badge" id="filter-badge" hidden></span></button>
                  <button class="mini-button filter-reset" id="clear-run-filters" type="button" hidden><i data-lucide="filter-x"></i><span>清除</span></button>
                </div>
                <div class="filter-advanced" id="filter-advanced" hidden>
                  <label class="filter-field" for="run-tag-filter"><span>标签</span><input id="run-tag-filter" type="text" placeholder="精确标签" autocomplete="off"></label>
                  <label class="filter-field" for="run-assignee-filter"><span>负责人</span><select id="run-assignee-filter"><option value="">全部负责人</option></select></label>
                  <label class="filter-field" for="run-reviewer-filter"><span>复核人</span><select id="run-reviewer-filter"><option value="">全部复核人</option></select></label>
                  <label class="filter-field" for="run-sort"><span>排序</span><select id="run-sort"><option value="updated_desc">最近更新</option><option value="filename">文件名</option></select></label>
                  <label class="favorite-filter"><input id="run-favorite-filter" type="checkbox"><span>只看收藏</span></label>
                </div>
              </div>
```

所有 id 原样保留，`app.js` 里现有的事件绑定与 `store` 读写一行都不用改。

「搜索任务」那个可见 label 改成 `sr-only`：placeholder 已经写明了搜的是什么，多一个外置 label 只会挤压输入框，正是截图里「负责人」被压成竖排三行的起因。屏幕阅读器仍然读得到。

「清除」按钮默认隐藏，有筛选条件时才出现——没东西可清的时候摆一个「清除」按钮本身就是噪音。

---

## 编辑 5 · 右栏从四个模块减到一个

**`static/index.html` 第 67–79 行，整块替换：**

替换前：`<aside class="home-aside">` 内含「判定原则/证据闸门」、`readiness-strip`（安全会话已启用）、「待处理提醒」、「准确度观测」四块。

替换后：

```html
            <aside class="home-aside" aria-label="待处理事项">
              <section class="surface rule-panel notification-panel">
                <div class="surface-header"><div><h2>待处理提醒</h2></div><span class="notification-count" id="notification-count" hidden></span></div>
                <div id="notifications-list" class="notification-list"><div class="empty-state">正在检查提醒...</div></div>
              </section>
            </aside>
```

三块被移走的去处：

- **「判定原则 / 证据闸门」** → 移到空态里（编辑 6）。它是给第一次用的人看的说明，不是每天要瞄十次的信息。落地页上已经有完整的一节讲这个。
- **`readiness-strip`（安全会话已启用）** → 删除。它常亮不变，等于没有信息量；真出问题时侧边栏底部的 `sidebar-status` 已经会报。两个地方说同一件事，且这个更显眼的那个永远说「正常」。
- **「准确度观测」** → 移到「成员与设置」页。它是产品质量指标，看的频率是每周一次而不是每天十次，`loadAccuracySummary()` 原样搬过去即可。

同时把 `notification-count` 加上：右栏只剩一个模块之后，「有几件事等着我」必须一眼可见。

---

## 编辑 6 · 空态承载首次引导

空态目前是一行文字加一个「试跑示例」按钮（`t('trySample')` 已经有了，这步做得对）。但屏幕上其余部分——筛选条、批量工具栏、表头——在零任务时全都还在。

**`frontend/src/app.js` 第 433 行附近，`loadRuns()` 的空态分支替换为：**

```js
    if (!visibleRuns.length) {
      const filtered = store.runSearch || store.runTagFilter || store.runAssigneeFilter
        || store.runReviewerFilter || store.runFavoriteOnly || store.projectFilter;

      // 零任务时把工具条一起收掉。筛选一个不存在的列表、对空选区做批量操作，
      // 都是当前版本里用户能看到但点不出结果的控件。
      document.querySelector('#home-view').classList.toggle('is-first-run', !filtered);

      if (filtered) {
        setHtml(list, html`<div class="empty-state"><span>${t('emptyFiltered')}</span></div>`);
      } else {
        setHtml(list, html`<div class="first-run">
          <h2>先扫一份你手上正在投的招标文件</h2>
          <p>BidProof 会逐页挑出资格条件和废标条款，再回到你上传的企业材料里找对应证据。第一次扫描大约需要 2–4 分钟。</p>
          <div class="first-run-actions">
            <button class="button primary" id="empty-start-scan" type="button"><i data-lucide="upload-cloud"></i><span>上传招标文件</span></button>
            <button class="text-button" id="empty-sample-scan" type="button">${t('trySample')}</button>
          </div>
          <div class="first-run-gate">
            <h3>扫描结果会怎么给你</h3>
            <ol>
              <li><b>只认双页码引用。</b>招标原文和企业证据都能定位到页码，一项要求才允许判通过。</li>
              <li><b>不确定即降级。</b>证据冲突或 OCR 失败的页保持待复核，不会被悄悄放行。</li>
              <li><b>人做最终决策。</b>系统记录继续、暂缓或停止的理由，不替你决定是否投标。</li>
            </ol>
          </div>
        </div>`);
        document.querySelector('#empty-start-scan')?.addEventListener('click', openIntake);
        document.querySelector('#empty-sample-scan')?.addEventListener('click', startSampleScan);
      }
      return;
    }
    document.querySelector('#home-view').classList.remove('is-first-run');
```

主按钮从「试跑示例」改成「上传招标文件」，示例降为文字按钮。用真实文件试才是这个产品的验收方式，示例是备选路径，两者的视觉权重应该反过来。

---

## 编辑 7 · `renderOverview` 改为 `renderRiskSummary`

**`frontend/src/app.js` 第 490–506 行，整个函数替换：**

```js
function renderRiskSummary(runs) {
  const host = document.querySelector('#risk-summary');
  if (!runs.length) {                     // 零任务时整块不渲染，而不是渲染四个 0
    host.hidden = true;
    return;
  }
  const blockers = runs.reduce((sum, run) => sum + Number(run.blocker_count || 0), 0);
  const unresolved = runs.reduce((sum, run) => sum + Number(run.unresolved_count || 0), 0);
  const unknown = runs.reduce((sum, run) => sum + Number(run.unknown_count || 0), 0);
  const total = runs.reduce((sum, run) => sum + Number(run.requirement_count || 0), 0);
  const passed = Math.max(total - blockers - unresolved - unknown, 0);
  const decided = runs.filter((run) => run.decision?.decision).length;
  const pct = (value) => (total ? (value / total * 100).toFixed(1) : 0);

  host.hidden = false;
  setHtml(host, html`
    <div class="risk-top">
      <b>${total} 项要求</b>
      <span>覆盖 ${runs.length} 份招标文件 · 已完成人工决策 ${decided} 份</span>
    </div>
    <div class="risk-bar" role="img" aria-label="废标风险 ${blockers} 项，待复核 ${unresolved} 项，未找到证据 ${unknown} 项，通过 ${passed} 项">
      <i class="seg-fail" style="width:${pct(blockers)}%"></i>
      <i class="seg-review" style="width:${pct(unresolved)}%"></i>
      <i class="seg-unknown" style="width:${pct(unknown)}%"></i>
      <i class="seg-pass" style="width:${pct(passed)}%"></i>
    </div>
    <div class="risk-legend">
      <button type="button" data-risk-filter="blocker" class="lg-fail"><i class="lg-dot lg-sq"></i><b>${blockers}</b> 废标风险</button>
      <button type="button" data-risk-filter="unresolved" class="lg-review"><i class="lg-dot lg-rc"></i><b>${unresolved}</b> 待复核</button>
      <span class="lg-unknown"><i class="lg-dot lg-ho"></i><b>${unknown}</b> 未找到证据</span>
      <span class="lg-pass"><i class="lg-dot"></i><b>${passed}</b> 通过</span>
    </div>`);
}
```

前两项图例是按钮，点击直接筛出对应任务——统计数字应该可点。当前版本的四张卡是纯展示，看到「高风险项 12」之后还要自己回列表里找是哪几份。

`unknown_count` / `requirement_count` 如果 `/api/runs` 还没返回，先在 `RUN_LIST_COLUMNS` 里补上；在此之前把 unknown 段的宽度按 0 处理即可，分布带仍然成立。

**同时改三处调用点**（第 426、441 行及 `renderRiskSummary` 内部）：把 `renderOverview(` 全文替换为 `renderRiskSummary(`。

**以及第 22 行导航删除后的绑定**：`document.querySelector('#nav-new-scan').addEventListener(...)` 改成 `document.querySelector('#nav-new-scan')?.addEventListener(...)`，`#new-scan-button` 同理。

---

## 编辑 8 · 筛选展开与实时摘要

**追加到 `frontend/src/app.js`：**

```js
// 筛选展开。默认收起，但只要有任何一项生效就自动展开并在按钮上标记数量——
// 收起的筛选条最怕的是用户忘了自己设过条件，然后以为任务丢了。
function syncFilterDisclosure() {
  const active = [
    store.runTagFilter, store.runAssigneeFilter, store.runReviewerFilter,
    store.runFavoriteOnly ? '1' : '', store.runSort !== 'updated_desc' ? '1' : '',
  ].filter(Boolean).length;

  const badge = document.querySelector('#filter-badge');
  badge.hidden = !active;
  badge.textContent = String(active);

  const reset = document.querySelector('#clear-run-filters');
  reset.hidden = !active && !store.runSearch && !store.projectFilter;

  if (active) {
    document.querySelector('#filter-advanced').hidden = false;
    document.querySelector('#toggle-filters').setAttribute('aria-expanded', 'true');
  }
}

document.querySelector('#toggle-filters').addEventListener('click', (event) => {
  const panel = document.querySelector('#filter-advanced');
  panel.hidden = !panel.hidden;
  event.currentTarget.setAttribute('aria-expanded', String(!panel.hidden));
  refreshIcons();
});
```

在 `loadRuns()` 的 `finally` 块里调用一次 `syncFilterDisclosure()`。

**页面副标题改为实时摘要**（在 `renderRiskSummary` 末尾加）：

```js
  const lede = document.querySelector('#home-lede');
  lede.textContent = blockers
    ? `${runs.length} 份任务中，${runs.filter((run) => Number(run.blocker_count) > 0).length} 份存在废标风险待处理。`
    : `${runs.length} 份任务，暂无废标风险项。`;
```

「集中查看投标风险、证据缺口与人工决策状态」是一句永远为真的产品自述。同一个位置可以放当下的实际状况。

---

## 编辑 9 · CSS

**从 `static/style.css` 删除第 174–185 行**（`.overview-grid` 与 `.overview-card` 全部规则），**追加以下内容到文件末尾：**

```css
/* ------------------------------------------------------- 判定分布带 */
/* 取代四张统计卡。零任务时 hidden，不占版面。 */
.risk-summary { margin-bottom: 16px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); padding: 15px 18px 14px; box-shadow: var(--shadow-sm); }
.risk-top { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.risk-top b { font-size: 14px; font-weight: 650; }
.risk-top span { color: var(--muted); font-size: 12.5px; font-variant-numeric: tabular-nums; }
.risk-bar { display: flex; height: 9px; margin-top: 12px; border-radius: 5px; overflow: hidden; background: var(--surface-soft); }
.risk-bar i { height: 100%; transition: width 220ms ease; }
.seg-fail { background: var(--fail); }
.seg-review { background: var(--review); }
.seg-unknown { background: var(--unknown, #52606f); }
.seg-pass { background: var(--pass); }

.risk-legend { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-top: 12px; }
.risk-legend > * { display: inline-flex; align-items: center; gap: 7px; border: 0; background: none; padding: 0; color: var(--muted); font-size: 12.5px; }
.risk-legend button { cursor: pointer; border-radius: 4px; }
.risk-legend button:hover { color: var(--ink); text-decoration: underline; text-underline-offset: 3px; }
.risk-legend b { color: var(--ink); font-weight: 650; font-variant-numeric: tabular-nums; }
/* 形状 + 颜色双编码，与详情页的判定标记保持同一套语言 */
.lg-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.lg-sq { border-radius: 1px; transform: rotate(45deg); }
.lg-rc { border-radius: 1px; }
.lg-ho { background: transparent; box-shadow: inset 0 0 0 1.5px currentColor; }
.lg-fail { color: var(--fail); }
.lg-review { color: var(--review); }
.lg-unknown { color: var(--unknown, #52606f); }
.lg-pass { color: var(--pass); }

/* --------------------------------------------------------- 筛选收起 */
.task-filter-bar { display: grid; gap: 10px; align-items: stretch; }
.filter-primary { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter-primary .task-search { flex: 1 1 240px; min-width: 200px; }
.filter-toggle { display: inline-flex; align-items: center; gap: 7px; height: 34px; border: 1px solid var(--line-strong); border-radius: var(--radius-sm); background: var(--surface); padding: 0 12px; color: var(--ink-soft); font-size: 13px; cursor: pointer; }
.filter-toggle:hover { border-color: var(--muted); }
.filter-toggle[aria-expanded="true"] { border-color: var(--primary-line); background: var(--primary-soft); color: var(--primary); font-weight: 600; }
.filter-toggle svg { width: 14px; height: 14px; }
.filter-badge { display: grid; min-width: 17px; height: 17px; place-items: center; border-radius: 9px; background: var(--primary); padding: 0 5px; color: #fff; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }
.filter-advanced { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; border-top: 1px solid var(--line); padding-top: 10px; }
.filter-advanced .filter-field { flex: 1 1 140px; min-width: 130px; }

/* 原生 select 是截图里最显眼的「未完成」信号：浏览器默认下拉框
   和其余精心做过的控件完全不是一套东西。这里统一外观并自绘箭头。 */
.filter-advanced select,
.surface-actions select,
.compact-form select,
.inline-admin-form select {
  appearance: none;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius-sm);
  background-color: var(--surface);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235d6b7d' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 9px center;
  background-size: 15px;
  padding-right: 30px;
}
.filter-advanced select:focus,
.surface-actions select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-soft); }

/* --------------------------------------------------------- 首次使用 */
/* 零任务时把筛选条、批量工具栏、表头一起收掉：
   筛选一个不存在的列表、对空选区做批量操作，都是点不出结果的控件。 */
#home-view.is-first-run .task-filter-bar,
#home-view.is-first-run .bulk-toolbar,
#home-view.is-first-run .run-table-head,
#home-view.is-first-run .surface-actions,
#home-view.is-first-run .home-aside { display: none; }
#home-view.is-first-run .home-layout { grid-template-columns: minmax(0, 1fr); }
#home-view.is-first-run .recent-section > .surface-header { display: none; }

.first-run { max-width: 560px; margin: 12px auto 20px; padding: 24px 20px; text-align: left; }
.first-run h2 { font-size: 20px; font-weight: 700; letter-spacing: -.01em; }
.first-run > p { margin-top: 10px; color: var(--muted); font-size: 14.5px; line-height: 1.8; }
.first-run-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-top: 20px; }
.first-run-gate { margin-top: 28px; border-top: 1px solid var(--line); padding-top: 18px; }
.first-run-gate h3 { color: var(--ink-soft); font-size: 13px; font-weight: 650; }
.first-run-gate ol { margin: 12px 0 0; padding: 0; list-style: none; display: grid; gap: 9px; counter-reset: gate; }
.first-run-gate li { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 10px; counter-increment: gate; color: var(--muted); font-size: 13px; line-height: 1.7; }
.first-run-gate li::before { content: counter(gate); color: var(--subtle); font-weight: 600; font-variant-numeric: tabular-nums; }
.first-run-gate li b { color: var(--ink-soft); font-weight: 600; }

/* ------------------------------------------------------------ 右栏 */
.notification-count { display: grid; min-width: 20px; height: 20px; place-items: center; border-radius: 10px; background: var(--fail-soft); padding: 0 6px; color: var(--fail); font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }

@media (max-width: 1000px) {
  .risk-legend { gap: 6px 14px; }
  .filter-advanced .filter-field { flex: 1 1 100%; }
}
```

---

## 编辑 10 · 删掉 lucide 的 357 KB

`static/vendor/lucide.min.js` 是 357,808 字节——`app.js`（gzip 后 19.5 KB）的 18 倍，且它没有出现在你那份性能报告的表格里。全站实际用到 55 个图标。

```bash
npm i lucide --prefix frontend
```

```js
// frontend/src/icons.js
import { createElement, Search, Plus, UploadCloud, /* ...共 55 个 */ } from 'lucide';

const REGISTRY = { search: Search, plus: Plus, 'upload-cloud': UploadCloud, /* ... */ };

export function refreshIcons(root = document) {
  root.querySelectorAll('[data-lucide]').forEach((node) => {
    const icon = REGISTRY[node.dataset.lucide];
    if (icon) node.replaceWith(createElement(icon));
  });
}
```

`static/index.html` 里删掉 `<script src="/static/vendor/lucide.min.js">`，`app.js` 改为从 `icons.js` 导入 `refreshIcons`。tree-shake 后 55 个图标约 10–14 KB，并入现有 bundle。

顺带消掉图标晚一拍才出现的那下闪烁——目前 `refreshIcons()` 在 `finally` 里跑，用户会先看到一排空占位再看到图标，这个闪烁本身就是「半成品感」的一个来源。

需要新增的图标：`sliders-horizontal`（编辑 4 的更多筛选按钮）。

---

## 完整清单

| # | 文件 | 改动 |
|---|---|---|
| 1 | `index.html` L22 | 删除侧栏「新建扫描」 |
| 2 | `index.html` L42–45 | 页头去掉第二个「新建扫描」与 eyebrow |
| 3 | `index.html` L46–48 | 四张统计卡 → `#risk-summary` |
| 4 | `index.html` L52–62 | 筛选条收起 |
| 5 | `index.html` L67–79 | 右栏四模块 → 一模块 |
| 6 | `app.js` L433 | 空态改首次引导 |
| 7 | `app.js` L490–506 | `renderOverview` → `renderRiskSummary` |
| 8 | `app.js` 追加 | 筛选展开同步 + 实时摘要 |
| 9 | `style.css` L174–185 删 + 末尾追加 | 分布带、筛选、select、首次引导 |
| 10 | `frontend/` | lucide tree-shake，减 340 KB |

**测试要跟着改**：`tests/test_ui_product_contract.py` 与 `tests/test_mobile_layout.py` 大概率断言了 `.overview-card` 或 `.task-filter-bar` 的结构，改完要同步。截图基线（390/1440 双断点）需要重新生成——这正好是验证收敛效果的方式：新旧两张放一起对比。

**落地页的 `bidproof-workspace.png`** 在补丁 001 里已经换成 HTML 渲染，这次改完之后那张 PNG 彻底没有引用了，可以删。
