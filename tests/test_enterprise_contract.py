import io
import sqlite3
import uuid
from pathlib import Path

import fitz
from fastapi.testclient import TestClient

from app import main
from app.config import DB_PATH


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def test_run_is_scoped_and_audited_by_workspace(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12, "blocks": []}])
    headers = {"X-Workspace-ID": "acme", "X-User-ID": "reviewer-1", "X-User-Role": "OWNER"}
    response = client.post("/api/runs", headers=headers, files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")})
    assert response.status_code == 200
    run = response.json()
    assert run["workspace_id"] == "acme"
    assert run["owner_id"] == "reviewer-1"
    assert client.get("/api/runs", headers=headers).json()[0]["run_id"] == run["run_id"]
    assert client.get("/api/runs", headers={"X-Workspace-ID": "other"}).json() == []
    audit = client.get(f"/api/runs/{run['run_id']}/audit", headers=headers)
    assert audit.status_code == 200
    assert any(event["event_type"] == "RUN_CREATED" for event in audit.json()["events"])
    client.delete(f"/api/runs/{run['run_id']}", headers=headers)


def test_every_run_subresource_is_scoped_by_workspace(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12, "blocks": []}])
    owner = {"X-Workspace-ID": "tenant-alpha", "X-User-ID": "owner-alpha", "X-User-Role": "OWNER"}
    attacker = {"X-Workspace-ID": "tenant-beta", "X-User-ID": "reviewer-beta", "X-User-Role": "REVIEWER"}
    run = client.post(
        "/api/runs",
        headers=owner,
        files={"tender": ("private.pdf", _pdf_bytes("资格要求"), "application/pdf")},
    ).json()
    run_id = run["run_id"]
    requirement_id = run["requirements"][0]["requirement_id"]

    for path in (
        f"/api/runs/{run_id}/requirements",
        f"/api/runs/{run_id}/evidence",
        f"/api/runs/{run_id}/report.html",
        f"/api/runs/{run_id}/report.csv",
        f"/api/runs/{run_id}/report.pdf",
    ):
        assert client.get(path, headers=attacker).status_code == 404, path

    assert client.post(
        f"/api/runs/{run_id}/review",
        headers=attacker,
        json={"requirement_id": requirement_id, "decision": "REJECT", "note": "越权修改"},
    ).status_code == 404
    assert client.post(
        f"/api/runs/{run_id}/decision",
        headers=attacker,
        json={"decision": "STOP", "note": "越权修改", "unresolved_requirement_ids": []},
    ).status_code == 404

    evidence_index = client.get("/api/evidence", headers=attacker).json()
    assert all(item["run_id"] != run_id for item in evidence_index["assets"])
    client.delete(f"/api/runs/{run_id}", headers=owner)


