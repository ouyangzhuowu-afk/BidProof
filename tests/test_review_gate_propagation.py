"""Review gate propagation: API and projections cannot mint forged PASS."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import main, presenters, quality_gates, review_policy
from app.services import scan_service
from tests.conftest import TEST_AUTH_HEADERS
from tests.test_citation_integrity import _requirement, _run_with_corpus


def _allow_quality(monkeypatch):
    monkeypatch.setattr(quality_gates, "allow_machine_pass", lambda report_dir=None: True)
    monkeypatch.setattr(review_policy, "engineering_allows_pass", lambda run=None: True)


def test_effective_status_demotes_forged_pass_without_corpus():
    requirement = _requirement()
    requirement["status"] = "PASS"
    run = {"source_documents": [], "state": {}}
    assert review_policy.effective_status(requirement, run) == "NEEDS_REVIEW"
    assert review_policy.review_required(requirement, run) is True
    projected = review_policy.project_requirement(requirement, run)
    assert projected["effective_status"] == "NEEDS_REVIEW"
    assert projected["review_required"] is True
    assert projected["citation_ok"] is False


def test_quality_gate_fail_blocks_pass_even_with_sound_citations(monkeypatch):
    monkeypatch.setattr(quality_gates, "allow_machine_pass", lambda report_dir=None: False)
    run = _run_with_corpus()
    requirement = _requirement()
    allowed, reason = review_policy.can_set_pass(requirement, run)
    assert allowed is False
    assert reason == review_policy.PASS_BLOCKED_QUALITY
    assert review_policy.effective_status({**requirement, "status": "PASS"}, run) == "NEEDS_REVIEW"


def test_public_run_propagates_effective_status_and_review_required(monkeypatch):
    _allow_quality(monkeypatch)
    run = _run_with_corpus()
    run.update(
        {
            "run_id": "run-gate",
            "status": "AUDIT",
            "created_at": "2026-10-02T00:00:00+00:00",
            "updated_at": "2026-10-02T00:00:00+00:00",
            "tender_filename": "same.pdf",
            "requirements": [{**_requirement(), "status": "PASS"}],
            "review": {"items": []},
            "state": {**_run_with_corpus()["state"], "scan_quality": {}},
        }
    )
    public = presenters.public_run(run)
    item = public["requirements"][0]
    assert item["status"] == "PASS"
    assert item["effective_status"] == "PASS"
    assert item["review_required"] is False
    assert item["citation_ok"] is True
    assert public["unresolved_count"] == 0


def test_public_summary_counts_use_effective_status_not_stored_pass(monkeypatch):
    monkeypatch.setattr(quality_gates, "allow_machine_pass", lambda report_dir=None: False)
    run = {
        "run_id": "run-summary",
        "status": "AUDIT",
        "created_at": "2026-10-02T00:00:00+00:00",
        "updated_at": "2026-10-02T00:00:00+00:00",
        "tender_filename": "tender.pdf",
        "source_documents": [],
        "requirements": [
            {
                "requirement_id": "REQ-0001",
                "category": "QUALIFICATION",
                "status": "PASS",
                "source": {},
                "evidence": [],
            }
        ],
        "review": {"items": []},
        "state": {},
    }
    summary = presenters.public_summary(run)
    assert summary["unresolved_count"] == 1
    assert summary["blocker_count"] == 1


def test_api_pass_bypass_without_evidence_is_rejected(monkeypatch):
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)

    def fake_extract(_path):
        return [{"page": 4, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12, "source_id": "TENDER-001"}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    response = client.post(
        "/api/runs",
        files={"tender": ("tender.pdf", b"%PDF-1.4 qualification", "application/pdf")},
    )
    run = response.json()
    requirement_id = run["requirements"][0]["requirement_id"]
    reviewed = client.post(
        f"/api/runs/{run['run_id']}/review",
        json={"requirement_id": requirement_id, "decision": "PASS", "revision": run["revision"]},
    )
    assert reviewed.status_code == 422
    assert run["requirements"][0].get("effective_status") in {None, "NEEDS_REVIEW"}
    client.delete(f"/api/runs/{run['run_id']}")


def test_api_confirm_pass_blocked_when_quote_does_not_match_page(monkeypatch, tmp_path):
    _allow_quality(monkeypatch)
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)

    tender_text = "资格要求：提供营业执照。"
    evidence_text = "本公司营业执照有效。"

    def fake_extract(path: Path):
        name = Path(path).name
        if name.startswith("tender-"):
            return [{"page": 1, "text": tender_text, "has_text": True, "char_count": len(tender_text)}]
        return [{"page": 1, "text": evidence_text, "has_text": True, "char_count": len(evidence_text)}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    created = client.post(
        "/api/runs",
        files=[
            ("tender", ("tender.txt", tender_text.encode(), "text/plain")),
            ("evidence", ("license.txt", evidence_text.encode(), "text/plain")),
        ],
        data={"company_name": "引用完整性测试"},
    )
    assert created.status_code == 200, created.text
    run = created.json()
    item = run["requirements"][0]
    # Corrupt the stored quote after scan so a later PASS would be forged.
    from app.repositories import runs as runs_repo

    stored = runs_repo.load(run["run_id"])
    stored["requirements"][0]["source"]["quote"] = "这段原文并不在招标首页"
    runs_repo.save(stored)

    forged = client.post(
        f"/api/runs/{run['run_id']}/review",
        json={
            "requirement_id": item["requirement_id"],
            "decision": "CONFIRM",
            "new_status": "PASS",
            "revision": stored["revision"],
        },
    )
    assert forged.status_code == 422
    assert "引用" in forged.json()["detail"] or "PASS" in forged.json()["detail"]
    latest = client.get(f"/api/runs/{run['run_id']}").json()
    assert latest["requirements"][0]["status"] != "PASS"
    assert latest["requirements"][0]["effective_status"] != "PASS"
    client.delete(f"/api/runs/{run['run_id']}")


def test_api_confirm_pass_succeeds_only_with_integrity_and_quality(monkeypatch):
    _allow_quality(monkeypatch)
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)
    tender_text = "资格要求：提供营业执照。"
    evidence_text = "本公司营业执照有效。"

    def fake_extract(path: Path):
        name = Path(path).name
        if name.startswith("tender-"):
            return [{"page": 1, "text": tender_text, "has_text": True, "char_count": len(tender_text)}]
        return [{"page": 1, "text": evidence_text, "has_text": True, "char_count": len(evidence_text)}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    created = client.post(
        "/api/runs",
        files=[
            ("tender", ("tender.txt", tender_text.encode(), "text/plain")),
            ("evidence", ("license.txt", evidence_text.encode(), "text/plain")),
        ],
        data={"company_name": "完整引用通过"},
    )
    assert created.status_code == 200, created.text
    run = created.json()
    item = run["requirements"][0]
    assert item["citation_ok"] is True
    assert not item.get("pass_block_reason")

    confirmed = client.post(
        f"/api/runs/{run['run_id']}/review",
        json={
            "requirement_id": item["requirement_id"],
            "decision": "CONFIRM",
            "new_status": "PASS",
            "revision": run["revision"],
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["requirements"][0]["status"] == "PASS"
    assert body["requirements"][0]["effective_status"] == "PASS"
    assert body["requirements"][0]["review_required"] is False
    client.delete(f"/api/runs/{run['run_id']}")
