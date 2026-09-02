import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import main
from app.db import create_scan_job


def _pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_remediation_lifecycle_is_scoped_and_audited(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    workspace = f"remediation-{uuid.uuid4().hex}"
    owner = {"X-Workspace-ID": workspace, "X-User-ID": "owner", "X-User-Role": "OWNER"}
    other = {"X-Workspace-ID": f"other-{uuid.uuid4().hex}", "X-User-ID": "other", "X-User-Role": "OWNER"}
    run = client.post("/api/runs", headers=owner, files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()

    created = client.post(
        f"/api/runs/{run['run_id']}/remediations",
        headers=owner,
        json={"title": "补充营业执照原件", "owner_id": "owner", "due_date": "2026-09-01", "requirement_id": run["requirements"][0]["requirement_id"]},
    )
    assert created.status_code == 201
    remediation_id = created.json()["remediation_id"]
    assert created.json()["status"] == "OPEN"
    assert client.get(f"/api/runs/{run['run_id']}/remediations", headers=other).status_code == 404

    updated = client.patch(f"/api/remediations/{remediation_id}", headers=owner, json={"status": "DONE", "note": "已归档原件"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "DONE"
    audit = client.get(f"/api/runs/{run['run_id']}/audit", headers=owner).json()["events"]
    assert any(event["event_type"] == "REMEDIATION_UPDATED" for event in audit)


def test_usage_and_privacy_surfaces_are_workspace_scoped():
    client = TestClient(main.app)
    headers = {"X-Workspace-ID": f"usage-{uuid.uuid4().hex}", "X-User-ID": "owner", "X-User-Role": "OWNER"}

    usage = client.get("/api/workspace/usage", headers=headers)
    privacy = client.get("/api/workspace/privacy", headers=headers)

    assert usage.status_code == 200
    assert {"runs", "members", "scan_jobs", "audit_events", "feedback"}.issubset(usage.json())
    assert privacy.status_code == 200
    assert privacy.json()["retention_days"] >= 1
    assert privacy.json()["uploaded_content_is_data"] is True
    assert "not legal advice" in privacy.json()["boundary"].lower()


def test_notifications_surface_overdue_remediations_and_failed_jobs(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    workspace = f"notifications-{uuid.uuid4().hex}"
    headers = {"X-Workspace-ID": workspace, "X-User-ID": "owner", "X-User-Role": "OWNER"}
    run = client.post("/api/runs", headers=headers, files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    due = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    created = client.post(f"/api/runs/{run['run_id']}/remediations", headers=headers, json={"title": "补齐证据", "due_date": due})
    assert created.status_code == 201
    create_scan_job(f"failed-{uuid.uuid4().hex}", workspace, None, "FAILED", {"error": "parse"})

    payload = client.get("/api/notifications", headers=headers)
    assert payload.status_code == 200
    types = {item["type"] for item in payload.json()["notifications"]}
    assert {"REMEDIATION_OVERDUE", "SCAN_JOB_FAILED"}.issubset(types)
