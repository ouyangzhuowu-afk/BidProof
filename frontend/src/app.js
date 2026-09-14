// @ts-nocheck
// Strangler leftover: keep checkJs off until remaining detail/intake logic moves to features/.
import { html, mount as setHtml } from './ui/render.js';
import { store } from './state.js';
import { t, formatDateTime } from './i18n/index.js';
import * as theme from './core/theme.js';
import { renderIcons } from './core/icons.js';
import { setLoading } from './core/dom.js';
// Confirm / secret-reveal callers moved to admin; app.js no longer imports them.
import { setCurrentRole } from './core/permissions.js';
import {
  ApiError,
  json,
  request,
  requestBlob,
  saveBlob,
  watchJob,
  UPLOAD_TIMEOUT_MS,
} from './core/http.js';
import { configureAuth, startAuth } from './features/auth/index.js';
import {
  mountRunsView,
  unmountRunsView,
  reloadRuns,
  reloadAccuracy,
  ensureFilterOptions,
} from './features/runs/list.js';
import {
  mountMatrix,
  unmountMatrix,
  resetMatrixView,
  renderMatrixSection,
} from './features/runs/matrix.js';
import {
  mountDecisionView,
  unmountDecisionView,
  render as renderDecision,
} from './features/runs/decision.js';
import { mountCollab, unmountCollab, loadCollab } from './features/runs/collab.js';
import { mountJobsView, unmountJobsView, reloadJobs } from './features/jobs/index.js';
import { mountAdminView, unmountAdminView, reloadAdmin } from './features/admin/index.js';
import { watchScanJob } from './features/scan/watcher.js';

const views = {
  home: document.querySelector('#home-view'),
  jobs: document.querySelector('#jobs-view'),
  admin: document.querySelector('#admin-view'),
  detail: document.querySelector('#detail-view'),
  decision: document.querySelector('#decision-view'),
};
const missedDialog = document.querySelector('#missed-panel');

const intakeDialog = document.querySelector('#intake-panel');
const openIntakeButtons = ['#new-scan-button', '#top-new-scan', '#nav-new-scan'];
openIntakeButtons.forEach((selector) => document.querySelector(selector).addEventListener('click', () => { store.rescanParentId = null; openIntake(); }));
document.querySelector('#close-intake').addEventListener('click', closeIntake);
document.querySelector('#cancel-intake').addEventListener('click', closeIntake);
document.querySelector('#nav-runs').addEventListener('click', showHome);
document.querySelector('#nav-jobs').addEventListener('click', showJobs);
document.querySelector('#nav-admin').addEventListener('click', showAdmin);
document.querySelector('#refresh-jobs').addEventListener('click', () => { void reloadJobs(); });
document.querySelectorAll('[data-mobile-view]').forEach((button) => button.addEventListener('click', () => {
  if (button.dataset.mobileView === 'home') showHome();
  if (button.dataset.mobileView === 'jobs') showJobs();
  if (button.dataset.mobileView === 'admin') showAdmin();
}));
document.querySelector('#export-html').addEventListener('click', () => exportCurrentRun('html'));
document.querySelector('#export-csv').addEventListener('click', () => exportCurrentRun('csv'));
document.querySelector('#export-pdf').addEventListener('click', () => exportCurrentRun('pdf'));
document.querySelector('#rescan-run').addEventListener('click', () => { store.rescanParentId = store.currentRun?.run_id || null; openIntake(); });
document.querySelector('#run-metadata-form').addEventListener('submit', saveRunMetadata);
document.querySelector('#report-missed').addEventListener('click', () => missedDialog.showModal());
document.querySelector('#close-missed').addEventListener('click', () => missedDialog.close());
document.querySelector('#cancel-missed').addEventListener('click', () => missedDialog.close());
document.querySelector('#missed-form').addEventListener('submit', submitMissedFeedback);
document.querySelector('#theme-toggle')?.addEventListener('click', () => {
  theme.cycle();
  const label = document.querySelector('#theme-toggle span');
  if (label) label.textContent = theme.resolved() === 'dark' ? t('nav.theme.toLight') : t('nav.theme.toDark');
});
document.querySelector('#back-home').addEventListener('click', showHome);
document.querySelector('#open-decision').addEventListener('click', showDecision);
document.querySelector('#aside-decision').addEventListener('click', showDecision);
document.querySelector('#back-detail').addEventListener('click', showDetail);
document.querySelector('#scan-form').addEventListener('submit', submitScan);
intakeDialog.addEventListener('click', (event) => {
  if (event.target === intakeDialog) closeIntake();
});

