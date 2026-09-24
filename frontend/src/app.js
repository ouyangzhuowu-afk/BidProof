// Legacy orchestration is migrated incrementally; critical runtime contracts are checked in core/validators.js.
import { html, mount as setHtml } from './ui/render.js';
import { store, clearLegacySessionState } from './state.js';
import { clearSessionState } from './core/store.js';
import { sessionVersion, isSessionCurrent } from './core/session.js';
import { assertRunEnvelope } from './core/validators.js';
import { formatDateTime } from './i18n/index.js';
import * as theme from './core/theme.js';
import { renderIcons } from './core/icons.js';
import { setLoading, resetDomCache } from './core/dom.js';
import { clearToasts, toastError, toastFromError } from './core/toast.js';
import { exportRun } from './api/runs.js';
import { getSampleTender } from './api/workspace.js';
import { startOnboarding, advanceOnboarding, stopOnboarding } from './features/runs/onboarding.js';
import { register } from './core/router.js';
// Confirm / secret-reveal callers moved to admin; app.js no longer imports them.
import { setCurrentRole } from './core/permissions.js';
import {
  ApiError,
  json,
  request,
  saveBlob,
  watchJob,
  UPLOAD_TIMEOUT_MS,
  resetSessionTransport,
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
import { watchScanJob, stopAllScans } from './features/scan/watcher.js';
import { mountIntakeFiles, refreshIntakeFiles, clearIntakeFiles, setIntakeBusy, isIntakeBusy } from './features/scan/intake.js';
import { getReviewProgress } from './features/runs/review-model.js';

const views = {
  home: document.querySelector('#home-view'),
  jobs: document.querySelector('#jobs-view'),
  admin: document.querySelector('#admin-view'),
  detail: document.querySelector('#detail-view'),
  decision: document.querySelector('#decision-view'),
};
const missedDialog = document.querySelector('#missed-panel');
let activeViewName = 'home';
let pendingRunLoad = null;
let sessionLocked = false;
let loadingStarter = false;

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
  renderThemeControl();
});
renderThemeControl();

function renderThemeControl() {
  const button = document.querySelector('#theme-toggle');
  if (!button) return;
  const labels = { light: '浅色', dark: '深色', system: '跟随系统' };
  const next = { light: 'dark', dark: 'system', system: 'light' };
  const current = theme.preference();
  button.querySelector('span').textContent = `外观：${labels[current]}`;
  button.setAttribute('aria-label', `当前外观：${labels[current]}，切换为${labels[next[current]]}`);
  button.title = `切换为${labels[next[current]]}`;
}
document.querySelector('#back-home').addEventListener('click', showHome);
document.querySelector('#open-decision').addEventListener('click', showDecision);
document.querySelector('#aside-decision').addEventListener('click', showDecision);
document.querySelector('#back-detail').addEventListener('click', showDetail);
document.querySelector('#scan-form').addEventListener('submit', submitScan);
intakeDialog.addEventListener('click', (event) => {
  if (event.target === intakeDialog) closeIntake();
});

mountIntakeFiles();
intakeDialog.addEventListener('cancel', (event) => { if (isIntakeBusy()) event.preventDefault(); });
window.addEventListener('bidproof:comments-changed', () => loadCollab());
window.addEventListener('bidproof:unauthorized', clearPrivateSession);
window.addEventListener('bidproof:session-ended', clearPrivateSession);
window.addEventListener('bidproof:review-changed', () => {
  renderDetailSummary();
  loadCollab();
});

refreshIcons();
export const ready = initializeApp();

async function initializeApp() {
  // 鉴权全部收进 features/auth/：四种模式、MFA 两步、以及从 URL 进入的
  // 激活 / 重置，都由那边的状态机决定。这里只提供「登录之后做什么」。
  configureAuth({
    onAuthenticated: async (user) => {
      if (sessionLocked) { window.location.replace('/app'); return; }
      store.currentUser = user;
      startOnboarding(user);
      const version = sessionVersion();
      renderCurrentUser();
      await loadProjects();
      if (!isSessionCurrent(version)) return;
      await reloadRuns();
      if (!isSessionCurrent(version)) return;
      navigateFromHash();
    },
  });
  await startAuth();
  const entryUrl = new URL(window.location.href);
  if (entryUrl.searchParams.get('logout') === 'unconfirmed') {
    toastError('服务端未确认退出，本地内容已重新加载。若仍显示已登录，请恢复连接后再次退出。');
    entryUrl.searchParams.delete('logout');
    history.replaceState(null, '', `${entryUrl.pathname}${entryUrl.search}${entryUrl.hash}`);
  }
}

