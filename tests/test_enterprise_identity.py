"""P3 identity: RBAC, CSRF, MFA replay, shared rate limits, OIDC claims and LDAP DNs."""

from __future__ import annotations

import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import csrf, directory, identity, main, oidc, totp
from app.authz import Permission, has_permission
from app.config import DB_PATH
from app.db import create_user, ensure_workspace, list_audit_events, record_audit_event
from app.security import password_hash, token_hash


def _remove_workspace(workspace_id: str) -> None:
    with sqlite3.connect(DB_PATH) as db:
        user_ids = [row[0] for row in db.execute("SELECT user_id FROM users WHERE workspace_id = ?", (workspace_id,))]
        for user_id in user_ids:
            db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM user_mfa WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM api_tokens WHERE user_id = ?", (user_id,))
        db.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM users WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM workspaces WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM audit_events WHERE workspace_id = ?", (workspace_id,))
        db.execute("DELETE FROM audit_events WHERE workspace_id = ?", ("-",))


def test_viewer_cannot_export_audit_csv_or_bulk_reports():
    client = TestClient(main.app)
    viewer = {"X-Workspace-ID": "rbac-view", "X-User-ID": "viewer", "X-User-Role": "VIEWER"}
    owner = {"X-Workspace-ID": "rbac-view", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    record_audit_event("rbac-view", "owner", "RBAC_EVENT")

    assert client.get("/api/audit/export.csv", headers=viewer).status_code == 403
    assert client.post(
        "/api/runs/bulk/report.zip",
        headers=viewer,
        json={"run_ids": ["missing"], "format": "pdf"},
    ).status_code == 403
    assert client.get("/api/audit/export.csv", headers=owner).status_code == 200


def test_viewer_permissions_exclude_privileged_actions():
    principal = {"workspace_id": "w", "user_id": "v", "role": "VIEWER"}

    assert has_permission(principal, Permission.RUN_READ)
    assert not has_permission(principal, Permission.REPORT_EXPORT)
    assert not has_permission(principal, Permission.AUDIT_EXPORT)
    assert not has_permission(principal, Permission.REPORT_BULK_EXPORT)
    assert not has_permission(principal, Permission.RUN_DELETE)


def test_csrf_rejects_cookie_authenticated_writes_without_the_header(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BIDPROOF_ENFORCE_CSRF", "1")
    workspace_id = f"csrf-{uuid.uuid4().hex}"
    username = f"csrf-{uuid.uuid4().hex[:12]}"
    user = create_user(workspace_id, username, password_hash("OwnerPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER", "CSRF")
    client = TestClient(main.app)
    try:
        assert client.post("/api/auth/login", json={"username": username, "password": "OwnerPass-2026!"}).status_code == 200
        assert client.cookies.get(csrf.COOKIE_NAME)

        blocked = client.post(
            "/api/auth/password",
            json={"current_password": "OwnerPass-2026!", "new_password": "OwnerPass-2026!!"},
        )
        assert blocked.status_code == 403
        assert "CSRF" in blocked.json()["detail"]

        allowed = client.post(
            "/api/auth/password",
            headers={csrf.HEADER_NAME: client.cookies.get(csrf.COOKIE_NAME)},
            json={"current_password": "OwnerPass-2026!", "new_password": "OwnerPass-2027!!"},
        )
        assert allowed.status_code == 200
    finally:
        _remove_workspace(workspace_id)


def test_totp_rejects_a_replayed_counter():
    secret = totp.new_secret()
    moment = 1_700_000_000.0
    code = totp.code_for_counter(secret, totp.counter_at(moment))
    used = totp.verify(secret, code, last_counter=0, moment=moment)

    assert used is not None
    assert totp.verify(secret, code, last_counter=used, moment=moment) is None


def test_login_rate_limit_is_shared_through_the_database(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(identity, "LOGIN_ATTEMPT_LIMIT", 3, raising=False)
    workspace_id = f"limit-{uuid.uuid4().hex}"
    username = f"shared-{uuid.uuid4().hex[:12]}"
    user = create_user(workspace_id, username, password_hash("CorrectPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER")
    client = TestClient(main.app)
    try:
        assert client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-1"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-2"}).status_code == 401
        limited = client.post("/api/auth/login", json={"username": username, "password": "wrong-pass-3"})
        assert limited.status_code == 429
        other = TestClient(main.app)
        assert other.post("/api/auth/login", json={"username": username, "password": "CorrectPass-2026!"}).status_code == 429
    finally:
        _remove_workspace(workspace_id)


def test_failed_login_is_audited_with_request_context():
    client = TestClient(main.app)
    response = client.post(
        "/api/auth/login",
        headers={"User-Agent": "identity-test", "X-Request-ID": "req-failed-login"},
        json={"username": "nobody-here", "password": "definitely-wrong"},
    )
    assert response.status_code == 401
    assert response.headers.get("X-Request-ID") == "req-failed-login"

    events = [event for event in list_audit_events("-") if event["event_type"] == "AUTH_LOGIN_FAILED"]
    assert events
    assert events[0]["outcome"] == "FAILURE"
    assert events[0]["request_id"] == "req-failed-login"
    assert events[0]["user_agent"] == "identity-test"
    _remove_workspace("-")


def test_oidc_rejects_forged_issuer_audience_and_nonce():
    settings = oidc.OIDCSettings(issuer="https://idp.example", client_id="bidproof", client_secret="secret")
    now = time.time()
    valid = {"iss": "https://idp.example", "aud": "bidproof", "exp": now + 120, "iat": now, "sub": "user-1", "nonce": "abc"}

    oidc.validate_claims(valid, settings, nonce="abc", now=now)
    with pytest.raises(oidc.OIDCError, match="issuer"):
        oidc.validate_claims({**valid, "iss": "https://evil.example"}, settings, nonce="abc", now=now)
    with pytest.raises(oidc.OIDCError, match="audience"):
        oidc.validate_claims({**valid, "aud": "other-app"}, settings, nonce="abc", now=now)
    with pytest.raises(oidc.OIDCError, match="expired"):
        oidc.validate_claims({**valid, "exp": now - 1000}, settings, nonce="abc", now=now)
    with pytest.raises(oidc.OIDCError, match="nonce"):
        oidc.validate_claims(valid, settings, nonce="other", now=now)


def test_ldap_bind_dn_rejects_filter_metacharacters():
    settings = directory.DirectorySettings(
        server_uri="ldaps://directory.example",
        user_dn_template="uid={username},ou=people,dc=example,dc=com",
    )

    assert directory.bind_dn_for(settings, "alice") == "uid=alice,ou=people,dc=example,dc=com"
    with pytest.raises(directory.DirectoryError):
        directory.bind_dn_for(settings, "alice)(uid=*")
    with pytest.raises(directory.DirectoryError):
        directory.bind_dn_for(settings, "alice,cn=admin")
    assert directory.ldap_filter_escape("cn=Alice (User)") == "cn=Alice \\28User\\29"


def test_api_token_authenticates_and_can_be_scoped():
    workspace_id = f"token-{uuid.uuid4().hex}"
    user = create_user(workspace_id, f"token-{uuid.uuid4().hex[:8]}", password_hash("OwnerPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER")
    client = TestClient(main.app)
    owner = {"X-Workspace-ID": workspace_id, "X-User-ID": user["user_id"], "X-User-Role": "OWNER"}
    try:
        created = client.post("/api/auth/tokens", headers=owner, json={"name": "ci", "permissions": ["run:read"]})
        assert created.status_code == 201
        token = created.json()["token"]
        assert token.startswith("bp_")
        assert "token_hash" not in created.json()

        listing = client.get("/api/runs", headers={"Authorization": f"Bearer {token}"})
        assert listing.status_code == 200
        forbidden = client.get("/api/audit/export.csv", headers={"Authorization": f"Bearer {token}"})
        assert forbidden.status_code == 403
        revoked = client.delete(f"/api/auth/tokens/{created.json()['token_id']}", headers=owner)
        assert revoked.status_code == 200
        assert client.get("/api/runs", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    finally:
        _remove_workspace(workspace_id)


def test_mfa_login_challenge_then_accepts_a_fresh_code():
    workspace_id = f"mfa-{uuid.uuid4().hex}"
    username = f"mfa-{uuid.uuid4().hex[:12]}"
    user = create_user(workspace_id, username, password_hash("OwnerPass-2026!"), "OWNER")
    ensure_workspace(workspace_id, user["user_id"], "OWNER")
    secret = totp.new_secret()
    from app.repositories import identity as identity_store

    identity_store.save_mfa(user["user_id"], secret, [token_hash("aaaa-bbbb-cccc")])
    identity_store.confirm_mfa(user["user_id"], 1)
    client = TestClient(main.app)
    try:
        first = client.post("/api/auth/login", json={"username": username, "password": "OwnerPass-2026!"})
        assert first.status_code == 200
        assert first.json()["mfa_required"] is True
        assert client.cookies.get(identity.SESSION_COOKIE) is None

        code = totp.code_for_counter(secret, totp.counter_at())
        verified = client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": first.json()["mfa_token"], "code": code},
        )
        assert verified.status_code == 200
        assert verified.json()["username"] == username
        replay = client.post(
            "/api/auth/mfa/verify",
            json={"mfa_token": first.json()["mfa_token"], "code": code},
        )
        assert replay.status_code == 401
    finally:
        _remove_workspace(workspace_id)
