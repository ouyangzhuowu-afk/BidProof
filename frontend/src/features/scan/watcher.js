/**
 * 后台扫描监视器。上传取得 job_id 后按服务端进度展示独立卡片。
 * 收起卡片仅隐藏界面，监视继续；完成或失败仍提示，但不会重建已收起卡片。
 * pagehide 统一关闭所有连接，避免遗留订阅。
 */

import { html, mount } from '../../ui/render.js';
import { toast, toastSuccess } from '../../core/toast.js';
import { shortId as _shortId } from '../../core/format.js';
import { jobsApi } from '../../api/index.js';

/** 同时监视的作业上限。超出的不再订阅，用户可去作业页查看。 */
const MAX_WATCHERS = 5;

/** @type {Map<string, { stop: () => void, filename: string }>} */
const watchers = new Map();
const hiddenJobs = new Set();

/** @type {HTMLElement | null} */
let dock = null;

/* ═══════════════════════════════════════════════════════════════════════════
   对外接口
   ═══════════════════════════════════════════════════════════════════════ */

/**
 * 开始监视一个扫描作业。
 *
 * @param {string} jobId
 * @param {string} filename 用于卡片标题。作业号对用户没有意义。
 * @param {(runId: string) => void} onOpen 用户点「查看结果」时的跳转回调
 */
export function watchScanJob(jobId, filename, onOpen) {
  if (watchers.has(jobId)) return;
  if (watchers.size >= MAX_WATCHERS) {
    toast('同时进行的扫描过多，可在「扫描作业」页查看进度。', 'info');
    return;
  }

  hiddenJobs.delete(jobId);
  renderCard(jobId, filename, { status: 'PENDING' });

  const stop = jobsApi.watchScan(jobId, {
    onProgress: (job) => { if (!hiddenJobs.has(jobId)) renderCard(jobId, filename, job); },
    onDone: (run) => {
      const hidden = hiddenJobs.has(jobId);
      release(jobId);
      hiddenJobs.delete(jobId);
      toastSuccess(`「${filename}」扫描完成。`);
      if (!hidden) renderDone(jobId, filename, run.run_id, onOpen);
    },
    onError: (error) => {
      const hidden = hiddenJobs.has(jobId);
      release(jobId);
      hiddenJobs.delete(jobId);
      if (hidden) toast(`「${filename}」扫描未完成：${error.message || '请在扫描作业中查看原因。'}`, 'error');
      else renderFailed(jobId, filename, error.message);
    },
  });

  watchers.set(jobId, { stop, filename });
}

/** 当前是否有正在监视的扫描。用于离开页面前的提醒。 */
export function hasActiveScans() {
  return watchers.size > 0;
}

/**
 * 关闭全部连接。页面卸载时调用 ——
 * 不这样做，SSE 连接会一直占着服务端的一个工作进程。
 */
export function stopAllScans() {
  for (const { stop } of watchers.values()) stop();
  watchers.clear();
  hiddenJobs.clear();
}

// 关闭 / 前后台切换都要收干净。用 pagehide 而不是 unload：
// 后者在 iOS Safari 的 bfcache 下不可靠。
window.addEventListener('pagehide', stopAllScans);

/* ═══════════════════════════════════════════════════════════════════════════
   停靠区
   ═══════════════════════════════════════════════════════════════════════ */

function ensureDock() {
  if (dock?.isConnected) return dock;
  dock = document.createElement('div');
  dock.className = 'scandock';
  // 进度是辅助信息，不该打断读屏正在朗读的内容。完成时的提示走 toast。
  dock.setAttribute('aria-live', 'polite');
  dock.setAttribute('aria-label', '正在进行的扫描');
  document.body.append(dock);
  return dock;
}

/** @param {string} jobId */
function cardFor(jobId) {
  const id = `scancard-${jobId}`;
  let card = document.getElementById(id);
  if (!card) {
    card = document.createElement('article');
    card.id = id;
    card.className = 'scancard';
    ensureDock().append(card);
  }
  return card;
}

