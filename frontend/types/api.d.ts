/**
 * BidProof API 契约类型。
 *
 * ⚠️ 全部由前端调用点反向推导，**未经 OpenAPI 校对**。
 * 每一个标注 [假设] 的字段都需要后端确认；不确定的地方一律写成可选 + 宽类型，
 * 宁可类型偏松，也不要用一个猜错的严格类型把正确的运行时值判成错误。
 *
 * 契约本身是硬约束：本次重构不修改任何路径、字段名或错误码。
 * 若后续要收紧（例如把 status 变成真正的联合类型），需先与后端对齐。
 */

// ---------------------------------------------------------------- 枚举
export type Role = 'OWNER' | 'ADMIN' | 'REVIEWER' | 'VIEWER';
export type RequirementStatus = 'PASS' | 'FAIL' | 'UNKNOWN' | 'NEEDS_REVIEW';
export type DecisionValue = 'CONTINUE' | 'HOLD' | 'STOP';
export type JobStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'DEAD';
export type RemediationStatus = 'OPEN' | 'IN_PROGRESS' | 'DONE' | 'CANCELLED';
export type BulkAction = 'ARCHIVE' | 'RESTORE' | 'DELETE';
export type ReviewDecision = 'CONFIRM' | 'REJECT' | 'REQUEST_EVIDENCE';
export type ReportFormat = 'html' | 'csv' | 'pdf';

/** [假设] 取自 #missed-category 的选项与 renderMatrix 的分组逻辑；后端可能还有其它值。 */
export type RequirementCategory =
  | 'FATAL' | 'QUALIFICATION' | 'DEADLINE' | 'BOND'
  | 'SIGNATURE' | 'CREDENTIAL' | 'SCORING'
  | (string & {});

// ---------------------------------------------------------------- 鉴权
export interface AuthStatus {
  authenticated: boolean;
  setup_required: boolean;
  /** true 时 bootstrap 表单应禁用提交。 */
  bootstrap_locked?: boolean;
  bootstrap_token_required?: boolean;
  personal_signup_enabled?: boolean;
  trial_join_enabled?: boolean;
  oidc_enabled?: boolean;
  mfa_enabled?: boolean;
  user?: CurrentUser;
}

export interface CurrentUser {
  user_id: string;
  username: string;
  role: Role;
  /** [假设] 登录响应与 status.user 结构相同。 */
  workspace_id?: string;
}

/** POST /api/auth/login 既可能返回用户，也可能返回 MFA 挑战。 */
export type LoginResponse = CurrentUser & {
  mfa_required?: boolean;
  mfa_token?: string;
};

export interface AccountActionInspect {
  action: 'INVITE' | 'RESET';
  username: string;
  role: Role;
}

export interface Session {
  session_id: string;
  current: boolean;
  /** [假设] 后端直接返回可读字符串，旧前端未做格式化。 */
  created_at: string;
  expires_at: string;
}

export interface MfaEnrollment {
  secret: string;
  recovery_codes: string[];
}

export interface ApiTokenSummary {
  token_id: string;
  name: string;
  token_prefix: string;
  revoked_at: string | null;
  /** Present only on create response; optional on list rows. */
  token?: string;
}

/** 仅创建时返回一次明文。 */
export interface ApiTokenCreated extends ApiTokenSummary {
  token: string;
}

// ---------------------------------------------------------------- 组织
export interface Member {
  user_id: string;
  username: string;
  role: Role;
  active: boolean;
}

export interface Project {
  project_id: string;
  name: string;
  code: string;
  archived_at: string | null;
}

// ---------------------------------------------------------------- 扫描
export interface Locator {
  /** 「第 12 页」「段落 8」「工作表 X · B17」——已由后端本地化。 */
  label: string;
}

export interface SourceReference {
  quote?: string;
  locator?: Locator;
}

export interface EvidenceReference extends SourceReference {
  filename: string;
}

export interface Requirement {
  requirement_id: string;
  label: string;
  title: string;
  category: RequirementCategory;
  status: RequirementStatus;
  /** [假设] 仅在 riskRank() 中使用，取值 'HIGH' 或其它。 */
  severity?: string;
  criticality?: string;
  detection_method?: string;
  source?: SourceReference;
  evidence?: EvidenceReference[];
}

export interface SourceDocument {
  source_id: string;
  filename?: string;
  role: 'tender' | 'evidence' | (string & {});
  file_type?: string;
  pages?: number;
  sha256?: string;
}

