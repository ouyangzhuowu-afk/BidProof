/** Evidence-led review cards. All source text passes through html()/mount(). */
import { delegate, el } from '../../core/dom.js';
import { store } from '../../core/store.js';
import { html, mount, mountNodes, emptyState } from '../../ui/render.js';
import { toast, toastFromError } from '../../core/toast.js';
import { statusLabel, categoryLabel, locatorLabel, riskRank } from '../../core/format.js';
import { runsApi } from '../../api/index.js';
import { hasCompleteCitation, latestReview, isHumanConfirmed, getReviewQueueCounts, effectiveStatus, isReviewRequired } from './review-model.js';
import { highlightQuote, quoteTerms, renderEvidenceReader } from './evidence-reader.js';

const PAGE_SIZE = 25;
const RISK_LIMIT = 3;
let teardown = [];
const initialView = () => ({ category: 'ALL', reviewStatus: 'ALL', search: '', page: 1, priorityPage: 0, selectedId: '', sourceContainer: '#risk-list' });
let view = initialView();
let viewEpoch = 0;
let busyRunId = '';
const collapsed = new Set();
const drafts = new Map();
const pendingNotes = new Map();

export function mountMatrix() {
  if (teardown.length) return;
  teardown = [
    delegate('#matrix-filters', 'click', '[data-category]', (_event, node) => {
      view.category = node.dataset.category; view.page = 1; renderMatrix();
    }),
    delegate('#matrix-filters', 'click', '[data-review-status]', (_event, node) => {
      view.reviewStatus = node.dataset.reviewStatus; view.page = 1; renderMatrix();
      el(`#matrix-filters [data-review-status="${view.reviewStatus}"]`)?.focus();
    }),
    delegate('#risk-list', 'click', '[data-risk-page]', (_event, node) => navigatePriority(node.dataset.riskPage)),
    delegate('#review-navigation', 'click', '[data-review-nav]', (_event, node) => navigateReview(node.dataset.reviewNav)),
    delegate('#matrix-pagination', 'click', '[data-page]', (_event, node) => {
      view.page += node.dataset.page === 'next' ? 1 : -1;
      renderMatrix();
      el('#matrix-title')?.scrollIntoView({ block: 'start', behavior: motion() ? 'smooth' : 'auto' });
    }),
    ...['#risk-list', '#requirements'].flatMap((container) => [
      delegate(container, 'click', '[data-review]', (_event, node) => {
        if (node.dataset.review === 'CONFIRM') void review(node);
        else openEditor(node, 'REJECT');
      }),
      delegate(container, 'click', '[data-note]', (_event, node) => openEditor(node, 'NOTE')),
      delegate(container, 'click', '[data-editor-cancel]', (_event, node) => closeEditor(node)),
      delegate(container, 'submit', '[data-review-form]', (event, node) => {
        event.preventDefault(); void saveEditor(node);
      }),
      delegate(container, 'input', '[data-review-text]', (_event, node) => {
        if (node.readOnly) return;
        const draft = drafts.get(node.dataset.id);
        if (draft) { draft.text = node.value; draft.texts[draft.mode] = node.value; }
        updateDraftMarkers(node.dataset.id);
      }),
      delegate(container, 'click', '.review-card__summary', (_event, node) => {
        const card = node.closest('[data-requirement-id]');
        if (card && !card.open) selectSource(card.dataset.requirementId, false, 'tender', container);
      }),
      delegate(container, 'click', '[data-source]', (_event, node) => selectSource(node.dataset.id, true, node.dataset.source, container)),
      delegate(container, 'click', '[data-accuracy]', (_event, node) => { void feedback(node); }),
    ]),
    delegate('#evidence-reader', 'click', '[data-reader-return]', returnToCard),
    bindSearch(),
  ];
}

export function unmountMatrix() {
  teardown.forEach((off) => off()); teardown = []; resetMatrixView();
}

export function resetMatrixView() {
  view = initialView();
  viewEpoch += 1;
  collapsed.clear(); drafts.clear();
  const input = el('#requirement-search'); if (input) input.value = '';
}

