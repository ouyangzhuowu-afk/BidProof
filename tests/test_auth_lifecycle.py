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


def test_personal_register_creates_isolated_owner_workspace(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True, raising=False)
    owner, enterprise_id, _ = _owner_client()
    client = TestClient(main.app)
    username = f"solo-{uuid.uuid4().hex[:12]}"
    personal_id = None
    try:
        status = client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json()["personal_signup_enabled"] is True

        created = client.post(
            "/api/auth/register",
            json={"username": username, "password": "PersonalPass-2026!"},
        )
        assert created.status_code == 201
        body = created.json()
        personal_id = body["workspace_id"]
        assert body["role"] == "OWNER"
        assert body["username"] == username
        assert personal_id != enterprise_id

        members = client.get("/api/members")
        assert members.status_code == 200
        assert [item["username"] for item in members.json()["members"]] == [username]
        enterprise_names = [item["username"] for item in owner.get("/api/members").json()["members"]]
        assert username not in enterprise_names

        assert client.post("/api/auth/logout").status_code == 200
        assert client.post(
            "/api/auth/login",
            json={"username": username, "password": "PersonalPass-2026!"},
        ).status_code == 200
    finally:
        _remove_workspace(enterprise_id)
        if personal_id:
            _remove_workspace(personal_id)


def test_two_personal_accounts_cannot_see_each_other(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True, raising=False)
    first_client = TestClient(main.app)
    second_client = TestClient(main.app)
    user_a = f"alpha-{uuid.uuid4().hex[:12]}"
    user_b = f"beta-{uuid.uuid4().hex[:12]}"
    workspace_ids: list[str] = []
    try:
        first = first_client.post(
            "/api/auth/register",
            json={"username": user_a, "password": "PersonalPass-2026!"},
        )
        second = second_client.post(
            "/api/auth/register",
            json={"username": user_b, "password": "PersonalPass-2026!", "display_name": "独立顾问"},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        workspace_ids = [first.json()["workspace_id"], second.json()["workspace_id"]]
        assert workspace_ids[0] != workspace_ids[1]
        assert [item["username"] for item in first_client.get("/api/members").json()["members"]] == [user_a]
        assert [item["username"] for item in second_client.get("/api/members").json()["members"]] == [user_b]
    finally:
        for workspace_id in workspace_ids:
            _remove_workspace(workspace_id)


def test_personal_register_rejects_duplicate_username(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True, raising=False)
    client = TestClient(main.app)
    username = f"dup-{uuid.uuid4().hex[:12]}"
    workspace_id = None
    try:
        first = client.post(
            "/api/auth/register",
            json={"username": username, "password": "PersonalPass-2026!"},
        )
        assert first.status_code == 201
        workspace_id = first.json()["workspace_id"]
        second = TestClient(main.app).post(
            "/api/auth/register",
            json={"username": username, "password": "AnotherPass-2026!"},
        )
        assert second.status_code == 409
    finally:
        if workspace_id:
            _remove_workspace(workspace_id)


def test_personal_register_can_be_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", False, raising=False)
    client = TestClient(main.app)
    assert client.get("/api/auth/status").json()["personal_signup_enabled"] is False
    denied = client.post(
        "/api/auth/register",
        json={"username": "anyone123", "password": "AnyonePass-2026!"},
    )
    assert denied.status_code == 403


def test_personal_register_works_when_production_bootstrap_is_locked(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production", raising=False)
    monkeypatch.setattr(config, "BOOTSTRAP_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True, raising=False)
    assert identity.bootstrap_locked() is True
    client = TestClient(main.app)
    username = f"locked-{uuid.uuid4().hex[:12]}"
    workspace_id = None
    try:
        created = client.post(
            "/api/auth/register",
            json={"username": username, "password": "PersonalPass-2026!"},
        )
        assert created.status_code == 201
        workspace_id = created.json()["workspace_id"]
        assert created.json()["role"] == "OWNER"
    finally:
        if workspace_id:
            _remove_workspace(workspace_id)
