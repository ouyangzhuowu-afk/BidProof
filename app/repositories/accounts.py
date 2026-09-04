"""User accounts, sessions and one-shot auth action tokens."""

from __future__ import annotations

from typing import Any

from .. import db


def count() -> int:
    return db.count_users()


def create(workspace_id: str, username: str, password_hash: str, role: str) -> dict[str, Any]:
    return db.create_user(workspace_id, username, password_hash, role)


def by_username(username: str, workspace_id: str | None = None) -> dict[str, Any] | None:
    return db.load_user_by_username(username, workspace_id=workspace_id)


def by_id(user_id: str) -> dict[str, Any] | None:
    return db.load_user_by_id(user_id)


def set_password(user_id: str, password_hash: str, *, revoke_sessions: bool = True) -> bool:
    """Replace the stored hash. Revokes existing sessions unless upgrading an old hash."""
    return db.update_user_password(user_id, password_hash, revoke_sessions=revoke_sessions)


def session_user(token_digest: str, now: str) -> dict[str, Any] | None:
    return db.load_session_user(token_digest, now)


def create_session(token_digest: str, user_id: str, expires_at: str) -> None:
    db.create_auth_session(token_digest, user_id, expires_at)


def delete_session(token_digest: str) -> None:
    db.delete_auth_session(token_digest)


def list_sessions(user_id: str, now: str, current_digest: str) -> list[dict[str, Any]]:
    return db.list_auth_sessions(user_id, now, current_digest)


def delete_session_for_user(user_id: str, session_id: str) -> bool:
    return db.delete_auth_session_for_user(user_id, session_id)


def delete_other_sessions(user_id: str, keep_digest: str) -> int:
    return db.delete_other_auth_sessions(user_id, keep_digest)


def create_action_token(token_digest: str, workspace_id: str, purpose: str, expires_at: str, created_by: str, **fields: Any) -> None:
    db.create_auth_action_token(token_digest, workspace_id, purpose, expires_at, created_by, **fields)


def load_action_token(token_digest: str) -> dict[str, Any] | None:
    return db.load_auth_action_token(token_digest)


def consume_action_token(token_digest: str, used_at: str) -> bool:
    return db.consume_auth_action_token(token_digest, used_at)
