"""Citation integrity: PASS needs a real document, in-bounds page, and page-matching quote.

Filename alone is never enough when multiple uploads share a name — resolve by
``source_id``. Fail closed when the page corpus is missing or the quote is not
found on the cited page.
"""

from __future__ import annotations

import re
from typing import Any

EVIDENCE_ROLES = frozenset({"evidence", "enterprise_evidence"})
TENDER_ROLES = frozenset({"tender"})

# Stable machine reasons used by review_policy and tests.
MISSING_DOC = "MISSING_DOC"
AMBIGUOUS_FILENAME = "AMBIGUOUS_FILENAME"
MISSING_SOURCE_ID = "MISSING_SOURCE_ID"
PAGE_OOB = "PAGE_OOB"
MISSING_PAGE = "MISSING_PAGE"
MISSING_SPAN = "MISSING_SPAN"
WRONG_PAGE_QUOTE = "WRONG_PAGE_QUOTE"
MISSING_CORPUS = "MISSING_CORPUS"
MISSING_EVIDENCE = "MISSING_EVIDENCE"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def quote_matches_page(quote: Any, page_text: Any) -> bool:
    needle = normalize_text(quote)
    haystack = normalize_text(page_text)
    return bool(needle) and bool(haystack) and needle in haystack


def page_number(reference: dict[str, Any] | None) -> int | None:
    if not reference:
        return None
    raw = reference.get("page")
    if raw is None and (reference.get("locator") or {}).get("kind") == "page":
        raw = (reference.get("locator") or {}).get("index")
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def locator_complete(reference: dict[str, Any] | None) -> bool:
    if not reference:
        return False
    locator = reference.get("locator") or {}
    label = str(locator.get("label") or "").strip()
    quote = str(reference.get("quote") or "").strip()
    return bool(label and quote)


def build_page_corpus(pages: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Map source_id → {page_str → raw page text} for later quote checks."""
    corpus: dict[str, dict[str, str]] = {}
    for page in pages:
        source_id = str(page.get("source_id") or "").strip()
        number = page_number(page)
        text = page.get("text")
        if not source_id or number is None or text is None:
            continue
        corpus.setdefault(source_id, {})[str(number)] = str(text)
    return corpus


def merge_page_corpus(*parts: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for part in parts:
        for source_id, pages in (part or {}).items():
            bucket = merged.setdefault(str(source_id), {})
            for page, text in (pages or {}).items():
                bucket[str(page)] = str(text)
    return merged


def source_documents(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not run:
        return []
    docs = run.get("source_documents") or []
    if docs:
        return list(docs)
    return list((run.get("state") or {}).get("source_documents") or [])


def citation_corpus(run: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if not run:
        return {}
    state = run.get("state") or {}
    raw = state.get("citation_corpus") or run.get("citation_corpus") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(source_id): {str(page): str(text) for page, text in (pages or {}).items()}
        for source_id, pages in raw.items()
        if isinstance(pages, dict)
    }


def resolve_document(
    run: dict[str, Any] | None,
    reference: dict[str, Any] | None,
    *,
    role: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve an archived document. Same-name files must not be guessed."""
    documents = source_documents(run)
    if not reference:
        return None, MISSING_DOC

    source_id = str(reference.get("source_id") or "").strip()
    if source_id:
        match = next((doc for doc in documents if doc.get("source_id") == source_id), None)
        if match is None:
            return None, MISSING_DOC
        return match, None

    roles = EVIDENCE_ROLES if role in EVIDENCE_ROLES or role == "evidence" else TENDER_ROLES
    filename = str(reference.get("filename") or "").strip()
    candidates = [
        doc
        for doc in documents
        if doc.get("role") in roles and (not filename or doc.get("filename") == filename)
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if len(candidates) > 1:
        return None, AMBIGUOUS_FILENAME
    return None, MISSING_DOC


def _page_text_for(run: dict[str, Any] | None, source_id: str, page: int) -> str | None:
    corpus = citation_corpus(run)
    pages = corpus.get(source_id) or {}
    if str(page) not in pages:
        return None
    return pages[str(page)]


def validate_side(
    run: dict[str, Any] | None,
    reference: dict[str, Any] | None,
    *,
    role: str,
) -> tuple[bool, str | None]:
    """Validate one citation side (tender or evidence)."""
    if not locator_complete(reference):
        return False, MISSING_SPAN

    document, resolve_issue = resolve_document(run, reference, role=role)
    if document is None:
        return False, resolve_issue or MISSING_DOC

    source_id = str(document.get("source_id") or "").strip()
    if not str((reference or {}).get("source_id") or "").strip():
        # Filename-only resolution is ambiguous under collisions; require an id for PASS.
        return False, MISSING_SOURCE_ID

    page = page_number(reference)
    if page is None:
        return False, MISSING_PAGE

    recorded_pages = document.get("pages")
    try:
        total = int(recorded_pages) if recorded_pages is not None else None
    except (TypeError, ValueError):
        total = None
    if total is not None and total > 0 and page > total:
        return False, PAGE_OOB

    page_text = _page_text_for(run, source_id, page)
    if page_text is None:
        return False, MISSING_CORPUS
    if not quote_matches_page((reference or {}).get("quote"), page_text):
        return False, WRONG_PAGE_QUOTE
    return True, None


def has_complete_citation(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> bool:
    """Structural dual citation. When ``run`` is provided, also check integrity."""
    source = requirement.get("source") or {}
    evidence = requirement.get("evidence") or []
    if run is None:
        return locator_complete(source) and any(locator_complete(item) for item in evidence)
    source_ok, _ = validate_side(run, source, role="tender")
    if not source_ok:
        return False
    return any(validate_side(run, item, role="evidence")[0] for item in evidence)


def citation_issues(requirement: dict[str, Any], run: dict[str, Any] | None = None) -> list[str]:
    issues: list[str] = []
    source_ok, source_issue = validate_side(run, requirement.get("source"), role="tender")
    if not source_ok and source_issue:
        issues.append(f"source:{source_issue}")

    evidence = requirement.get("evidence") or []
    if not evidence:
        issues.append(f"evidence:{MISSING_EVIDENCE}")
        return issues

    evidence_ok = False
    for index, item in enumerate(evidence):
        ok, issue = validate_side(run, item, role="evidence")
        if ok:
            evidence_ok = True
        elif issue:
            issues.append(f"evidence[{index}]:{issue}")
    if evidence_ok:
        # Drop per-item failures when at least one evidence citation is sound.
        issues = [item for item in issues if not item.startswith("evidence[")]
    return issues


def annotate_evidence_source_ids(requirements: list[dict[str, Any]], evidence_pages: list[dict[str, Any]]) -> None:
    """Backfill source_id onto evidence hits from the page that produced them."""
    by_key = {
        (page.get("source_filename"), page.get("page")): page.get("source_id")
        for page in evidence_pages
        if page.get("source_id")
    }
    for requirement in requirements:
        for item in requirement.get("evidence") or []:
            if item.get("source_id"):
                continue
            source_id = by_key.get((item.get("filename"), item.get("page")))
            if source_id:
                item["source_id"] = source_id
