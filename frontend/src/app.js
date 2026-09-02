import { html, raw, setHtml } from './escape.js';
import { store } from './state.js';

const views = {
  home: document.querySelector('#home-view'),
  jobs: document.querySelector('#jobs-view'),
  admin: document.querySelector('#admin-view'),
  detail: document.querySelector('#detail-view'),
  decision: document.querySelector('#decision-view'),
};
const PAGE_SIZE = 12;
const missedDialog = document.querySelector('#missed-panel');
const authDialog = document.querySelector('#auth-panel');
const accountActionDialog = document.querySelector('#account-action-panel');

const intakeDialog = document.querySelector('#intake-panel');
const openIntakeButtons = ['#new-scan-button', '#top-new-scan', '#nav-new-scan'];
openIntakeButtons.forEach((selector) => document.querySelector(selector).addEventListener('click', () => { store.rescanParentId = null; openIntake(); }));
document.querySelector('#close-intake').addEventListener('click', closeIntake);
document.querySelector('#cancel-intake').addEventListener('click', closeIntake);
document.querySelector('#nav-runs').addEventListener('click', showHome);
document.querySelector('#nav-jobs').addEventListener('click', showJobs);
document.querySelector('#nav-admin').addEventListener('click', showAdmin);
document.querySelector('#refresh-jobs').addEventListener('click', loadJobs);
document.querySelector('#member-form').addEventListener('submit', createMember);
document.querySelectorAll('[data-member-mode]').forEach((button) => button.addEventListener('click', () => setMemberCreateMode(button.dataset.memberMode)));
document.querySelectorAll('[data-auth-mode]').forEach((button) => button.addEventListener('click', () => setAuthMode(button.dataset.authMode === 'trial')));
document.querySelector('#project-form').addEventListener('submit', createProject);
document.querySelector('#retention-form').addEventListener('submit', saveRetention);
document.querySelector('#purge-retention').addEventListener('click', purgeRetention);
document.querySelector('#create-backup').addEventListener('click', createBackup);
document.querySelector('#password-form').addEventListener('submit', changePassword);
document.querySelector('#mfa-form').addEventListener('submit', submitMfaSettings);
document.querySelector('#mfa-enroll').addEventListener('click', enrollMfa);
document.querySelector('#token-form').addEventListener('submit', createApiToken);
document.querySelector('#tokens-list').addEventListener('click', (event) => {
  const button = event.target.closest('[data-revoke-token]');
  if (button) revokeApiToken(button.dataset.revokeToken);
});
document.querySelectorAll('[data-mobile-view]').forEach((button) => button.addEventListener('click', () => {
  if (button.dataset.mobileView === 'home') showHome();
  if (button.dataset.mobileView === 'jobs') showJobs();
  if (button.dataset.mobileView === 'admin') showAdmin();
}));
document.querySelector('#refresh-runs').addEventListener('click', loadRuns);
document.querySelector('#run-scope').addEventListener('change', (event) => { store.runScope = event.target.value; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-project-filter').addEventListener('change', (event) => { store.projectFilter = event.target.value; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-search').addEventListener('input', (event) => {
  store.runSearch = event.target.value.trim();
  clearTimeout(store.runSearchTimer);
  store.runSearchTimer = setTimeout(() => { store.selectedRunIds.clear(); loadRuns(); }, 250);
});
document.querySelector('#run-tag-filter').addEventListener('change', (event) => { store.runTagFilter = event.target.value.trim(); store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-assignee-filter').addEventListener('change', (event) => { store.runAssigneeFilter = event.target.value; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-reviewer-filter').addEventListener('change', (event) => { store.runReviewerFilter = event.target.value; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-favorite-filter').addEventListener('change', (event) => { store.runFavoriteOnly = event.target.checked; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#run-sort').addEventListener('change', (event) => { store.runSort = event.target.value; store.selectedRunIds.clear(); loadRuns(); });
document.querySelector('#clear-run-filters').addEventListener('click', clearRunFilters);
document.querySelector('#select-all-runs').addEventListener('change', toggleAllRuns);
document.querySelector('#bulk-archive').addEventListener('click', () => bulkManage('ARCHIVE'));
document.querySelector('#bulk-restore').addEventListener('click', () => bulkManage('RESTORE'));
document.querySelector('#bulk-export').addEventListener('click', bulkExportReports);
document.querySelector('#bulk-delete').addEventListener('click', () => bulkManage('DELETE'));
document.querySelector('#export-html').addEventListener('click', () => exportCurrentRun('html'));
document.querySelector('#export-csv').addEventListener('click', () => exportCurrentRun('csv'));
document.querySelector('#export-pdf').addEventListener('click', () => exportCurrentRun('pdf'));
document.querySelector('#rescan-run').addEventListener('click', () => { store.rescanParentId = store.currentRun?.run_id || null; openIntake(); });
document.querySelector('#run-metadata-form').addEventListener('submit', saveRunMetadata);
document.querySelector('#comment-form').addEventListener('submit', addComment);
document.querySelector('#remediation-form').addEventListener('submit', createRemediation);
document.querySelector('#remediations-list').addEventListener('change', (event) => {
  const select = event.target.closest('[data-remediation-status]');
  if (select) updateRemediation(select.dataset.remediationStatus, { status: select.value }, select);
});
document.querySelector('#report-missed').addEventListener('click', () => missedDialog.showModal());
document.querySelector('#close-missed').addEventListener('click', () => missedDialog.close());
document.querySelector('#cancel-missed').addEventListener('click', () => missedDialog.close());
document.querySelector('#missed-form').addEventListener('submit', submitMissedFeedback);
document.querySelector('#auth-form').addEventListener('submit', submitAuth);
document.querySelector('#account-action-form').addEventListener('submit', submitAccountAction);
document.querySelector('#logout-button').addEventListener('click', logout);
document.querySelectorAll('[data-password-toggle]').forEach((button) => button.addEventListener('click', togglePasswordVisibility));
document.querySelector('#back-home').addEventListener('click', showHome);
document.querySelector('#open-decision').addEventListener('click', showDecision);
document.querySelector('#aside-decision').addEventListener('click', showDecision);
document.querySelector('#back-detail').addEventListener('click', showDetail);
document.querySelector('#scan-form').addEventListener('submit', submitScan);
document.querySelector('#decision-form').addEventListener('submit', submitDecision);
document.querySelector('#requirements').addEventListener('click', handleRequirementAction);
document.querySelector('#risk-list').addEventListener('click', handleRequirementAction);
document.querySelector('#requirement-search').addEventListener('input', (event) => {
  store.searchTerm = event.target.value.trim().toLocaleLowerCase('zh-CN');
  store.matrixPage = 1;
  renderMatrix();
});
intakeDialog.addEventListener('click', (event) => {
  if (event.target === intakeDialog) closeIntake();
});
authDialog.addEventListener('cancel', (event) => event.preventDefault());
accountActionDialog.addEventListener('cancel', (event) => event.preventDefault());

refreshIcons();
initializeApp();

async function initializeApp() {
  try {
    if (await initializeAccountAction()) return;
    const status = await request('/api/auth/status');
    store.authStatus = status;
    const mfaToken = new URLSearchParams(window.location.search).get('mfa_token');
    if (mfaToken && !status.authenticated) {
      store.pendingMfaToken = mfaToken;
      return showAuth(false);
    }
    if (!status.authenticated && !status.setup_required) return showAuth(false);
    if (status.setup_required) return showAuth(true, status.bootstrap_locked ? '生产环境尚未配置初始化令牌，请联系运维人员。' : '');
    store.currentUser = status.user;
    renderCurrentUser();
    await loadProjects();
    loadRuns();
  } catch (error) { showAuth(false, error.message); }
}

function showAuth(setup, message = '') {
  store.authSetupRequired = setup;
  if (setup) store.authTrialMode = false;
  const trialEnabled = !setup && Boolean(store.authStatus?.trial_join_enabled);
  document.querySelector('#auth-mode-wrap').hidden = !trialEnabled;
  if (!trialEnabled) store.authTrialMode = false;
  applyAuthMode(message);
  document.querySelector('#auth-form button[type="submit"]').disabled = Boolean(store.authStatus?.bootstrap_locked);
  if (!authDialog.open) authDialog.showModal();
  setTimeout(() => {
    const focusId = store.pendingMfaToken ? '#auth-mfa-code' : (setup ? '#auth-workspace' : (store.authTrialMode ? '#auth-join-code' : '#auth-username'));
    document.querySelector(focusId)?.focus();
  }, 0);
  refreshIcons();
}

function setAuthMode(trial) {
  store.authTrialMode = Boolean(trial) && Boolean(store.authStatus?.trial_join_enabled) && !store.authSetupRequired;
  applyAuthMode('');
  setTimeout(() => document.querySelector(store.authTrialMode ? '#auth-join-code' : '#auth-username')?.focus(), 0);
  refreshIcons();
}

function applyAuthMode(message = '') {
  const setup = store.authSetupRequired;
  const trial = !setup && store.authTrialMode;
  document.querySelectorAll('[data-auth-mode]').forEach((button) => {
    button.classList.toggle('is-active', (button.dataset.authMode === 'trial') === trial);
  });
  document.querySelector('#auth-title').textContent = setup ? '初始化企业管理员' : (trial ? '试用加入企业空间' : '登录企业空间');
  document.querySelector('#auth-subtitle').textContent = setup
    ? '使用运维令牌创建首个企业空间和所有者账号。'
    : (trial ? '输入组织者提供的试用加入码，自助创建复核人账号。' : '使用企业账号进入任务与证据数据。');
  document.querySelector('#setup-fields').hidden = !setup;
  document.querySelector('#auth-workspace').required = setup;
  const tokenRequired = setup && Boolean(store.authStatus?.bootstrap_token_required);
  document.querySelector('#bootstrap-token-wrap').hidden = !tokenRequired;
  document.querySelector('#auth-bootstrap-token').required = tokenRequired;
  document.querySelector('#trial-join-fields').hidden = !trial;
  document.querySelector('#auth-join-code').required = trial;
  document.querySelector('#auth-confirm-wrap').hidden = !(setup || trial);
  document.querySelector('#auth-password-confirm').required = setup || trial;
  document.querySelector('#auth-password').minLength = (setup || trial) ? 12 : 1;
  document.querySelector('#auth-password').autocomplete = (setup || trial) ? 'new-password' : 'current-password';
  document.querySelector('#auth-password-hint').hidden = !(setup || trial);
  document.querySelector('#auth-help').hidden = setup;
  document.querySelector('#auth-help').textContent = trial
    ? '已有账号？切换到「登录」。忘记密码仍需管理员重置。'
    : (store.authStatus?.trial_join_enabled
      ? '没有账号？切换到「试用加入」。无法登录可联系管理员重置密码。'
      : '无法登录？请联系企业管理员生成一次性密码重置链接。');
  document.querySelector('#auth-submit-label').textContent = store.pendingMfaToken ? '完成验证' : (setup ? '创建并进入' : (trial ? '加入并进入' : '登录'));
  document.querySelector('#mfa-fields').hidden = !store.pendingMfaToken;
  document.querySelector('#auth-mfa-code').required = Boolean(store.pendingMfaToken);
  document.querySelector('#auth-username').disabled = Boolean(store.pendingMfaToken);
  document.querySelector('#auth-password').disabled = Boolean(store.pendingMfaToken);
  document.querySelector('#oidc-login-wrap').hidden = setup || trial || Boolean(store.pendingMfaToken) || !store.authStatus?.oidc_enabled;
  document.querySelector('#auth-message').textContent = message || (store.pendingMfaToken ? '请输入身份验证器中的 6 位验证码。' : '');
}

async function submitAuth(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const loadingLabel = store.pendingMfaToken ? '正在验证' : (store.authSetupRequired ? '正在初始化' : (store.authTrialMode ? '正在加入' : '正在登录'));
  setButtonLoading(button, true, loadingLabel);
  try {
    if (store.pendingMfaToken) {
      store.currentUser = await request('/api/auth/mfa/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: document.querySelector('#auth-mfa-code').value, mfa_token: store.pendingMfaToken }),
      });
      store.pendingMfaToken = '';
      authDialog.close();
      form.reset();
      renderCurrentUser();
      await loadProjects();
      await loadRuns();
      return;
    }
    const payload = { username: document.querySelector('#auth-username').value.trim(), password: document.querySelector('#auth-password').value };
    let endpoint = '/api/auth/login';
    if (store.authSetupRequired) {
      if (payload.password !== document.querySelector('#auth-password-confirm').value) throw new Error('两次输入的密码不一致');
      payload.workspace_name = document.querySelector('#auth-workspace').value.trim();
      payload.bootstrap_token = document.querySelector('#auth-bootstrap-token').value || null;
      endpoint = '/api/auth/bootstrap';
    } else if (store.authTrialMode) {
      if (payload.password !== document.querySelector('#auth-password-confirm').value) throw new Error('两次输入的密码不一致');
      payload.join_code = document.querySelector('#auth-join-code').value;
      endpoint = '/api/auth/trial-join';
    }
    const result = await request(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (result.mfa_required) {
      store.pendingMfaToken = result.mfa_token;
      applyAuthMode('请输入身份验证器中的 6 位验证码。');
      document.querySelector('#auth-mfa-code').focus();
      return;
    }
    store.currentUser = result;
    authDialog.close();
    form.reset();
    store.authTrialMode = false;
    renderCurrentUser();
    await loadProjects();
    await loadRuns();
  } catch (error) {
    document.querySelector('#auth-message').textContent = error.message;
    document.querySelector(store.pendingMfaToken ? '#auth-mfa-code' : (store.authTrialMode ? '#auth-join-code' : '#auth-password')).focus();
  }
  finally { setButtonLoading(button, false); }
}

async function logout() {
  await request('/api/auth/logout', { method: 'POST' });
  window.location.replace('/app');
}

function renderCurrentUser() {
  const container = document.querySelector('#current-user');
  container.hidden = !store.currentUser;
  document.querySelector('#logout-button').hidden = !store.currentUser;
  document.querySelector('#current-username').textContent = store.currentUser?.username || '';
  document.querySelector('#current-user-role').textContent = store.currentUser ? roleLabel(store.currentUser.role) : '';
  document.querySelector('#password-username').value = store.currentUser?.username || '';
}

function togglePasswordVisibility(event) {
  const button = event.currentTarget;
  const input = document.querySelector(`#${CSS.escape(button.dataset.passwordToggle)}`);
  const showing = input.type === 'text';
  input.type = showing ? 'password' : 'text';
  button.setAttribute('aria-label', showing ? '显示密码' : '隐藏密码');
setHtml(button, html`<i data-lucide="${showing ? 'eye' : 'eye-off'}"></i>`);
  refreshIcons();
}

async function initializeAccountAction() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const requestedAction = params.get('auth_action');
  if (!token || !['activate', 'reset'].includes(requestedAction)) return false;
  try {
    const inspected = await request(`/api/auth/action?token=${encodeURIComponent(token)}`);
    store.accountAction = { token, action: inspected.action };
    document.querySelector('#account-action-title').textContent = inspected.action === 'INVITE' ? '激活企业账号' : '重置账号密码';
    document.querySelector('#account-action-subtitle').textContent = inspected.action === 'INVITE' ? `接受邀请并设置 ${roleLabel(inspected.role)} 账号密码。` : '设置新密码后，旧会话将全部失效。';
    document.querySelector('#account-action-username').value = inspected.username;
    document.querySelector('#account-action-submit').textContent = inspected.action === 'INVITE' ? '激活并进入' : '重置并进入';
  } catch (error) {
    store.accountAction = null;
    document.querySelector('#account-action-message').textContent = error.message;
    document.querySelector('#account-action-form button[type="submit"]').disabled = true;
  }
  accountActionDialog.showModal();
  refreshIcons();
  return true;
}

async function submitAccountAction(event) {
  event.preventDefault();
  if (!store.accountAction) return;
  const password = document.querySelector('#account-action-password').value;
  const confirm = document.querySelector('#account-action-confirm').value;
  const message = document.querySelector('#account-action-message');
  if (password !== confirm) {
    message.textContent = '两次输入的密码不一致';
    document.querySelector('#account-action-confirm').focus();
    return;
  }
  const button = event.currentTarget.querySelector('button[type="submit"]');
  setButtonLoading(button, true, '正在设置');
  try {
    const endpoint = store.accountAction.action === 'INVITE' ? '/api/auth/activate' : '/api/auth/reset-password';
    store.currentUser = await request(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: store.accountAction.token, password }) });
    window.history.replaceState({}, '', '/app');
    accountActionDialog.close();
    renderCurrentUser();
    await loadProjects();
    await loadRuns();
  } catch (error) {
    message.textContent = error.message;
  } finally { setButtonLoading(button, false); }
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