/** Remove private DOM before a replacement identity can authenticate. A successful
 * reauthentication reloads a fresh application, rebuilding listeners and caches. */
function clearPrivateSession() {
  if (sessionLocked) return;
  sessionLocked = true;
  stopOnboarding();
  cancelRunLoad();
  unmountRunsView(); unmountMatrix(); unmountDecisionView(); unmountCollab(); unmountJobsView(); unmountAdminView();
  stopAllScans(); resetSessionTransport(); clearSessionState();
  clearLegacySessionState(); clearIntakeFiles();
  // Keep only the authentication forms alive until the fresh application loads.
  for (const form of document.querySelectorAll('form:not(#auth-form):not(#account-action-form)')) form.reset();
  for (const dialog of document.querySelectorAll('dialog:not(#auth-panel):not(#account-action-panel)')) if (dialog.open) dialog.close();
  for (const view of Object.values(views)) view?.replaceChildren();
  document.querySelector('#app-main')?.replaceChildren();
  document.querySelector('#toast')?.replaceChildren();
  clearToasts(); resetDomCache();
  renderCurrentUser();
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
  const passwordUsername = document.querySelector('#password-username');
  if (passwordUsername) passwordUsername.value = store.currentUser?.username || '';
}




async function startSampleScan(scenario = 'software') {
  if (sessionLocked || loadingStarter || isIntakeBusy()) return;
  if (!['software', 'operations', 'own'].includes(scenario)) return;
  if (scenario === 'own') { store.rescanParentId = null; await openIntake(); return; }
  const version = sessionVersion();
  loadingStarter = true;
  for (const button of document.querySelectorAll('[data-starter]')) button.disabled = true;
  showToast('正在准备示例文件…');
  try {
    const [tender, evidence] = await Promise.all([
      getSampleTender(scenario, 'tender'), getSampleTender(scenario, 'evidence'),
    ]);
    if (!isSessionCurrent(version)) return;
    // Never replace files a person has already selected while a request was pending.
    if (document.querySelector('#tender-file').files.length || document.querySelector('#evidence-files').files.length) {
      await openIntake();
      showToast('已保留你选好的材料。清空文件后可重新选择示例。');
      return;
    }
    const label = scenario === 'software' ? '软件实施' : '系统运维';
    for (const [selector, blob, suffix] of [['#tender-file', tender, '招标文件'], ['#evidence-files', evidence, '企业材料']]) {
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], `【合成示例】${label}-${suffix}.pdf`, { type: 'application/pdf' }));
      document.querySelector(selector).files = transfer.files;
    }
    if (!document.querySelector('#company-name').value) document.querySelector('#company-name').value = '示例软件服务企业';
    refreshIntakeFiles();
    store.rescanParentId = null;
    await openIntake();
    showToast('两份合成示例已备好，点击“开始审查”查看结果。');
  } catch (error) {
    if (!isSessionCurrent(version)) return;
    showToast(`${error.message}。可以重试，或上传自己的材料。`);
    store.rescanParentId = null;
    await openIntake();
  } finally {
    loadingStarter = false;
    for (const button of document.querySelectorAll('[data-starter]')) button.disabled = false;
  }
}

async function openIntake() {
  if (sessionLocked) return;
  const version = sessionVersion();
  await loadProjects();
  if (!isSessionCurrent(version)) return;
  if (store.rescanParentId && store.currentRun?.project_id) document.querySelector('#tender-project').value = store.currentRun.project_id;
  if (!intakeDialog.open) intakeDialog.showModal();
  advanceOnboarding(1);
  const ready = document.querySelector('#tender-file').files.length;
  document.querySelector(ready ? '#scan-form button[type="submit"]' : '#tender-file').focus();
  refreshIcons();
}

function closeIntake() {
  if (isIntakeBusy()) return;
  if (intakeDialog.open) intakeDialog.close();
  document.querySelector('#message').textContent = '';
}






