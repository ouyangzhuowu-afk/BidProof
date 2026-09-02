import sqlite3

from fastapi.testclient import TestClient

from app import config, main
from app.security import password_hash
from app.services import scan_service
from app.db import cancel_scan_job, create_auth_session, create_scan_job, create_user, init_db, load_scan_job, start_scan_job, update_scan_job


def _pdf_bytes(text: str) -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    payload = document.tobytes()
    document.close()
    return payload


def test_run_source_files_are_downloadable_only_with_workspace_scope(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{
        "page": 1,
        "text": "资格要求",
        "has_text": True,
        "char_count": 4,
        "blocks": [],
    }])
    owner = {"X-Workspace-ID": "download-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    created = client.post(
        "/api/runs",
        headers=owner,
        files=[
            ("tender", ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")),
            ("evidence", ("proof.txt", "营业执照有效".encode("utf-8"), "text/plain")),
        ],
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    tender = client.get(f"/api/runs/{run_id}/files/TENDER-001", headers=owner)
    assert tender.status_code == 200
    assert tender.content.startswith(b"%PDF")
    assert "attachment" in tender.headers["content-disposition"]

    evidence = client.get(f"/api/runs/{run_id}/files/EVD-001", headers=owner)
    assert evidence.status_code == 200
    assert evidence.content == "营业执照有效".encode("utf-8")

    foreign = {**owner, "X-Workspace-ID": "other-ws"}
    assert client.get(f"/api/runs/{run_id}/files/TENDER-001", headers=foreign).status_code == 404
    assert client.get(f"/api/runs/{run_id}/files/../../outside", headers=owner).status_code in {404, 400}


def test_pending_scan_job_can_be_cancelled_and_is_not_recoverable():
    database = config.DB_PATH
    create_scan_job("cancel-me", "cancel-ws", None, "PENDING", {"tender_path": "pending.pdf"}, database)
    client = TestClient(main.app)
    owner = {"X-Workspace-ID": "cancel-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}

    response = client.post("/api/jobs/cancel-me/cancel", headers=owner)

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"
    assert load_scan_job("cancel-me", database)["status"] == "CANCELLED"


def test_cancelled_scan_job_cannot_be_started_again():
    database = config.DB_PATH
    create_scan_job("already-cancelled", "cancel-ws-2", None, "PENDING", {}, database)
    assert cancel_scan_job("already-cancelled", database)["status"] == "CANCELLED"

    assert start_scan_job("already-cancelled", database) is False
    update_scan_job("already-cancelled", "COMPLETED", progress_message="错误覆盖", path=database)
    assert load_scan_job("already-cancelled", database)["status"] == "CANCELLED"
    assert load_scan_job("already-cancelled", database)["progress_message"] == "已取消"


def test_password_change_revokes_existing_sessions():
    database = config.DB_PATH
    init_db(database)
    user = create_user("password-ws", "password-user", password_hash("old-password-123"), "OWNER", database)
    token_hash = "existing-session-hash"
    create_auth_session(token_hash, user["user_id"], "2999-01-01T00:00:00+00:00", database)

    client = TestClient(main.app)
    try:
        login = client.post("/api/auth/login", json={"username": "password-user", "password": "old-password-123"})
        assert login.status_code == 200

        changed = client.post("/api/auth/password", json={"current_password": "old-password-123", "new_password": "new-password-456"})
        assert changed.status_code == 200
        assert changed.json()["sessions_revoked"] is True
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT COUNT(*) FROM auth_sessions WHERE user_id = ?", (user["user_id"],)).fetchone()[0] == 0
    finally:
        with sqlite3.connect(database) as db:
            db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user["user_id"],))
            db.execute("DELETE FROM workspace_members WHERE user_id = ?", (user["user_id"],))
            db.execute("DELETE FROM users WHERE user_id = ?", (user["user_id"],))


def test_task_reviewer_is_independent_from_assignee_and_persisted(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    owner = {"X-Workspace-ID": "reviewer-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    created = client.post("/api/runs", headers=owner, files={"tender": ("reviewer.pdf", _pdf_bytes("资格要求"), "application/pdf")})
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    updated = client.patch(
        f"/api/runs/{run_id}/metadata",
        headers=owner,
        json={"assignee_id": "owner-a", "reviewer_id": "reviewer-b", "tags": ["重点"], "favorite": True},
    )

    assert updated.status_code == 200
    assert updated.json()["assignee_id"] == "owner-a"
    assert updated.json()["reviewer_id"] == "reviewer-b"
    assert client.get(f"/api/runs/{run_id}", headers=owner).json()["reviewer_id"] == "reviewer-b"


def test_run_list_supports_search_tag_favorite_and_reviewer_filters(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    owner = {"X-Workspace-ID": "filter-ws", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    other = {"X-Workspace-ID": "filter-other", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    first = client.post("/api/runs", headers=owner, files={"tender": ("Alpha资格.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    second = client.post("/api/runs", headers=owner, files={"tender": ("Beta普通.pdf", _pdf_bytes("资格要求"), "application/pdf")}).json()
    client.post("/api/runs", headers=other, files={"tender": ("Alpha泄漏.pdf", _pdf_bytes("资格要求"), "application/pdf")})
    client.patch(f"/api/runs/{first['run_id']}/metadata", headers=owner, json={"reviewer_id": "reviewer-1", "tags": ["重点", "本周"], "favorite": True})
    client.patch(f"/api/runs/{second['run_id']}/metadata", headers=owner, json={"reviewer_id": "reviewer-2", "tags": ["普通"], "favorite": False})

    response = client.get("/api/runs?search=Alpha&tag=重点&favorite=true&reviewer_id=reviewer-1&sort=filename", headers=owner)

    assert response.status_code == 200
    assert [item["run_id"] for item in response.json()] == [first["run_id"]]