async function loadRuns() {
  const list = document.querySelector('#runs-list');
  const refresh = document.querySelector('#refresh-runs');
setHtml(list, html`<div class="run-skeleton"></div><div class="run-skeleton"></div><div class="run-skeleton"></div>`);
  refresh.disabled = true;
  try {
    await loadTaskFilterOptions();
    const params = new URLSearchParams({ include_archived: String(store.runScope !== 'ACTIVE'), sort: store.runSort });
    if (store.projectFilter) params.set('project_id', store.projectFilter);
    if (store.runSearch) params.set('search', store.runSearch);
    if (store.runTagFilter) params.set('tag', store.runTagFilter);
    if (store.runAssigneeFilter) params.set('assignee_id', store.runAssigneeFilter);
    if (store.runReviewerFilter) params.set('reviewer_id', store.runReviewerFilter);
    if (store.runFavoriteOnly) params.set('favorite', 'true');
    const runs = await request(`/api/runs?${params.toString()}`);
    const visibleRuns = store.runScope === 'ARCHIVED' ? runs.filter((run) => run.archived_at) : store.runScope === 'ACTIVE' ? runs.filter((run) => !run.archived_at) : runs;
    renderOverview(visibleRuns);
    loadAccuracySummary();
    loadNotifications();
    store.selectedRunIds.forEach((id) => { if (!visibleRuns.some((run) => run.run_id === id)) store.selectedRunIds.delete(id); });
    updateBulkControls(visibleRuns);
    if (!visibleRuns.length) {
      const filtered = store.runSearch || store.runTagFilter || store.runAssigneeFilter || store.runReviewerFilter || store.runFavoriteOnly || store.projectFilter;
setHtml(list, html`<div class="empty-state"><span>${filtered ? '没有符合当前筛选的任务，请调整条件或清除筛选。' : '还没有扫描任务，请先上传一份招标文件。'}</span></div>`);
      return;
    }
    list.replaceChildren(...visibleRuns.map(renderRunRow));
    updateBulkControls(visibleRuns);
  } catch (error) {
setHtml(list, html`<div class="empty-state error-text">${error.message}，请检查本地服务后重试。</div>`);
    renderOverview([]);
  } finally {
    refresh.disabled = false;
    refreshIcons();
  }
}