export function renderMatrixSection() {
  const open = openIds();
  renderRisks(); renderMatrix(); restoreOpen(open);
  const run = store.get().currentRun;
  if (!run) return;
  const selected = run.requirements.find((item) => item.requirement_id === view.selectedId)
    || priorityItems(run)[0] || run.requirements[0] || null;
  view.selectedId = selected?.requirement_id || '';
  renderEvidenceReader(run, selected, view.search); markSelected(); renderNavigation();
}

function bindSearch() {
  const input = el('#requirement-search');
  if (!input) return () => {};
  let timer;
  const handler = (event) => {
    clearTimeout(timer);
    const value = event.target.value.trim().toLocaleLowerCase('zh-CN');
    timer = setTimeout(() => { view.search = value; view.page = 1; renderMatrix(); }, 180);
  };
  input.addEventListener('input', handler);
  return () => { clearTimeout(timer); input.removeEventListener('input', handler); };
}

function renderMatrix() {
  const run = store.get().currentRun;
  const target = el('#requirements');
  if (!run || !target) return;
  renderFilters(run);
  const filtered = run.requirements.filter(matches).sort((a, b) => riskRank(a) - riskRank(b));
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  view.page = Math.min(Math.max(1, view.page), pageCount);
  const start = (view.page - 1) * PAGE_SIZE;
  const items = filtered.slice(start, start + PAGE_SIZE);
  const count = el('#matrix-count'); if (count) count.textContent = `共 ${filtered.length} 项`;
  if (!items.length) mount(target, emptyState({ icon: 'filter-x', title: '没有符合条件的条款',
    body: view.search || view.category !== 'ALL' || view.reviewStatus !== 'ALL' ? '切换审查状态、清空搜索词或切回「全部」类别试试。' : '暂未提取到条款，请检查扫描质量与上传材料。' }));
  else mountNodes(target, items.map((item) => renderCard(item, false)));
  renderPager(filtered.length, pageCount, start); markSelected();
}

function matches(item) {
  const confirmed = isHumanConfirmed(store.get().currentRun, item);
  if (view.reviewStatus === 'PENDING' && confirmed) return false;
  if (view.reviewStatus === 'CONFIRMED' && !confirmed) return false;
  if (view.category !== 'ALL' && item.category !== view.category) return false;
  if (!view.search) return true;
  return `${item.category} ${categoryLabel(item.category)} ${item.label} ${item.title} ${item.source?.quote || ''} ${(item.evidence || []).map((entry) => `${entry.filename} ${entry.quote}`).join(' ')}`
    .toLocaleLowerCase('zh-CN').includes(view.search);
}

function renderFilters(run) {
  const all = run.requirements;
  const reviewCounts = getReviewQueueCounts(run);
  const counts = new Map();
  all.forEach((item) => counts.set(item.category, (counts.get(item.category) || 0) + 1));
  mount(el('#matrix-filters'), html`
    <div class="review-state-filters" role="group" aria-label="按人工审查状态筛选">
      ${[['PENDING', '待处理', reviewCounts.pending], ['CONFIRMED', '已核销', reviewCounts.confirmed], ['ALL', '全部', reviewCounts.total]].map(([value, label, count]) => html`
        <button type="button" data-review-status="${value}" aria-pressed="${String(view.reviewStatus === value)}">${label}<span>${count}</span></button>`)}
    </div>
    <p class="review-state-help">系统已满足仍需人工核销；存疑驳回的条款继续保留在待处理中。</p>
    <div class="review-category-filters" role="group" aria-label="按条款类别筛选">
    <button class="tab" type="button" data-category="ALL" aria-pressed="${String(view.category === 'ALL')}">全部 <span class="tab__count">${all.length}</span></button>
    ${[...counts.entries()].sort((a, b) => b[1] - a[1]).map(([category, count]) => html`
      <button class="tab" type="button" data-category="${category}" aria-pressed="${String(view.category === category)}">${categoryLabel(category)} <span class="tab__count">${count}</span></button>`)}
    </div>
  `);
}

function priorityItems(run) {
  return run.requirements.filter((item) => item.status !== 'PASS'
    && (item.criticality === 'BLOCKER' || ['FATAL', 'QUALIFICATION', 'DEADLINE'].includes(item.category)))
    .sort((a, b) => riskRank(a) - riskRank(b));
}

