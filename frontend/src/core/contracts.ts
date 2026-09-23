/** Strict boundary contracts. Keep these aligned with app/schemas.py. */
export type DecisionValue = 'CONTINUE' | 'HOLD' | 'STOP';
export type RequirementStatus = 'PASS' | 'FAIL' | 'UNKNOWN' | 'NEEDS_REVIEW';
export interface DecisionCommand {
  decision: DecisionValue;
  note: string;
  unresolved_requirement_ids: string[];
  revision: number;
}
export interface RunEnvelope extends Record<string, unknown> {
  run_id: string;
  revision: number;
  requirements: Array<Record<string, unknown> & { requirement_id: string; status: RequirementStatus }>;
}
export type TelemetryModule = 'boot' | 'runtime' | 'network' | 'decision' | 'collaboration' | 'jobs';
export type TelemetryCode = 'UNEXPECTED' | 'BOOT_FAILED' | 'NETWORK' | 'TIMEOUT' | 'INVALID_RESPONSE' | 'SERVER_ERROR';
export interface DiagnosticEvent {
  schema: 1;
  code: TelemetryCode;
  module: TelemetryModule;
  error_type: 'Error' | 'TypeError' | 'RangeError' | 'SyntaxError' | 'ApiError' | 'Unknown';
  release: string;
  route: 'home' | 'detail' | 'decision' | 'jobs' | 'admin' | 'unknown';
  status: number;
  request_id?: string;
  occurred_at: string;
}
export type DiagnosticSink = (event: Readonly<DiagnosticEvent>) => void | Promise<void>;