document.querySelectorAll('.drop-zone').forEach((zone) => {
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const input = zone.querySelector('input[type="file"]');
    if (e.dataTransfer.files.length) input.files = e.dataTransfer.files;
  });
});

refreshIcons();
initializeApp();

async function initializeApp() {
  // 鉴权全部收进 features/auth/：四种模式、MFA 两步、以及从 URL 进入的
  // 激活 / 重置，都由那边的状态机决定。这里只提供「登录之后做什么」。
  configureAuth({
    onAuthenticated: async (user) => {
      store.currentUser = user;
      renderCurrentUser();
      await loadProjects();
      await reloadRuns();
      navigateFromHash();
    },
  });
  await startAuth();
}






function renderCurrentUser() {
  // 权限判定统一走 core/permissions.js。之所以在这里推而不是让它订阅 store：
  // 目前 app.js 用 state.js、features/* 用 core/store.js，两套并存。
  setCurrentRole(store.currentUser?.role);
  const container = document.querySelector('#current-user');
  container.hidden = !store.currentUser;
  document.querySelector('#logout-button').hidden = !store.currentUser;
  document.querySelector('#current-username').textContent = store.currentUser?.username || '';
  document.querySelector('#current-user-role').textContent = store.currentUser ? roleLabel(store.currentUser.role) : '';
  document.querySelector('#password-username').value = store.currentUser?.username || '';
}




async function startSampleScan() {
  try {
    const response = await requestBlob('/api/sample-tender');
    const blob = await response.blob();
    const file = new File([blob], 'sample-tender.pdf', { type: 'application/pdf' });
    const input = document.querySelector('#tender-file');
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    store.rescanParentId = null;
    await openIntake();
    showToast('已填入样例招标文件，确认后即可开始扫描。');
  } catch (error) {
    showToast(`${error.message}，请手动上传招标文件。`);
    store.rescanParentId = null;
    await openIntake();
  }
}

async function openIntake() {
  await loadProjects();
  if (store.rescanParentId && store.currentRun?.project_id) document.querySelector('#tender-project').value = store.currentRun.project_id;
  if (!intakeDialog.open) intakeDialog.showModal();
  document.querySelector('#company-name').focus();
  refreshIcons();
}

function closeIntake() {
  if (intakeDialog.open) intakeDialog.close();
  document.querySelector('#message').textContent = '';
}






async function submitScan(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = document.querySelector('#message');
  setButtonLoading(button, true, '正在扫描');
  message.textContent = '正在抽取页级证据并建立索引，请勿关闭窗口。';
  try {
    const formData = new FormData(form);
    if (!document.querySelector('#evidence-files').files.length) formData.delete('evidence');
    if (store.rescanParentId) {
      store.currentRun = await request(`/api/runs/${encodeURIComponent(store.rescanParentId)}/rescan`, { method: 'POST', body: formData, timeoutMs: UPLOAD_TIMEOUT_MS });
    } else {
      // 【行为改变】提交后立刻放行，不再用全屏遮罩把应用锁住 30 分钟。
      // 扫描在后台跑，进度显示在右下角停靠区，完成时提示并可跳转。
      // 详见 features/scan/watcher.js 顶部说明。
      const job = await request('/api/jobs', { method: 'POST', body: formData, timeoutMs: UPLOAD_TIMEOUT_MS });
      const filename = document.querySelector('#tender-file')?.files?.[0]?.name || '招标文件';
      form.reset();
      closeIntake();
      store.rescanParentId = null;
      watchScanJob(job.job_id, filename, (runId) => { void openRun(runId); });
      showToast('扫描已进入后台队列，完成后会通知你。');
      await reloadRuns();
      return;
    }
    // 重扫是同步契约，直接拿到 Run。
    form.reset();
    closeIntake();
    store.rescanParentId = null;
    resetMatrixView();
    showDetail();
    await reloadRuns();
    showToast('重新扫描完成，已生成新版本证据链。');
  } catch (error) {
    message.textContent = `${error.message}。请检查文件格式后重试。`;
  } finally {
    setButtonLoading(button, false);
  }
}