function renderRisks() {
  const run = store.get().currentRun; const target = el('#risk-list');
  if (!run || !target) return;
  const items = priorityItems(run); const count = el('#priority-count');
  if (count) count.textContent = `${items.length} 项`;
  if (!items.length) {
    mount(target, emptyState({ icon: 'shield-check', title: '当前没有待处理的优先风险项',
      body: '继续核对下方普通条款；此提示不代表投标合规保证。' })); return;
  }
  const pageCount = Math.ceil(items.length / RISK_LIMIT);
  view.priorityPage = Math.min(view.priorityPage, pageCount - 1);
  const start = view.priorityPage * RISK_LIMIT;
  mountNodes(target, items.slice(start, start + RISK_LIMIT).map((item) => renderCard(item, true)));
  if (items.length > RISK_LIMIT) {
    const pager = document.createElement('nav'); pager.className = 'review-priority-pager';
    pager.setAttribute('aria-label', '优先风险分批核验');
    mount(pager, html`<span>优先风险 ${start + 1}–${Math.min(start + RISK_LIMIT, items.length)} / ${items.length}</span>
      <div><button type="button" class="btn btn--secondary btn--sm" data-risk-page="prev" ${view.priorityPage === 0 ? 'disabled' : ''}>前 3 项</button>
      <button type="button" class="btn btn--secondary btn--sm" data-risk-page="next" ${view.priorityPage === pageCount - 1 ? 'disabled' : ''}>${view.priorityPage === pageCount - 1 ? '已到最后一组' : `继续处理后 ${Math.min(RISK_LIMIT, items.length - start - RISK_LIMIT)} 项`}<i data-lucide="arrow-right" aria-hidden="true"></i></button></div>`);
    target.append(pager);
  }
}

function navigatePriority(direction) {
  const run = store.get().currentRun;
  if (!run) return;
  view.priorityPage = Math.max(0, view.priorityPage + (direction === 'next' ? 1 : -1));
  renderRisks();
  const next = priorityItems(run)[view.priorityPage * RISK_LIMIT];
  if (next) { selectSource(next.requirement_id, false, 'tender', '#risk-list'); returnToCard(); }
}

function navigationState(run) {
  const ordered = [...run.requirements].sort((a, b) => riskRank(a) - riskRank(b));
  const index = ordered.findIndex((item) => item.requirement_id === view.selectedId);
  const later = [...ordered.slice(index + 1), ...ordered.slice(0, Math.max(index, 0))];
  return {
    current: ordered[index], index, total: ordered.length,
    previous: index > 0 ? ordered[index - 1] : null,
    next: later.find((item) => item.requirement_id !== view.selectedId && !isHumanConfirmed(run, item)),
  };
}

function renderNavigation() {
  const run = store.get().currentRun;
  const target = el('#review-navigation');
  if (!run || !target) return;
  const current = navigationState(run);
  const counts = getReviewQueueCounts(run);
  const busy = busyRunId === run.run_id;
  mount(target, html`<div class="review-navigation__context">
      <span>${current.total ? `正在看第 ${Math.max(0, current.index + 1)} / ${current.total} 条` : '暂无可核验的条目'}</span>
      <strong>${current.current?.label || '选择一条要求开始核验'}</strong>
      <small>${!counts.total ? '尚未提取到要求项' : counts.pending ? `${counts.pending} 项待处理` : '全部条款已人工核销'}</small>
    </div><div class="review-navigation__actions">
      <button type="button" class="btn btn--secondary btn--sm" data-review-nav="previous" ${!current.previous || busy ? 'disabled' : ''}><i data-lucide="arrow-left" aria-hidden="true"></i>上一条</button>
      <button type="button" class="btn btn--secondary btn--sm" data-review-nav="next" ${!current.next || busy ? 'disabled' : ''}>下一待办<i data-lucide="arrow-right" aria-hidden="true"></i></button>
    </div>`);
}

function navigateReview(direction) {
  const run = store.get().currentRun;
  if (!run || busyRunId === run.run_id) return;
  const navigation = navigationState(run);
  const item = direction === 'previous' ? navigation.previous : navigation.next;
  if (!item) return;
  // The navigation is explicitly task-wide. Clear only filters hiding the target.
  if (!matches(item)) {
    view.category = 'ALL'; view.reviewStatus = 'ALL'; view.search = '';
    const search = el('#requirement-search'); if (search) search.value = '';
    toast('已切换到全部条款，定位所选待办。');
  }
  const ordered = run.requirements.filter(matches).sort((a, b) => riskRank(a) - riskRank(b));
  const index = ordered.findIndex((entry) => entry.requirement_id === item.requirement_id);
  view.page = Math.floor(index / PAGE_SIZE) + 1;
  view.selectedId = item.requirement_id; view.sourceContainer = '#requirements';
  renderMatrix();
  const card = [...document.querySelectorAll('#requirements [data-requirement-id]')].find((node) => node.dataset.requirementId === item.requirement_id);
  if (card) card.open = true;
  selectSource(item.requirement_id, false, 'tender', '#requirements');
  returnToCard();
}

