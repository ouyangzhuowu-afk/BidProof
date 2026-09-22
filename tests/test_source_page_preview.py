"""Source previews preserve file authorization and return actual bounded pages."""

import fitz
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.repositories import runs
from app.services import scan_service

OWNER = {"X-Workspace-ID": "page-preview", "X-User-ID": "owner", "X-User-Role": "OWNER"}


def pdf_bytes(*, width=600, height=800):
    with fitz.open() as document:
        for color in ((1, 0, 0), (0, 0, 1)):
            page = document.new_page(width=width, height=height)
            page.draw_rect(fitz.Rect(10, 10, width - 10, height - 10), color=color, fill=color)
        return document.tobytes()


@pytest.fixture
def preview_run(monkeypatch):
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{
        "page": 1, "text": "资格要求：提供营业执照。", "has_text": True,
        "char_count": 14, "blocks": [],
    }])
    client = TestClient(main.app)
    created = client.post("/api/runs", headers=OWNER, files=[
        ("tender", ("tender.pdf", pdf_bytes(), "application/pdf")),
        ("evidence", ("proof.txt", "营业执照".encode(), "text/plain")),
        ("evidence", ("proof.pdf", pdf_bytes(width=8000, height=6000), "application/pdf")),
    ])
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]
    yield client, run_id
    client.delete(f"/api/runs/{run_id}", headers=OWNER)


def test_source_preview_returns_requested_original_page_and_bounds_large_pages(preview_run):
    client, run_id = preview_run
    base = f"/api/runs/{run_id}/files"
    first = client.get(f"{base}/TENDER-001/pages/1", headers=OWNER)
    second = client.get(f"{base}/TENDER-001/pages/2", headers=OWNER)
    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert "no-store" in first.headers["cache-control"]
    assert first.content.startswith(b"\x89PNG\r\n\x1a\n")
    one, two = fitz.Pixmap(first.content), fitz.Pixmap(second.content)
    assert one.pixel(100, 100) == (255, 0, 0)
    assert two.pixel(100, 100) == (0, 0, 255)
    large = client.get(f"{base}/EVD-002/pages/1", headers=OWNER)
    assert large.status_code == 200
    image = fitz.Pixmap(large.content)
    assert max(image.width, image.height) <= 2000


def test_source_preview_requires_same_authorization_as_download(preview_run, monkeypatch):
    client, run_id = preview_run
    url = f"/api/runs/{run_id}/files/TENDER-001/pages/1"
    assert client.get(url, headers={**OWNER, "X-Workspace-ID": "foreign"}).status_code == 404
    assert client.get(url, headers={**OWNER, "X-User-Role": "VIEWER"}).status_code == 403
    monkeypatch.setattr(config, "ALLOW_TRUSTED_HEADERS", False)
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("page,status", [(0, 422), (-1, 422), (3, 404), ("unknown", 422)])
def test_source_preview_rejects_invalid_page_numbers(preview_run, page, status):
    client, run_id = preview_run
    response = client.get(f"/api/runs/{run_id}/files/TENDER-001/pages/{page}", headers=OWNER)
    assert response.status_code == status


def test_source_preview_rejects_non_pdf_missing_and_escaped_sources(preview_run, tmp_path):
    client, run_id = preview_run
    base = f"/api/runs/{run_id}/files"
    assert client.get(f"{base}/EVD-001/pages/1", headers=OWNER).status_code == 415
    assert client.get(f"{base}/missing/pages/1", headers=OWNER).status_code == 404
    assert client.get(f"{base}/..%2Foutside/pages/1", headers=OWNER).status_code in {400, 404}

    # Even a stored source record must not turn the preview into a file reader.
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(pdf_bytes())
    run = runs.load(run_id)
    run["evidence_files"].append({"asset_id": "ESCAPED", "path": str(outside), "filename": "outside.pdf"})
    runs.save(run)
    assert client.get(f"{base}/ESCAPED/pages/1", headers=OWNER).status_code == 404


def test_source_preview_handles_a_corrupt_pdf_without_returning_file_bytes(preview_run):
    client, run_id = preview_run
    run = runs.load(run_id)
    from pathlib import Path

    Path(run["tender_path"]).write_bytes(b"this is not a PDF")
    response = client.get(f"/api/runs/{run_id}/files/TENDER-001/pages/1", headers=OWNER)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
