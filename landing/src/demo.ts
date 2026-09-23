import { CASES, CASE_ORDER, confirm, initialState, isCaseId, saveNote } from './demo-model';
import { emitMarketing } from './tracking';

export function mountDemo(document: Document): () => void {
  const root = document.querySelector<HTMLElement>('[data-demo]');
  const view = document.defaultView;
  if (!root || !view) return () => {};
  function element<T extends HTMLElement>(selector: string): T {
    const found = root?.querySelector<T>(selector);
    if (!found) throw new Error(`Demo contract missing: ${selector}`);
    return found;
  }
  const controller = new view.AbortController();
  const { signal } = controller;
  const panel = element<HTMLElement>('#demo-panel');
  const tabs = [...root.querySelectorAll<HTMLButtonElement>('[data-case]')];
  const note = element<HTMLTextAreaElement>('#demo-note');
  const confirmButton = element<HTMLButtonElement>('[data-demo-confirm]');
  const rejectButton = element<HTMLButtonElement>('[data-demo-reject]');
  const verdict = element<HTMLElement>('[data-demo-verdict]');
  const progress = element<HTMLProgressElement>('[data-demo-progress]');
  const noteEditor = element<HTMLElement>('[data-note-editor]');
  const noteCount = element<HTMLElement>('[data-note-count]');
  const status = element<HTMLElement>('[data-demo-status]');
  let state = initialState();
  function setText(selector: string, value: string): void { element(selector).textContent = value; }
  function preserveDraft(): void { saveNote(state, note.value); }
  function render(): void {
    const item = CASES[state.selected];
    const reviewed = state.selected === 'matched' && state.confirmed;
    for (const tab of tabs) {
      const selected = tab.dataset.case === state.selected;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    panel.setAttribute('aria-labelledby', `demo-tab-${state.selected}`);
    setText('[data-demo-title]', item.title);
    setText('[data-demo-category]', item.category);
    verdict.className = `pill ${reviewed ? 'pass' : item.verdict}`;
    verdict.textContent = reviewed ? '已核销通过' : state.doubtful[state.selected] ? '存疑待复核' : item.label;
    for (const side of ['tender', 'evidence'] as const) {
      const citation = item[side];
      setText(`[data-${side}-file]`, citation.file);
      setText(`[data-${side}-page]`, citation.page === null ? '待补充' : `P.${citation.page}`);
      setText(`[data-${side}-section]`, citation.section);
      setText(`[data-${side}-quote]`, citation.quote);
    }
    element('.evidence-paper').classList.toggle('is-missing', item.evidence.page === null);
    setText('[data-demo-explanation]', `↳ ${reviewed ? '本页示例已完成一次人工确认；真实工作台会留存复核记录。' : item.explanation}`);
    setText('[data-matched-label]', state.confirmed ? '已核销通过 · 示例确认已记录' : '有据可查 · 等待人工确认');
    const count = state.confirmed ? 1 : 0;
    setText('[data-demo-count]', `${count} / 3`);
    progress.value = count;
    progress.textContent = `${count} / 3`;
    confirmButton.disabled = !item.canConfirm || reviewed;
    confirmButton.textContent = reviewed ? '已核销通过 ✓' : '确认无误通过';
    rejectButton.textContent = reviewed ? '改为存疑' : '记录存疑';
    note.value = state.notes[state.selected];
    noteCount.textContent = `${note.value.length} / 500`;
    noteEditor.hidden = !state.editorOpen;
    element('[data-demo-note]').textContent = state.editorOpen ? '收起备注' : note.value ? '查看备注' : '添加备注';
  }
  root.addEventListener('click', (event) => {
    if (!(event.target instanceof view.Element)) return;
    const tab = event.target.closest<HTMLButtonElement>('[data-case]');
    if (tab && isCaseId(tab.dataset.case)) {
      preserveDraft();
      state.selected = tab.dataset.case;
      state.editorOpen = false;
      render();
      status.textContent = `${CASES[state.selected].title}。${CASES[state.selected].explanation}`;
      emitMarketing(document, 'demo', 'select');
      return;
    }
    if (event.target.closest('[data-demo-confirm]')) {
      preserveDraft();
      if (!confirm(state)) return;
      render();
      status.textContent = '示例确认已记录，人工核销进度为 1 / 3。其余两项仍需补充或核对证据。';
      emitMarketing(document, 'demo', 'confirm');
    } else if (event.target.closest('[data-demo-reject]')) {
      preserveDraft();
      if (state.selected === 'matched') state.confirmed = false;
      state.doubtful[state.selected] = true;
      state.editorOpen = true;
      render();
      note.focus();
      status.textContent = '示例已标记存疑，仍保留在待处理范围。可以在备注里写下需要继续核对的内容。';
      emitMarketing(document, 'demo', 'reject');
    } else if (event.target.closest('[data-demo-note]')) {
      preserveDraft();
      state.editorOpen = !state.editorOpen;
      render();
      if (state.editorOpen) note.focus();
    } else if (event.target.closest('[data-note-save]')) {
      preserveDraft();
      state.editorOpen = false;
      render();
      element<HTMLButtonElement>('[data-demo-note]').focus();
      status.textContent = note.value.trim() ? '示例备注已保留在当前页面。刷新或恢复示例后清除，不会发送或保存到服务器。' : '空白备注已清除。该操作不改变核销状态。';
      emitMarketing(document, 'demo', 'note');
    } else if (event.target.closest('[data-demo-reset]')) {
      state = initialState();
      render();
      status.textContent = '示例已恢复，所有当前页备注与核销状态已清除。';
      emitMarketing(document, 'demo', 'reset');
    }
  }, { signal });
  root.querySelector('[role="tablist"]')?.addEventListener('keydown', (event) => {
    if (!(event instanceof view.KeyboardEvent) || !(event.target instanceof view.HTMLButtonElement)) return;
    const current = tabs.indexOf(event.target);
    if (current === -1) return;
    let next = current;
    if (['ArrowDown', 'ArrowRight'].includes(event.key)) next = (current + 1) % CASE_ORDER.length;
    else if (['ArrowUp', 'ArrowLeft'].includes(event.key)) next = (current + CASE_ORDER.length - 1) % CASE_ORDER.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = CASE_ORDER.length - 1;
    else return;
    event.preventDefault();
    tabs[next]?.click();
    tabs[next]?.focus();
  }, { signal });
  note.addEventListener('input', () => { preserveDraft(); note.value = state.notes[state.selected]; noteCount.textContent = `${note.value.length} / 500`; }, { signal });
  render();
  return () => controller.abort();
}
