/** Pure review rules. Keep citation and progress semantics aligned with presenters.py / review_policy. */

/** @typedef {import('../../../types/api.js').Requirement} Requirement */
/** @typedef {import('../../../types/api.js').Run} Run */

/** Prefer server `effective_status`; fall back to stored status. */
export function effectiveStatus(/** @type {Requirement} */ item) {
  return item?.effective_status || item?.status || 'NEEDS_REVIEW';
}

/** Prefer server `review_required`; fall back to local citation + status rules. */
export function isReviewRequired(/** @type {Requirement} */ item) {
  if (typeof item?.review_required === 'boolean') return item.review_required;
  const status = effectiveStatus(item);
  return status === 'UNKNOWN' || status === 'NEEDS_REVIEW' || status === 'FAIL'
    || (status === 'PASS' && !hasCompleteCitation(item));
}

/** A conclusion needs a locatable quotation on both sides, exactly as the API requires. */
export function hasCompleteCitation(/** @type {Requirement} */ item) {
  if (typeof item?.citation_ok === 'boolean') return item.citation_ok;
  const complete = (entry) => Boolean(entry?.locator?.label && entry?.quote && entry?.source_id);
  return complete(item.source) && (item.evidence || []).some(complete);
}

/** Comments and machine PASS results are deliberately excluded from human progress. */
export function getReviewProgress(/** @type {Run} */ run) {
  const known = new Set(run.requirements.map((item) => item.requirement_id));
  const reviewed = new Set((run.review?.items || [])
    .filter((item) => known.has(item.requirement_id))
    .map((item) => item.requirement_id)).size;
  const total = known.size;
  return { reviewed, total, pending: total - reviewed, percent: total ? Math.round(reviewed / total * 100) : 0 };
}

export function latestReview(/** @type {Run} */ run, /** @type {string} */ id) {
  return [...(run.review?.items || [])].reverse().find((item) => item.requirement_id === id);
}

/** A machine PASS remains a human to-do until its latest review explicitly retains PASS. */
export function isHumanConfirmed(run, item) {
  const review = latestReview(run, item.requirement_id);
  return effectiveStatus(item) === 'PASS' && review?.new_status === 'PASS' && !isReviewRequired(item);
}

export function getReviewQueueCounts(run) {
  const confirmed = run.requirements.filter((item) => isHumanConfirmed(run, item)).length;
  return { total: run.requirements.length, confirmed, pending: run.requirements.length - confirmed };
}

/** Resolve a real archived document. Duplicate names are ambiguous and must not be guessed. */
export function referenceDocument(run, reference, role) {
  const documents = run.source_documents || [];
  if (reference?.source_id) {
    return documents.find((document) => document.source_id === reference.source_id) || null;
  }
  const roles = role === 'evidence' ? ['evidence', 'enterprise_evidence'] : [role];
  const candidates = documents.filter((document) => roles.includes(document.role)
    && (!reference?.filename || document.filename === reference.filename));
  return candidates.length === 1 ? candidates[0] : null;
}

/** Physical page comes from extraction metadata, never from a guessed quote location. */
export function referencePage(reference) {
  const page = Number(reference?.page ?? (reference?.locator?.kind === 'page' ? reference.locator.index : 0));
  return Number.isInteger(page) && page > 0 ? page : null;
}
