import sqlite3
import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import config, identity, main
from app.repositories import accounts
from app.security import password_hash
from app.config import DB_PATH
from app.db import create_user, ensure_workspace


def _remove_workspace(workspace_id: str) -> None:
    with sqlite3.connect(DB_PATH) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "auth_action_tokens" in tables:
            db.execute("DELETE FROM auth_action_tokens WHERE workspace_id = ?", (workspace_id,))
        user_ids = [row[0] for row in db.execute("SELECT user_id FROM users WHERE workspace_id = ?", (workspace_id,))]
        for user_id in user_ids:
            db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM users WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))


def _owner_client() -> tuple[TestClient, str, dict]:
    workspace_id = f"auth-{uuid.uuid4().hex}"
    username = f"owner-{uuid.uuid4().hex[:12]}"
    password = "OwnerPass-2026!"
    user = create_user(workspace_id, username, password_hash(password), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER", "认证测试企业")
    client = TestClient(main.app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client, workspace_id, user


def _token_from_path(path: str) -> str:
    return parse_qs(urlparse(path).query)["token"][0]


def test_production_bootstrap_is_locked_without_operations_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(config, "BOOTSTRAP_TOKEN", "", raising=False)
    monkeypatch.setattr(accounts, "count", lambda: 0)
    client = TestClient(main.app)

    status = client.get("/api/auth/status")
    bootstrap = client.post(
        "/api/auth/bootstrap",
        json={"workspace_name": "测试企业", "username": "owner", "password": "OwnerPass-2026!"},
    )

    assert status.status_code == 200
    assert status.json()["bootstrap_locked"] is True
    assert bootstrap.status_code == 503


def test_owner_invites_member_and_member_sets_password_once():
    owner, workspace_id, _ = _owner_client()
    invited_username = f"reviewer-{uuid.uuid4().hex[:12]}"
    try:
        issued = owner.post(
            "/api/auth/invitations",
            json={"username": invited_username, "role": "REVIEWER"},
        )
        assert issued.status_code == 201
        token = _token_from_path(issued.json()["activation_path"])

        inspected = TestClient(main.app).get("/api/auth/action", params={"token": token})
        assert inspected.status_code == 200
        assert inspected.json() == {
            "action": "INVITE",
            "username": invited_username,
            "role": "REVIEWER",
        }

        activated = TestClient(main.app).post(
            "/api/auth/activate",
            json={"token": token, "password": "ReviewerPass-2026!"},
        )
        assert activated.status_code == 200
        assert activated.json()["role"] == "REVIEWER"
        assert TestClient(main.app).post(
            "/api/auth/activate",
            json={"token": token, "password": "AnotherPass-2026!"},
        ).status_code == 410
        assert TestClient(main.app).post(
            "/api/auth/login",
            json={"username": invited_username, "password": "ReviewerPass-2026!"},
        ).status_code == 200
    finally:
        _remove_workspace(workspace_id)


def test_owner_issues_one_time_member_password_reset():
    owner, workspace_id, _ = _owner_client()
    username = f"member-{uuid.uuid4().hex[:12]}"
    member = create_user(workspace_id, username, password_hash("OldPassword-2026!"), "VIEWER")
    ensure_workspace(workspace_id, member["user_id"], "VIEWER")
    try:
        issued = owner.post(f"/api/members/{member['user_id']}/password-reset")
        assert issued.status_code == 201
        token = _token_from_path(issued.json()["reset_path"])

        reset = TestClient(main.app).post(
            "/api/auth/reset-password",
            json={"token": token, "password": "NewPassword-2026!"},
        )
        assert reset.status_code == 200
        assert TestClient(main.app).post(
            "/api/auth/login", json={"username": username, "password": "OldPassword-2026!"}
        ).status_code == 401
        assert TestClient(main.app).post(
            "/api/auth/login", json={"username": username, "password": "NewPassword-2026!"}
        ).status_code == 200
        assert TestClient(main.app).post(
            "/api/auth/reset-password",
            json={"token": token, "password": "ThirdPassword-2026!"},
        ).status_code == 410
    finally:
        _remove_workspace(workspace_id)


def test_repeated_login_failures_are_rate_limited(monkeypatch: pytest.MonkeyPatch):
    workspace_id = f"rate-{uuid.uuid4().hex}"
    username = f"limited-{uuid.uuid4().hex[:12]}"
    user = create_user(workspace_id, username, password_hash("CorrectPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER", "限速测试企业")
    monkeypatch.setattr(identity, "LOGIN_ATTEMPT_LIMIT", 3, raising=False)
    client = TestClient(main.app)
    try:
        assert client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-1"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-2"}).status_code == 401
        limited = client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-3"})
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) > 0
        assert client.post(
            "/api/auth/login", json={"username": username, "password": "CorrectPass-2026!"}
        ).status_code == 429
    finally:
        _remove_workspace(workspace_id)


def test_trial_join_creates_reviewer_when_code_configured(monkeypatch: pytest.MonkeyPatch):
    workspace_id = f"trial-{uuid.uuid4().hex}"
    owner_name = f"owner-{uuid.uuid4().hex[:12]}"
    owner = create_user(workspace_id, owner_name, password_hash("OwnerPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, owner["user_id"], "OWNER", "试用空间")
    monkeypatch.setattr(config, "TRIAL_JOIN_CODE", "TeamTrial-2026", raising=False)
    client = TestClient(main.app)
    joiner = f"joiner-{uuid.uuid4().hex[:12]}"
    try:
        status = client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json()["trial_join_enabled"] is True

        denied = client.post(
            "/api/auth/trial-join",
            json={"username": joiner, "password": "JoinerPass-2026!", "join_code": "wrong-code"},
        )
        assert denied.status_code == 403

        joined = client.post(
            "/api/auth/trial-join",
            json={"username": joiner, "password": "JoinerPass-2026!", "join_code": "TeamTrial-2026"},
        )
        assert joined.status_code == 201
        assert joined.json()["role"] == "REVIEWER"
        assert client.post(
            "/api/auth/login",
            json={"username": joiner, "password": "JoinerPass-2026!"},
        ).status_code == 200
    finally:
        _remove_workspace(workspace_id)


def test_trial_join_disabled_without_code(monkeypatch: pytest.MonkeyPatch):
    workspace_id = f"closed-{uuid.uuid4().hex}"
    owner = create_user(workspace_id, f"owner-{uuid.uuid4().hex[:12]}", password_hash("OwnerPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, owner["user_id"], "OWNER", "关闭试用")
    monkeypatch.setattr(config, "TRIAL_JOIN_CODE", "", raising=False)
    client = TestClient(main.app)
    try:
        assert client.get("/api/auth/status").json()["trial_join_enabled"] is False
        assert client.post(
            "/api/auth/trial-join",
            json={"username": "anyone123", "password": "AnyonePass-2026!", "join_code": "anything"},
        ).status_code == 403
    finally:
        _remove_workspace(workspace_id)
