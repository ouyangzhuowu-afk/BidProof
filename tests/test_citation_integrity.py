"""Citation integrity: forged PASS paths must fail closed."""

from __future__ import annotations

from app import citations


def _run_with_corpus() -> dict:
    return {
        "source_documents": [
            {
                "source_id": "TENDER-001",
                "role": "tender",
                "filename": "same.pdf",
                "pages": 2,
                "page_index": [
                    {"page": 1, "ocr_status": "NOT_REQUIRED"},
                    {"page": 2, "ocr_status": "NOT_REQUIRED"},
                ],
            },
            {
                "source_id": "EVD-001",
                "role": "enterprise_evidence",
                "filename": "same.pdf",
                "pages": 1,
                "page_index": [{"page": 1, "ocr_status": "NOT_REQUIRED"}],
            },
            {
                "source_id": "EVD-002",
                "role": "enterprise_evidence",
                "filename": "same.pdf",
                "pages": 1,
                "page_index": [{"page": 1, "ocr_status": "NOT_REQUIRED"}],
            },
        ],
        "state": {
            "citation_corpus": {
                "TENDER-001": {
                    "1": "资格要求：提供营业执照。",
                    "2": "投标截止时间：2026年9月1日。",
                },
                "EVD-001": {"1": "本公司营业执照有效，统一社会信用代码 123。"},
                "EVD-002": {"1": "银行保函金额符合要求。"},
            }
        },
    }


def _requirement(**overrides) -> dict:
    base = {
        "requirement_id": "REQ-0001",
        "category": "QUALIFICATION",
        "status": "NEEDS_REVIEW",
        "source": {
            "source_id": "TENDER-001",
            "page": 1,
            "locator": {"kind": "page", "label": "第 1 页", "index": 1},
            "quote": "资格要求：提供营业执照。",
        },
        "evidence": [
            {
                "source_id": "EVD-001",
                "filename": "same.pdf",
                "page": 1,
                "locator": {"kind": "page", "label": "第 1 页", "index": 1},
                "quote": "本公司营业执照有效",
            }
        ],
    }
    base.update(overrides)
    return base


def test_quote_must_match_cited_page_text():
    run = _run_with_corpus()
    ok, reason = citations.validate_side(
        run,
        {
            "source_id": "TENDER-001",
            "page": 1,
            "locator": {"kind": "page", "label": "第 1 页", "index": 1},
            "quote": "银行保函金额符合要求",
        },
        role="tender",
    )
    assert ok is False
    assert reason == citations.WRONG_PAGE_QUOTE


def test_wrong_page_cite_is_rejected_even_when_quote_exists_elsewhere():
    run = _run_with_corpus()
    # Quote lives on page 2 of tender, but citation claims page 1.
    ok, reason = citations.validate_side(
        run,
        {
            "source_id": "TENDER-001",
            "page": 1,
            "locator": {"kind": "page", "label": "第 1 页", "index": 1},
            "quote": "投标截止时间：2026年9月1日。",
        },
        role="tender",
    )
    assert ok is False
    assert reason == citations.WRONG_PAGE_QUOTE


def test_page_out_of_bounds_is_rejected():
    run = _run_with_corpus()
    ok, reason = citations.validate_side(
        run,
        {
            "source_id": "EVD-001",
            "page": 9,
            "locator": {"kind": "page", "label": "第 9 页", "index": 9},
            "quote": "本公司营业执照有效",
        },
        role="evidence",
    )
    assert ok is False
    assert reason == citations.PAGE_OOB


def test_missing_span_blocks_complete_citation():
    run = _run_with_corpus()
    requirement = _requirement(
        source={
            "source_id": "TENDER-001",
            "page": 1,
            "locator": {"kind": "page", "label": "第 1 页", "index": 1},
            "quote": "",
        }
    )
    assert citations.has_complete_citation(requirement, run) is False
    assert any(issue.endswith(citations.MISSING_SPAN) for issue in citations.citation_issues(requirement, run))


def test_same_name_files_require_source_id_not_filename_guess():
    run = _run_with_corpus()
    # Two enterprise evidence files share the upload name; omitting source_id must not resolve.
    requirement = _requirement(
        evidence=[
            {
                "filename": "same.pdf",
                "page": 1,
                "locator": {"kind": "page", "label": "第 1 页", "index": 1},
                "quote": "本公司营业执照有效",
            }
        ]
    )
    assert citations.has_complete_citation(requirement, run) is False
    issues = citations.citation_issues(requirement, run)
    assert any(
        issue.endswith((citations.MISSING_SOURCE_ID, citations.AMBIGUOUS_FILENAME))
        for issue in issues
    )


def test_sound_dual_citation_passes_integrity_when_corpus_matches():
    run = _run_with_corpus()
    requirement = _requirement()
    assert citations.has_complete_citation(requirement, run) is True
    assert citations.citation_issues(requirement, run) == []


def test_build_page_corpus_indexes_by_source_and_page():
    corpus = citations.build_page_corpus(
        [
            {"source_id": "TENDER-001", "page": 1, "text": "A"},
            {"source_id": "EVD-001", "page": 2, "text": "B"},
        ]
    )
    assert corpus == {"TENDER-001": {"1": "A"}, "EVD-001": {"2": "B"}}
