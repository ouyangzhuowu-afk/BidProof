"""S-A-09: public tender corpus collector (engineering fixtures only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest

from work.eval.collect_public_tenders import (
    ForbiddenOutputError,
    completed_documents,
    failed_records,
    load_manifest,
    main as collect_main,
    run_collection,
    summarize,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
CANONICAL_PDFS = ROOT / "work" / "public-eval" / "pdfs"
PILOT_LEDGER = ROOT / "outputs" / "pilot-ledger.csv"
ICP_LEDGER = ROOT / "outputs" / "icp-outreach.csv"
LINE_CER_GATE = 0.02


def _tiny_pdf(text: str = "医院招标 医疗器械") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    payload = doc.tobytes()
    doc.close()
    return payload


def _candidate(candidate_id: str, url: str, **extra):
    row = {
        "candidate_id": candidate_id,
        "title": extra.pop("title", candidate_id),
        "publisher": extra.pop("publisher", "public government portal"),
        "source_type": extra.pop("source_type", "provincial_public_resource_platform"),
        "domain": extra.pop("domain", "hospital_meddevice"),
        "source_url": url,
        "file_url": extra.pop("file_url", url),
    }
    row.update(extra)
    return row


def test_completed_rows_require_source_url_and_sha256():
    manifest = {
        "documents": [
            {"document_id": "ok", "source_url": "https://gov.example/a.pdf", "sha256": "abc"},
            {"document_id": "no-hash", "source_url": "https://gov.example/b.pdf"},
            {"document_id": "no-url", "sha256": "def"},
            {"document_id": "failed-row", "source_url": "https://gov.example/dead.pdf", "status": "failed"},
        ],
        "fetch_failures": [
            {"source_url": "https://gov.example/dead.pdf", "error": "HTTP 404", "counts_as_completed": False}
        ],
    }
    done = completed_documents(manifest)
    assert [row["document_id"] for row in done] == ["ok"]
    assert len(failed_records(manifest)) == 1
    summary = summarize(manifest, newly_added=1, newly_failed=1)
    assert summary["completed_documents"] == 1
    assert summary["failed_urls"] == 1
    assert summary["newly_added"] == 1
    assert summary["newly_failed"] == 1
    assert summary["product_pass"] is False
    assert summary["business_pass"] is False


def test_failed_urls_are_recorded_but_never_counted_as_completed(tmp_path):
    payloads = {
        "https://gov.example/hospital.pdf": _tiny_pdf("三甲医院 监护仪"),
        "https://gov.example/dead.pdf": b"Not Found",
    }
    statuses = {
        "https://gov.example/hospital.pdf": 200,
        "https://gov.example/dead.pdf": 404,
    }

    def fake_fetch(url: str) -> tuple[int, bytes, str]:
        return statuses[url], payloads[url], "application/pdf" if url.endswith("hospital.pdf") else "text/html"

    sleeps: list[float] = []
    dest = tmp_path / "pdfs"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"schema_version": "1.0", "documents": [], "fetch_failures": []}), encoding="utf-8")
    report = run_collection(
        candidates=[
            _candidate("pub-med-001", "https://gov.example/hospital.pdf", title="医院监护仪采购"),
            _candidate("pub-dead-001", "https://gov.example/dead.pdf", title="dead"),
        ],
        manifest_path=manifest_path,
        pdfs_dir=dest,
        fetch=fake_fetch,
        sleeper=sleeps.append,
        delay_seconds=1.5,
    )
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report["newly_added"] == 1
    assert report["newly_failed"] == 1
    assert report["completed_documents"] == 1
    assert report["failed_urls"] == 1
    assert len(completed_documents(stored)) == 1
    assert completed_documents(stored)[0]["source_url"] == "https://gov.example/hospital.pdf"
    assert completed_documents(stored)[0]["sha256"] == hashlib.sha256(payloads["https://gov.example/hospital.pdf"]).hexdigest()
    assert stored["fetch_failures"][0]["source_url"] == "https://gov.example/dead.pdf"
    assert stored["fetch_failures"][0].get("counts_as_completed") is False
    assert "sha256" not in stored["fetch_failures"][0] or not stored["fetch_failures"][0].get("sha256")
    assert sleeps == [1.5]
    pdf_files = list(dest.glob("*.pdf"))
    assert len(pdf_files) == 1
    assert pdf_files[0].read_bytes().startswith(b"%PDF")


def test_known_failures_are_skipped_unless_retry_requested(tmp_path):
    calls: list[str] = []

    def fake_fetch(url: str) -> tuple[int, bytes, str]:
        calls.append(url)
        return 404, b"gone", "text/html"

    dest = tmp_path / "pdfs"
    manifest_path = tmp_path / "manifest.json"
    dead = _candidate("pub-dead-001", "https://gov.example/dead.pdf")
    first = run_collection(
        candidates=[dead],
        manifest_path=manifest_path,
        pdfs_dir=dest,
        fetch=fake_fetch,
        sleeper=lambda _: None,
        delay_seconds=0,
    )
    assert first["newly_failed"] == 1
    second = run_collection(
        candidates=[dead],
        manifest_path=manifest_path,
        pdfs_dir=dest,
        fetch=fake_fetch,
        sleeper=lambda _: None,
        delay_seconds=0,
    )
    assert second["newly_failed"] == 0
    assert calls == ["https://gov.example/dead.pdf"]
    retried = run_collection(
        candidates=[dead],
        manifest_path=manifest_path,
        pdfs_dir=dest,
        fetch=fake_fetch,
        sleeper=lambda _: None,
        delay_seconds=0,
        retry_failures=True,
    )
    assert retried["newly_failed"] == 1
    assert calls == ["https://gov.example/dead.pdf", "https://gov.example/dead.pdf"]
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(failed_records(stored)) == 1
    assert completed_documents(stored) == []


def test_non_pdf_body_is_a_failed_url_not_a_completed_document(tmp_path):
    def fake_fetch(url: str) -> tuple[int, bytes, str]:
        return 200, b"<html>login wall</html>", "text/html"

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    report = run_collection(
        candidates=[_candidate("html-wall", "https://gov.example/login-wall.pdf")],
        manifest_path=manifest_path,
        pdfs_dir=tmp_path / "pdfs",
        fetch=fake_fetch,
        sleeper=lambda _: None,
        delay_seconds=0,
    )
    stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert report["newly_added"] == 0
    assert report["newly_failed"] == 1
    assert completed_documents(stored) == []
    assert failed_records(stored)[0]["source_url"].endswith("login-wall.pdf")


def test_collector_refuses_ledger_output_paths(tmp_path):
    with pytest.raises(ForbiddenOutputError):
        run_collection(
            candidates=[],
            manifest_path=tmp_path / "pilot-ledger.csv",
            pdfs_dir=tmp_path / "pdfs",
            fetch=lambda url: (200, b"%PDF", "application/pdf"),
            sleeper=lambda _: None,
            delay_seconds=0,
        )
    with pytest.raises(ForbiddenOutputError):
        run_collection(
            candidates=[],
            manifest_path=tmp_path / "manifest.json",
            pdfs_dir=tmp_path / "icp-outreach",
            fetch=lambda url: (200, b"%PDF", "application/pdf"),
            sleeper=lambda _: None,
            delay_seconds=0,
        )


def test_cli_does_not_touch_pilot_or_icp_ledgers(tmp_path):
    pdf = _tiny_pdf()
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps({"candidates": [_candidate("cli-001", "https://gov.example/ok.pdf")]}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    pdfs_dir = tmp_path / "pdfs"
    report_dir = tmp_path / "ocr-benchmark"
    pilot_before = PILOT_LEDGER.read_text(encoding="utf-8")
    icp_before = ICP_LEDGER.read_text(encoding="utf-8")

    def fake_fetch(url: str) -> tuple[int, bytes, str]:
        return 200, pdf, "application/pdf"

    from work.eval import collect_public_tenders as mod

    original = mod.default_fetch
    mod.default_fetch = fake_fetch
    try:
        code = collect_main(
            [
                "--candidates",
                str(candidates),
                "--manifest",
                str(manifest_path),
                "--pdfs-dir",
                str(pdfs_dir),
                "--report-dir",
                str(report_dir),
                "--delay",
                "0",
            ]
        )
    finally:
        mod.default_fetch = original

    assert code == 0
    assert PILOT_LEDGER.read_text(encoding="utf-8") == pilot_before
    assert ICP_LEDGER.read_text(encoding="utf-8") == icp_before
    assert not list(tmp_path.rglob("*pilot-ledger*"))
    assert not list(tmp_path.rglob("*icp-outreach*"))
    md = (report_dir / "public-tender-fetch-report.md").read_text(encoding="utf-8")
    assert "newly_added" in md or "newly added" in md.lower()
    assert "product PASS" not in md.lower() or "not a product" in md.lower()
    assert "T-005" in md and "not" in md.lower()


def test_canonical_public_eval_manifest_completed_rows_have_url_and_matching_sha256():
    manifest = load_manifest(CANONICAL_MANIFEST)
    issues = validate_manifest(manifest, CANONICAL_PDFS)
    assert issues == []
    done = completed_documents(manifest)
    assert len(done) >= 12
    assert sum(1 for row in done if row.get("leaf_id") == "S-A-09") >= 9
    assert len(failed_records(manifest)) >= 1
    for row in done:
        assert row["source_url"].startswith("http")
        assert len(row["sha256"]) == 64
        path = ROOT / row["path"] if row.get("path") else CANONICAL_PDFS / row["filename"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    for row in failed_records(manifest):
        assert row.get("source_url")
        assert row.get("counts_as_completed") is False
        assert not row.get("sha256")


def test_s_a_09_does_not_relax_line_cer_gate():
    from work.eval.rapidocr_line_cer import LINE_CER_GATE as live_gate

    assert live_gate == LINE_CER_GATE == 0.02
