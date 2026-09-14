/**
 * 运维区：保留策略、备份、服务健康、用量、隐私声明。
 *
 * 最主要的改动是把 `loadOperations()` 拆开。旧实现是这样的：
 *
 *   const [settings, preview, health, usage, privacy] = await Promise.all([...]);
 *
 * 五个互不相关的面板共用一个 try/catch，任何一个接口挂掉，
 * 五块全变成一句「运行状态加载失败」—— 而其中四块的数据其实已经拿到了。
 * 这和批次 7 修掉的协作区是同一个模式。现在每块自己取数、自己显示状态。
 *
 * 第二处是权限。备份与 API 令牌在旧实现里没有角色判断，只有 403 兜底：
 *
 *   } catch (error) {
 *     setHtml(target, '当前角色无备份管理权限');
 *     createBackup.hidden = true;
 *   }
 *
 * 于是网络断了、后端 500、超时，用户看到的都是「你没权限」。
 * 现在可见性由 core/permissions.js 前置判定，403 只作为兜底，
 * 且必须经过 isPermissionError() —— **只有 403 才能说权限**。
 */

import { delegate, bind, el, withLoading } from '../../core/dom.js';
import { html, mount, emptyState, errorState, skeleton } from '../../ui/render.js';
import { confirmAction, confirmWithWord } from '../../ui/confirm.js';
import { toastSuccess, toastFromError } from '../../core/toast.js';
import { formatDate, backupStatusLabel } from '../../core/format.js';
import { can, isPermissionError } from '../../core/permissions.js';
import { workspaceApi } from '../../api/index.js';

/** @type {(() => void)[]} */
let teardown = [];
/** 当前已保存的保留天数。用于判断这次修改是调大还是调小。 */
let savedRetentionDays = null;

export function mountOperations() {
  if (teardown.length) return;
  teardown = [
    bind('#retention-form', 'submit', (event) => { void saveRetention(event); }),
    bind('#purge-retention', 'click', (event) => { void purge(event.currentTarget); }),
    bind('#create-backup', 'click', (event) => { void createBackup(event.currentTarget); }),
    delegate('#operations-health', 'click', '#health-retry', () => { void loadHealth(); }),
    delegate('#backups-list', 'click', '#backups-retry', () => { void loadBackups(); }),
  ];
  load();
}

export function unmountOperations() {
  for (const off of teardown) off();
  teardown = [];
}

/** 五块独立加载。**刻意不用 Promise.all** —— 它们之间没有依赖关系。 */
export function load() {
  el('#purge-retention')?.toggleAttribute('hidden', !can('retention.purge'));
  el('#retention-form')?.toggleAttribute('hidden', !can('retention.configure'));
  el('#create-backup')?.toggleAttribute('hidden', !can('backups.manage'));

  void loadRetention();
  void loadBackups();
  void loadHealth();
  void loadUsage();
  void loadPrivacy();
}

/* ═══════════════════════════════════════════════════════════════════════════
   保留策略
   ═══════════════════════════════════════════════════════════════════════ */

async function loadRetention() {
  const target = el('#retention-preview');
  if (!target) return;
  mount(target, skeleton('line', 1));
  try {
    // 设置与预览是两个端点，但它们只在这一块里一起用，
    // 且缺任何一个这块都没法显示，所以这里的合并是有依据的。
    const [settings, preview] = await Promise.all([
      workspaceApi.getWorkspaceSettings(),
      workspaceApi.previewRetention(),
    ]);
    savedRetentionDays = Number(settings.retention_days);
    const input = /** @type {HTMLInputElement | null} */ (el('#retention-days'));
    if (input) input.value = String(settings.retention_days);

    mount(target, html`
      <p class="callout" data-tone="${preview.count > 0 ? 'warning' : 'info'}">
        <i data-lucide="${preview.count > 0 ? 'triangle-alert' : 'info'}"></i>
        <span>
          ${preview.count > 0
            ? html`<strong>${preview.count}</strong> 个已归档任务早于
                   ${formatDate(preview.cutoff, { withTime: false })}，可被清理。`
            : '当前没有到期的归档任务。'}
          执行清理前会再预览一次。
        </span>
      </p>`);
  } catch (error) {
    mount(target, errorState({ title: '保留策略加载失败', error }));
  }
}

/**
 * 保存保留天数。**调小是 T2**：它等于预告一次批量删除。
 * 调大或不变则直接保存 —— 放宽保留期没有破坏性。
 *
 * @param {Event} event
 */
async function saveRetention(event) {
  event.preventDefault();
  const form = /** @type {HTMLFormElement} */ (event.currentTarget);
  const days = Number(new FormData(form).get('retention_days'));
  if (!Number.isFinite(days) || days <= 0) return;

  if (savedRetentionDays !== null && days < savedRetentionDays) {
    const ok = await confirmAction({
      title: '缩短保留期',
      body: `保留期将从 ${savedRetentionDays} 天改为 ${days} 天。`
        + '更多已归档任务会因此进入待清理范围，在下次执行清理时被永久删除。',
      confirmLabel: `改为 ${days} 天`,
      tone: 'danger',
    });
    if (!ok) return;
  }

  await withLoading(form.querySelector('button[type="submit"]'), async () => {
    try {
      await workspaceApi.saveWorkspaceSettings({ retention_days: days });
      toastSuccess('保留策略已保存。');
      await loadRetention();
    } catch (error) {
      toastFromError(error, '策略未保存。');
    }
  });
}