/** Priority cards open; the complete matrix stays compact and searchable. */
function renderCard(item, priority) {
  const run = store.get().currentRun; const record = latestReview(run, item.requirement_id);
  const node = document.createElement('details');
  node.className = priority ? 'review-card review-card--priority' : 'req review-card review-card--compact';
  const displayStatus = effectiveStatus(item);
  node.dataset.status = displayStatus; node.dataset.requirementId = item.requirement_id; node.dataset.category = item.category;
  node.dataset.reviewRequired = String(isReviewRequired(item));
  if (priority && !collapsed.has(item.requirement_id)) node.open = true;
  mount(node, html`
    <summary class="review-card__summary">
      <span class="review-card__identity"><span class="review-card__category">${categoryLabel(item.category)}</span><strong>${item.label}</strong><small class="review-card__draft" data-draft-for="${item.requirement_id}" ${hasDraft(item.requirement_id) ? '' : 'hidden'}>草稿未保存</small></span>
      <span class="review-card__summary-locator">${locatorLabel(item.source)}</span>
      <span class="review-status review-status--${displayStatus}" data-human-confirmed="${String(isHumanConfirmed(run, item))}"><span aria-hidden="true"></span>${isHumanConfirmed(run, item) ? '已核销通过' : displayStatus === 'PASS' ? '系统已满足 · 待核销' : statusLabel(displayStatus)}</span>
      <i class="review-card__caret" data-lucide="chevron-down" aria-hidden="true"></i>
    </summary>
    <div class="review-card__body">
      <p class="review-card__title">${item.title}</p>
      ${citation(item)}
      ${record?.note ? html`<p class="review-card__saved-note"><i data-lucide="message-square-text" aria-hidden="true"></i>上次复核备注：${record.note}</p>` : ''}
      ${actions(item)}
      <div class="review-editor" data-editor="${item.requirement_id}">${drafts.has(item.requirement_id) ? editor(item.requirement_id) : ''}</div>
      <details class="review-secondary"><summary>检出反馈与处理提示</summary><div>
        <p>通用处理提示：核对适用条件、证明材料有效期与签章。候选匹配仍需人工判断。</p>
        <span>检出质量反馈</span>
        <button type="button" class="btn btn--sm btn--ghost" data-accuracy="RELEVANT" data-id="${item.requirement_id}" data-category="${item.category}">有效检出</button>
        <button type="button" class="btn btn--sm btn--ghost" data-accuracy="NOT_RELEVANT" data-id="${item.requirement_id}" data-category="${item.category}">标为误报</button>
        <small>只记录检出质量，不改变本条判定。</small>
      </div></details>
    </div>
  `);
  return node;
}

function citation(item) {
  const terms = quoteTerms(item, view.search);
  return html`<div class="review-citations">
    <div class="review-citation"><button class="review-citation__source" type="button" data-source="tender" data-id="${item.requirement_id}">
      <i data-lucide="file-text" aria-hidden="true"></i>招标文件 <span>${locatorLabel(item.source)}</span><i data-lucide="arrow-up-right" aria-hidden="true"></i></button>
      <blockquote>${item.source?.quote ? highlightQuote(item.source.quote, terms) : html`<span class="review-citation__missing">未提取到可核验原文</span>`}</blockquote></div>
    <div class="review-citation"><button class="review-citation__source" type="button" data-source="evidence" data-id="${item.requirement_id}">
      <i data-lucide="files" aria-hidden="true"></i>匹配证据 <span>${item.evidence?.length ? locatorLabel(item.evidence[0]) : '待补充'}</span><i data-lucide="arrow-up-right" aria-hidden="true"></i></button>
      <blockquote>${item.evidence?.length ? highlightQuote(item.evidence[0].quote || '已定位，尚无可核验摘录。', terms) : html`<span class="review-citation__missing">暂无可核验的企业证据，请补充材料。</span>`}</blockquote>
      ${item.evidence?.length ? html`<small>${item.evidence[0].filename}${item.evidence.length > 1 ? ` · 另有 ${item.evidence.length - 1} 处证据` : ''}</small>` : ''}</div>
  </div>`;
}