async function loadTaskFilterOptions() {
  if (!store.membersCache.length) store.membersCache = (await request('/api/members')).members;
  const options = memberOptionList('全部负责人');
  const assignee = document.querySelector('#run-assignee-filter');
  const reviewer = document.querySelector('#run-reviewer-filter');
  setHtml(assignee, options);
  setHtml(reviewer, memberOptionList('全部复核人'));
  assignee.value = store.runAssigneeFilter;
  reviewer.value = store.runReviewerFilter;
}

function clearRunFilters() {
  store.runSearch = '';
  store.runTagFilter = '';
  store.runAssigneeFilter = '';
  store.runReviewerFilter = '';
  store.runFavoriteOnly = false;
  store.runSort = 'updated_desc';
  document.querySelector('#run-search').value = '';
  document.querySelector('#run-tag-filter').value = '';
  document.querySelector('#run-assignee-filter').value = '';
  document.querySelector('#run-reviewer-filter').value = '';
  document.querySelector('#run-favorite-filter').checked = false;
  document.querySelector('#run-sort').value = store.runSort;
  store.selectedRunIds.clear();
  loadRuns();
}

async function loadNotifications() {
  const target = document.querySelector('#notifications-list');
  try {
    const payload = await request('/api/notifications');
    if (!payload.notifications.length) {
setHtml(target, html`<div class="empty-state success-text">暂无需要立即处理的提醒。</div>`);
      return;
    }
setHtml(target, payload.notifications.slice(0, 6).map((item) => html`<article class="notification-item ${item.severity}"><span class="notification-icon"><i data-lucide="${item.type === 'SCAN_JOB_FAILED' ? 'triangle-alert' : 'calendar-clock'}"></i></span><span><strong>${item.title}</strong><small>${item.message}${item.run_id ? ` · 任务 ${item.run_id.slice(0, 12)}` : ''}</small></span></article>`));
    if (payload.count > 6) target.insertAdjacentHTML('beforeend', `<small class="notification-more">还有 ${payload.count - 6} 条提醒，请打开对应任务或作业查看。</small>`);
    refreshIcons();
  } catch (error) {setHtml(target, html`<div class="empty-state error-text">${error.message}，提醒加载失败。</div>`); }
}

function renderOverview(runs) {
  const totalBlockers = runs.reduce((sum, run) => sum + Number(run.blocker_count || 0), 0);
  const totalUnresolved = runs.reduce((sum, run) => sum + Number(run.unresolved_count || 0), 0);
  const decided = runs.filter((run) => run.decision?.decision).length;
  const items = [
    ['扫描任务', runs.length, '累计任务', 'files', 'neutral'],
    ['高风险项', totalBlockers, '优先核对资格与废标项', 'shield-alert', 'danger'],
    ['待复核项', totalUnresolved, '尚未形成确定证据链', 'circle-help', 'warning'],
    ['已做决策', decided, `覆盖 ${runs.length ? Math.round(decided / runs.length * 100) : 0}% 任务`, 'clipboard-check', 'success'],
  ];
  document.querySelector('#overview-grid').replaceChildren(...items.map(([label, value, note, icon, tone]) => {
    const card = document.createElement('div');
    card.className = `overview-card ${tone}`;
setHtml(card, html`<div class="overview-top"><span>${label}</span><span class="overview-icon"><i data-lucide="${icon}"></i></span></div><strong>${value}</strong><small>${note}</small>`);
    return card;
  }));
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
      store.currentRun = await request(`/api/runs/${encodeURIComponent(store.rescanParentId)}/rescan`, { method: 'POST', body: formData });
    } else {
      const job = await request('/api/jobs', { method: 'POST', body: formData });
      form.reset();
      closeIntake();
      showToast('扫描任务已进入后台队列。');
      store.currentRun = await waitForJob(job.job_id);
    }
    form.reset();
    closeIntake();
    store.rescanParentId = null;
    store.activeCategory = 'ALL';
    store.searchTerm = '';
    store.matrixPage = 1;
    showDetail();
    await loadRuns();
    showToast('扫描完成，已生成可复核证据链。');
  } catch (error) {
    message.textContent = `${error.message}。请检查文件格式后重试。`;
  } finally {
    setButtonLoading(button, false);
  }
}