def test_viewer_cannot_mutate_or_delete_run(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    owner = {"X-Workspace-ID": "acme-view", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    viewer = {"X-Workspace-ID": "acme-view", "X-User-ID": "viewer", "X-User-Role": "VIEWER"}
    run = client.post("/api/runs", headers=owner, files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    response = client.post("/api/runs/bulk", headers=viewer, json={"run_ids": [run["run_id"]], "action": "ARCHIVE"})
    assert response.status_code == 403
    assert client.delete(f"/api/runs/{run['run_id']}", headers=viewer).status_code == 403
    client.delete(f"/api/runs/{run['run_id']}", headers=owner)


def test_pdf_report_is_a_real_pdf(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    run = client.post("/api/runs", files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    stored = main.load_run(run["run_id"])
    base_requirement = stored["requirements"][0]
    stored["requirements"] = [
        {**base_requirement, "requirement_id": f"REQ-{index:04d}", "title": f"资格要求 {index}"}
        for index in range(1, 46)
    ]
    main.save_run(stored)
    report = client.get(f"/api/runs/{run['run_id']}/report.pdf")
    assert report.status_code == 200
    assert report.content.startswith(b"%PDF")
    document = fitz.open(stream=report.content, filetype="pdf")
    assert document.page_count >= 2
    extracted = "\n".join(page.get_text() for page in document)
    assert "REQ-0045" in extracted
    assert "45" in extracted
    document.close()
    client.delete(f"/api/runs/{run['run_id']}")


def test_database_has_audit_and_job_tables():
    with sqlite3.connect(DB_PATH) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"audit_events", "scan_jobs", "workspaces", "workspace_members"}.issubset(tables)


def test_rescan_creates_version_and_diff(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12, "blocks": []}])
    first = client.post("/api/runs", files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    second_response = client.post(
        f"/api/runs/{first['run_id']}/rescan",
        files={"tender": ("tender-v2.pdf", _pdf_bytes("资格要求"), "application/pdf")},
    )
    assert second_response.status_code == 200
    second = second_response.json()
    assert second["parent_run_id"] == first["run_id"]
    assert second["version_number"] == 2
    diff = client.get(f"/api/runs/{second['run_id']}/diff/{first['run_id']}")
    assert diff.status_code == 200
    assert set(diff.json()) >= {"added", "removed", "changed"}
    client.delete(f"/api/runs/{second['run_id']}")
    client.delete(f"/api/runs/{first['run_id']}")


def test_assignment_tags_comments_and_health_detail(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    headers = {"X-Workspace-ID": "collab", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    run = client.post("/api/runs", headers=headers, files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    metadata = client.patch(
        f"/api/runs/{run['run_id']}/metadata",
        headers=headers,
        json={"assignee_id": "reviewer-2", "tags": ["本周截止", "重点"], "favorite": True},
    )
    assert metadata.status_code == 200
    assert metadata.json()["assignee_id"] == "reviewer-2"
    assert metadata.json()["favorite"] is True
    comment = client.post(f"/api/runs/{run['run_id']}/comments", headers=headers, json={"body": "请复核营业执照原件"})
    assert comment.status_code == 200
    comments = client.get(f"/api/runs/{run['run_id']}/comments", headers=headers).json()["comments"]
    assert comments[0]["body"] == "请复核营业执照原件"
    health = client.get("/healthz?detail=true").json()
    assert health["database"] == "ok"
    assert "last_backup_at" in health
    client.delete(f"/api/runs/{run['run_id']}", headers=headers)


def test_upload_size_limit_is_enforced(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 8)
    response = client.post("/api/runs", files={"tender": ("large.txt", b"123456789", "text/plain")})
    assert response.status_code == 413


def test_file_signature_must_match_extension():
    client = TestClient(main.app)
    response = client.post("/api/runs", files={"tender": ("fake.pdf", b"MZ executable", "application/pdf")})
    assert response.status_code == 422


def test_persistent_scan_job_accepts_upload_and_links_run(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    response = client.post("/api/jobs", files={"tender": ("queued.pdf", _pdf_bytes("资格要求"), "application/pdf")})
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "COMPLETED"
    assert job["run_id"]
    client.delete(f"/api/runs/{job['run_id']}")


def test_background_scan_ignores_browser_empty_optional_evidence(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])

    boundary = "bidproof-empty-evidence"
    body = b"".join(
        [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"tender\"; filename=\"queued.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode(),
            _pdf_bytes("资格要求"),
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"evidence\"; filename=\"\"\r\nContent-Type: application/octet-stream\r\n\r\n\r\n--{boundary}--\r\n".encode(),
        ]
    )
    response = client.post("/api/jobs", content=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})

    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "COMPLETED"
    client.delete(f"/api/runs/{job['run_id']}")


def test_job_list_is_workspace_scoped(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    workspace = f"jobs-{uuid.uuid4().hex}"
    owner = {"X-Workspace-ID": workspace, "X-User-ID": "job-owner", "X-User-Role": "OWNER"}
    other = {"X-Workspace-ID": f"other-{uuid.uuid4().hex}", "X-User-ID": "other-owner", "X-User-Role": "OWNER"}
    queued = client.post("/api/jobs", headers=owner, files={"tender": ("queued.pdf", _pdf_bytes("资格要求"), "application/pdf")})
    assert queued.status_code == 202
    listed = client.get("/api/jobs", headers=owner)
    assert listed.status_code == 200
    assert queued.json()["job_id"] in {item["job_id"] for item in listed.json()["jobs"]}
    assert queued.json()["job_id"] not in {item["job_id"] for item in client.get("/api/jobs", headers=other).json()["jobs"]}
    job = client.get(f"/api/jobs/{queued.json()['job_id']}", headers=owner).json()
    client.delete(f"/api/runs/{job['run_id']}", headers=owner)


def test_duplicate_upload_and_retention_preview_are_auditable(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    workspace = f"lifecycle-{uuid.uuid4().hex}"
    owner = {"X-Workspace-ID": workspace, "X-User-ID": "lifecycle-owner", "X-User-Role": "OWNER"}
    viewer = {"X-Workspace-ID": workspace, "X-User-ID": "lifecycle-viewer", "X-User-Role": "VIEWER"}
    same_file = _pdf_bytes("资格要求")
    payload = {"tender": ("same.pdf", same_file, "application/pdf")}
    first = client.post("/api/runs", headers=owner, files=payload).json()
    second = client.post("/api/runs", headers=owner, files={"tender": ("same.pdf", same_file, "application/pdf")}).json()
    assert first["run_id"] in second["duplicate_run_ids"]

    assert client.post("/api/runs/bulk", headers=owner, json={"run_ids": [first["run_id"]], "action": "ARCHIVE"}).status_code == 200
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("UPDATE runs SET archived_at = '2000-01-01T00:00:00+00:00' WHERE run_id = ?", (first["run_id"],))
    settings = client.patch("/api/workspace/settings", headers=owner, json={"retention_days": 30})
    assert settings.status_code == 200
    preview = client.get("/api/retention/preview", headers=owner).json()
    assert first["run_id"] in preview["run_ids"]
    assert second["run_id"] not in preview["run_ids"]
    assert client.post("/api/retention/purge", headers=viewer).status_code == 403
    purged = client.post("/api/retention/purge", headers=owner)
    assert purged.status_code == 200
    assert purged.json()["deleted"] == 1
    assert client.get(f"/api/runs/{first['run_id']}", headers=owner).status_code == 404
    client.delete(f"/api/runs/{second['run_id']}", headers=owner)


def test_permanent_delete_removes_run_owned_data_and_uploads(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    headers = {"X-Workspace-ID": f"delete-{uuid.uuid4().hex}", "X-User-ID": "delete-owner", "X-User-Role": "OWNER"}
    run = client.post("/api/runs", headers=headers, files={"tender": ("delete.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    run_id = run["run_id"]
    requirement_id = run["requirements"][0]["requirement_id"]
    client.post(f"/api/runs/{run_id}/comments", headers=headers, json={"body": "删除前评论"})
    client.post(f"/api/runs/{run_id}/accuracy-feedback", headers=headers, json={"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": requirement_id})
    upload_dir = Path(main.load_run(run_id)["tender_path"]).parent
    assert upload_dir.exists()

    assert client.delete(f"/api/runs/{run_id}", headers=headers).status_code == 200
    assert not upload_dir.exists()
    with sqlite3.connect(DB_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM comments WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM accuracy_feedback WHERE run_id = ?", (run_id,)).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM scan_jobs WHERE run_id = ?", (run_id,)).fetchone()[0] == 0


def test_projects_group_runs_and_are_isolated_by_workspace(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    workspace = f"projects-{uuid.uuid4().hex}"
    owner = {"X-Workspace-ID": workspace, "X-User-ID": "project-owner", "X-User-Role": "OWNER"}
    viewer = {"X-Workspace-ID": workspace, "X-User-ID": "project-viewer", "X-User-Role": "VIEWER"}
    other = {"X-Workspace-ID": f"other-{uuid.uuid4().hex}", "X-User-ID": "other-owner", "X-User-Role": "OWNER"}

    created = client.post("/api/projects", headers=owner, json={"name": "华东政务项目", "code": "EAST-GOV"})
    assert created.status_code == 201
    project = created.json()
    assert client.post("/api/projects", headers=viewer, json={"name": "无权项目", "code": "NOPE"}).status_code == 403
    assert project["project_id"] in {item["project_id"] for item in client.get("/api/projects", headers=owner).json()["projects"]}
    assert project["project_id"] not in {item["project_id"] for item in client.get("/api/projects", headers=other).json()["projects"]}

    run = client.post(
        "/api/runs",
        headers=owner,
        data={"project_id": project["project_id"]},
        files={"tender": ("project.pdf", _pdf_bytes("资格要求"), "application/pdf")},
    )
    assert run.status_code == 200
    assert run.json()["project_id"] == project["project_id"]
    filtered = client.get(f"/api/runs?project_id={project['project_id']}", headers=owner).json()
    assert [item["run_id"] for item in filtered] == [run.json()["run_id"]]

    archived = client.patch(f"/api/projects/{project['project_id']}", headers=owner, json={"archived": True})
    assert archived.status_code == 200
    blocked = client.post(
        "/api/runs",
        headers=owner,
        data={"project_id": project["project_id"]},
        files={"tender": ("blocked.pdf", _pdf_bytes("资格要求"), "application/pdf")},
    )
    assert blocked.status_code == 409
    client.delete(f"/api/runs/{run.json()['run_id']}", headers=owner)


def test_accuracy_feedback_produces_category_metrics(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    headers = {"X-Workspace-ID": f"metrics-{uuid.uuid4().hex}", "X-User-ID": "metrics-reviewer", "X-User-Role": "OWNER"}
    run = client.post("/api/runs", headers=headers, files={"tender": ("metrics.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    detected_payload = {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": run["requirements"][0]["requirement_id"]}
    first = client.post(f"/api/runs/{run['run_id']}/accuracy-feedback", headers=headers, json=detected_payload)
    repeated = client.post(f"/api/runs/{run['run_id']}/accuracy-feedback", headers=headers, json={**detected_payload, "note": "重复确认应覆盖"})
    assert first.status_code == repeated.status_code == 200
    assert first.json()["feedback_id"] == repeated.json()["feedback_id"]

    missed_payload = {
        "category": "QUALIFICATION",
        "predicted": "MISSED",
        "actual": "RELEVANT",
        "locator_label": "第 2 页",
        "quote": "投标人须提供有效营业执照",
        "note": "人工发现漏项",
    }
    missed = client.post(f"/api/runs/{run['run_id']}/accuracy-feedback", headers=headers, json=missed_payload)
    missed_repeated = client.post(f"/api/runs/{run['run_id']}/accuracy-feedback", headers=headers, json=missed_payload)
    assert missed.status_code == missed_repeated.status_code == 200
    assert missed.json()["feedback_id"] == missed_repeated.json()["feedback_id"]

    metrics = client.get("/api/accuracy/metrics", headers=headers).json()
    qualification = next(item for item in metrics["categories"] if item["category"] == "QUALIFICATION")
    assert qualification["tp"] == 1
    assert qualification["fp"] == 0
    assert qualification["fn"] == 1
    assert qualification["sample_size"] == 2
    assert qualification["precision"] == 1.0
    assert qualification["recall"] == 0.5
    assert qualification["false_discovery_rate"] == 0.0
    assert qualification["miss_rate"] == 0.5
    assert qualification["detected_total"] == 1
    assert qualification["labeled_detected"] == 1
    assert qualification["coverage"] == 1.0
    assert qualification["measurement_status"] == "INSUFFICIENT"
    client.delete(f"/api/runs/{run['run_id']}", headers=headers)


def test_auth_bootstrap_login_and_session_enforcement():
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM auth_sessions")
        connection.execute("DELETE FROM users")


def test_owner_can_manage_members_and_deactivation_revokes_access():
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM auth_sessions")
        connection.execute("DELETE FROM users")
    owner = TestClient(main.app)
    assert owner.post(
        "/api/auth/bootstrap",
        json={"workspace_name": "成员测试企业", "username": "member-owner-test", "password": "OwnerPass-2026!"},
    ).status_code == 200

    created = owner.post(
        "/api/members",
        json={"username": "member-reviewer-test", "password": "ReviewerPass-2026!", "role": "REVIEWER"},
    )
    assert created.status_code == 201
    reviewer_id = created.json()["user_id"]
    assert "password_hash" not in created.json()
    members = owner.get("/api/members")
    assert members.status_code == 200
    assert {item["username"] for item in members.json()["members"]} == {"member-owner-test", "member-reviewer-test"}
    assert all("password_hash" not in item for item in members.json()["members"])

    reviewer = TestClient(main.app)
    assert reviewer.post("/api/auth/login", json={"username": "member-reviewer-test", "password": "ReviewerPass-2026!"}).status_code == 200
    assert reviewer.post(
        "/api/members",
        json={"username": "forbidden-user", "password": "ForbiddenPass-2026!", "role": "VIEWER"},
    ).status_code == 403

    deactivated = owner.patch(f"/api/members/{reviewer_id}", json={"active": False})
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert reviewer.get("/api/runs").status_code == 401
    assert reviewer.post("/api/auth/login", json={"username": "member-reviewer-test", "password": "ReviewerPass-2026!"}).status_code == 401

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM auth_sessions")
        connection.execute("DELETE FROM users")
    setup_client = TestClient(main.app)
    setup = setup_client.post("/api/auth/bootstrap", json={"workspace_name": "安全测试企业", "username": "owner-auth-test", "password": "StrongPass-2026!"})
    assert setup.status_code == 200
    assert setup.json()["role"] == "OWNER"
    anonymous = TestClient(main.app)
    assert anonymous.get("/api/runs").status_code == 401
    login = anonymous.post("/api/auth/login", json={"username": "owner-auth-test", "password": "StrongPass-2026!"})
    assert login.status_code == 200
    assert anonymous.get("/api/runs").status_code == 200
    assert anonymous.post("/api/auth/logout").status_code == 200
    assert anonymous.get("/api/runs").status_code == 401
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("DELETE FROM auth_sessions")
        connection.execute("DELETE FROM users")
