/**
 * Upload selection and background-scan lifecycle regressions; DOM only, no network.
 * JSDOM_MODULE points to a separately installed jsdom/lib/api.js.
 * jsdom does not implement DataTransfer, so this harness supplies its FileList
 * factory as a test adapter. Native input.files and FormData still run. jsdom's
 * form reset omits FileList clearing, so the adapter supplies that browser step.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isAbsolute } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const dependency = process.env.JSDOM_MODULE || 'jsdom';
const apiUrl = isAbsolute(dependency) ? pathToFileURL(dependency).href : import.meta.resolve(dependency);
const { JSDOM } = await import(apiUrl);
let factory;
let idl;
try {
  factory = (await import(new URL('./generated/idl/FileList.js', apiUrl).href)).default;
  idl = (await import(new URL('./generated/idl/utils.js', apiUrl).href)).default;
} catch {
  factory = (await import(new URL('./jsdom/living/generated/FileList.js', apiUrl).href)).default;
  idl = (await import(new URL('./jsdom/living/generated/utils.js', apiUrl).href)).default;
}
const source = await readFile(new URL('../../static/index.html', import.meta.url), 'utf8');
const dom = new JSDOM(source, { url: 'https://bidproof.invalid/app' });
const { window } = dom;
const originals = new Map();
for (const name of ['window', 'document', 'Element', 'HTMLElement', 'HTMLInputElement', 'HTMLButtonElement',
  'Event', 'CustomEvent', 'FormData', 'File', 'DataTransfer', 'EventSource', 'fetch']) {
  originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
  if (window[name]) Object.defineProperty(globalThis, name, { configurable: true, writable: true, value: window[name] });
}
globalThis.window = window;
class Transfer {
  constructor(files = []) {
    this.files = factory.create(window);
    this.items = { add: (file) => { idl.implForWrapper(this.files).push(idl.implForWrapper(file)); } };
    for (const file of files) this.items.add(file);
  }
}
globalThis.DataTransfer = Transfer;
const sources = new Map();
class Events {
  constructor(url) { this.url = url; this.closed = false; sources.set(url, this); }
  close() { this.closed = true; }
  emit(payload) { this.onmessage?.({ data: JSON.stringify(payload) }); }
}
globalThis.EventSource = Events;
const requests = [];
globalThis.fetch = (url) => {
  requests.push(String(url));
  assert.equal(String(url), '/api/runs/completed-run');
  return Promise.resolve(new Response(JSON.stringify({ run_id: 'completed-run' }), { headers: { 'content-type': 'application/json' } }));
};

const { mountIntakeFiles, refreshIntakeFiles, validateIntakeFiles, setIntakeBusy, isIntakeBusy } = await import('../src/features/scan/intake.js');
const { watchScanJob, hasActiveScans, stopAllScans } = await import('../src/features/scan/watcher.js');
const form = window.document.querySelector('#scan-form');
const tender = window.document.querySelector('#tender-file');
const evidence = window.document.querySelector('#evidence-files');
form.addEventListener('reset', (event) => {
  queueMicrotask(() => {
    if (!event.defaultPrevented) { tender.value = ''; evidence.value = ''; }
  });
});
const file = (name, contents = 'text', modified = 1) => new window.File([contents], name, { lastModified: modified });
const select = (input, files) => {
  input.files = new Transfer(files).files;
  input.dispatchEvent(new window.Event('change', { bubbles: true }));
};
const drop = (input, files) => {
  const event = new window.Event('drop', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', { value: new Transfer(files) });
  input.closest('.drop-zone').dispatchEvent(event);
};
const summary = (input) => window.document.querySelector(`#${input.id}-selection`);
const feedback = (input) => window.document.querySelector(`#${input.id}-feedback`);
const names = (input) => Array.from(input.files, (entry) => entry.name);
const pause = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
async function waitFor(predicate, label) {
  const until = Date.now() + 1000;
  while (!predicate() && Date.now() < until) await pause(5);
  assert.ok(predicate(), label);
}
async function reset() { setIntakeBusy(false); form.reset(); await pause(0); }
function dismissToasts() {
  let node;
  while ((node = window.document.querySelector('.toast-region .toast'))) node.click();
}
mountIntakeFiles({ maxUploadBytes: 8 });
mountIntakeFiles();

try {
  await test('intake selection, accessibility and busy-state contracts', async (suite) => {
    await suite.test('repeated mount preserves configured cap and does not duplicate feedback', async () => {
      await reset();
      assert.equal(window.document.querySelectorAll('#tender-file-feedback').length, 1);
      assert.equal(window.document.querySelectorAll('#intake-transfer-status').length, 1);
      select(tender, [file('oversize.pdf', '123456789')]);
      assert.deepEqual(names(tender), []);
      assert.match(feedback(tender).textContent, /超过单文件 8 B/);
      assert.equal(tender.getAttribute('aria-invalid'), 'true');
      assert.ok(window.document.getElementById(tender.getAttribute('aria-errormessage')));
    });

    await suite.test('evidence supports additive selection and announces retained duplicates without replacing them', async () => {
      await reset();
      const first = file('证书.pdf'); const second = file('合同.pdf');
      const live = summary(evidence);
      select(evidence, [first]); select(evidence, [first, second]);
      assert.deepEqual(names(evidence), ['证书.pdf', '合同.pdf']);
      assert.equal(evidence.files[0], first);
      assert.equal(summary(evidence), live, 'The live region must persist across updates.');
      assert.equal(live.getAttribute('aria-live'), 'polite');
      assert.match(live.textContent, /已经选过/);
      assert.equal(feedback(evidence).querySelectorAll('[data-remove-file]').length, 2);
    });

    await suite.test('different documents sharing a filename and tender/evidence collisions preserve earlier choices', async () => {
      await reset();
      select(tender, [file('招标.pdf')]); select(evidence, [file('证书.pdf')]);
      select(evidence, [file('证书.pdf', 'other', 2), file('合同.pdf')]);
      assert.deepEqual(names(evidence), ['证书.pdf']);
      assert.match(feedback(evidence).textContent, /重名/);
      select(tender, [file('证书.pdf')]);
      assert.deepEqual(names(tender), ['招标.pdf']);
      assert.match(feedback(tender).textContent, /重名/);
      select(evidence, [file('另一证书.pdf')]);
      assert.deepEqual(names(evidence), ['证书.pdf', '另一证书.pdf']);
      assert.equal(evidence.getAttribute('aria-invalid'), 'false');
    });

    await suite.test('dragging many tenders or unsupported files cannot replace a valid previous choice', async () => {
      await reset();
      drop(tender, [file('original.pdf')]);
      drop(tender, [file('one.pdf'), file('two.pdf')]);
      assert.deepEqual(names(tender), ['original.pdf']);
      assert.match(feedback(tender).textContent, /每次选择 1 份/);
      drop(tender, [file('unsafe.exe')]);
      assert.deepEqual(names(tender), ['original.pdf']);
      drop(tender, [file('replacement.pdf')]);
      assert.deepEqual(names(tender), ['replacement.pdf']);
      assert.equal(feedback(tender).querySelector('[role="alert"]'), null);
    });

    await suite.test('removal restores keyboard focus and announces the last removed material', async () => {
      await reset(); select(evidence, [file('a.pdf'), file('b.pdf')]);
      const live = summary(evidence);
      feedback(evidence).querySelector('[data-remove-file="0"]').click();
      assert.deepEqual(names(evidence), ['b.pdf']);
      assert.equal(window.document.activeElement, feedback(evidence).querySelector('[data-remove-file="0"]'));
      feedback(evidence).querySelector('[data-remove-file="0"]').click();
      assert.deepEqual(names(evidence), []);
      assert.equal(window.document.activeElement, evidence);
      assert.equal(summary(evidence), live);
      assert.match(live.textContent, /当前未选择材料/);
      assert.match(live.textContent, /已移除“b.pdf”/);
    });

    await suite.test('captured FormData remains correct while every editable upload field is locked and restored', async () => {
      await reset(); select(tender, [file('tender.pdf')]); select(evidence, [file('evidence.pdf')]);
      const metadata = form.querySelector('textarea'); metadata.disabled = true;
      const data = new window.FormData(form);
      setIntakeBusy(true); setIntakeBusy(true);
      assert.equal(isIntakeBusy(), true);
      for (const control of form.querySelectorAll('input, select, textarea, button')) assert.equal(control.disabled, true);
      assert.equal(window.document.querySelector('#close-intake').disabled, true);
      assert.equal(data.get('tender').name, 'tender.pdf');
      assert.equal(data.get('evidence').name, 'evidence.pdf');
      const progress = window.document.querySelector('#intake-transfer-status [role="progressbar"]');
      assert.equal(progress.hasAttribute('aria-valuenow'), false, 'No fabricated percentage may be exposed.');
      drop(tender, [file('ignored.pdf')]);
      assert.deepEqual(names(tender), ['tender.pdf']);
      setIntakeBusy(false);
      assert.equal(metadata.disabled, true, 'Pre-existing disabled state must be restored.');
      assert.equal(tender.disabled, false);
      assert.equal(form.querySelector('#company-name').disabled, false);
      assert.equal(form.querySelector('#tender-project').disabled, false);
      assert.equal(window.document.querySelector('#close-intake').disabled, false);
      assert.deepEqual(names(evidence), ['evidence.pdf']);
      metadata.disabled = false;
    });

    await suite.test('native required errors are described inline and clear on a valid replacement', async () => {
      await reset(); tender.checkValidity();
      assert.match(feedback(tender).textContent, /请选择招标文件/);
      select(tender, [file('valid.pdf')]);
      assert.equal(tender.getAttribute('aria-invalid'), 'false');
      assert.equal(feedback(tender).querySelector('[role="alert"]'), null);
      assert.equal(validateIntakeFiles(), true);
    });

    await suite.test('programmatically assigned colliding files are still rejected at submit', async () => {
      await reset();
      tender.files = new Transfer([file('same.pdf')]).files;
      evidence.files = new Transfer([file('same.pdf', 'other')]).files;
      refreshIntakeFiles();
      assert.equal(validateIntakeFiles(), false);
      assert.match(feedback(evidence).textContent, /重名/);
    });

    await suite.test('filenames stay text and a native reset clears selections and stale messages', async () => {
      await reset();
      const name = '"><img src=x>.pdf';
      select(tender, [file(name)]);
      assert.match(feedback(tender).textContent, /<img src=x>/);
      assert.equal(feedback(tender).querySelector('img'), null);
      await reset();
      assert.deepEqual(names(tender), []); assert.deepEqual(names(evidence), []);
      assert.equal(summary(tender).textContent, '');
      assert.equal(feedback(tender).querySelector('[role="alert"]'), null);
    });
  });

  await test('background scan card dismissal persists through real job events', async (suite) => {
    await suite.test('hidden scan stays hidden on progress and completion, while completion is announced', async () => {
      watchScanJob('hidden-done', '已收起.pdf', () => {});
      const stream = sources.get('/api/jobs/hidden-done/events');
      window.document.querySelector('[data-scan-hide="hidden-done"]').click();
      assert.equal(hasActiveScans(), true);
      assert.equal(stream.closed, false);
      stream.emit({ status: 'RUNNING', progress_current: 1, progress_total: 4 });
      assert.equal(window.document.getElementById('scancard-hidden-done'), null);
      stream.emit({ status: 'COMPLETED', run_id: 'completed-run' });
      await waitFor(() => !hasActiveScans(), 'Completed scan should release its subscription.');
      assert.equal(stream.closed, true);
      assert.equal(window.document.getElementById('scancard-hidden-done'), null);
      assert.match(window.document.querySelector('.toast-region').textContent, /已收起.pdf.*扫描完成/);
      dismissToasts();
    });

    await suite.test('hidden scan failure is announced without restoring the card', () => {
      watchScanJob('hidden-fail', '待检查.pdf', () => {});
      const stream = sources.get('/api/jobs/hidden-fail/events');
      window.document.querySelector('[data-scan-hide="hidden-fail"]').click();
      stream.emit({ status: 'FAILED', progress_message: '无法读取该文件' });
      assert.equal(hasActiveScans(), false);
      assert.equal(window.document.getElementById('scancard-hidden-fail'), null);
      assert.match(window.document.querySelector('.toast--error').textContent, /无法读取该文件/);
      dismissToasts();
    });

    await suite.test('visible scan still exposes its result and rewatching a completed id starts visibly', async () => {
      let opened = '';
      watchScanJob('hidden-done', '新一轮.pdf', (id) => { opened = id; });
      assert.ok(window.document.getElementById('scancard-hidden-done'));
      sources.get('/api/jobs/hidden-done/events').emit({ status: 'COMPLETED', run_id: 'completed-run' });
      await waitFor(() => window.document.querySelector('[data-scan-open]'), 'Visible completion must offer its result.');
      window.document.querySelector('[data-scan-open]').click();
      assert.equal(opened, 'completed-run');
      assert.equal(window.document.getElementById('scancard-hidden-done'), null);
      assert.deepEqual(requests, ['/api/runs/completed-run', '/api/runs/completed-run']);
      dismissToasts();
    });
  });
} finally {
  setIntakeBusy(false); stopAllScans(); dismissToasts(); dom.window.close();
  for (const [key, descriptor] of originals) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
}
