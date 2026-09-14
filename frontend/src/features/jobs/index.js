/**
 * 扫描作业页。
 *
 * 从 app.js 搬出时修掉的：
 *
 *   1. 旧实现只在进入页面时拉一次。作业是活的，用户盯着一个不动的
 *      「扫描中 3/47」，只能手动点刷新。现在有作业在跑时自动轮询，
 *      全部进入终态后自动停 —— 不做无意义的后台请求。
 *   2. 重试/取消按钮在每次渲染后逐个 addEventListener。改为委托。
 *   3. 进度条在未知总数时显示 0%，看起来像卡死。改为不确定态。
 *   4. 用 <table> 而不是 div 网格：作业记录是标准的行列数据，
 *      读屏用户需要「第 3 行 状态列 失败」这样的播报。
 */

import { delegate, el, withLoading } from '../../core/dom.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { toast, toastFromError } from '../../core/toast.js';
import { formatRelative, shortId, jobStatusLabel } from '../../core/format.js';
import { jobsApi } from '../../api/index.js';
import { confirmAction } from '../../ui/confirm.js';

/** @typedef {import('../../../types/api.js').ScanJob} ScanJob */

/** 还有作业在跑时的轮询间隔。5s 足够跟上进度，又不至于打爆后端。 */
const POLL_MS = 5000;

/** 未进入终态的状态集合。 */
const LIVE = new Set(['PENDING', 'RUNNING']);

/** @type {(() => void)[]} */
let teardown = [];
/** @type {ReturnType<typeof setInterval> | null} */
let poller = null;

export function mountJobsView() {
  if (teardown.length) return;
  teardown = [
    delegate('#jobs-list', 'click', '[data-retry-job]', (_e, node) => {
      void act('retry', /** @type {HTMLButtonElement} */ (node));
    }),
    delegate('#jobs-list', 'click', '[data-cancel-job]', (_e, node) => {
      void act('cancel', /** @type {HTMLButtonElement} */ (node));
    }),
    delegate('#jobs-list', 'click', '#jobs-retry-load', () => { void load(); }),
  ];
  void load();
}

export function unmountJobsView() {
  stopPolling();
  for (const off of teardown) off();
  teardown = [];
}

/* ═══════════════════════════════════════════════════════════════════════════
   取数
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {boolean} [silent] 轮询刷新不显示骨架屏，否则列表每 5 秒闪一次 */
async function load(silent = false) {
  const target = el('#jobs-list');
  if (!target) return;

  if (!silent) mount(target, skeleton('row', 3));
  const refresh = /** @type {HTMLButtonElement | null} */ (el('#refresh-jobs'));
  if (refresh) refresh.disabled = true;

  try {
    const { jobs } = await jobsApi.listJobs({ limit: 200 });
    const count = el('#jobs-count');
    if (count) count.textContent = `${jobs.length} 个作业`;

    if (!jobs.length) {
      stopPolling();
      mount(target, emptyState({
        icon: 'inbox',
        title: '还没有后台扫描作业',
        body: '新建扫描后，这里会显示每次作业的进度、重试次数与结果。',
      }));
      return;
    }

    render(jobs, target);
    // 有活的作业才轮询；全部终态就停。
    if (jobs.some((job) => LIVE.has(job.status))) startPolling();
    else stopPolling();
  } catch (error) {
    stopPolling();
    // 轮询失败不要把已经渲染好的列表替换成错误态 —— 那会让用户以为数据没了。
    if (silent) return;
    mount(target, errorState({ title: '作业记录加载失败', error, retryId: 'jobs-retry-load' }));
  } finally {
    if (refresh) refresh.disabled = false;
  }
}

function startPolling() {
  if (poller) return;
  poller = setInterval(() => { void load(true); }, POLL_MS);
}

function stopPolling() {
  if (!poller) return;
  clearInterval(poller);
  poller = null;
}

/* ═══════════════════════════════════════════════════════════════════════════
   渲染
   ═══════════════════════════════════════════════════════════════════════ */