function actions(item) {
  const run = store.get().currentRun;
  const permitted = store.get().currentUser?.role !== 'VIEWER';
  // Server pass_block_reason means CONFIRM cannot mint PASS even if citations look complete locally.
  const passBlocked = Boolean(item.pass_block_reason) || !hasCompleteCitation(item);
  const revision = Number(run.revision);
  const unavailable = !permitted || busyRunId === run.run_id || !Number.isInteger(revision) || revision < 1;
  const confirmed = isHumanConfirmed(run, item);
  const notePending = pendingNotes.has(`${run.run_id}:${item.requirement_id}`);
  return html`<div class="review-actions" role="group" aria-label="${item.label}的人工复核">
    <button class="btn btn--primary btn--sm" type="button" data-review="CONFIRM" data-id="${item.requirement_id}" ${unavailable || passBlocked || confirmed ? 'disabled' : ''}
      title="${passBlocked ? (item.pass_block_reason === 'QUALITY_GATE_FAIL' ? 'OCR 工程门禁未通过，暂不能核销通过' : '需同时具备招标与企业证据的定位及原文摘录') : '确认引用、有效期与适用条件无误后通过'}"><i data-lucide="check" aria-hidden="true"></i>${confirmed ? '已核销通过' : '确认无误通过'}</button>
    <button class="btn btn--secondary btn--sm" type="button" data-review="REJECT" data-id="${item.requirement_id}" ${unavailable || notePending ? 'disabled' : ''}>存疑驳回</button>
    <button class="btn btn--ghost btn--sm" type="button" data-note data-id="${item.requirement_id}" ${!permitted || busyRunId === run.run_id || notePending ? 'disabled' : ''}><i data-lucide="message-square-plus" aria-hidden="true"></i>添加备注</button>
  </div>${passBlocked ? html`<p class="review-gate"><i data-lucide="lock-keyhole" aria-hidden="true"></i>${item.pass_block_reason === 'QUALITY_GATE_FAIL' ? 'OCR 工程门禁未通过，补齐门禁后方可核销通过。' : '双向引用不完整或未通过原文核验，补齐后方可核销通过。'}</p>` : ''}`;
}

function editor(id) {
  const draft = drafts.get(id); if (!draft) return '';
  const rejecting = draft.mode === 'REJECT';
  const notePending = pendingNotes.has(`${store.get().currentRun?.run_id}:${id}`);
  const readOnly = store.get().currentUser?.role === 'VIEWER' || notePending;
  const unavailable = readOnly || busyRunId === store.get().currentRun?.run_id;
  return html`<form class="review-editor__form" data-review-form data-id="${id}" data-mode="${draft.mode}">
    <label>${rejecting ? '说明存疑原因' : '人工备注'}<textarea data-review-text data-id="${id}" name="note" rows="3" required maxlength="1800" ${readOnly ? 'readonly' : ''} placeholder="${rejecting ? '例如：证书有效期与要求不符，需重新核验。' : '记录与此条款有关的核验信息。'}">${draft.text}</textarea></label>
    <p>${rejecting ? '提交后转为待人工确认，原因会保留在复核记录中。' : '备注仅保存为条款评论，不改变当前判定。'}</p>
    <div><button class="btn btn--primary btn--sm" type="submit" ${unavailable ? 'disabled' : ''}>${notePending ? '正在保存备注…' : rejecting ? '记录原因并驳回' : '保存备注'}</button><button class="btn btn--ghost btn--sm" type="button" data-editor-cancel data-id="${id}" ${notePending ? 'disabled' : ''}>取消</button></div>
  </form>`;
}

function openEditor(button, mode) {
  const id = button.dataset.id; const prior = drafts.get(id);
  if (pendingNotes.has(`${store.get().currentRun?.run_id}:${id}`)) return;
  const texts = { ...prior?.texts, ...(prior ? { [prior.mode]: prior.text } : {}) };
  drafts.set(id, { mode, text: texts[mode] || '', texts });
  const target = button.closest('.review-card')?.querySelector('[data-editor]');
  mount(target, editor(id)); target?.querySelector('textarea')?.focus();
}