/**
 * 清理到期归档。T3，且确认词用 PURGE 而不是 DELETE。
 *
 * 先重新取一次预览再确认 —— 确认文案里的数字必须是**执行前的实时值**，
 * 页面上那个可能已经过了几分钟。旧实现这一点做对了，保留。
 *
 * @param {Element} button
 */
async function purge(button) {
  try {
    const preview = await workspaceApi.previewRetention();
    if (!preview.count) {
      toastSuccess('当前没有到期归档任务。');
      return;
    }
    const ok = await confirmWithWord({
      title: '清理到期归档',
      body: `将永久删除 ${preview.count} 个到期归档任务及其上传文件，不可恢复。`
        + '已导出的报告将不再能追溯到原始材料。',
      word: 'PURGE',
      confirmLabel: `清理 ${preview.count} 个任务`,
    });
    if (!ok) return;

    await withLoading(button, async () => {
      const result = await workspaceApi.purgeRetention();
      toastSuccess(`已清理 ${result.deleted} 个到期任务。`);
      await loadRetention();
    });
  } catch (error) {
    toastFromError(error, '清理未执行。');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   备份
   ═══════════════════════════════════════════════════════════════════════ */

async function loadBackups() {
  const target = el('#backups-list');
  if (!target) return;
  mount(target, skeleton('row', 2));
  try {
    const { backups } = await workspaceApi.listBackups();
    if (!backups.length) {
      mount(target, emptyState({
        icon: 'database-backup',
        title: '还没有已登记备份',
        body: '创建备份会同时做一次完整性校验，结果记录在这里。',
      }));
      return;
    }
    mount(target, backups.map((backup) => html`
      <article class="admin-row" data-tone="${backup.valid ? 'ok' : 'danger'}">
        <span class="admin-row__icon"><i data-lucide="database"></i></span>
        <span class="admin-row__main">
          <strong class="is-mono">${backup.backup_id}</strong>
          <small>${formatDate(backup.created_at)}</small>
        </span>
        <span class="chip ${backup.valid ? 'chip--info' : 'chip--danger'}">
          ${backup.valid ? '已验证' : '校验失败'}
        </span>
      </article>
    `));
  } catch (error) {
    // 只有 403 才说权限。旧实现把所有失败都说成「当前角色无备份管理权限」，
    // 管理员会因此以为自己权限被改了。
    mount(target, isPermissionError(error)
      ? emptyState({ icon: 'lock', title: '当前角色不能查看备份' })
      : errorState({ title: '备份记录加载失败', error, retryId: 'backups-retry' }));
  }
}

/** @param {Element} button */
async function createBackup(button) {
  await withLoading(button, async () => {
    try {
      const result = await workspaceApi.createBackup();
      // 「创建成功」与「校验通过」是两件事，不能合并成一句话说。
      toastSuccess(result.valid ? '备份已创建并通过校验。' : '备份已创建，但完整性校验未通过。');
      await Promise.allSettled([loadBackups(), loadHealth()]);
    } catch (error) {
      toastFromError(error, '备份未完成。');
    }
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   健康 / 用量 / 隐私
   ═══════════════════════════════════════════════════════════════════════ */

async function loadHealth() {
  const target = el('#operations-health');
  if (!target) return;
  mount(target, skeleton('line', 2));
  try {
    const health = await workspaceApi.getHealth();
    const reasons = health.degraded_reasons || [];
    mount(target, html`
      <dl class="stat-grid">
        <div class="stat"><dt>数据库</dt><dd>${health.database || '未知'}</dd></div>
        <div class="stat"><dt>备份</dt><dd>${backupStatusLabel(health.backup_status)}</dd></div>
        <div class="stat" data-tone="${Number(health.failed_jobs || 0) > 0 ? 'danger' : ''}">
          <dt>失败作业</dt><dd>${Number(health.failed_jobs || 0)}</dd>
        </div>
        <div class="stat">
          <dt>最近验证备份</dt>
          <dd>${health.last_verified_backup_at
            ? formatDate(health.last_verified_backup_at, { withTime: false })
            : '无'}</dd>
        </div>
      </dl>
      ${reasons.length
        ? html`<p class="callout" data-tone="warning">
                 <i data-lucide="triangle-alert"></i>
                 <span>降级原因：${reasons.join('、')}</span></p>`
        : html`<p class="hint">未发现降级原因。</p>`}
    `);
  } catch (error) {
    mount(target, errorState({ title: '运行状态加载失败', error, retryId: 'health-retry' }));
  }
}

async function loadUsage() {
  const target = el('#workspace-usage');
  if (!target) return;
  mount(target, skeleton('line', 1));
  try {
    const usage = await workspaceApi.getUsage();
    mount(target, html`
      <dl class="stat-grid">
        <div class="stat"><dt>任务</dt><dd>${usage.runs}</dd></div>
        <div class="stat"><dt>作业</dt><dd>${usage.scan_jobs}</dd></div>
        <div class="stat"><dt>整改项</dt><dd>${usage.remediations}</dd></div>
        <div class="stat"><dt>审计事件</dt><dd>${usage.audit_events}</dd></div>
      </dl>`);
  } catch (error) {
    mount(target, errorState({ title: '用量加载失败', error }));
  }
}

/** 隐私声明是合规展示内容，原样呈现，不得删减或改写。 */
async function loadPrivacy() {
  const target = el('#workspace-privacy');
  if (!target) return;
  try {
    const privacy = await workspaceApi.getPrivacy();
    mount(target, html`
      <p>${privacy.boundary}</p>
      <p>${privacy.deletion}</p>
      <p class="hint">当前保留策略：${privacy.retention_days} 天。</p>`);
  } catch (error) {
    mount(target, errorState({ title: '隐私声明加载失败', error }));
  }
}
