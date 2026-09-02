"""API tokens, MFA records, directory bindings and one-shot login flows."""

from __future__ import annotations

from typing import Any

from .. import db


def create_token(**fields: Any) -> dict[str, Any]:
    return db.create_api_token(**fields)


def list_tokens(workspace_id: str) -> list[dict[str, Any]]:
    return db.list_api_tokens(workspace_id)


def load_token_by_hash(token_digest: str, now: str) -> dict[str, Any] | None:
    return db.load_api_token_by_hash(token_digest, now)


def touch_token(token_id: str) -> None:
    db.touch_api_token(token_id)


def revoke_token(workspace_id: str, token_id: str) -> dict[str, Any] | None:
    return db.revoke_api_token(workspace_id, token_id)


def load_mfa(user_id: str) -> dict[str, Any] | None:
    return db.load_user_mfa(user_id)


def save_mfa(user_id: str, secret: str, recovery_codes: list[str]) -> dict[str, Any]:
    return db.upsert_user_mfa(user_id, secret, recovery_codes)


def confirm_mfa(user_id: str, last_counter: int) -> None:
    db.confirm_user_mfa(user_id, last_counter)


def update_mfa(user_id: str, last_counter: int, recovery_codes: list[str] | None = None) -> None:
    db.update_user_mfa_counter(user_id, last_counter, recovery_codes)


def delete_mfa(user_id: str) -> None:
    db.delete_user_mfa(user_id)


def load_binding(provider: str, issuer: str, subject: str) -> dict[str, Any] | None:
    return db.load_identity_binding(provider, issuer, subject)


def remember_binding(user_id: str, provider: str, issuer: str, subject: str) -> dict[str, Any]:
    return db.upsert_identity_binding(user_id, provider, issuer, subject)


def start_flow(state: str, provider: str, **fields: Any) -> dict[str, Any]:
    return db.create_login_flow(state, provider, **fields)


def load_flow(state: str, provider: str, now: str) -> dict[str, Any] | None:
    return db.load_login_flow(state, provider, now)


def consume_flow(state: str, provider: str, now: str) -> dict[str, Any] | None:
    return db.consume_login_flow(state, provider, now)