function closeEditor(button) {
  const id = button.dataset.id;
  clearDraftMode(id, button.closest('form')?.dataset.mode);
  const card = button.closest('.review-card');
  mount(card?.querySelector('[data-editor]'), editor(id));
  updateDraftMarkers(id); card?.querySelector('[data-note]')?.focus();
}

function hasDraft(id) {
  const draft = drafts.get(id);
  return Boolean(draft && [draft.text, ...Object.values(draft.texts || {})].some((text) => String(text).trim()));
}

function updateDraftMarkers(id) {
  for (const marker of document.querySelectorAll('[data-draft-for]')) {
    if (marker.dataset.draftFor === id) marker.hidden = !hasDraft(id);
  }
}

function clearDraftMode(id, mode) {
  const draft = drafts.get(id);
  if (!draft || !mode) return;
  const texts = { ...draft.texts, [draft.mode]: draft.text };
  delete texts[mode];
  const next = Object.keys(texts).find((key) => texts[key].trim());
  if (next) drafts.set(id, { mode: next, text: texts[next], texts });
  else drafts.delete(id);
}

async function saveEditor(form) {
  if (store.get().currentUser?.role === 'VIEWER') return;
  if (!form.reportValidity()) return;
  const submittedText = String(new FormData(form).get('note') || '');
  const note = submittedText.trim();
  if (!note) { form.querySelector('textarea')?.focus(); return; }
  const button = form.querySelector('button[type="submit"]');
  if (form.dataset.mode === 'REJECT') {
    await review(button, note, form.dataset.id, 'REJECT'); return;
  }
  const run = store.get().currentRun; if (!run || busyRunId === run.run_id) return;
  const id = form.dataset.id;
  const key = `${run.run_id}:${id}`;
  if (pendingNotes.has(key)) return;
  const operation = { epoch: viewEpoch, submittedText };
  pendingNotes.set(key, operation);
  refreshNoteEditors(id);
  try {
    await runsApi.addComment(run.run_id, { body: `【条款 ${id}】${note}` });
    if (store.get().currentRun?.run_id !== run.run_id || operation.epoch !== viewEpoch) return;
    const draft = drafts.get(id);
    const currentText = draft?.mode === 'NOTE' ? draft.text : draft?.texts?.NOTE;
    if (currentText === submittedText) clearDraftMode(id, 'NOTE');
    toast('人工备注已保存，条款判定保持不变。', 'success');
    window.dispatchEvent(new CustomEvent('bidproof:comments-changed'));
  } catch (error) {
    if (store.get().currentRun?.run_id === run.run_id && operation.epoch === viewEpoch) toastFromError(error, '备注未保存，请重试。');
  } finally {
    if (pendingNotes.get(key) === operation) pendingNotes.delete(key);
    if (store.get().currentRun?.run_id === run.run_id) refreshNoteEditors(id);
  }
}

/** Update both presentations of a clause, leaving every other clause's draft untouched. */
function refreshNoteEditors(id) {
  const run = store.get().currentRun;
  if (!run) return;
  const readOnly = store.get().currentUser?.role === 'VIEWER';
  const notePending = pendingNotes.has(`${run.run_id}:${id}`);
  const reviewing = busyRunId === run.run_id;
  const locked = readOnly || reviewing || notePending;
  const active = document.activeElement;
  for (const card of document.querySelectorAll('[data-requirement-id]')) {
    if (card.dataset.requirementId !== id) continue;
    const target = card.querySelector('[data-editor]');
    const restoreFocus = Boolean(active && target?.contains(active));
    mount(target, editor(id));
    for (const action of card.querySelectorAll('[data-note], [data-review="REJECT"]')) {
      action.disabled = locked;
      if (reviewing) action.dataset.wasDisabled = String(readOnly || notePending);
    }
    // A concurrent review may have temporarily locked these replaced buttons.
    // Restore their current permission/pending state when that review settles.
    if (reviewing) for (const action of target?.querySelectorAll('button') || []) {
      action.dataset.wasDisabled = String(notePending || (readOnly && action.type === 'submit'));
      action.disabled = true;
    }
    if (restoreFocus) (target?.querySelector('textarea') || card.querySelector('[data-note]'))?.focus({ preventScroll: true });
  }
  updateDraftMarkers(id);
}

