/**
 * 国际化。
 *
 * 旧实现里 i18n.js 只有 5 个 key，而 app.js 内硬编码了 481 处中文字面量——
 * 切到英文后界面依然全中文。合规约束要求保留 i18n，所以这里把它补成真的能用的层：
 *
 *   - 字典按域分组（nav / verdict / state / action / error），key 可读。
 *   - 支持 {name} 占位符插值，不再用模板串直接拼中文。
 *   - 缺 key 时回退到 zh，再回退到 key 本身，并在开发期告警。
 *   - 语言切换写 <html lang>，让屏幕阅读器与断词规则跟着变。
 *
 * 注意：**服务端返回的 detail 不翻译**。错误码契约属于后端，前端不做映射，
 * 否则会掩盖真实错误。需要本地化的后端文案应由后端按 Accept-Language 返回。
 */

const STORAGE_KEY = 'bidproof-lang';
const isDev = import.meta.env?.DEV ?? false;

export const zh = {
  'nav.runs': '扫描任务',
  'nav.newScan': '新建扫描',
  'nav.jobs': '扫描作业',
  'nav.admin': '成员与设置',
  'nav.logout': '退出登录',
  'nav.theme.toDark': '深色模式',
  'nav.theme.toLight': '浅色模式',

  'verdict.PASS': '已通过',
  'verdict.FAIL': '不通过',
  'verdict.UNKNOWN': '待确认',
  'verdict.NEEDS_REVIEW': '待复核',

  'decision.CONTINUE': '继续',
  'decision.HOLD': '暂缓',
  'decision.STOP': '停止',
  'decision.none': '未记录',

  'role.OWNER': '所有者',
  'role.ADMIN': '管理员',
  'role.REVIEWER': '复核人',
  'role.VIEWER': '只读成员',

  'job.PENDING': '排队中',
  'job.RUNNING': '扫描中',
  'job.COMPLETED': '已完成',
  'job.FAILED': '失败',
  'job.CANCELLED': '已取消',

  'citation.tender': '招标原文',
  'citation.evidence': '企业证据',
  'citation.noQuote': '未提取到可引用原文',
  'citation.noEvidence': '未匹配到企业证据，需人工复核',
  'citation.noLocator': '定位缺失',

  // 空状态是邀请动作，不是一句说明文字。
  'empty.runs.title': '还没有扫描任务',
  'empty.runs.body': '上传一份招标文件，系统会逐条抽取要求项，并为每一条标出原文与证据的页码。',
  'empty.runs.action': '用样例招标文件试跑',
  'empty.filtered.title': '没有符合条件的任务',
  'empty.filtered.body': '当前筛选条件下没有结果。清除筛选，或换一个负责人、标签再试。',
  'empty.filtered.action': '清除筛选',
  'empty.jobs.title': '没有后台作业',
  'empty.jobs.body': '新建扫描后，排队与执行记录会出现在这里。',
  'empty.comments': '还没有评论',
  'empty.audit': '还没有审计记录',
  'empty.remediations.title': '还没有整改行动',
  'empty.remediations.body': '发现证据缺口后，在这里分派负责人并跟踪截止日期。',
  'empty.notifications': '没有需要立即处理的提醒',
  'empty.backups': '还没有登记备份',
  'empty.tokens': '还没有 API 令牌',
  'empty.sessions': '没有有效会话',

  // 失败状态说清楚「发生了什么」和「怎么办」，不道歉、不含糊。
  'error.runs.title': '任务列表没能载入',
  'error.jobs.title': '作业记录没能载入',
  'error.members.title': '成员列表没能载入',
  'error.retry': '重试',
  'error.network': '无法连接服务，请检查网络后重试。',
  'error.forbidden': '当前角色没有这项权限。',
  'error.passwordMismatch': '两次输入的密码不一致',

  'action.refresh': '刷新',
  'action.archive': '归档',
  'action.restore': '恢复',
  'action.delete': '删除',
  'action.export': '导出报告',
  'action.cancel': '取消',
  'action.save': '保存',
  'action.confirm': '确认',

  'toast.decisionSaved': '已保存人工决策',
  'toast.reviewUpdated': '已更新复核状态',
  'toast.commentAdded': '已添加评论',
  'toast.linkCopied': '已复制安全链接',
  'toast.bulk.ARCHIVE': '已归档 {count} 个任务',
  'toast.bulk.RESTORE': '已恢复 {count} 个任务',
  'toast.bulk.DELETE': '已删除 {count} 个任务',

  'scan.queued': '扫描任务已进入后台队列',
  'scan.progress': '{message}（{percent}%）',
  'scan.done': '扫描完成，已生成可复核证据链',
  'scan.detached': '扫描仍在后台执行。可以离开本页，完成后在任务列表查看；刷新不会重复提交。',

  'selection.none': '未选择任务',
  'selection.count': '已选择 {count} 个任务',
  'matrix.count': '共 {count} 项',
  'pagination.range': '显示 {start}-{end}，共 {total} 项',
};