async function submitScan(event) {
  event.preventDefault();
  if (sessionLocked || isIntakeBusy()) return;
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = document.querySelector('#message');
  const session = sessionVersion();
  const parentId = store.rescanParentId;
  const filename = document.querySelector('#tender-file')?.files?.[0]?.name || '招标文件';
  setButtonLoading(button, true, '正在提交');
  message.textContent = '';
  try {
    const formData = new FormData(form);
    if (!document.querySelector('#evidence-files').files.length) formData.delete('evidence');
    if (parentId) formData.set('parent_run_id', parentId);
    setIntakeBusy(true);
    const job = await request('/api/jobs', { method: 'POST', body: formData, timeoutMs: UPLOAD_TIMEOUT_MS });
    if (!isSessionCurrent(session)) return;
    if (typeof job?.job_id !== 'string' || !job.job_id) throw new Error('提交结果未能确认，请先在扫描作业中核对，避免重复提交');
    advanceOnboarding(2);
    setIntakeBusy(false);
    form.reset(); closeIntake(); store.rescanParentId = null;
    watchScanJob(job.job_id, filename, (runId) => { if (isSessionCurrent(session)) void openRun(runId); });
    showToast(parentId ? '新版本已进入后台队列，完成后可对比原版本。' : '扫描已进入后台队列，完成后会通知你。');
    await reloadRuns();
  } catch (error) {
    if (isSessionCurrent(session)) message.textContent = `${error.message}。如提交超时，请先在扫描作业中核对结果。`;
  } finally {
    if (isSessionCurrent(session)) {
      setIntakeBusy(false);
      setButtonLoading(button, false);
    }
  }
}









async function exportCurrentRun(format) {
  if (sessionLocked || !store.currentRun) return;
  try { await exportRun(store.currentRun.run_id, format); }
  catch (error) { toastFromError(error, '报告未能下载，请重试。'); }
}

async function openRun(runId, destination = 'detail') {
  if (sessionLocked) return;
  cancelRunLoad();
  const controller = new AbortController();
  pendingRunLoad = controller;
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.hidden = false;
  try {
    const run = await request(`/api/runs/${encodeURIComponent(runId)}`, { signal: controller.signal });
    // A slow earlier task must not replace a newer task or pull the user back
    // after they navigated away. Some transports may settle after cancellation.
    if (pendingRunLoad !== controller) return;
    assertRunEnvelope(run, runId);
    pendingRunLoad = null;
    if (overlay) overlay.hidden = true;
    store.currentRun = run;
    advanceOnboarding(3);
    resetMatrixView();
    document.querySelector('#requirement-search').value = '';
    if (destination === 'decision') showDecision();
    else showDetail();
  } catch (error) {
    if (pendingRunLoad === controller && !error.isAborted) showToast(`${error.message}，请刷新任务列表后重试。`);
  } finally {
    if (pendingRunLoad === controller) {
      pendingRunLoad = null;
      if (overlay) overlay.hidden = true;
    }
  }
}

function cancelRunLoad() {
  pendingRunLoad?.abort();
  pendingRunLoad = null;
  const overlay = document.getElementById('loading-overlay');
  if (overlay) overlay.hidden = true;
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
  if (sessionLocked) return;
  // 视图切换仍由 app.js 的 showView 负责（路由迁移见批次 5）。
  // 这里只保证进入本视图时新模块被挂载、离开时被卸载。
  showView('home', '扫描任务');
  void ensureFilterOptions().then(() => { if (activeViewName === 'home') mountRunsView(); });
  reloadRuns();
}

function showJobs() {
  if (sessionLocked) return;
  showView('jobs', '扫描作业');
  mountJobsView();
  void reloadJobs();
}




function showAdmin() {
  if (sessionLocked) return;
  showView('admin', '成员与设置');
  // 四个面板各自取数、各自显示状态。旧实现用一个 Promise.all 拉五个接口，
  // 任何一个挂掉五块一起变错误态 —— 而其中四块的数据其实已经拿到了。
  mountAdminView();
  reloadAdmin();
}
























function showDecision() {
  if (sessionLocked) return;
  if (!store.get?.().currentRun && !store.currentRun) return;
  showView('decision', '人工决策');
  mountDecisionView();
  renderDecision();
}

function showDetail() {
  if (sessionLocked) return;
  mountMatrix();
  mountCollab();
  if (!store.currentRun) return showHome();
  showView('detail', '审查工作台');
  renderDetail();
}