function exportCurrentRun(format) {
  if (!store.currentRun) return;
  const link = document.createElement('a');
  link.href = `/api/runs/${encodeURIComponent(store.currentRun.run_id)}/report.${format}`;
  link.download = `bidproof-${store.currentRun.run_id.slice(0, 12)}.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

async function openRun(runId) {
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.hidden = false;
  try {
    store.currentRun = await request(`/api/runs/${encodeURIComponent(runId)}`);
    resetMatrixView();
    document.querySelector('#requirement-search').value = '';
    showDetail();
  } catch (error) {
    showToast(`${error.message}，请刷新任务列表后重试。`);
  } finally {
    if (overlay) overlay.hidden = true;
  }
}


/**
 * 只负责填两个下拉：任务列表的项目筛选、扫描弹窗的项目选择。
 *
 * 旧版这个函数同时还渲染管理页的项目列表并绑定归档按钮，
 * 于是管理页刷新一次就会顺手重置用户在别处选好的筛选。
 * 管理页那一份现在在 features/admin/projects.js。
 */
async function loadProjects() {
  try {
    const payload = await request('/api/projects?include_archived=true');
    store.projectsCache = payload.projects;
    const active = store.projectsCache.filter((project) => !project.archived_at);

    // 两个下拉都可能不在当前视图里 —— 裸 querySelector(...).innerHTML
    // 在别的页面会抛 TypeError 把整页拖垮，必须判空。
    const filter = document.querySelector('#run-project-filter');
    if (filter) {
      const previous = filter.value;
      setHtml(filter, [
        html`<option value="">全部项目</option>`,
        ...store.projectsCache.map((project) => html`<option value="${project.project_id}">${project.code} · ${project.name}${project.archived_at ? '（已归档）' : ''}</option>`),
      ]);
      filter.value = store.projectFilter || previous || '';
    }

    const tender = document.querySelector('#tender-project');
    if (tender) {
      const previous = tender.value;
      setHtml(tender, active.map((project) => html`<option value="${project.project_id}">${project.code} · ${project.name}</option>`));
      if (active.some((project) => project.project_id === previous)) tender.value = previous;
    }
  } catch (error) {
    // 下拉取不回来不该阻塞任何页面，静默降级为「全部项目」。
    console.warn('[bidproof] 项目下拉加载失败', error);
  }
}

function memberOptionList(placeholder) {
  return [
    html`<option value="">${placeholder}</option>`,
    ...store.membersCache.filter((member) => member.active).map((member) => html`<option value="${member.user_id}">${member.username} · ${roleLabel(member.role)}</option>`),
  ];
}

function showHome() {
  // 视图切换仍由 app.js 的 showView 负责（路由迁移见批次 5）。
  // 这里只保证进入本视图时新模块被挂载、离开时被卸载。
  void ensureFilterOptions().then(mountRunsView);
  showView('home', '扫描任务');
  reloadRuns();
}

function showJobs() {
  showView('jobs', '扫描作业');
  mountJobsView();
  void reloadJobs();
}




function showAdmin() {
  showView('admin', '成员与设置');
  // 四个面板各自取数、各自显示状态。旧实现用一个 Promise.all 拉五个接口，
  // 任何一个挂掉五块一起变错误态 —— 而其中四块的数据其实已经拿到了。
  mountAdminView();
  reloadAdmin();
}
























function showDecision() {
  if (!store.get?.().currentRun && !store.currentRun) return;
  showView('decision', '人工决策');
  mountDecisionView();
  renderDecision();
}

function showDetail() {
  mountMatrix();
  mountCollab();
  if (!store.currentRun) return showHome();
  showView('detail', '扫描详情');
  renderDetail();
}


function showView(name, context, pushHash = true) {
  if (name !== 'home') unmountRunsView();
  if (name !== 'detail') unmountMatrix();
  if (name !== 'jobs') unmountJobsView();
  if (name !== 'decision') unmountDecisionView();
  if (name !== 'admin') unmountAdminView();
  if (name !== 'detail') unmountCollab();
  Object.entries(views).forEach(([key, view]) => { view.hidden = key !== name; });
  document.querySelector('#page-context').textContent = context;
  if (pushHash) {
    const runId = store.currentRun?.run_id;
    const hash = (name === 'detail' || name === 'decision') && runId ? `#${name}/${runId}` : `#${name}`;
    if (location.hash !== hash) history.pushState(null, '', hash);
  }
  document.querySelector('#nav-runs').classList.toggle('active', name === 'home');
  document.querySelector('#nav-runs').toggleAttribute('aria-current', name === 'home');
  for (const [navId, viewName] of [['nav-jobs', 'jobs'], ['nav-admin', 'admin']]) {
    const nav = document.querySelector(`#${navId}`);
    nav.classList.toggle('active', name === viewName);
    nav.toggleAttribute('aria-current', name === viewName);
  }
  document.querySelectorAll('[data-mobile-view]').forEach((button) => button.classList.toggle('active', button.dataset.mobileView === name || (button.dataset.mobileView === 'home' && ['detail', 'decision'].includes(name))));
  window.scrollTo({ top: 0, behavior: 'instant' });
  document.querySelector('#app-main').focus({ preventScroll: true });
  refreshIcons();
}