export interface ScanQuality {
  total_pages?: number;
  ocr_required_pages?: number;
  ocr_failed_pages?: number;
  interpretation?: string;
}

export interface Decision {
  decision: DecisionValue;
  note?: string;
  unresolved_requirement_ids?: string[];
  decided_at?: string;
  decided_by?: string;
}

/** GET /api/runs 返回的列表项。[假设] 是完整 Run 的子集。 */
export interface RunSummary {
  run_id: string;
  tender_filename: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  blocker_count: number;
  unresolved_count: number;
  project_id?: string;
  favorite?: boolean;
  tags?: string[];
  assignee_id?: string | null;
  reviewer_id?: string | null;
  decision?: Decision | null;
}

export interface Run extends RunSummary {
  requirement_count: number;
  version_number?: number;
  parent_run_id?: string | null;
  /** 乐观并发令牌，POST /review 必须回传。 */
  revision: string | number;
  requirements: Requirement[];
  evidence_assets: unknown[];
  source_documents?: SourceDocument[];
  scan_quality?: ScanQuality;
  duplicate_run_ids?: string[];
}

export interface RunDiff {
  added: Array<{ title?: string } | { after?: { title?: string } }>;
  removed: Array<{ title?: string } | { after?: { title?: string } }>;
  changed: Array<{ after?: { title?: string } }>;
}

// ---------------------------------------------------------------- 作业
export interface ScanJob {
  job_id: string;
  run_id: string | null;
  status: JobStatus;
  attempts?: number;
  updated_at: string;
  progress_current?: number;
  progress_total?: number;
  progress_message?: string;
  error?: string;
}

// ---------------------------------------------------------------- 协作
export interface Comment {
  /** [假设] 后端只给 user_id，界面直接展示了原始 id。建议后端补 username。 */
  user_id: string;
  body: string;
  created_at: string;
}

export interface AuditEvent {
  event_type: string;
  user_id: string;
  created_at: string;
  note?: string;
}

export interface Remediation {
  remediation_id: string;
  title: string;
  status: RemediationStatus;
  requirement_id: string | null;
  owner_id: string | null;
  due_date: string | null;
  note?: string;
}

export interface Notification {
  type: 'SCAN_JOB_FAILED' | (string & {});
  severity: string;
  title: string;
  message: string;
  run_id?: string;
}

// ---------------------------------------------------------------- 治理
export interface WorkspaceSettings { retention_days: number }
export interface RetentionPreview { count: number; cutoff: string }
export interface WorkspaceUsage {
  runs: number; scan_jobs: number; remediations: number; audit_events: number;
}
export interface WorkspacePrivacy {
  boundary: string; deletion: string; retention_days: number;
}
export interface HealthDetail {
  database?: string;
  backup_status?: 'verified' | 'unverified' | 'missing';
  failed_jobs?: number;
  last_verified_backup_at?: string | null;
  degraded_reasons?: string[];
}
export interface Backup {
  backup_id: string; created_at: string; valid: boolean;
}

export interface AccuracyCategoryMetric {
  category: RequirementCategory;
  measurement_status: 'MEASURABLE' | (string & {});
  precision: number | null;
  recall: number | null;
  coverage: number | null;
  sample_size: number;
  review_population_complete: boolean;
}

/** /api/accuracy/metrics 的响应体。 */
export interface AccuracySummary {
  categories: AccuracyCategoryMetric[];
  /** [假设] 全局汇总；部分部署只返回 categories。 */
  precision?: number | null;
  recall?: number | null;
  sample_size?: number;
  measurement_status?: string;
  /**
   * 复核样本是否已覆盖全量。
   * 合规约束：为 false 时 precision/recall 只是抽样估计，
   * 界面**不得**呈现为已验证指标，必须降级文案。
   */
  review_population_complete?: boolean;
}

/** 检出准确性反馈的取值。与 ReviewDecision 不同：这条不改变判定，只回流信号。 */
export type AccuracyVerdict = 'RELEVANT' | 'NOT_RELEVANT';

/**
 * 任务列表的可见范围。纯前端概念 —— 请求时折算成 include_archived，
 * 余下的 ARCHIVED / ALL 差异在前端过滤（见 api/runs.js filterByScope）。
 */
export type RunScope = 'ACTIVE' | 'ARCHIVED' | 'ALL';

// ---------------------------------------------------------------- 错误
/** 服务端错误体。`detail` 是唯一保证存在的字段。 */
export interface ApiErrorShape {
  detail?: string;
  /** [假设] 目前未观察到；若后端有业务错误码，前端已预留读取位。 */
  code?: string;
}
