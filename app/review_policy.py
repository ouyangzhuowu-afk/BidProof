"""Review policy: PASS is fail-closed unless citation integrity and quality allow it.

Human CONFIRM cannot mint a PASS when evidence is missing, citations are
incomplete/forged, OCR quality gates fail, or cited pages failed extraction.
"""

from __future__ import annotations

from typing import Any

from . import citations, quality_gates

PASS_BLOCKED_QUALITY = "QUALITY_GATE_FAIL"
PASS_BLOCKED_OCR_PAGE = "CITED_PAGE_OCR_FAILED"
PASS_BLOCKED_CITATION = "CITATION_INTEGRITY_FAIL"
PASS_BLOCKED_COVERAGE = "INCOMPLETE_COVERAGE"


def engineering_allows_pass(run: dict[str, Any] | None = None) -> bool:
    """Global OCR engineering gates must pass before any product PASS."""
    report_dir = None
    if run:
        override = (run.get("state") or {}).get("quality_gate_report_dir")
        if override:
            report_dir = override
    return quality_gates.allow_machine_pass(report_dir)


def cited_pages_ocr_ok(requirement: dict[str, Any], run: dict[str, Any] | None) -> bool:
    """Reject PASS when a cited page was marked OCR FAILED in the page index."""
    documents = {doc.get("source_id"): doc for doc in citations.source_documents(run)}
    sides: list[dict[str, Any]] = []
    source = requirement.get("source") or {}
    if source:
        sides.append(source)
    sides.extend(requirement.get("evidence") or [])
    for side in sides:
        source_id = str(side.get("source_id") or "").strip()
        page = citations.page_number(side)
        if not source_id or page is None:
            continue
        document = documents.get(source_id) or {}
        for entry in document.get("page_index") or []:
            if citations.page_number(entry) != page:
                continue
            if entry.get("ocr_status") == "FAILED":
                return False
    return True


def pass_block_reason(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> str | None:
    """Return a stable block reason, or None when PASS is allowed."""
    if not engineering_allows_pass(run):
        return PASS_BLOCKED_QUALITY
    issues = citations.citation_issues(requirement, run)
    if issues:
        if any(issue.endswith(citations.MISSING_EVIDENCE) for issue in issues):
            return citations.MISSING_EVIDENCE
        if any(
            issue.endswith(code)
            for issue in issues
            for code in (
                citations.MISSING_SPAN,
                citations.MISSING_PAGE,
                citations.MISSING_CORPUS,
            )
        ):
            return PASS_BLOCKED_COVERAGE
        return PASS_BLOCKED_CITATION
    if not cited_pages_ocr_ok(requirement, run):
        return PASS_BLOCKED_OCR_PAGE
    return None


def can_set_pass(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> tuple[bool, str | None]:
    reason = pass_block_reason(requirement, run)
    return reason is None, reason


def review_required(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> bool:
    status = str(requirement.get("status") or "")
    if status in {"UNKNOWN", "NEEDS_REVIEW", "FAIL"}:
        return True
    return status == "PASS" and bool(pass_block_reason(requirement, run))


def effective_status(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> str:
    """Stored PASS collapses to NEEDS_REVIEW when integrity/quality no longer hold."""
    status = str(requirement.get("status") or "NEEDS_REVIEW")
    if status != "PASS":
        return status
    if pass_block_reason(requirement, run):
        return "NEEDS_REVIEW"
    return "PASS"


def enforce_pass_or_raise(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> None:
    from fastapi import HTTPException

    allowed, reason = can_set_pass(requirement, run)
    if allowed:
        return
    detail = {
        citations.MISSING_EVIDENCE: "PASS 必须同时具备招标和企业证据页码引用",
        PASS_BLOCKED_QUALITY: "OCR 工程门禁未通过，不能将要求项标为 PASS",
        PASS_BLOCKED_OCR_PAGE: "引用页 OCR 失败，不能将要求项标为 PASS",
        PASS_BLOCKED_COVERAGE: "PASS 需要可核验的文档、页码与原文摘录",
        PASS_BLOCKED_CITATION: "引用完整性校验失败：需要真实文档、合法页码且原文与页内容匹配",
    }.get(reason or "", "PASS 被复核策略拒绝")
    raise HTTPException(status_code=422, detail=detail)


def project_requirement(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public requirement projection with effective_status / review_required."""
    projected = dict(requirement)
    projected["effective_status"] = effective_status(requirement, run)
    projected["review_required"] = review_required(requirement, run)
    projected["citation_ok"] = citations.has_complete_citation(requirement, run)
    block = pass_block_reason(requirement, run)
    if block:
        projected["pass_block_reason"] = block
    else:
        projected.pop("pass_block_reason", None)
    return projected