function showView(name, context, pushHash = true) {
  cancelRunLoad();
  activeViewName = name;
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
  document.querySelector('#nav-runs').classList.toggle('active', ['home', 'detail', 'decision'].includes(name));
  setNavCurrent(document.querySelector('#nav-runs'), name === 'home' || name === 'detail' || name === 'decision');
  for (const [navId, viewName] of [['nav-jobs', 'jobs'], ['nav-admin', 'admin']]) {
    const nav = document.querySelector(`#${navId}`);
    nav.classList.toggle('active', name === viewName);
    setNavCurrent(nav, name === viewName);
  }
  document.querySelectorAll('[data-mobile-view]').forEach((button) => button.classList.toggle('active', button.dataset.mobileView === name || (button.dataset.mobileView === 'home' && ['detail', 'decision'].includes(name))));
  window.scrollTo({ top: 0, behavior: 'instant' });
  document.querySelector('#app-main').focus({ preventScroll: true });
  refreshIcons();
}

function setNavCurrent(node, current) {
  if (current) node.setAttribute('aria-current', 'page');
  else node.removeAttribute('aria-current');
}

function navigateFromHash() {
  const hash = location.hash.replace(/^#/, '');
  if (!hash) return showHome();
  const [view, id] = hash.split('/');
  if (view === 'home') showHome();
  else if (view === 'jobs') showJobs();
  else if (view === 'admin') showAdmin();
  else if ((view === 'detail' || view === 'decision') && id) openRun(id, view);
}

window.addEventListener('popstate', navigateFromHash);


function renderDetail() {
  document.querySelector('#detail-title').textContent = store.currentRun.tender_filename;
  document.querySelector('#detail-subtitle').textContent = `第 ${store.currentRun.version_number || 1} 轮审查 · ${store.currentRun.requirement_count} 项要求 · ${store.currentRun.evidence_assets.length} 份企业证据`;
  document.querySelector('#detail-updated').textContent = `更新于 ${formatDate(store.currentRun.updated_at)}`;
  renderDetailSummary();
  renderSourceFiles();

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

function renderDetailSummary() {
  const run = store.currentRun;
  if (!run) return;
  const items = run.requirements || [];
  const fatal = items.filter((item) => item.category === 'FATAL' && item.status !== 'PASS').length;
  const unresolved = items.filter((item) => item.status !== 'PASS').length;
  const pending = items.filter((item) => ['UNKNOWN', 'NEEDS_REVIEW'].includes(item.status)).length;
  const progress = getReviewProgress(run);
  const quality = run.scan_quality || {};
  const gates = quality.ocr_engineering_gates || {};
  const incomplete = Number(quality.ocr_failed_pages || 0) > 0 || Number(quality.low_text_confidence_pages || 0) > 0;
  const qualityPending = incomplete || gates.forced_requirement_status === 'NEEDS_REVIEW';
  let title = fatal ? `仍有 ${fatal} 项废标风险待处理` : unresolved ? `还有 ${unresolved} 项需要核验` : progress.pending ? '初检完成，请继续人工核验' : '本轮人工审查已完成';
  let note = fatal ? '优先核对红线条款及对应证据，再完成其他审查项。' : '逐项对照原文，记录判断依据与处理结果。';
  if (!items.length) { title = '尚无可核验的审查项'; note = '请检查上传材料与扫描质量，空结果不代表无风险。'; }
  else if (incomplete) { note = '部分原文识别不完整，请先检查扫描质量并核对原页。'; if (!unresolved) title = '原文识别仍需核验'; }
  else if (gates.forced_requirement_status === 'NEEDS_REVIEW' && !unresolved) { title = '条款已处理，扫描质量仍待复核'; }
  const target = document.querySelector('#detail-summary');
  target.dataset.tone = fatal ? 'fatal' : (!items.length || unresolved || qualityPending || progress.pending ? 'review' : 'pass');
  setHtml(target, html`
    <div class="health-verdict"><span class="health-verdict__icon"><i data-lucide="${fatal ? 'shield-alert' : 'clipboard-check'}" aria-hidden="true"></i></span><div><strong>${title}</strong><p>${note}</p></div></div>
    <dl class="health-metrics">
      <div><dt>未解除废标风险</dt><dd class="${fatal ? 'is-danger' : ''}">${fatal}<small> 项</small></dd></div>
      <div><dt>待复核 / 补证据</dt><dd class="${pending ? 'is-review' : ''}">${pending}<small> 项</small></dd></div>
      <div><dt>人工审查进度</dt><dd>${progress.reviewed}<small> / ${progress.total} 项已处理</small></dd><progress max="${Math.max(1, progress.total)}" value="${progress.reviewed}" aria-label="人工已处理 ${progress.reviewed} / ${progress.total} 项"></progress></div>
    </dl>`);
  const audit = document.querySelector('#audit-summary');
  setHtml(audit, html`<p class="audit-copy">人工已处理包括确认与驳回；处理进度不代表风险已经解除。通过需具备招标和企业证据的双侧定位与原文。</p>`);
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
  const run = store.currentRun;
  const assignee = document.querySelector('#run-assignee');
  const reviewer = document.querySelector('#run-reviewer');
  try {
    if (!store.membersCache.length) store.membersCache = (await request('/api/members')).members;
    if (store.currentRun?.run_id !== run.run_id || activeViewName !== 'detail') return;
    setHtml(assignee, memberOptionList('未分配'));
    setHtml(reviewer, memberOptionList('未分配'));
    const owner = document.querySelector('#remediation-owner');
    if (owner) { const selected = owner.value; setHtml(owner, memberOptionList('未分配')); owner.value = selected; }
    assignee.value = store.currentRun.assignee_id || '';
    reviewer.value = store.currentRun.reviewer_id || '';
  } catch (_error) {
    if (store.currentRun?.run_id !== run.run_id || activeViewName !== 'detail') return;
setHtml(assignee, html`<option value="${store.currentRun.assignee_id || ''}">${store.currentRun.assignee_id || '未分配'}</option>`);
setHtml(reviewer, html`<option value="${store.currentRun.reviewer_id || ''}">${store.currentRun.reviewer_id || '未分配'}</option>`);
  }
}

async function loadVersionDiff() {
  const run = store.currentRun;
  const section = document.querySelector('#version-diff');
  if (!store.currentRun?.parent_run_id) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const target = document.querySelector('#version-diff-content');
setHtml(target, html`<div class="run-skeleton"></div>`);
  try {
    const diff = await request(`/api/runs/${encodeURIComponent(run.run_id)}/diff/${encodeURIComponent(run.parent_run_id)}`);
    if (store.currentRun?.run_id !== run.run_id || activeViewName !== 'detail') return;
    const items = [['新增', diff.added, 'plus'], ['移除', diff.removed, 'minus'], ['状态变化', diff.changed, 'refresh-ccw']];
setHtml(target, items.map(([label, values, icon]) => html`<div class="diff-block"><span><i data-lucide="${icon}"></i>${label}</span><strong>${values.length}</strong><small>${values.slice(0, 3).map((item) => (item.after || item).title || '').join('；') || '无'}</small></div>`));
  } catch (error) {
    if (store.currentRun?.run_id !== run.run_id || activeViewName !== 'detail') return;
    setHtml(target, html`<div class="empty-state error-text">${error.message}，版本差异加载失败。</div>`);
  }
  refreshIcons();
}

async function saveRunMetadata(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const runId = store.currentRun.run_id;
  setButtonLoading(button, true, '保存中');
  try {
    const updated = await request(`/api/runs/${encodeURIComponent(runId)}/metadata`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignee_id: document.querySelector('#run-assignee').value.trim() || null, reviewer_id: document.querySelector('#run-reviewer').value.trim() || null, tags: document.querySelector('#run-tags').value.split(',').map((tag) => tag.trim()).filter(Boolean), favorite: document.querySelector('#run-favorite').checked }),
    });
    if (store.currentRun?.run_id !== runId) return;
    if (Number(updated.revision) >= Number(store.currentRun.revision)) store.currentRun = updated;
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
window.addEventListener('bidproof:start-sample-scan', (event) => { void startSampleScan(event.detail?.scenario); });

// 矩阵里的检出质量反馈会影响准确率面板，但两者分属不同视图。
// 用事件通知，避免 matrix.js 反向依赖任务列表模块。
window.addEventListener('bidproof:accuracy-changed', () => { void reloadAccuracy(); });

// Migrated views navigate through core/router; register the legacy entry points too.
// This preserves real task links and decision links during incremental migration.
register({ name: 'home', title: '扫描任务', enter: () => showHome() });
register({ name: 'jobs', title: '扫描作业', enter: () => showJobs() });
register({ name: 'admin', title: '成员与设置', enter: () => showAdmin() });
register({ name: 'detail', title: '审查工作台', takesId: true, enter: (id) => openRun(id) });
register({ name: 'decision', title: '人工决策', takesId: true, enter: (id) => openRun(id, 'decision') });
