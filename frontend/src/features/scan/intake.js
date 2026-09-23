/**
 * File intake preserves native inputs so FormData remains the upload contract.
 * No file content is parsed here. File signatures and extraction stay server-side.
 * A size cap is applied only when supplied by the server, never from a guessed limit.
 */
import { html, mount } from '../../ui/render.js';

const EXTENSIONS = new Set(['pdf', 'docx', 'xlsx', 'pptx', 'txt', 'md']);
const FORMAT_LABEL = 'PDF、DOCX、XLSX、PPTX、TXT 或 MD';
const fields = new Map();
let form = null;
let busy = false;
let maxUploadBytes = null;
let status = null;
const lockedControls = new Map();

/** @param {number} bytes */
export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Extension/size preflight only; this does not certify content as safe or readable.
 * @param {File[]} files
 * @param {{ multiple?: boolean, maxBytes?: number | null }} options
 * @returns {string[]}
 */
export function validateFiles(files, { multiple = false, maxBytes = null } = {}) {
  if (!multiple && files.length > 1) return ['招标文件每次选择 1 份，请将企业资质放入企业证据区。'];
  const errors = [];
  for (const file of files) {
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!file.name.includes('.') || !EXTENSIONS.has(extension)) {
      errors.push(`“${file.name}”格式不支持，请选择 ${FORMAT_LABEL}。`);
    } else if (file.size === 0) {
      errors.push(`“${file.name}”为空文件，请检查后重新选择。`);
    } else if (Number.isFinite(maxBytes) && maxBytes > 0 && file.size > maxBytes) {
      errors.push(`“${file.name}”超过单文件 ${formatFileSize(maxBytes)} 的上传限制。`);
    }
  }
  return errors;
}

/**
 * Mount once after #scan-form is present. Existing ids/names are kept intact.
 * @param {{ maxUploadBytes?: number }} options Actual server-configured cap, in bytes.
 */