/** A late response must not roll back a newer version already displayed for this run. */
function newestRun(response) {
  const current = store.get().currentRun;
  return current?.run_id === response.run_id && Number(current.revision) > Number(response.revision) ? current : response;
}

async function review(button, note = '', id = button.dataset.id, decision = button.dataset.review) {
  if (store.get().currentUser?.role === 'VIEWER') return;
  const run = store.get().currentRun; if (!run || busyRunId === run.run_id) return;
  const epoch = viewEpoch;
  const item = run.requirements.find((entry) => entry.requirement_id === id);
  const revision = Number(run.revision);
  if (!item || !Number.isInteger(revision) || revision < 1) { toast('任务版本信息不完整，请重新打开任务后复核。', 'error'); return; }
  if (decision === 'CONFIRM' && (item.pass_block_reason || !hasCompleteCitation(item))) { toast('缺少双向原文引用或复核门禁未通过，暂不能核销通过。', 'error'); return; }
  if (decision === 'REJECT' && !note.trim()) return;
  busyRunId = run.run_id; setReviewBusy(true); button.setAttribute('aria-busy', 'true');
  try {
    const updated = await runsApi.reviewRequirement(run.run_id, { requirement_id: id, decision, revision, note,
      ...(decision === 'CONFIRM' ? { new_status: 'PASS' } : {}) });
    if (store.get().currentRun?.run_id !== run.run_id || epoch !== viewEpoch) return;
    const card = button.closest('.review-card');
    const status = newestRun(updated).requirements.find((entry) => entry.requirement_id === id)?.effective_status
      || newestRun(updated).requirements.find((entry) => entry.requirement_id === id)?.status;
    if (card && status) { card.dataset.status = status; card.classList.add('review-card--saved'); }
    if (motion()) {
      const body = card?.querySelector('.review-card__body');
      body?.animate?.([{ height: `${body.getBoundingClientRect().height}px`, opacity: 1 }, { height: '0px', opacity: 0, paddingBottom: '0px' }],
        { duration: 220, easing: 'ease-out', fill: 'forwards' });
      await new Promise((resolve) => { setTimeout(resolve, 240); });
    }
    if (store.get().currentRun?.run_id !== run.run_id || epoch !== viewEpoch) return;
    const open = openIds().filter((entry) => entry !== id);
    collapsed.add(id);
    if (decision === 'REJECT') clearDraftMode(id, 'REJECT');
    busyRunId = '';
    const accepted = newestRun(updated);
    store.set({ currentRun: accepted }); renderMatrixSection(); restoreOpen(open);
    for (const card of document.querySelectorAll('[data-requirement-id]')) if (card.dataset.requirementId === id) card.removeAttribute('open');
    focusAfterReview(id);
    toast(accepted !== updated ? '复核记录已保存，当前显示任务的较新版本。' : decision === 'CONFIRM' ? '已核销通过，复核记录已保存。' : '已记录存疑原因，条款保持待人工确认。', 'success');
    window.dispatchEvent(new CustomEvent('bidproof:review-changed', { detail: { run: accepted, requirementId: id } }));
  } catch (error) {
    if (store.get().currentRun?.run_id !== run.run_id || epoch !== viewEpoch) return;
    if (error?.status === 409) {
      try {
        const latest = await runsApi.getRun(run.run_id);
        if (store.get().currentRun?.run_id === run.run_id && epoch === viewEpoch) {
          const accepted = newestRun(latest);
          store.set({ currentRun: accepted }); busyRunId = ''; renderMatrixSection();
          window.dispatchEvent(new CustomEvent('bidproof:review-changed', { detail: { run: accepted } })); focusAfterReview(id);
        }
      } catch { /* The original conflict still explains why this review was not saved. */ }
      toast('其他成员已更新任务，本次操作未保存。请核对最新内容后重新提交。', 'error');
    } else toastFromError(error, '复核未保存，请重试。');
  } finally {
    if (busyRunId === run.run_id) busyRunId = '';
    if (store.get().currentRun?.run_id === run.run_id && !busyRunId) {
      if (epoch !== viewEpoch) renderMatrixSection();
      else setReviewBusy(false);
    }
    button.removeAttribute('aria-busy');
  }
}