function navigateFromHash() {
  const hash = location.hash.replace(/^#/, '');
  if (!hash) return;
  const [view, id] = hash.split('/');
  if (view === 'home') showHome();
  else if (view === 'jobs') showJobs();
  else if (view === 'admin') showAdmin();
  else if ((view === 'detail' || view === 'decision') && id) openRun(id);
}

window.addEventListener('popstate', navigateFromHash);


function renderDetail() {
  document.querySelector('#detail-title').textContent = store.currentRun.tender_filename;
  document.querySelector('#detail-subtitle').textContent = `${store.currentRun.run_id.slice(0, 12)} · 版本 ${store.currentRun.version_number || 1} · ${store.currentRun.requirement_count} 项要求 · ${store.currentRun.evidence_assets.length} 份企业证据`;
  document.querySelector('#detail-updated').textContent = `更新于 ${formatDate(store.currentRun.updated_at)}`;
  const metrics = [
    ['致命风险', store.currentRun.blocker_count, 'danger', 'shield-alert'],
    ['待复核', store.currentRun.unresolved_count, 'warning', 'circle-help'],
    ['要求项', store.currentRun.requirement_count, 'neutral', 'list-checks'],
    ['人工决定', decisionLabel(store.currentRun.decision?.decision || '未记录'), 'decision', 'clipboard-check'],
  ];
  document.querySelector('#detail-summary').replaceChildren(...metrics.map(([label, value, tone, icon]) => {
    const card = document.createElement('div');
    card.className = `metric ${tone}`;
setHtml(card, html`<span class="metric-icon"><i data-lucide="${icon}"></i></span><span><span>${label}</span><strong>${String(value)}</strong></span>`);
    return card;
  }));
  renderSourceFiles();
setHtml(document.querySelector('#audit-summary'), html`<div class="audit-metric"><span>企业证据</span><strong>${store.currentRun.evidence_assets.length}</strong></div><div class="audit-metric"><span>高风险项</span><strong>${store.currentRun.blocker_count}</strong></div><div class="audit-metric"><span>待复核项</span><strong>${store.currentRun.unresolved_count}</strong></div><p class="audit-copy">只有招标原文与企业证据均有页码引用时，要求项才允许判定为 PASS。</p>`);
  const quality = store.currentRun.scan_quality || {};
setHtml(document.querySelector('#quality-summary'), html`<p class="eyebrow">文本质量</p><p>${quality.total_pages || 0} 页 · ${quality.ocr_required_pages || 0} 页需 OCR · ${quality.ocr_failed_pages || 0} 页 OCR 失败</p><small>${quality.interpretation || '规则初筛结果，需人工复核。'}</small>`);
  const duplicateWarning = document.querySelector('#duplicate-warning');
  duplicateWarning.hidden = !(store.currentRun.duplicate_run_ids || []).length;
setHtml(duplicateWarning, duplicateWarning.hidden ? '' : html`<i data-lucide="copy-check"></i><span>检测到同一招标文件已有 ${store.currentRun.duplicate_run_ids.length} 个任务：${store.currentRun.duplicate_run_ids.map((id) => id.slice(0, 12)).join('、')}。请先确认是否需要重复扫描。</span>`);
  loadAssigneeOptions();
  document.querySelector('#run-tags').value = (store.currentRun.tags || []).join(', ');
  document.querySelector('#run-favorite').checked = Boolean(store.currentRun.favorite);
  renderMatrixSection();
  loadCollab();
  loadVersionDiff();
  refreshIcons();
}

function renderSourceFiles() {
  const target = document.querySelector('#source-files');
  const documents = store.currentRun?.source_documents || [];
  if (!documents.length) {
setHtml(target, html`<div class="empty-state">未保存可下载的原始材料索引。</div>`);
    return;
  }
setHtml(target, documents.map((item) => {
    const icon = item.role === 'tender' ? 'file-search' : 'file-check-2';
    const role = item.role === 'tender' ? '招标文件' : '企业证据';
    const sha = item.sha256 ? ` · SHA-256 ${item.sha256.slice(0, 12)}…` : '';
    return html`<a class="source-file-row" href="/api/runs/${encodeURIComponent(store.currentRun.run_id)}/files/${encodeURIComponent(item.source_id)}" target="_blank" rel="noopener" download><span class="file-icon"><i data-lucide="${icon}"></i></span><span class="operation-main"><strong>${item.filename || item.source_id}</strong><small>${role} · ${item.file_type || 'file'} · ${Number(item.pages || 0)} 个定位单元${sha}</small></span><i data-lucide="download" aria-hidden="true"></i></a>`;
  }));
  refreshIcons();
}

async function loadAssigneeOptions() {
  const assignee = document.querySelector('#run-assignee');
  const reviewer = document.querySelector('#run-reviewer');
  try {
    if (!store.membersCache.length) store.membersCache = (await request('/api/members')).members;
    setHtml(assignee, memberOptionList('未分配'));
    setHtml(reviewer, memberOptionList('未分配'));
    assignee.value = store.currentRun.assignee_id || '';
    reviewer.value = store.currentRun.reviewer_id || '';
  } catch (_error) {
setHtml(assignee, html`<option value="${store.currentRun.assignee_id || ''}">${store.currentRun.assignee_id || '未分配'}</option>`);
setHtml(reviewer, html`<option value="${store.currentRun.reviewer_id || ''}">${store.currentRun.reviewer_id || '未分配'}</option>`);
  }
}

async function loadVersionDiff() {
  const section = document.querySelector('#version-diff');
  if (!store.currentRun?.parent_run_id) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const target = document.querySelector('#version-diff-content');
setHtml(target, html`<div class="run-skeleton"></div>`);
  try {
    const diff = await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/diff/${encodeURIComponent(store.currentRun.parent_run_id)}`);
    const items = [['新增', diff.added, 'plus'], ['移除', diff.removed, 'minus'], ['状态变化', diff.changed, 'refresh-ccw']];
setHtml(target, items.map(([label, values, icon]) => html`<div class="diff-block"><span><i data-lucide="${icon}"></i>${label}</span><strong>${values.length}</strong><small>${values.slice(0, 3).map((item) => (item.after || item).title || '').join('；') || '无'}</small></div>`));
  } catch (error) {setHtml(target, html`<div class="empty-state error-text">${error.message}，版本差异加载失败。</div>`); }
  refreshIcons();
}

async function saveRunMetadata(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setButtonLoading(button, true, '保存中');
  try {
    store.currentRun = await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/metadata`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignee_id: document.querySelector('#run-assignee').value.trim() || null, reviewer_id: document.querySelector('#run-reviewer').value.trim() || null, tags: document.querySelector('#run-tags').value.split(',').map((tag) => tag.trim()).filter(Boolean), favorite: document.querySelector('#run-favorite').checked }),
    });
    showToast('协作信息已保存。');
    loadCollab();
  } catch (error) { showToast(`${error.message}，保存失败。`); }
  finally { setButtonLoading(button, false); }
}








