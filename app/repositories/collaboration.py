"""Comments, remediation items and accuracy feedback."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .. import db


def add_comment(workspace_id: str, run_id: str, user_id: str, body: str) -> dict[str, Any]:
    return db.add_comment(workspace_id, run_id, user_id, body)


def comments(workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    return db.list_comments(workspace_id, run_id)


def create_remediation(workspace_id: str, run_id: str, payload: dict) -> dict[str, Any]:
    return db.create_remediation(workspace_id, run_id, payload)


def remediations(workspace_id: str, run_id: str) -> list[dict[str, Any]]:
    return db.list_remediations(workspace_id, run_id)


def workspace_remediations(workspace_id: str) -> list[dict[str, Any]]:
    return db.list_workspace_remediations(workspace_id)


def update_remediation(remediation_id: str, changes: dict) -> dict[str, Any]:
    return db.update_remediation(remediation_id, changes)


def require_scoped_remediation(remediation_id: str, principal: dict[str, str]) -> dict[str, Any]:
    item = db.load_remediation(remediation_id)
    if item is None or item["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="整改项不存在")
    return item


def add_accuracy_feedback(workspace_id: str, run_id: str, user_id: str, payload: dict) -> dict[str, Any]:
    return db.add_accuracy_feedback(workspace_id, run_id, user_id, payload)


def accuracy_metrics(workspace_id: str, scopes: tuple[str, ...]) -> list[dict[str, Any]]:
    return db.accuracy_metrics(workspace_id, scopes=scopes)