export function mountIntakeFiles(options = {}) {
  form = document.querySelector('#scan-form');
  if (!form) return;
  const configuredValue = options.maxUploadBytes ?? form.dataset.maxUploadBytes;
  if (configuredValue !== undefined) {
    const configured = Number(configuredValue);
    maxUploadBytes = Number.isFinite(configured) && configured > 0 ? configured : null;
  }
  if (form.dataset.intakeMounted === 'true') {
    refreshIntakeFiles();
    return;
  }
  form.dataset.intakeMounted = 'true';

  for (const zone of form.querySelectorAll('.drop-zone[data-target]')) {
    const input = document.getElementById(zone.dataset.target);
    if (!(input instanceof HTMLInputElement) || input.type !== 'file') continue;
    const feedback = document.createElement('div');
    feedback.className = 'intake-file-feedback';
    feedback.id = `${input.id}-feedback`;
    zone.after(feedback);
    mount(feedback, html`<div class="intake-file-errors" id="${input.id}-errors"></div>
      <p class="intake-file-summary" id="${input.id}-selection" role="status" aria-live="polite" aria-atomic="true"></p>
      <div class="intake-file-items"></div>`);
    const formatHint = zone.querySelector('.drop-zone-meta');
    if (formatHint) {
      formatHint.id ||= `${input.id}-formats`;
      mount(formatHint, html`PDF / DOCX / XLSX / PPTX / TXT / MD`);
    }
    const describedBy = new Set((input.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
    if (formatHint) describedBy.add(formatHint.id);
    describedBy.add(`${input.id}-selection`);
    input.setAttribute('aria-describedby', [...describedBy].join(' '));
    input.setAttribute('aria-errormessage', `${input.id}-errors`);
    const field = { input, zone, feedback, files: Array.from(input.files || []), errors: [], notice: '' };
    fields.set(input.id, field);

    input.addEventListener('change', () => acceptFiles(field, Array.from(input.files || [])));
    input.addEventListener('invalid', () => {
      if (input.required && !input.files?.length) {
        field.errors = ['请选择招标文件后开始审查。']; renderField(field);
      }
    });
    zone.addEventListener('dragover', (event) => {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = busy ? 'none' : 'copy';
      if (!busy) zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', (event) => {
      if (!zone.contains(event.relatedTarget)) zone.classList.remove('drag-over');
    });
    zone.addEventListener('drop', (event) => {
      event.preventDefault();
      zone.classList.remove('drag-over');
      if (!busy) acceptFiles(field, Array.from(event.dataTransfer?.files || []));
    });
    feedback.addEventListener('click', (event) => {
      const target = event.target instanceof Element ? event.target.closest('[data-remove-file]') : null;
      if (!target || busy) return;
      const index = Number(target.dataset.removeFile);
      const removed = field.files[index];
      if (!removed) return;
      const next = field.files.filter((_, position) => position !== index);
      replaceFiles(field, next);
      field.errors = [];
      field.notice = `已移除“${removed.name}”。`;
      renderField(field);
      const nextButton = feedback.querySelectorAll('[data-remove-file]')[Math.min(index, next.length - 1)];
      (nextButton || input).focus();
    });
    renderField(field);
  }

  status = document.createElement('section');
  status.className = 'intake-transfer';
  status.id = 'intake-transfer-status';
  status.hidden = true;
  status.setAttribute('aria-live', 'polite');
  const actions = form.querySelector('.dialog-actions');
  if (actions) actions.before(status);
  else form.append(status);

  form.addEventListener('reset', () => {
    // The native reset happens after the event; read the inputs only afterwards.
    queueMicrotask(refreshIntakeFiles);
  });
  form.addEventListener('submit', (event) => {
    if (busy || !validateIntakeFiles()) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
}

function fileKey(file) {
  return `${file.name}\u0000${file.size}\u0000${file.lastModified}`;
}

function replaceFiles(field, files) {
  const transfer = new DataTransfer();
  for (const file of files) transfer.items.add(file);
  field.input.files = transfer.files;
  field.files = files;
}

// Distinct documents with the same display name are easy to confuse in a review.
// Keep the earlier choice and ask for a distinguishable name before adding more.
function duplicateName(field, files) {
  const all = [...fields.values()].flatMap((entry) => entry === field ? files : entry.files);
  const names = new Set();
  for (const file of all) {
    const name = file.name;
    if (names.has(name)) return name;
    names.add(name);
  }
  return '';
}

function acceptFiles(field, incoming) {
  if (busy || !incoming.length) {
    replaceFiles(field, field.files);
    return;
  }
  const errors = validateFiles(incoming, { multiple: field.input.multiple, maxBytes: maxUploadBytes });
  const candidates = field.input.multiple ? [...field.files, ...incoming] : incoming;
  const selected = new Map();
  for (const file of candidates) if (!selected.has(fileKey(file))) selected.set(fileKey(file), file);
  const unique = [...selected.values()];
  const conflict = duplicateName(field, unique);
  if (conflict) errors.push(`“${conflict}”与已选材料重名，请重命名后再添加，确保每份原件可区分。`);
  if (errors.length) {
    // Reject the whole batch, keeping any previous valid choice intact.
    replaceFiles(field, field.files);
    field.errors = errors;
    field.notice = '';
    renderField(field);
    return;
  }
  const skipped = candidates.length - unique.length;
  replaceFiles(field, unique);
  field.errors = [];
  field.notice = skipped ? `${skipped} 份材料已经选过，已保留先前选择。` : '';
  renderField(field);
}

function renderField(field) {
  const { input, zone, files, errors, feedback, notice } = field;
  zone.classList.toggle('has-files', files.length > 0);
  zone.classList.toggle('has-error', errors.length > 0);
  input.setAttribute('aria-invalid', String(errors.length > 0));
  const meta = zone.querySelector('[data-intake-file-hint]');
  if (meta) {
    mount(meta, files.length
      ? html`${input.multiple ? '继续添加材料' : '点击更换招标文件'}`
      : html`拖拽到这里，或点击选择`);
  }
  mount(feedback.querySelector('.intake-file-errors'), errors.length ? html`<div class="intake-file-error" role="alert">
      <i data-lucide="triangle-alert" aria-hidden="true"></i>
      <div>${errors.map((error) => html`<p>${error}</p>`)}
      ${files.length ? html`<p>之前选择的材料已保留。</p>` : ''}</div>
    </div>` : '');
  const selectionText = files.length
    ? `已选择 ${files.length} 份 · ${formatFileSize(files.reduce((total, file) => total + file.size, 0))}`
    : notice ? '当前未选择材料。' : '';
  const announcement = `${selectionText}\u0000${notice}`;
  if (field.lastAnnouncement !== announcement) {
    mount(feedback.querySelector('.intake-file-summary'), html`${selectionText}${notice ? html`<span class="intake-file-notice">${notice}</span>` : ''}`);
    field.lastAnnouncement = announcement;
  }
  mount(feedback.querySelector('.intake-file-items'), files.length ? html`<ul class="intake-file-list" aria-label="${input.multiple ? '已选企业证据' : '已选招标文件'}">
      ${files.map((file, index) => html`<li class="intake-file-row">
        <span class="intake-file-icon"><i data-lucide="files" aria-hidden="true"></i></span>
        <span class="intake-file-info"><span class="intake-file-name" title="${file.name}">${file.name}</span>
          <span class="intake-file-size">${formatFileSize(file.size)}</span></span>
        ${busy
          ? html`<button class="intake-file-remove" type="button" disabled aria-label="移除 ${file.name}"><i data-lucide="x" aria-hidden="true"></i></button>`
          : html`<button class="intake-file-remove" type="button" data-remove-file="${index}" aria-label="移除 ${file.name}"><i data-lucide="x" aria-hidden="true"></i></button>`}
      </li>`)}
    </ul>` : '');
}

/** Call after assigning input.files programmatically (for example a sample file). */
export function refreshIntakeFiles() {
  for (const field of fields.values()) {
    field.files = Array.from(field.input.files || []);
    field.errors = [];
    field.notice = '';
    renderField(field);
  }
}

/** Authentication reset must release native FileList and cached File references synchronously. */
export function clearIntakeFiles() {
  for (const field of fields.values()) {
    field.input.value = '';
    field.files = []; field.errors = []; field.notice = '';
  }
  setIntakeBusy(false);
}

/** Recheck at submit; the server remains the authority for format and size. */
export function validateIntakeFiles() {
  let valid = true;
  // Reconcile all native inputs first, including a sample assigned by app.js.
  for (const field of fields.values()) field.files = Array.from(field.input.files || []);
  for (const field of fields.values()) {
    const files = Array.from(field.input.files || []);
    const errors = validateFiles(files, { multiple: field.input.multiple, maxBytes: maxUploadBytes });
    if (field.input.required && files.length === 0) errors.unshift('请选择招标文件后开始审查。');
    const conflict = duplicateName(field, files);
    if (conflict) errors.push(`“${conflict}”与其他材料重名，请重命名后重新选择。`);
    field.files = files;
    field.errors = errors;
    renderField(field);
    if (errors.length && valid) {
      valid = false;
      field.input.focus();
    }
  }
  return valid;
}

/**
 * Invoke after creating FormData: disabled native inputs are not successful controls.
 * Always release in finally; on request failure all selected files remain in place.
 * @param {boolean} nextBusy
 * @param {string} message An honest description of the current network operation.
 */
export function setIntakeBusy(nextBusy, message = '正在上传材料并创建审查任务') {
  const next = Boolean(nextBusy);
  if (next && !busy) {
    for (const control of document.querySelectorAll('#scan-form input, #scan-form select, #scan-form textarea, #scan-form button, #close-intake')) {
      lockedControls.set(control, control.disabled);
      control.disabled = true;
    }
  } else if (!next && busy) {
    for (const [control, disabled] of lockedControls) control.disabled = disabled;
    lockedControls.clear();
  }
  busy = next;
  form?.setAttribute('aria-busy', String(busy));
  for (const field of fields.values()) {
    field.zone.classList.toggle('is-busy', busy);
    field.zone.classList.remove('drag-over');
    renderField(field);
  }
  if (!status) return;
  status.hidden = !busy;
  mount(status, busy ? html`
    <div class="intake-transfer-heading"><span class="intake-transfer-indicator" aria-hidden="true"></span><strong>${message}</strong></div>
    <p>请保持此窗口打开。任务创建后，可继续处理其他工作。</p>
    <div class="intake-transfer-track" role="progressbar" aria-label="${message}"><span></span></div>
    <div class="intake-transfer-skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
  ` : '');
}

/** Keeps close/backdrop/Escape behavior from hiding a pending request. */
export function isIntakeBusy() { return busy; }
