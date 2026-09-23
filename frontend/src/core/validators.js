// @ts-check
/** @param {unknown} value @returns {value is Record<string, unknown>} */
export function isRecord(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }

/** @param {unknown} value @returns {number | null} */
export function revisionOf(value) {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 ? value : null;
}

/** Validate the critical envelope before any response replaces the active task.
 * This deliberately does not claim validation of the whole legacy Run shape.
 * @param {unknown} value @param {string} expectedId
 * @returns {asserts value is import('./contracts.js').RunEnvelope}
 */
export function assertRunEnvelope(value, expectedId) {
  const statuses = new Set(['PASS', 'FAIL', 'UNKNOWN', 'NEEDS_REVIEW']);
  if (!isRecord(value) || value.run_id !== expectedId || revisionOf(value.revision) === null
    || !Array.isArray(value.requirements) || !value.requirements.every((item) => isRecord(item)
      && typeof item.requirement_id === 'string' && item.requirement_id.length > 0
      && typeof item.status === 'string' && statuses.has(item.status))) {
    throw new Error('任务结果不完整，请重新打开任务。');
  }
}

/** @param {unknown} value @returns {asserts value is import('./contracts.js').DecisionCommand} */
export function assertDecisionCommand(value) {
  if (!isRecord(value) || !['CONTINUE', 'HOLD', 'STOP'].includes(String(value.decision))
    || typeof value.note !== 'string' || value.note.length > 4000
    || revisionOf(value.revision) === null || !Array.isArray(value.unresolved_requirement_ids)
    || value.unresolved_requirement_ids.length > 500
    || !value.unresolved_requirement_ids.every((id) => typeof id === 'string' && id.length > 0)) {
    throw new Error('决策信息或任务版本无效，请重新核对后保存。');
  }
}