function roleLabel(value) { return ({ OWNER: '所有者', ADMIN: '管理员', REVIEWER: '复核人', VIEWER: '只读成员' })[value] || value; }














async function submitMissedFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const reviewComplete = document.querySelector('#accuracy-review-complete').checked;
    await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/accuracy-feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: document.querySelector('#missed-category').value, predicted: 'MISSED', actual: 'RELEVANT', locator_label: document.querySelector('#missed-locator').value.trim(), quote: document.querySelector('#missed-quote').value.trim(), note: document.querySelector('#missed-note').value.trim(), dataset_scope: 'PILOT', review_complete: reviewComplete }) });
    form.reset();
    missedDialog.close();
    showToast('漏项反馈已记录。');
    await reloadAccuracy();
  } catch (error) { showToast(`${error.message}，反馈未保存。`); }
}



/**
 * 按钮加载态。
 * 旧实现把 button.innerHTML 存进 dataset 再用 raw() 还原，等于把一段已渲染的
 * DOM 字符串当作可信 HTML 重新注入——只要按钮里渲染过用户可控文本，就是一条
 * 自我 XSS 通道。现在只切 data-loading，DOM 一个字都不动，文案由 CSS 负责。
 * 第三个参数保留以免改动 18 处调用点，但不再使用。
 *
 * @param {Element | null} button
 * @param {boolean} loading
 * @param {string} [_label] 已废弃
 */
