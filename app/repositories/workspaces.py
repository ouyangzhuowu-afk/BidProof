"""Workspaces, membership and per-workspace settings."""

from __future__ import annotations

from typing import Any

from .. import db


def ensure(workspace_id: str, user_id: str, role: str, name: str | None = None) -> None:
    db.ensure_workspace(workspace_id, user_id, role, name)


def primary_id() -> str | None:
    return db.primary_workspace_id()


def members(workspace_id: str) -> list[dict[str, Any]]:
    return db.list_workspace_members(workspace_id)


def update_member(workspace_id: str, user_id: str, role: str | None, active: bool | None) -> dict[str, Any]:
    return db.update_workspace_member(workspace_id, user_id, role, active)


def settings(workspace_id: str) -> dict[str, Any]:
    return db.get_workspace_settings(workspace_id)


def update_settings(workspace_id: str, retention_days: int) -> dict[str, Any]:
    return db.update_workspace_settings(workspace_id, retention_days)


def usage(workspace_id: str) -> dict[str, Any]:
    return db.workspace_usage(workspace_id)