export const en = {
  'nav.runs': 'Scans',
  'nav.newScan': 'New scan',
  'nav.jobs': 'Jobs',
  'nav.admin': 'Members & settings',
  'nav.logout': 'Sign out',
  'nav.theme.toDark': 'Dark mode',
  'nav.theme.toLight': 'Light mode',

  'verdict.PASS': 'Passed',
  'verdict.FAIL': 'Failed',
  'verdict.UNKNOWN': 'No evidence found',
  'verdict.NEEDS_REVIEW': 'Needs review',

  'decision.CONTINUE': 'Continue',
  'decision.HOLD': 'Hold',
  'decision.STOP': 'Stop',
  'decision.none': 'Not recorded',

  'role.OWNER': 'Owner',
  'role.ADMIN': 'Admin',
  'role.REVIEWER': 'Reviewer',
  'role.VIEWER': 'Viewer',

  'job.PENDING': 'Queued',
  'job.RUNNING': 'Scanning',
  'job.COMPLETED': 'Completed',
  'job.FAILED': 'Failed',
  'job.CANCELLED': 'Cancelled',

  'citation.tender': 'Tender text',
  'citation.evidence': 'Company evidence',
  'citation.noQuote': 'No quotable passage extracted',
  'citation.noEvidence': 'No evidence matched — needs review',
  'citation.noLocator': 'No locator',

  'empty.runs.title': 'No scans yet',
  'empty.runs.body': 'Upload a tender document. Every requirement it finds gets a page reference on both the tender and your evidence.',
  'empty.runs.action': 'Try a sample tender',
  'empty.filtered.title': 'Nothing matches',
  'empty.filtered.body': 'No results with these filters. Clear them, or try another owner or tag.',
  'empty.filtered.action': 'Clear filters',
  'empty.jobs.title': 'No background jobs',
  'empty.jobs.body': 'Queue and execution records appear here after you start a scan.',
  'empty.comments': 'No comments yet',
  'empty.audit': 'No audit records yet',
  'empty.remediations.title': 'No remediation actions',
  'empty.remediations.body': 'When you find an evidence gap, assign an owner and a due date here.',
  'empty.notifications': 'Nothing needs attention',
  'empty.backups': 'No backups registered',
  'empty.tokens': 'No API tokens',
  'empty.sessions': 'No active sessions',

  'error.runs.title': 'Could not load scans',
  'error.jobs.title': 'Could not load jobs',
  'error.members.title': 'Could not load members',
  'error.retry': 'Retry',
  'error.network': 'Cannot reach the service. Check your connection and retry.',
  'error.forbidden': 'Your role does not have this permission.',
  'error.passwordMismatch': 'Passwords do not match',

  'action.refresh': 'Refresh',
  'action.archive': 'Archive',
  'action.restore': 'Restore',
  'action.delete': 'Delete',
  'action.export': 'Export report',
  'action.cancel': 'Cancel',
  'action.save': 'Save',
  'action.confirm': 'Confirm',

  'toast.decisionSaved': 'Decision saved',
  'toast.reviewUpdated': 'Review status updated',
  'toast.commentAdded': 'Comment added',
  'toast.linkCopied': 'Secure link copied',
  'toast.bulk.ARCHIVE': 'Archived {count} scans',
  'toast.bulk.RESTORE': 'Restored {count} scans',
  'toast.bulk.DELETE': 'Deleted {count} scans',

  'scan.queued': 'Scan queued',
  'scan.progress': '{message} ({percent}%)',
  'scan.done': 'Scan complete — evidence chain ready for review',
  'scan.detached': 'The scan is still running in the background. You can leave this page; it will appear in the list when done. Refreshing will not resubmit it.',

  'selection.none': 'No scans selected',
  'selection.count': '{count} selected',
  'matrix.count': '{count} requirements',
  'pagination.range': 'Showing {start}–{end} of {total}',
};

const dictionaries = { zh, en };

/** @returns {'zh' | 'en'} */
export function currentLang() {
  return localStorage.getItem(STORAGE_KEY) === 'en' ? 'en' : 'zh';
}

/**
 * @param {string} key
 * @param {Record<string, string | number>} [params]
 */
export function t(key, params) {
  const table = dictionaries[currentLang()];
  const template = table[key] ?? zh[key];
  if (template === undefined) {
    if (isDev) console.warn(`[i18n] 缺少词条：${key}`);
    return key;
  }
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    (name in params ? String(params[name]) : match));
}

/** @param {'zh' | 'en'} lang */
export function setLang(lang) {
  const next = lang === 'en' ? 'en' : 'zh';
  localStorage.setItem(STORAGE_KEY, next);
  document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN';
}

/** 数字与日期跟随语言，不再写死 'zh-CN'。 */
export const locale = () => (currentLang() === 'en' ? 'en-US' : 'zh-CN');

/** @param {string | number | Date | null | undefined} value */
export function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(locale(), {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** @param {string | null | undefined} value ISO date (YYYY-MM-DD) */
export function formatDate(value) {
  if (!value) return '—';
  return new Date(`${value}T00:00:00`).toLocaleDateString(locale());
}
