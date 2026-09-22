"""Different originals keep their identity even when uploaded names collide."""

from __future__ import annotations

import hashlib

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.uploads import safe_filename

OWNER = {"X-Workspace-ID": "source-identity-tests", "X-User-ID": "identity-owner", "X-User-Role": "OWNER"}
SOURCE_IDS = ("TENDER-001", "EVD-001", "EVD-002")
COLORS = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
PIXELS = ((255, 0, 0), (0, 255, 0), (0, 0, 255))


def original_pdf(source_id: str, color: tuple[int, int, int]) -> bytes:
    """Generated local material: searchable text plus a distinct original-page mark."""
    with fitz.open() as document:
        page = document.new_page(width=400, height=500)
        page.draw_rect(fitz.Rect(20, 20, 100, 100), color=color, fill=color)
        page.insert_text((40, 125), f"SOURCE ID: {source_id}", fontsize=11)
        page.insert_textbox(
            fitz.Rect(40, 155, 360, 460),
            "界面工程测试生成材料，非真实招标文件或企业证明。\n"
            "投标人资格要求：提供有效的营业执照及软件实施服务相关业绩证明。\n"
            "本文件只验证同名上传的原文、文件摘要和原页图像不会相互覆盖。\n"
            "请按来源编号独立保存招标材料与每一份企业证据，并保留原始文件名称。",
            fontname="china-s",
            fontsize=11,
        )
        return document.tobytes()


@pytest.mark.parametrize("route", ["/api/runs", "/api/jobs"], ids=["direct", "queued"])
@pytest.mark.parametrize(
    "filenames",
    [
        ("same.pdf", "same.pdf", "same.pdf"),
        ("proof_copy.pdf", "proof..copy.pdf", "proof_copy.pdf"),
    ],
    ids=["identical-names", "sanitized-collision"],
)
def test_uploaded_originals_remain_distinct_after_scan_and_page_preview(monkeypatch, route, filenames):
    # Keep the real PDF parser and upload pipeline. No OCR or external services
    # are needed for these generated, searchable originals.
    monkeypatch.setenv("BID_OCR_PROVIDER", "disabled")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    monkeypatch.setattr(config, "JOB_RUNNER", "inline")
    assert len({safe_filename(name) for name in filenames}) == 1, "The fixture must collide under the actual sanitizer."
    originals = [original_pdf(source_id, color) for source_id, color in zip(SOURCE_IDS, COLORS)]
    expected_hashes = [hashlib.sha256(payload).hexdigest() for payload in originals]
    assert len(set(expected_hashes)) == 3
    files = [
        ("tender" if index == 0 else "evidence", (filename, payload, "application/pdf"))
        for index, (filename, payload) in enumerate(zip(filenames, originals))
    ]
    client = TestClient(main.app)
    created = client.post(route, headers=OWNER, files=files, data={"company_name": "文件身份回归测试示例"})
    assert created.status_code == (202 if route == "/api/jobs" else 200), created.text
    if route == "/api/jobs":
        job_id = created.json()["job_id"]
        job_response = client.get(f"/api/jobs/{job_id}", headers=OWNER)
        assert job_response.status_code == 200
        job = job_response.json()
        assert job["status"] == "COMPLETED", job
        run_id = job["run_id"]
        assert not (config.JOB_STAGING_DIR / job_id).exists(), "Completed jobs release staging without losing the final originals."
    else:
        run_id = created.json()["run_id"]

    try:
        loaded = client.get(f"/api/runs/{run_id}", headers=OWNER)
        assert loaded.status_code == 200
        run = loaded.json()
        documents = {entry["source_id"]: entry for entry in run["source_documents"]}
        assert set(documents) == set(SOURCE_IDS)
        assert run["tender_filename"] == filenames[0]
        assert run["tender_sha256"] == expected_hashes[0]
        assert [asset["filename"] for asset in run["evidence_assets"]] == list(filenames[1:])
        assert [asset["sha256"] for asset in run["evidence_assets"]] == expected_hashes[1:]

        for source_id, filename, original, digest, pixel in zip(SOURCE_IDS, filenames, originals, expected_hashes, PIXELS):
            assert documents[source_id]["filename"] == filename, "Internal storage names must not replace the displayed upload name."
            assert documents[source_id]["sha256"] == digest
            assert documents[source_id]["pages"] == 1
            download = client.get(f"/api/runs/{run_id}/files/{source_id}", headers=OWNER)
            assert download.status_code == 200
            assert download.content == original, f"{source_id} was overwritten by another same-named upload."
            assert hashlib.sha256(download.content).hexdigest() == digest
            with fitz.open(stream=download.content, filetype="pdf") as document:
                assert f"SOURCE ID: {source_id}" in document[0].get_text()

            preview = client.get(f"/api/runs/{run_id}/files/{source_id}/pages/1", headers=OWNER)
            assert preview.status_code == 200
            assert preview.headers["content-type"] == "image/png"
            assert fitz.Pixmap(preview.content).pixel(60, 60) == pixel, f"{source_id} preview must show its own original page."
    finally:
        deleted = client.delete(f"/api/runs/{run_id}", headers=OWNER)
        assert deleted.status_code == 200