/**
 * @param {string} jobId
 * @param {string} filename
 * @param {{ status?: string, progress_current?: number, progress_total?: number, progress_message?: string }} job
 */
function renderCard(jobId, filename, job) {
  const total = Number(job.progress_total || 0);
  const current = Number(job.progress_current || 0);
  // 总数未知时走不确定态。显示一个假的 0% 会让用户以为卡住了 ——
  // 后端在数完页数之前确实给不出分母。
  const known = total > 0;
  const percent = known ? Math.min(100, Math.round((current / total) * 100)) : 0;

  mount(cardFor(jobId), html`
    <div class="scancard__head">
      <span class="scancard__name" title="${filename}">${filename}</span>
      <button class="icon-btn" type="button" data-scan-hide="${jobId}"
              aria-label="收起此卡片（扫描继续在后台进行）">
        <i data-lucide="x"></i>
      </button>
    </div>
    <div class="progress" data-indeterminate="${String(!known)}">
      <div class="progress__bar">
        <div class="progress__fill" style="width:${known ? percent : 35}%"></div>
      </div>
      <div class="progress__label">
        <span>${job.progress_message || '正在扫描'}</span>
        <span>${known ? `${percent}%` : ''}</span>
      </div>
    </div>
    <p class="scancard__hint">可以继续使用，完成后会通知你。</p>
  `);
}

/**
 * @param {string} jobId
 * @param {string} filename
 * @param {string} runId
 * @param {(runId: string) => void} onOpen
 */
function renderDone(jobId, filename, runId, onOpen) {
  const card = cardFor(jobId);
  card.dataset.state = 'done';
  mount(card, html`
    <div class="scancard__head">
      <span class="scancard__name" title="${filename}">${filename}</span>
      <button class="icon-btn" type="button" data-scan-hide="${jobId}" aria-label="关闭">
        <i data-lucide="x"></i>
      </button>
    </div>
    <p class="scancard__hint">扫描完成，共生成 1 份核验结果。</p>
    <button class="btn btn--sm btn--primary" type="button" data-scan-open="${runId}">
      <i data-lucide="arrow-right"></i><span>查看结果</span>
    </button>
  `);
  card.querySelector('[data-scan-open]')?.addEventListener('click', () => {
    onOpen(runId);
    dismiss(jobId);
  });
}

/** @param {string} jobId @param {string} filename @param {string} reason */
function renderFailed(jobId, filename, reason) {
  const card = cardFor(jobId);
  card.dataset.state = 'failed';
  mount(card, html`
    <div class="scancard__head">
      <span class="scancard__name" title="${filename}">${filename}</span>
      <button class="icon-btn" type="button" data-scan-hide="${jobId}" aria-label="关闭">
        <i data-lucide="x"></i>
      </button>
    </div>
    <p class="callout" data-tone="danger">
      <i data-lucide="triangle-alert"></i>
      <span>${reason || '扫描失败。可在「扫描作业」页重试。'}</span>
    </p>
  `);
}

/**
 * 收起卡片。注意语义：**只是收起界面，不取消作业** ——
 * 取消要去作业页，那是个有后果的操作，不该藏在一个 × 按钮里。
 *
 * @param {string} jobId
 */
function dismiss(jobId) {
  if (watchers.has(jobId)) hiddenJobs.add(jobId);
  document.getElementById(`scancard-${jobId}`)?.remove();
  if (dock && !dock.childElementCount) { dock.remove(); dock = null; }
}

/** 结束监视但保留卡片（完成态/失败态仍需展示）。 */
function release(jobId) {
  watchers.get(jobId)?.stop();
  watchers.delete(jobId);
}

// 收起按钮用委托：卡片会被反复重建，逐个绑定必然漏。
document.addEventListener('click', (event) => {
  const button = /** @type {HTMLElement} */ (event.target)?.closest?.('[data-scan-hide]');
  if (button) dismiss(button.dataset.scanHide);
});