async function waitForJob(jobId) {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const job = await request(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (job.status === 'COMPLETED' && job.run_id) return request(`/api/runs/${encodeURIComponent(job.run_id)}`);
    if (job.status === 'FAILED') throw new Error('后台扫描失败，可在作业记录中重试');
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  throw new Error('扫描仍在后台执行，请稍后刷新任务列表');
}

function renderRunRow(run) {
  const row = document.createElement('div');
  const decision = run.decision?.decision || '未记录';
  row.className = 'run-row';
  row.dataset.runId = run.run_id;
  row.setAttribute('aria-label', `打开 ${run.tender_filename}，${run.blocker_count} 项高风险，${run.unresolved_count} 项待复核`);
setHtml(row, html`<label class="run-select" aria-label="选择 ${run.tender_filename}"><input type="checkbox" data-run-select="${run.run_id}" ${store.selectedRunIds.has(run.run_id) ? 'checked' : ''}><span></span></label><button class="run-open" type="button" aria-label="打开 ${run.tender_filename}，${run.blocker_count} 项高风险，${run.unresolved_count} 项待复核"><span class="run-main"><strong title="${run.tender_filename}">${run.tender_filename}</strong><small>${formatDate(run.updated_at || run.created_at)} · ${run.run_id.slice(0, 12)}</small></span><span class="run-stat danger"><b>${run.blocker_count}</b><span>高风险</span></span><span class="run-stat warning"><b>${run.unresolved_count}</b><span>待复核</span></span><span class="decision-pill ${decision}">${decisionLabel(decision)}</span><span class="run-arrow"><i data-lucide="chevron-right"></i></span></button>`);
  row.querySelector('[data-run-select]').addEventListener('change', (event) => { if (event.target.checked) store.selectedRunIds.add(run.run_id); else store.selectedRunIds.delete(run.run_id); updateBulkControls(); });
  row.querySelector('.run-open').addEventListener('click', () => openRun(run.run_id));
  return row;
}

function toggleAllRuns(event) {
  document.querySelectorAll('[data-run-select]').forEach((input) => {
    input.checked = event.target.checked;
    if (event.target.checked) store.selectedRunIds.add(input.dataset.runSelect); else store.selectedRunIds.delete(input.dataset.runSelect);
  });
  updateBulkControls();
}

function updateBulkControls(visibleRuns = []) {
  const count = store.selectedRunIds.size;
  document.querySelector('#selection-count').textContent = count ? `已选择 ${count} 个任务` : '未选择任务';
  document.querySelector('#bulk-archive').disabled = !count || store.runScope === 'ARCHIVED';
  document.querySelector('#bulk-restore').disabled = !count || store.runScope === 'ACTIVE';
  document.querySelector('#bulk-restore').hidden = store.runScope === 'ACTIVE';
  document.querySelector('#bulk-delete').disabled = !count;
  document.querySelector('#bulk-export').disabled = !count;
  const selectAll = document.querySelector('#select-all-runs');
  const total = visibleRuns.length || document.querySelectorAll('[data-run-select]').length;
  selectAll.checked = Boolean(total && count === total);
  selectAll.indeterminate = Boolean(count && count < total);
  refreshIcons();
}

async function bulkManage(action) {
  if (!store.selectedRunIds.size) return;
  if (action === 'DELETE' && !window.confirm(`确定永久删除已选择的 ${store.selectedRunIds.size} 个任务及其上传文件吗？此操作不可恢复。`)) return;
  try {
    const result = await request('/api/runs/bulk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_ids: [...store.selectedRunIds], action }) });
    store.selectedRunIds.clear();
    await loadRuns();
    showToast(`${action === 'ARCHIVE' ? '已归档' : action === 'RESTORE' ? '已恢复' : '已删除'} ${result.updated} 个任务。`);
  } catch (error) { showToast(`${error.message}，批量操作未完成。`); }
}

async function bulkExportReports() {
  if (!store.selectedRunIds.size) return;
  const button = document.querySelector('#bulk-export');
  setButtonLoading(button, true, '导出中');
  try {
    const response = await requestBlobResponse('/api/runs/bulk/report.zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_ids: [...store.selectedRunIds], format: 'pdf' }),
    });
    const blob = await response.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'bidproof-reports.zip';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    showToast(`已导出 ${store.selectedRunIds.size} 个任务的 PDF 报告。`);
  } catch (error) {
    showToast(`${error.message}，请重试。`);
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
  try {
    store.currentRun = await request(`/api/runs/${encodeURIComponent(runId)}`);
    store.activeCategory = 'ALL';
    store.searchTerm = '';
    store.matrixPage = 1;
    document.querySelector('#requirement-search').value = '';
    showDetail();
  } catch (error) {
    showToast(`${error.message}，请刷新任务列表后重试。`);
  }
}


function memberOptionList(placeholder) {
  return [
    html`<option value="">${placeholder}</option>`,
    ...store.membersCache.filter((member) => member.active).map((member) => html`<option value="${member.user_id}">${member.username} · ${roleLabel(member.role)}</option>`),
  ];
}

function showHome() {
  showView('home', '扫描任务');
  loadRuns();
}

function showJobs() {
  showView('jobs', '扫描作业');
  loadJobs();
}

async function loadJobs() {
  const target = document.querySelector('#jobs-list');
  const refresh = document.querySelector('#refresh-jobs');
setHtml(target, html`<div class="run-skeleton"></div><div class="run-skeleton"></div>`);
  refresh.disabled = true;
  try {
    const payload = await request('/api/jobs?limit=200');
    document.querySelector('#jobs-count').textContent = `${payload.jobs.length} 个作业`;
    if (!payload.jobs.length) {
setHtml(target, html`<div class="empty-state">还没有后台扫描作业。</div>`);
      return;
    }
setHtml(target, payload.jobs.map((job) => {
      const retry = job.status === 'FAILED' ? html`<button class="mini-button" type="button" data-retry-job="${job.job_id}"><i data-lucide="refresh-ccw"></i><span>重试</span></button>` : '';
      const cancel = ['PENDING', 'RUNNING'].includes(job.status) ? html`<button class="mini-button danger-action" type="button" data-cancel-job="${job.job_id}"><i data-lucide="circle-stop"></i><span>取消</span></button>` : '';
      const progressTotal = Number(job.progress_total || 0);
      const progressCurrent = Math.min(Number(job.progress_current || 0), progressTotal || Number(job.progress_current || 0));
      const progressLabel = progressTotal ? `${progressCurrent}/${progressTotal}` : (job.progress_message || '等待开始');
      const progressPercent = progressTotal ? Math.round(progressCurrent / progressTotal * 100) : 0;
      return html`<article class="job-row"><span class="operation-main"><strong>${job.job_id.slice(0, 12)}</strong><small>${job.run_id ? `任务 ${job.run_id.slice(0, 12)}` : (job.error || job.progress_message || '等待生成任务')}</small><span class="job-progress" aria-label="处理进度 ${progressLabel}"><span class="job-progress-track"><span style="width:${progressPercent}%"></span></span><small>${progressLabel}</small></span></span><span class="status-pill ${job.status}">${jobStatusLabel(job.status)}</span><span>${Number(job.attempts || 0)}</span><time>${formatDate(job.updated_at)}</time><span>${retry}${cancel}</span></article>`;
    }));
    target.querySelectorAll('[data-retry-job]').forEach((button) => button.addEventListener('click', () => retryJob(button)));
    target.querySelectorAll('[data-cancel-job]').forEach((button) => button.addEventListener('click', () => cancelJob(button)));
  } catch (error) {
setHtml(target, html`<div class="empty-state error-text">${error.message}，作业记录加载失败。</div>`);
  } finally {
    refresh.disabled = false;
    refreshIcons();
  }
}

async function retryJob(button) {
  setButtonLoading(button, true, '重试中');
  try {
    await request(`/api/jobs/${encodeURIComponent(button.dataset.retryJob)}/retry`, { method: 'POST' });
    showToast('作业已重新进入队列。');
    await loadJobs();
  } catch (error) { showToast(`${error.message}，重试未启动。`); }
  finally { setButtonLoading(button, false); }
}

async function cancelJob(button) {
  if (!window.confirm('确定取消这个扫描作业吗？已完成的结果不会被删除。')) return;
  setButtonLoading(button, true, '取消中');
  try {
    await request(`/api/jobs/${encodeURIComponent(button.dataset.cancelJob)}/cancel`, { method: 'POST' });
    showToast('作业已取消。');
    await loadJobs();
  } catch (error) { showToast(`${error.message}，作业未取消。`); }
  finally { setButtonLoading(button, false); }
}

function showAdmin() {
  showView('admin', '成员与设置');
  loadOperations();
}

async function loadMembers() {
  const target = document.querySelector('#members-list');
setHtml(target, html`<div class="run-skeleton"></div>`);
  try {
    const payload = await request('/api/members');
    store.membersCache = payload.members;
    const canManage = ['OWNER', 'ADMIN'].includes(store.currentUser?.role);
    document.querySelector('#member-form').hidden = !canManage;
setHtml(target, store.membersCache.map((member) => {
      const roleControls = canManage && member.role !== 'OWNER' ? html`<select data-member-role="${member.user_id}" aria-label="${member.username} 的角色"><option value="ADMIN" ${member.role === 'ADMIN' ? 'selected' : ''}>管理员</option><option value="REVIEWER" ${member.role === 'REVIEWER' ? 'selected' : ''}>复核人</option><option value="VIEWER" ${member.role === 'VIEWER' ? 'selected' : ''}>只读成员</option></select><button class="mini-button" type="button" data-member-active="${member.user_id}" data-active="${member.active}">${member.active ? '停用' : '启用'}</button>` : html`<span class="role-label">${roleLabel(member.role)}</span>`;
      const resetControl = canManage && member.active ? html`<button class="mini-button" type="button" data-member-reset="${member.user_id}">重置密码</button>` : '';
      return html`<article class="member-row ${member.active ? '' : 'is-inactive'}"><span class="member-avatar"><i data-lucide="user-round"></i></span><span class="operation-main"><strong>${member.username}</strong><small>${member.user_id.slice(0, 12)} · ${member.active ? '可登录' : '已停用'}</small></span><span class="member-controls">${roleControls}${resetControl}</span></article>`;
    }));
    target.querySelectorAll('[data-member-role]').forEach((select) => select.addEventListener('change', () => updateMember(select.dataset.memberRole, { role: select.value })));
    target.querySelectorAll('[data-member-active]').forEach((button) => button.addEventListener('click', () => updateMember(button.dataset.memberActive, { active: button.dataset.active !== 'true' })));
    target.querySelectorAll('[data-member-reset]').forEach((button) => button.addEventListener('click', () => resetMemberPassword(button.dataset.memberReset, button)));
  } catch (error) {setHtml(target, html`<div class="empty-state error-text">${error.message}，成员加载失败。</div>`); }
  refreshIcons();
}

async function loadProjects() {
  const target = document.querySelector('#projects-list');
  try {
    const payload = await request('/api/projects?include_archived=true');
    store.projectsCache = payload.projects;
    const activeProjects = store.projectsCache.filter((project) => !project.archived_at);
    const filter = document.querySelector('#run-project-filter');
setHtml(filter, [html`<option value="">全部项目</option>`, ...store.projectsCache.map((project) => html`<option value="${project.project_id}">${project.code} · ${project.name}${project.archived_at ? '（已归档）' : ''}</option>`)]);
    filter.value = store.projectFilter;
    const tenderProject = document.querySelector('#tender-project');
    const previousTender = tenderProject.value;
setHtml(tenderProject, activeProjects.map((project) => html`<option value="${project.project_id}">${project.code} · ${project.name}</option>`));
    if (activeProjects.some((project) => project.project_id === previousTender)) tenderProject.value = previousTender;
    const canManage = ['OWNER', 'ADMIN'].includes(store.currentUser?.role);
    document.querySelector('#project-form').hidden = !canManage;
setHtml(target, store.projectsCache.map((project) => html`<article class="project-row ${project.archived_at ? 'is-inactive' : ''}"><span class="member-avatar"><i data-lucide="folder"></i></span><span class="operation-main"><strong>${project.name}</strong><small>${project.code} · ${project.archived_at ? '已归档' : '可创建扫描'}</small></span>${canManage && project.code !== 'DEFAULT' ? html`<button class="mini-button" type="button" data-project-archive="${project.project_id}" data-archived="${Boolean(project.archived_at)}">${project.archived_at ? '恢复' : '归档'}</button>` : html`<span class="role-label">默认</span>`}</article>`));
    target.querySelectorAll('[data-project-archive]').forEach((button) => button.addEventListener('click', () => toggleProject(button)));
  } catch (error) {
setHtml(target, html`<div class="empty-state error-text">${error.message}，项目加载失败。</div>`);
  }
  refreshIcons();
}

async function createProject(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setButtonLoading(button, true, '创建中');
  try {
    const code = document.querySelector('#project-code').value.trim();
    await request('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: document.querySelector('#project-name').value.trim(), code: code || null }) });
    form.reset();
    showToast('项目已创建。');
    await loadProjects();
  } catch (error) { showToast(`${error.message}，项目未创建。`); }
  finally { setButtonLoading(button, false); }
}

async function toggleProject(button) {
  try {
    await request(`/api/projects/${encodeURIComponent(button.dataset.projectArchive)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ archived: button.dataset.archived !== 'true' }) });
    showToast(button.dataset.archived === 'true' ? '项目已恢复。' : '项目已归档。');
    await loadProjects();
  } catch (error) { showToast(`${error.message}，项目状态未更新。`); }
}

async function createMember(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = document.querySelector('#member-message');
  const direct = store.memberCreateMode === 'direct';
  setButtonLoading(button, true, direct ? '开户中' : '生成中');
  try {
    const username = document.querySelector('#member-username').value.trim();
    const role = document.querySelector('#member-role').value;
    if (direct) {
      const password = document.querySelector('#member-password').value;
      if (password.length < 12) throw new Error('直接开户密码至少 12 位');
      await request('/api/members', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password, role }) });
      form.reset();
      setMemberCreateMode('direct');
      message.textContent = `已为 ${username} 直接开户，请线下告知对方密码。`;
      await loadMembers();
    } else {
      const invitation = await request('/api/auth/invitations', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, role }) });
      form.reset();
      setMemberCreateMode('invite');
      showSecureLink(message, invitation.activation_path, '邀请链接已生成，72 小时内有效。');
    }
  } catch (error) { message.textContent = error.message; }
  finally { setButtonLoading(button, false); }
}

function setMemberCreateMode(mode) {
  store.memberCreateMode = mode === 'direct' ? 'direct' : 'invite';
  document.querySelectorAll('[data-member-mode]').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.memberMode === store.memberCreateMode);
  });
  const direct = store.memberCreateMode === 'direct';
  document.querySelector('#member-password-wrap').hidden = !direct;
  document.querySelector('#member-password').required = direct;
  document.querySelector('#member-submit-label').textContent = direct ? '直接开户' : '生成邀请';
  refreshIcons();
}

async function resetMemberPassword(userId, button) {
  setButtonLoading(button, true, '生成中');
  const message = document.querySelector('#member-message');
  try {
    const reset = await request(`/api/members/${encodeURIComponent(userId)}/password-reset`, { method: 'POST' });
    showSecureLink(message, reset.reset_path, '密码重置链接已生成，1 小时内有效。');
  } catch (error) { message.textContent = error.message; }
  finally { setButtonLoading(button, false); }
}

function showSecureLink(target, path, prefix) {
  const url = new URL(path, window.location.origin).toString();
setHtml(target, html`${prefix} <a href="${url}">打开链接</a> <button class="text-button" type="button" data-copy-secure-link>复制</button>`);
  target.querySelector('[data-copy-secure-link]').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(url);
      showToast('安全链接已复制。');
    } catch (_error) {
      window.prompt('复制以下安全链接', url);
    }
  });
}

async function updateMember(userId, payload) {
  try {
    await request(`/api/members/${encodeURIComponent(userId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    showToast('成员权限已更新。');
    await loadMembers();
  } catch (error) { showToast(`${error.message}，成员未更新。`); }
}

async function loadOperations() {
  await Promise.all([loadMembers(), loadProjects(), loadMfaStatus(), loadApiTokens()]);
  const healthTarget = document.querySelector('#operations-health');
  const backupTarget = document.querySelector('#backups-list');
  try {
    const [settings, preview, health, usage, privacy] = await Promise.all([request('/api/workspace/settings'), request('/api/retention/preview'), request('/healthz?detail=true'), request('/api/workspace/usage'), request('/api/workspace/privacy')]);
    document.querySelector('#retention-days').value = settings.retention_days;
setHtml(document.querySelector('#retention-preview'), html`<strong>${preview.count}</strong><span>个已归档任务早于 ${formatDate(preview.cutoff)}，执行前仍会再次预览。</span>`);
setHtml(healthTarget, html`<div class="health-grid"><span><small>数据库</small><strong>${health.database || 'unknown'}</strong></span><span><small>备份</small><strong>${backupStatusLabel(health.backup_status)}</strong></span><span><small>失败作业</small><strong>${Number(health.failed_jobs || 0)}</strong></span><span><small>最近验证</small><strong>${health.last_verified_backup_at ? formatDate(health.last_verified_backup_at) : '无'}</strong></span></div><small class="health-reasons">${health.degraded_reasons?.length ? `降级原因：${health.degraded_reasons.join('、')}` : '未发现降级原因'}</small>`);
setHtml(document.querySelector('#workspace-usage'), html`<div class="health-grid"><span><small>任务</small><strong>${usage.runs}</strong></span><span><small>作业</small><strong>${usage.scan_jobs}</strong></span><span><small>整改项</small><strong>${usage.remediations}</strong></span><span><small>审计事件</small><strong>${usage.audit_events}</strong></span></div>`);
setHtml(document.querySelector('#workspace-privacy'), html`<p>${privacy.boundary}</p><p>${privacy.deletion}</p><small>当前保留策略：${privacy.retention_days} 天</small>`);
  } catch (error) {setHtml(healthTarget, html`<div class="empty-state error-text">${error.message}，运行状态加载失败。</div>`); }
  try {
    const payload = await request('/api/backups');
setHtml(backupTarget, payload.backups.length ? payload.backups.map((backup) => html`<article class="backup-row"><span class="operation-main"><strong>${backup.backup_id}</strong><small>${formatDate(backup.created_at)}</small></span><span class="status-pill ${backup.valid ? 'COMPLETED' : 'FAILED'}">${backup.valid ? '已验证' : '未验证'}</span></article>`) : html`<div class="empty-state">还没有已登记备份。</div>`);
  } catch (error) {
setHtml(backupTarget, html`<div class="empty-state">当前角色无备份管理权限。</div>`);
    document.querySelector('#create-backup').hidden = true;
  }
  document.querySelector('#purge-retention').hidden = !['OWNER', 'ADMIN'].includes(store.currentUser?.role);
  refreshIcons();
}

async function saveRetention(event) {
  event.preventDefault();
  try {
    await request('/api/workspace/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ retention_days: Number(document.querySelector('#retention-days').value) }) });
    showToast('保留策略已保存。');
    await loadOperations();
  } catch (error) { showToast(`${error.message}，策略未保存。`); }
}

async function purgeRetention() {
  try {
    const preview = await request('/api/retention/preview');
    if (!preview.count) return showToast('当前没有到期归档任务。');
    if (!window.confirm(`将永久删除 ${preview.count} 个到期归档任务及上传文件，确定继续吗？`)) return;
    const result = await request('/api/retention/purge', { method: 'POST' });
    showToast(`已清理 ${result.deleted} 个到期任务。`);
    await loadOperations();
  } catch (error) { showToast(`${error.message}，清理未执行。`); }
}

async function createBackup() {
  const button = document.querySelector('#create-backup');
  setButtonLoading(button, true, '备份中');
  try {
    const result = await request('/api/backups', { method: 'POST' });
    showToast(result.valid ? '备份已创建并通过校验。' : '备份已创建但校验失败。');
    await loadOperations();
  } catch (error) { showToast(`${error.message}，备份未完成。`); }
  finally { setButtonLoading(button, false); }
}

async function changePassword(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = document.querySelector('#password-message');
  message.textContent = '';
  setButtonLoading(button, true, '更新中');
  try {
    await request('/api/auth/password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: document.querySelector('#current-password').value, new_password: document.querySelector('#new-password').value }) });
    form.reset();
    await request('/api/auth/logout', { method: 'POST' });
    window.location.replace('/app');
  } catch (error) { message.textContent = `${error.message}，密码未更新。`; }
  finally { setButtonLoading(button, false); }
}

async function loadMfaStatus() {
  const status = document.querySelector('#mfa-status');
  const secret = document.querySelector('#mfa-secret');
  if (!status) return;
  secret.hidden = true;
  secret.textContent = '';
  try {
    const payload = await request('/api/auth/status');
setHtml(status, payload.mfa_enabled
      ? html`<strong>已启用。</strong><span>登录时需要验证器或恢复码。</span>`
      : html`<span>尚未启用二次验证。</span>`);
  } catch (error) {
setHtml(status, html`<div class="empty-state error-text">${error.message}</div>`);
  }
}

async function enrollMfa() {
  const message = document.querySelector('#mfa-message');
  const secret = document.querySelector('#mfa-secret');
  message.textContent = '';
  try {
    const payload = await request('/api/auth/mfa/enroll', { method: 'POST' });
    secret.hidden = false;
    secret.textContent = `密钥：${payload.secret}\n恢复码（仅显示一次）：\n${payload.recovery_codes.join('\n')}`;
    message.textContent = '请用验证器扫描或录入密钥，然后输入一个验证码确认。';
  } catch (error) { message.textContent = error.message; }
}

async function submitMfaSettings(event) {
  event.preventDefault();
  const message = document.querySelector('#mfa-message');
  const code = document.querySelector('#mfa-code').value.trim();
  message.textContent = '';
  try {
    const status = await request('/api/auth/status');
    if (status.mfa_enabled) {
      await request('/api/auth/mfa/disable', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
      showToast('二次验证已关闭。');
    } else {
      await request('/api/auth/mfa/confirm', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) });
      showToast('二次验证已启用。');
    }
    document.querySelector('#mfa-code').value = '';
    await loadMfaStatus();
  } catch (error) { message.textContent = error.message; }
}

async function loadApiTokens() {
  const target = document.querySelector('#tokens-list');
  try {
    const payload = await request('/api/auth/tokens');
setHtml(target, payload.tokens.length
      ? payload.tokens.map((token) => html`<article class="backup-row"><span class="operation-main"><strong>${token.name}</strong><small>${token.token_prefix} · ${token.revoked_at ? '已撤销' : '有效'}</small></span>${token.revoked_at ? '' : html`<button class="button secondary" type="button" data-revoke-token="${token.token_id}">撤销</button>`}</article>`)
      : html`<div class="empty-state">还没有 API 令牌。</div>`);
    document.querySelector('#token-form').hidden = false;
  } catch (error) {
setHtml(target, html`<div class="empty-state">当前角色不能管理 API 令牌。</div>`);
    document.querySelector('#token-form').hidden = true;
  }
}

async function createApiToken(event) {
  event.preventDefault();
  const message = document.querySelector('#token-message');
  message.textContent = '';
  try {
    const created = await request('/api/auth/tokens', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: document.querySelector('#token-name').value.trim() }),
    });
    document.querySelector('#token-name').value = '';
    message.textContent = `请立即保存令牌：${created.token}`;
    await loadApiTokens();
  } catch (error) { message.textContent = error.message; }
}

async function revokeApiToken(tokenId) {
  try {
    await request(`/api/auth/tokens/${encodeURIComponent(tokenId)}`, { method: 'DELETE' });
    showToast('令牌已撤销。');
    await loadApiTokens();
  } catch (error) { showToast(`${error.message}，令牌未撤销。`); }
}

function showDetail() {
  if (!store.currentRun) return showHome();
  showView('detail', '扫描详情');
  renderDetail();
}

function showDecision() {
  if (!store.currentRun) return;
  showView('decision', '人工决策');
  const unresolved = store.currentRun.requirements.filter((item) => ['UNKNOWN', 'NEEDS_REVIEW'].includes(item.status));
  const select = document.querySelector('#unresolved-items');
  select.replaceChildren(...unresolved.map((item) => {
    const option = document.createElement('option');
    option.value = item.requirement_id;
    option.textContent = `${item.requirement_id} · ${item.label} · ${item.title.slice(0, 56)}`;
    option.selected = store.currentRun.decision?.unresolved_requirement_ids?.includes(item.requirement_id) || false;
    return option;
  }));
  const decision = store.currentRun.decision?.decision || 'HOLD';
  const radio = document.querySelector(`#decision-form input[value="${decision}"]`);
  if (radio) radio.checked = true;
  document.querySelector('#decision-note').value = store.currentRun.decision?.note || '';
setHtml(document.querySelector('#decision-context-content'), html`<div class="context-metric"><strong>${store.currentRun.blocker_count}</strong><span>资格 / 废标风险</span></div><div class="context-metric"><strong>${store.currentRun.unresolved_count}</strong><span>未解决要求</span></div><div class="context-metric"><strong>${store.currentRun.requirement_count}</strong><span>全部要求项</span></div><p>${store.currentRun.decision?.note || '尚未记录人工决定。请先核对高风险项与证据缺口。'}</p>`);
  refreshIcons();
}

function showView(name, context) {
  Object.entries(views).forEach(([key, view]) => { view.hidden = key !== name; });
  document.querySelector('#page-context').textContent = context;
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

async function submitDecision(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const values = new FormData(form);
  const unresolved = [...form.querySelector('#unresolved-items').selectedOptions].map((option) => option.value);
  const message = document.querySelector('#decision-message');
  setButtonLoading(button, true, '正在保存');
  message.textContent = '';
  try {
    store.currentRun = await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/decision`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision: values.get('decision'), note: values.get('note'), unresolved_requirement_ids: unresolved }),
    });
    showDetail();
    showToast('人工决策已保存。');
  } catch (error) {
    message.textContent = `${error.message}，请重试。`;
  } finally {
    setButtonLoading(button, false);
  }
}

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
  renderRisks();
  renderMatrix();
  loadCollaboration();
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
    loadCollaboration();
  } catch (error) { showToast(`${error.message}，保存失败。`); }
  finally { setButtonLoading(button, false); }
}

async function addComment(event) {
  event.preventDefault();
  const input = document.querySelector('#comment-body');
  const body = input.value.trim();
  if (!body) return;
  try {
    await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/comments`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
    input.value = '';
    await loadCollaboration();
    showToast('评论已添加。');
  } catch (error) { showToast(`${error.message}，评论未保存。`); }
}

async function loadCollaboration() {
  if (!store.currentRun) return;
  try {
    const [comments, audit, remediations] = await Promise.all([
      request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/comments`),
      request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/audit`),
      request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/remediations`),
    ]);
setHtml(document.querySelector('#comments-list'), comments.comments.length ? comments.comments.map((item) => html`<article class="activity-item"><strong>${item.user_id}</strong><p>${item.body}</p><time>${formatDate(item.created_at)}</time></article>`) : html`<div class="empty-state">暂无评论</div>`);
    setHtml(document.querySelector('#audit-events'), audit.events.length ? audit.events.slice(0, 30).map((item) => html`<article class="activity-item"><strong>${auditLabel(item.event_type)}</strong><p>${item.user_id}</p><time>${formatDate(item.created_at)}</time></article>`) : html`<div class="empty-state">暂无审计记录</div>`);
    await loadRemediationOwners();
    renderRemediations(remediations.remediations || []);
  } catch (error) {
setHtml(document.querySelector('#comments-list'), html`<div class="empty-state error-text">协作记录加载失败</div>`);
setHtml(document.querySelector('#remediations-list'), html`<div class="empty-state error-text">${error.message}，整改项加载失败</div>`);
  }
}

async function loadRemediationOwners() {
  const select = document.querySelector('#remediation-owner');
  try {
    if (!store.membersCache.length) store.membersCache = (await request('/api/members')).members;
setHtml(select, memberOptionList('未分配'));
  } catch (_error) {
setHtml(select, html`<option value="">未分配</option>`);
  }
  const requirementSelect = document.querySelector('#remediation-requirement');
setHtml(requirementSelect, [html`<option value="">不关联具体要求</option>`, ...(store.currentRun?.requirements || []).map((item) => html`<option value="${item.requirement_id}">${item.requirement_id} · ${item.label}</option>`)]);
}

function renderRemediations(items) {
  const target = document.querySelector('#remediations-list');
  if (!items.length) {
setHtml(target, html`<div class="empty-state">暂无整改行动。发现证据缺口后，可在这里分派负责人并跟踪截止日期。</div>`);
    return;
  }
setHtml(target, items.map((item) => {
    const owner = store.membersCache.find((member) => member.user_id === item.owner_id);
    const due = item.due_date ? new Date(`${item.due_date}T00:00:00`).toLocaleDateString('zh-CN') : '未设置';
    const overdue = item.due_date && !['DONE', 'CANCELLED'].includes(item.status) && new Date(`${item.due_date}T23:59:59`) < new Date();
    return html`<article class="remediation-row ${overdue ? 'is-overdue' : ''}"><div class="remediation-main"><strong>${item.title}</strong><small>${item.requirement_id ? `关联要求 ${item.requirement_id}` : '未关联具体要求'} · ${owner?.username || item.owner_id || '未分配'} · ${overdue ? '已逾期' : `截止 ${due}`}</small>${item.note ? html`<p>${item.note}</p>` : ''}</div><div class="remediation-controls"><label class="sr-only" for="remediation-status-${item.remediation_id}">整改状态</label><select id="remediation-status-${item.remediation_id}" data-remediation-status="${item.remediation_id}"><option value="OPEN" ${item.status === 'OPEN' ? 'selected' : ''}>待处理</option><option value="IN_PROGRESS" ${item.status === 'IN_PROGRESS' ? 'selected' : ''}>处理中</option><option value="DONE" ${item.status === 'DONE' ? 'selected' : ''}>已完成</option><option value="CANCELLED" ${item.status === 'CANCELLED' ? 'selected' : ''}>已取消</option></select></div></article>`;
  }));
}

async function createRemediation(event) {
  event.preventDefault();
  if (!store.currentRun) return;
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setButtonLoading(button, true, '创建中');
  try {
    await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/remediations`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: document.querySelector('#remediation-title-input').value.trim(), requirement_id: document.querySelector('#remediation-requirement').value || null, owner_id: document.querySelector('#remediation-owner').value || null, due_date: document.querySelector('#remediation-due').value || null }),
    });
    form.reset();
    await loadCollaboration();
    showToast('整改项已创建。');
  } catch (error) { showToast(`${error.message}，整改项未创建。`); }
  finally { setButtonLoading(button, false); }
}

async function updateRemediation(remediationId, payload, control) {
  if (control) control.disabled = true;
  try {
    await request(`/api/remediations/${encodeURIComponent(remediationId)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    await loadCollaboration();
    showToast('整改状态已更新。');
  } catch (error) {
    showToast(`${error.message}，整改状态未更新。`);
    if (control) control.disabled = false;
  }
}

function auditLabel(value) {
  return ({ RUN_CREATED: '创建扫描', RUN_RESCANNED: '重新扫描', RUN_METADATA_UPDATED: '更新协作信息', COMMENT_ADDED: '添加评论', ACCURACY_FEEDBACK_ADDED: '提交准确度反馈', SCAN_JOB_COMPLETED: '后台扫描完成', RUN_ARCHIVE: '归档任务', RUN_RESTORE: '恢复任务', REMEDIATION_CREATED: '创建整改项', REMEDIATION_UPDATED: '更新整改项' })[value] || value;
}

function roleLabel(value) { return ({ OWNER: '所有者', ADMIN: '管理员', REVIEWER: '复核人', VIEWER: '只读成员' })[value] || value; }
function jobStatusLabel(value) { return ({ PENDING: '排队中', RUNNING: '扫描中', COMPLETED: '已完成', FAILED: '失败', CANCELLED: '已取消' })[value] || value; }
function backupStatusLabel(value) { return ({ verified: '已验证', unverified: '未验证', missing: '无备份' })[value] || value || '未知'; }

function renderRisks() {
  const risks = store.currentRun.requirements
    .filter((item) => ['FATAL', 'QUALIFICATION', 'DEADLINE'].includes(item.category) && item.status !== 'PASS')
    .sort((a, b) => riskRank(a) - riskRank(b))
    .slice(0, 4);
  const target = document.querySelector('#risk-list');
  if (!risks.length) {
setHtml(target, html`<div class="empty-state success-text">当前没有需要优先处理的高风险项。</div>`);
    return;
  }
  target.replaceChildren(...risks.map(renderRiskCard));
}

function renderMatrix() {
  const categories = ['ALL', ...new Set(store.currentRun.requirements.map((item) => item.category))];
  const filters = document.querySelector('#matrix-filters');
  filters.replaceChildren(...categories.map((category) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `filter-button ${store.activeCategory === category ? 'active' : ''}`;
    button.textContent = category === 'ALL' ? '全部' : category;
    button.setAttribute('aria-pressed', String(store.activeCategory === category));
    button.addEventListener('click', () => { store.activeCategory = category; store.matrixPage = 1; renderMatrix(); });
    return button;
  }));
  const filtered = store.currentRun.requirements.filter((item) => {
    const categoryMatch = store.activeCategory === 'ALL' || item.category === store.activeCategory;
    const haystack = `${item.category} ${item.label} ${item.title} ${item.source?.quote || ''}`.toLocaleLowerCase('zh-CN');
    return categoryMatch && (!store.searchTerm || haystack.includes(store.searchTerm));
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  store.matrixPage = Math.min(store.matrixPage, pageCount);
  const start = (store.matrixPage - 1) * PAGE_SIZE;
  const items = filtered.slice(start, start + PAGE_SIZE);
  document.querySelector('#matrix-count').textContent = `共 ${filtered.length} 项`;
  const target = document.querySelector('#requirements');
  if (!items.length) setHtml(target, html`<div class="empty-state">没有符合当前条件的要求项。</div>`);
  else target.replaceChildren(...items.map(renderRequirementRow));
  renderPagination(filtered.length, pageCount);
  refreshIcons();
}

function renderRiskCard(item) {
  const article = document.createElement('article');
  article.className = `risk-card ${item.status === 'FAIL' ? 'is-fail' : ''}`;
setHtml(article, html`${requirementHeading(item)}<p class="requirement-title">${item.title}</p>${citationMarkup(item)}${explanationMarkup(item)}${requirementFooter(item)}`);
  return article;
}

function renderRequirementRow(item) {
  const details = document.createElement('details');
  details.className = 'requirement-row';
  const source = item.source || {};
setHtml(details, html`<summary class="requirement-summary"><span class="requirement-name"><strong>${item.label}</strong><small>${item.category} · ${item.requirement_id}</small></span><span class="source-page">${locatorLabel(source)}</span><span class="status ${item.status}">${statusLabel(item.status)}</span><span class="expand-icon"><i data-lucide="chevron-down"></i></span></summary><div class="requirement-detail"><p class="requirement-title">${item.title}</p>${citationMarkup(item)}${explanationMarkup(item)}${requirementFooter(item)}</div>`);
  return details;
}

function requirementHeading(item) {
  return html`<div class="requirement-top"><div><span class="category-label">${item.category}</span><h3>${item.label}</h3></div><span class="status ${item.status}">${statusLabel(item.status)}</span></div>`;
}

function citationMarkup(item) {
  const source = item.source || {};
  const evidence = item.evidence || [];
  const evidenceMarkup = evidence.length
    ? evidence.map((entry) => html`<strong>${entry.filename} · ${locatorLabel(entry)}</strong><p>${entry.quote || '已定位'}</p>`)
    : html`<strong class="muted">未匹配，需人工复核</strong>`;
  return html`<div class="citation-grid"><div class="citation-block"><span>招标原文</span><strong>${locatorLabel(source)}</strong><p>${source.quote || '未提取到可引用原文'}</p></div><div class="citation-block"><span>企业证据</span>${evidenceMarkup}</div></div>`;
}

function locatorLabel(item) {
  return item?.locator?.label || '定位缺失';
}

function explanationMarkup(item) {
  const gap = (item.evidence || []).length ? '已定位候选企业证据，仍需人工确认语义充分性与原件有效性' : ['QUALIFICATION', 'CREDENTIAL', 'BOND', 'SIGNATURE'].includes(item.category) ? '未定位到可核验的企业证据' : '该项主要依赖招标原文，需人工确认适用条件';
  const impact = item.category === 'FATAL' ? '可能导致废标或资格失效' : item.category === 'QUALIFICATION' ? '可能导致资格审查不通过' : item.category === 'DEADLINE' ? '错过节点可能导致文件不被接收' : '可能影响合规性、评分或材料完整性';
  const action = ['UNKNOWN', 'NEEDS_REVIEW'].includes(item.status) ? '补充证据并由人工复核' : item.status === 'FAIL' ? '核对原文并制定风险处置方案' : '保留原文定位并确认原件有效';
  return html`<div class="explanation-grid"><div><span>证据缺口</span><strong>${gap}</strong></div><div><span>风险影响</span><strong>${impact}</strong></div><div><span>建议动作</span><strong>${action}</strong></div></div>`;
}

function requirementFooter(item) {
  const actions = item.status === 'PASS' || item.status === 'FAIL'
    ? html`<button class="mini-button" data-review="CONFIRM" data-id="${item.requirement_id}">确认结论</button><button class="mini-button" data-review="REJECT" data-id="${item.requirement_id}">驳回结论</button>`
    : html`<button class="mini-button" data-review="REQUEST_EVIDENCE" data-id="${item.requirement_id}">请求证据</button><button class="mini-button" data-review="CONFIRM" data-id="${item.requirement_id}">保留复核</button>`;
  return html`<div class="requirement-footer"><span>${item.detection_method || 'deterministic'} · ${item.criticality || 'REVIEW'}</span><div class="action-buttons">${actions}<button class="mini-button" data-accuracy="RELEVANT" data-id="${item.requirement_id}" data-category="${item.category}">确认有效</button><button class="mini-button" data-accuracy="NOT_RELEVANT" data-id="${item.requirement_id}" data-category="${item.category}">标记误报</button></div></div>`;
}

function renderPagination(total, pageCount) {
  const target = document.querySelector('#matrix-pagination');
  if (!total) {
    target.replaceChildren();
    return;
  }
  const start = (store.matrixPage - 1) * PAGE_SIZE + 1;
  const end = Math.min(store.matrixPage * PAGE_SIZE, total);
setHtml(target, html`<span class="pagination-info">显示 ${start}-${end}，共 ${total} 项</span><span class="pagination-actions"><button class="page-button" type="button" data-page="prev" ${store.matrixPage === 1 ? 'disabled' : ''}><i data-lucide="arrow-left"></i><span>上一页</span></button><button class="page-button" type="button" data-page="next" ${store.matrixPage === pageCount ? 'disabled' : ''}><span>下一页</span><i data-lucide="arrow-right"></i></button></span>`);
  target.querySelector('[data-page="prev"]').addEventListener('click', () => { store.matrixPage -= 1; renderMatrix(); scrollMatrixIntoView(); });
  target.querySelector('[data-page="next"]').addEventListener('click', () => { store.matrixPage += 1; renderMatrix(); scrollMatrixIntoView(); });
}

function scrollMatrixIntoView() {
  document.querySelector('#matrix-title').scrollIntoView({ block: 'start', behavior: 'smooth' });
}

function handleRequirementAction(event) {
  const accuracyButton = event.target.closest('[data-accuracy]');
  if (accuracyButton) {
    submitDetectedFeedback(accuracyButton);
    return;
  }
  const button = event.target.closest('[data-review]');
  if (!button) return;
  reviewRequirement(button.dataset.id, button.dataset.review, button);
}

async function submitDetectedFeedback(button) {
  button.disabled = true;
  try {
    const reviewComplete = document.querySelector('#accuracy-review-complete').checked;
    await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/accuracy-feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: button.dataset.category, predicted: 'DETECTED', actual: button.dataset.accuracy, requirement_id: button.dataset.id, note: '界面人工反馈', dataset_scope: 'PILOT', review_complete: reviewComplete }) });
    showToast(button.dataset.accuracy === 'RELEVANT' ? '有效要求已确认。' : '误报反馈已记录。');
    await loadAccuracySummary();
  } catch (error) { button.disabled = false; showToast(`${error.message}，反馈未保存。`); }
}

async function submitMissedFeedback(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const reviewComplete = document.querySelector('#accuracy-review-complete').checked;
    await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/accuracy-feedback`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ category: document.querySelector('#missed-category').value, predicted: 'MISSED', actual: 'RELEVANT', locator_label: document.querySelector('#missed-locator').value.trim(), quote: document.querySelector('#missed-quote').value.trim(), note: document.querySelector('#missed-note').value.trim(), dataset_scope: 'PILOT', review_complete: reviewComplete }) });
    form.reset();
    missedDialog.close();
    showToast('漏项反馈已记录。');
    await loadAccuracySummary();
  } catch (error) { showToast(`${error.message}，反馈未保存。`); }
}