function setButtonLoading(button, loading, _label = '') {
  setLoading(button, loading);
}

function showToast(message) {
  const toast = document.querySelector('#app-toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(store.toastTimer);
  store.toastTimer = setTimeout(() => { toast.hidden = true; }, 4000);
}

/**
 * 旧实现每次都对整个 document 重扫 [data-lucide] 并替换节点，详情页一次渲染
 * 触发 5 次全文档扫描。setHtml() 现在已按子树渲染图标，这里只兜底处理
 * 直接操作 DOM 而没走 setHtml 的少数路径，且已渲染节点不会重做。
 */
function refreshIcons() {
  renderIcons(document);
}


function decisionLabel(value) {
  return ({ CONTINUE: '继续', HOLD: '暂缓', STOP: '停止', '未记录': '未记录' })[value] || value;
}


/** 语言跟随 i18n，不再写死 zh-CN。 */
function formatDate(value) {
  return formatDateTime(value);
}

// 空状态里的「用示例文件试跑」在 features/runs/list.js 中触发，
// 但打开扫描弹窗的逻辑还在 app.js。用事件解耦，避免反向依赖。
window.addEventListener('bidproof:start-sample-scan', () => { void startSampleScan(); });

// 矩阵里的检出质量反馈会影响准确率面板，但两者分属不同视图。
// 用事件通知，避免 matrix.js 反向依赖任务列表模块。
window.addEventListener('bidproof:accuracy-changed', () => { void reloadAccuracy(); });