/** @param {ScanJob[]} jobs @param {Element} target */
function render(jobs, target) {
  mount(target, html`
    <div class="table-wrap">
      <table class="table table--responsive">
        <thead>
          <tr>
            <th scope="col">作业</th>
            <th scope="col">进度</th>
            <th scope="col">状态</th>
            <th scope="col" class="td--num">重试</th>
            <th scope="col">更新时间</th>
            <th scope="col" class="td--actions"><span class="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>${jobs.map(row)}</tbody>
      </table>
    </div>
  `);
}

/** @param {ScanJob} job */
function row(job) {
  const total = Number(job.progress_total || 0);
  const current = Number(job.progress_current || 0);
  const known = total > 0;
  const percent = known ? Math.min(100, Math.round((current / total) * 100)) : 0;
  const live = LIVE.has(job.status);

  return html`
    <tr data-status="${job.status}">
      <td data-label="作业">
        <span class="chip chip--mono">${shortId(job.job_id)}</span>
        <small class="hint">${job.run_id ? `任务 ${shortId(job.run_id)}` : (job.error || '等待生成任务')}</small>
      </td>
      <td data-label="进度">
        ${live || known
          ? html`
            <div class="progress" data-indeterminate="${String(live && !known)}">
              <div class="progress__bar">
                <div class="progress__fill" style="width:${known ? percent : 35}%"></div>
              </div>
              <div class="progress__label">
                <span>${known ? `${current}/${total}` : (job.progress_message || '等待开始')}</span>
              </div>
            </div>`
          : html`<span class="hint">${job.progress_message || '—'}</span>`}
      </td>
      <td data-label="状态"><span class="chip ${toneOf(job.status)}">${jobStatusLabel(job.status)}</span></td>
      <td data-label="重试" class="td--num">${Number(job.attempts || 0)}</td>
      <td data-label="更新时间">${formatRelative(job.updated_at)}</td>
      <td data-label="操作" class="td--actions">
        ${job.status === 'FAILED'
          ? html`<button class="btn btn--sm btn--secondary" type="button" data-retry-job="${job.job_id}">
                   <i data-lucide="refresh-ccw"></i><span>重试</span></button>`
          : ''}
        ${live
          ? html`<button class="btn btn--sm btn--ghost" type="button" data-cancel-job="${job.job_id}">
                   <i data-lucide="circle-stop"></i><span>取消</span></button>`
          : ''}
      </td>
    </tr>
  `;
}

/** @param {string} status */
function toneOf(status) {
  if (status === 'FAILED' || status === 'DEAD') return 'chip--danger';
  if (status === 'RUNNING') return 'chip--info';
  if (status === 'COMPLETED') return '';
  return 'chip--warning';
}

/* ═══════════════════════════════════════════════════════════════════════════
   动作
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * @param {'retry' | 'cancel'} kind
 * @param {HTMLButtonElement} button
 */
async function act(kind, button) {
  const jobId = kind === 'retry' ? button.dataset.retryJob : button.dataset.cancelJob;

  if (kind === 'cancel') {
    // 取消是有后果的操作，必须确认。但它不是不可逆的破坏性操作 ——
    // 已完成的结果不会被删除，所以用普通确认，不用输入确认词。
    const ok = await confirmAction({
      title: '取消扫描作业',
      body: '作业会立即停止执行。已完成的解析结果不会被删除，可以重新发起扫描。',
      confirmLabel: '取消作业',
      cancelLabel: '继续运行',
    });
    if (!ok) return;
  }

  await withLoading(button, async () => {
    try {
      await (kind === 'retry' ? jobsApi.retryJob(jobId) : jobsApi.cancelJob(jobId));
      toast(kind === 'retry' ? '作业已重新进入队列。' : '作业已取消。', 'success');
      await load(true);
    } catch (error) {
      toastFromError(error, kind === 'retry' ? '重试未启动。' : '取消未生效。');
    }
  });
}

/** 供工具栏刷新按钮调用。 */
export function reloadJobs() {
  return load();
}