async function loadAccuracySummary() {
  const target = document.querySelector('#accuracy-summary');
  try {
    const metrics = await request('/api/accuracy/metrics');
setHtml(target, metrics.categories.length ? metrics.categories.slice(0, 4).map((item) => {
      const status = item.measurement_status === 'MEASURABLE' ? '可计量' : '证据不足';
      const coverage = item.coverage == null ? '—' : `${Math.round(item.coverage * 100)}%`;
      return html`<div><span class="rule-icon ${item.measurement_status === 'MEASURABLE' ? 'safe' : 'warning'}"><i data-lucide="chart-no-axes-combined"></i></span><span><strong>${item.category} · ${status}</strong><small>观察精确率 ${item.precision ?? '—'} · 召回率 ${item.recall ?? '—'} · 覆盖 ${coverage} · 样本 ${item.sample_size} · 完整复核 ${item.review_population_complete ? '是' : '否'}</small></span></div>`;
    }) : html`<div class="empty-state">尚无人工反馈样本</div>`);
    refreshIcons();
  } catch (error) {setHtml(target, html`<div class="empty-state error-text">指标加载失败</div>`); }
}

async function reviewRequirement(requirementId, decision, button) {
  button.disabled = true;
  try {
    store.currentRun = await request(`/api/runs/${encodeURIComponent(store.currentRun.run_id)}/review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requirement_id: requirementId, decision, note: '' }),
    });
    renderDetail();
    showToast('复核状态已更新。');
  } catch (error) {
    button.disabled = false;
    showToast(`${error.message}，请重试。`);
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, withCsrf(options));
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : { detail: await response.text() };
  if (!response.ok) {
    if (response.status === 401 && !url.startsWith('/api/auth/')) showAuth(false);
    throw new Error(payload.detail || '请求失败');
  }
  return payload;
}

// Same session handling as request(), for endpoints whose success path is a binary download.
async function requestBlobResponse(url, options = {}) {
  const response = await fetch(url, withCsrf(options));
  if (!response.ok) {
    if (response.status === 401 && !url.startsWith('/api/auth/')) showAuth(false);
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : { detail: await response.text() };
    throw new Error(payload.detail || '请求失败');
  }
  return response;
}

function csrfHeaders() {
  const match = document.cookie.split('; ').find((row) => row.startsWith('bidproof_csrf='));
  if (!match) return {};
  return { 'X-CSRF-Token': decodeURIComponent(match.slice('bidproof_csrf='.length)) };
}

function withCsrf(options = {}) {
  return { credentials: 'same-origin', ...options, headers: { ...csrfHeaders(), ...(options.headers || {}) } };
}

function setButtonLoading(button, loading, label = '') {
  if (loading) {
    button.dataset.originalHtml = button.innerHTML;
    button.disabled = true;
setHtml(button, html`<i data-lucide="loader-circle"></i><span>${label}</span>`);
  } else {
    button.disabled = false;
    if (button.dataset.originalHtml) setHtml(button, raw(button.dataset.originalHtml));
  }
  refreshIcons();
}

function showToast(message) {
  const toast = document.querySelector('#app-toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(store.toastTimer);
  store.toastTimer = setTimeout(() => { toast.hidden = true; }, 4000);
}

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons({ attrs: { 'aria-hidden': 'true' } });
}

function riskRank(item) {
  const severity = item.severity === 'HIGH' ? 0 : 1;
  const status = item.status === 'FAIL' ? 0 : item.status === 'UNKNOWN' ? 1 : 2;
  return severity * 10 + status;
}

function decisionLabel(value) {
  return ({ CONTINUE: '继续', HOLD: '暂缓', STOP: '停止', '未记录': '未记录' })[value] || value;
}

function statusLabel(value) {
  return ({ PASS: '已通过', FAIL: '不通过', UNKNOWN: '待确认', NEEDS_REVIEW: '待复核' })[value] || value;
}

function formatDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

