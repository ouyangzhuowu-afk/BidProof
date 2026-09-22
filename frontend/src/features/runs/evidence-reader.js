/** Two-sided reading without fabricated document pages or unescaped rich text. */
import { el } from '../../core/dom.js';
import { html, mount, emptyState } from '../../ui/render.js';
import { locatorLabel, categoryLabel } from '../../core/format.js';
import { paths } from '../../api/paths.js';
import { referenceDocument, referencePage } from './review-model.js';

// Keep the current clause's reading position through verdict-only rerenders.
// Changing the clause or run starts at its own citations, not the previous page.
const sessions = new WeakMap();

/** Highlight text fragments through the same SafeHtml boundary as every other quotation. */
export function highlightQuote(text, terms = []) {
  const value = String(text || '');
  const words = [...new Set(terms.map(String).map((term) => term.trim()).filter(Boolean))]
    .slice(0, 16).map((term) => term.slice(0, 80));
  if (!words.length) return html`${value}`;
  const expression = new RegExp(`(${words.sort((a, b) => b.length - a.length)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi');
  return html`${value.split(expression).map((part, index) => index % 2 ? html`<mark>${part}</mark>` : html`${part}`)}`;
}

export function quoteTerms(item, search = '') {
  return [search, ...(item.evidence || []).flatMap((entry) => entry.matched_terms || []),
    '无效投标', '否决投标', '废标', '不得', '必须', '有效期', '截止'];
}

/** @param {import('../../../types/api.js').Run} run @param {import('../../../types/api.js').Requirement | null} item */
export function renderEvidenceReader(run, item, search = '') {
  const target = el('#evidence-reader');
  if (!target) return;
  if (!item) {
    sessions.delete(target);
    mount(target, emptyState({ icon: 'panels-top-left', title: '原文对照', body: '选择任意条款的出处，在这里并排核对招标要求与企业材料。' }));
    return;
  }
  const key = `${run.run_id}:${item.requirement_id}`;
  let session = sessions.get(target);
  if (session?.key !== key) {
    session = { key, selectedEvidence: 0, positions: new Map() };
    sessions.set(target, session);
  }
  session.selectedEvidence = Math.min(session.selectedEvidence, Math.max(0, (item.evidence || []).length - 1));
  const terms = quoteTerms(item, search);
  mount(target, html`
    <header class="evidence-reader__head">
      <div><span class="evidence-reader__eyebrow">核对每一个判断的依据</span><h2>双向原文对照</h2></div>
      <button type="button" class="reader-return" data-reader-return><i data-lucide="arrow-left" aria-hidden="true"></i>返回当前条款</button>
    </header>
    <div class="evidence-reader__context"><span>${categoryLabel(item.category)}</span><strong>${item.label}</strong></div>
    <div class="evidence-reader__columns">
      ${readerSide(run, item.source || {}, 'tender', terms, session, 'tender')}
      <div class="evidence-reader__evidence">
        ${evidenceSelector(item, session.selectedEvidence)}
        <div data-selected-evidence>${selectedEvidence(run, item, terms, session)}</div>
      </div>
    </div>
    <p class="evidence-reader__footnote">摘录用于快速定位；请结合原件上下文、有效期与签章完成判断。</p>
  `);
  bindSide(target.querySelector('[data-reader-role="tender"]'), run, item.source || {}, 'tender', session, 'tender');
  bindSelectedEvidence(target, run, item, session);
  target.querySelector('[data-evidence-select]')?.addEventListener('change', (event) => {
    const index = Number(event.currentTarget.value);
    if (!Number.isInteger(index) || !item.evidence?.[index]) return;
    session.selectedEvidence = index;
    const container = target.querySelector('[data-selected-evidence]');
    mount(container, selectedEvidence(run, item, terms, session));
    bindSelectedEvidence(target, run, item, session);
    const message = target.querySelector('[data-evidence-selection-status]');
    if (message) message.textContent = `已显示第 ${index + 1} 份匹配证据，共 ${item.evidence.length} 份。`;
  });
}

function evidenceSelector(item, selected) {
  const evidence = item.evidence || [];
  if (evidence.length < 2) return '';
  return html`<div class="reader-evidence-picker">
    <label for="reader-evidence-choice">匹配证据 · 共 ${evidence.length} 份</label>
    <select id="reader-evidence-choice" data-evidence-select aria-describedby="reader-evidence-selection-status">
      ${evidence.map((reference, index) => html`<option value="${index}" ${index === selected ? 'selected' : ''}>${index + 1}. ${reference.filename || '来源文件未记录'} · ${locatorLabel(reference)}</option>`)}
    </select>
    <p id="reader-evidence-selection-status" data-evidence-selection-status role="status">当前显示第 ${selected + 1} 份；切换后可继续核对其他证据。</p>
  </div>`;
}

function selectedEvidence(run, item, terms, session) {
  const reference = item.evidence?.[session.selectedEvidence];
  return reference ? readerSide(run, reference, 'evidence', terms, session, `evidence:${session.selectedEvidence}`)
    : html`<section class="reader-source reader-source--missing" data-reader-role="evidence"><h3>企业资质与证明</h3>
        <div class="reader-source__missing"><i data-lucide="file-search" aria-hidden="true"></i>
        <strong>暂未匹配到证据</strong><p>补充材料并重新扫描后，可在此核验对应页。</p></div></section>`;
}

function bindSelectedEvidence(target, run, item, session) {
  const reference = item.evidence?.[session.selectedEvidence];
  if (reference) bindSide(target.querySelector('[data-reader-role="evidence"]'), run, reference, 'evidence', session, `evidence:${session.selectedEvidence}`);
}

function sourceModel(run, reference, role, session, slot) {
  const document = referenceDocument(run, reference, role);
  const citation = referencePage(reference);
  const isPdf = document && /(?:^|\.)pdf$/i.test(document.file_type || document.filename?.split('.').pop() || '');
  const sourceUrl = document ? paths.runs.file(run.run_id, document.source_id) : null;
  // `pages` comes from source_documents, not the citation or number of excerpts.
  // The PNG API does not return page_count; absent/conflicting metadata stays unknown.
  const recorded = Number(document?.pages);
  const positiveTotal = Number.isSafeInteger(recorded) && recorded > 0 ? recorded : null;
  const conflicting = Boolean(positiveTotal && citation && positiveTotal < citation);
  const total = conflicting ? null : positiveTotal;
  const key = `${slot}:${document?.source_id || ''}:${document?.sha256 || ''}:${citation || ''}`;
  let position = session.positions.get(key);
  if (!position) {
    position = { page: citation, zoom: false };
    session.positions.set(key, position);
  }
  if (total && position.page > total) position.page = citation;
  return { document, citation, sourceUrl, total, conflicting, position,
    preview: Boolean(sourceUrl && isPdf && citation) };
}

function readerSide(run, reference, role, terms, session, slot) {
  const model = sourceModel(run, reference, role, session, slot);
  const { document, sourceUrl } = model;
  return html`
    <section class="reader-source" data-reader-role="${role}">
      <div class="reader-source__label"><h3>${role === 'tender' ? '招标文件' : '企业资质与证明'}</h3>
        <span class="reader-source__page">引用位置 · ${locatorLabel(reference)}</span></div>
      <p class="reader-source__filename">${document?.filename || reference.filename || (role === 'tender' ? run.tender_filename : '来源文件未记录')}</p>
      <div class="reader-excerpt"><span>原文摘录</span>
        <blockquote>${reference.quote ? highlightQuote(reference.quote, terms) : '未提取到可核对的原文，请查看原件。'}</blockquote></div>
      ${model.preview ? html`<details class="reader-original" open>${originalContent(model)}</details>`
        : html`<p class="reader-source__unavailable">${document ? '此处展示文字摘录，可下载原件核对完整上下文。' : '未记录可唯一匹配的原件，当前仅展示提取的摘录。'}</p>`}
      ${sourceUrl ? html`<a class="reader-source__download" href="${sourceUrl}" download><i data-lucide="download" aria-hidden="true"></i>下载原件</a>` : ''}
    </section>
  `;
}

function originalContent(model) {
  const { document, citation, total, conflicting, position } = model;
  const { page, zoom } = position;
  return html`<summary>原始 PDF · 当前第 ${page} 页</summary>
    <div class="reader-page-navigation" role="group" aria-label="${document.filename}原页导航">
      <button type="button" data-reader-page="previous" ${page <= 1 ? 'disabled' : ''} aria-label="上一页">上一页</button>
      <button type="button" data-reader-page="next" ${(total && page >= total) || page >= Number.MAX_SAFE_INTEGER ? 'disabled' : ''} aria-label="下一页">下一页</button>
      <button type="button" data-reader-page="citation" ${page === citation ? 'disabled' : ''}>回到引用页</button>
    </div>
    <p class="reader-page-position" data-reader-position tabindex="-1"><strong>正在浏览第 ${page} 页</strong>
      <span>引用第 ${citation} 页 · ${total ? `文件记录共 ${total} 页` : conflicting ? '页数记录与引用不一致，请核对原件' : '总页数未记录'}</span></p>
    ${page !== citation ? html`<p class="reader-context-notice">当前正在查看相邻上下文，上方摘录仍来自引用第 ${citation} 页。</p>` : ''}
    <button type="button" class="reader-page__zoom" data-page-zoom aria-pressed="${String(zoom)}">${zoom ? '适应宽度' : '放大原页'}</button>
    <p class="reader-load-status" data-page-status role="status">正在加载第 ${page} 页原文…</p>
    <div class="reader-page reader-page--loading ${zoom ? 'reader-page--zoom' : ''}" tabindex="0" role="region" aria-busy="true" aria-label="${document.filename}原始第${page}页，可滚动阅读">
      <img data-source-page alt="${document.filename}，原始 PDF 第 ${page} 页" loading="lazy">
    </div>`;
}

function bindSide(side, run, reference, role, session, slot) {
  const original = side?.querySelector('.reader-original');
  if (!original) return;
  const model = sourceModel(run, reference, role, session, slot);
  loadOriginal(original, model);
  original.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.hasAttribute('data-page-zoom')) {
      model.position.zoom = !model.position.zoom;
      const page = original.querySelector('.reader-page');
      page.classList.toggle('reader-page--zoom', model.position.zoom);
      button.setAttribute('aria-pressed', String(model.position.zoom));
      button.textContent = model.position.zoom ? '适应宽度' : '放大原页';
      if (model.position.zoom) page.focus({ preventScroll: true });
      return;
    }
    const action = button.dataset.readerPage;
    if (!['previous', 'next', 'citation', 'retry'].includes(action)) return;
    const nextPage = action === 'previous' ? model.position.page - 1
      : action === 'next' ? model.position.page + 1
        : action === 'citation' ? model.citation : model.position.page;
    if (!Number.isSafeInteger(nextPage) || nextPage < 1 || (model.total && nextPage > model.total)) return;
    model.position.page = nextPage;
    mount(original, originalContent(model));
    loadOriginal(original, model);
    const nextControl = original.querySelector(`[data-reader-page="${action}"]:not(:disabled)`)
      || original.querySelector('[data-reader-position]');
    nextControl?.focus({ preventScroll: true });
  });
}

function loadOriginal(original, model) {
  const image = original.querySelector('img[data-source-page]');
  const frame = original.querySelector('.reader-page');
  const status = original.querySelector('[data-page-status]');
  const current = model.position.page;
  const stillCurrent = () => image.isConnected && model.position.page === current;
  image.addEventListener('load', () => {
    if (!stillCurrent()) return;
    frame.classList.remove('reader-page--loading'); frame.setAttribute('aria-busy', 'false');
    status.textContent = `已显示第 ${current} 页原文。`;
  }, { once: true });
  image.addEventListener('error', () => {
    if (!stillCurrent()) return;
    mount(frame, html`<p class="reader-page__fallback">原页暂时无法显示。可重试，或下载原件核对；摘录仍可阅读。</p>
      <button class="reader-page-retry" type="button" data-reader-page="retry">重新加载第 ${current} 页</button>`);
    frame.classList.remove('reader-page--loading', 'reader-page--zoom'); frame.setAttribute('aria-busy', 'false');
    status.textContent = `第 ${current} 页加载失败，摘录已保留。`;
    const zoom = original.querySelector('[data-page-zoom]'); if (zoom) zoom.hidden = true;
  }, { once: true });
  // Bind load/error before assigning src; cached images must get the same feedback.
  image.setAttribute('src', `${model.sourceUrl}/pages/${current}`);
}