function setReviewBusy(busy) {
  for (const button of document.querySelectorAll('#risk-list button[data-review], #requirements button[data-review], #risk-list button[data-note], #requirements button[data-note], .review-editor button, [data-review-nav], [data-risk-page]')) {
    if (busy) { button.dataset.wasDisabled = String(button.disabled); button.disabled = true; }
    else if ('wasDisabled' in button.dataset) { button.disabled = button.dataset.wasDisabled === 'true'; delete button.dataset.wasDisabled; }
  }
}

function focusAfterReview(id) {
  const card = [...document.querySelectorAll('#requirements [data-requirement-id], #risk-list [data-requirement-id]')].find((node) => node.dataset.requirementId === id);
  const target = card?.querySelector('summary') || el('#matrix-title');
  target?.setAttribute('tabindex', '0'); target?.focus({ preventScroll: true });
}

function selectSource(id, focus, side = 'tender', container = '#risk-list') {
  const run = store.get().currentRun; const item = run?.requirements.find((entry) => entry.requirement_id === id);
  if (!run || !item) return;
  view.selectedId = id; view.sourceContainer = container; renderEvidenceReader(run, item, view.search); markSelected(); renderNavigation();
  if (focus) {
    const reader = el('#evidence-reader');
    const target = reader?.querySelector(side === 'evidence' ? '[data-reader-role="evidence"]' : '[data-reader-role="tender"]') || reader;
    target?.setAttribute('tabindex', '-1'); target?.focus({ preventScroll: true });
    if (window.matchMedia('(max-width: 1100px)').matches) target?.scrollIntoView({ block: 'start', behavior: motion() ? 'smooth' : 'auto' });
  }
}
function returnToCard() {
  const candidates = [...document.querySelectorAll(`${view.sourceContainer} [data-requirement-id]`), ...document.querySelectorAll('[data-requirement-id]')];
  const card = candidates.find((node) => node.dataset.requirementId === view.selectedId);
  const target = card?.querySelector('summary') || el('#matrix-title');
  target?.setAttribute('tabindex', '0');
  target?.focus({ preventScroll: true });
  target?.scrollIntoView({ block: 'center', behavior: motion() ? 'smooth' : 'auto' });
}
function markSelected() {
  for (const card of document.querySelectorAll('[data-requirement-id]')) card.classList.toggle('review-card--selected', card.dataset.requirementId === view.selectedId);
}

async function feedback(button) {
  const run = store.get().currentRun; if (!run) return;
  const complete = el('#accuracy-review-complete'); button.disabled = true;
  try {
    await runsApi.submitAccuracyFeedback(run.run_id, { category: button.dataset.category, predicted: 'DETECTED', actual: button.dataset.accuracy,
      requirement_id: button.dataset.id, review_complete: Boolean(complete?.checked) });
    toast(button.dataset.accuracy === 'RELEVANT' ? '已记录为有效检出。' : '误报反馈已记录，条款判定保持不变。', 'success');
    window.dispatchEvent(new CustomEvent('bidproof:accuracy-changed'));
  } catch (error) { toastFromError(error, '反馈未保存。'); }
  finally { button.disabled = false; }
}

function renderPager(total, pageCount, start) {
  mount(el('#matrix-pagination'), !total ? '' : html`
    <button class="pager__page" type="button" data-page="prev" ${view.page === 1 ? 'disabled' : ''} aria-label="上一页"><i data-lucide="arrow-left" aria-hidden="true"></i></button>
    <span class="pager__page" aria-current="page">${view.page}</span>
    <button class="pager__page" type="button" data-page="next" ${view.page === pageCount ? 'disabled' : ''} aria-label="下一页"><i data-lucide="arrow-right" aria-hidden="true"></i></button>
    <span class="pager__info">显示 ${start + 1}–${Math.min(start + PAGE_SIZE, total)}，共 ${total} 项</span>`);
}
function motion() { return !window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
function openIds() { return [...document.querySelectorAll('#requirements [data-requirement-id][open]')].map((node) => node.dataset.requirementId); }
function restoreOpen(ids) {
  for (const node of document.querySelectorAll('#requirements [data-requirement-id]')) if (ids.includes(node.dataset.requirementId)) node.open = true;
}
