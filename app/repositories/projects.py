"""Projects that group runs inside a workspace."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .. import db


def create(workspace_id: str, name: str, code: str) -> dict[str, Any]:
    return db.create_project(workspace_id, name, code)


def ensure_default(workspace_id: str) -> dict[str, Any]:
    return db.ensure_default_project(workspace_id)


def load(project_id: str) -> dict[str, Any] | None:
    return db.load_project(project_id)


def list_for_workspace(workspace_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
    return db.list_projects(workspace_id, include_archived)


def update(project_id: str, name: str | None, archived: bool | None) -> dict[str, Any]:
    return db.update_project(project_id, name, archived)


def require_scoped(project_id: str, principal: dict[str, str]) -> dict[str, Any]:
    project = db.load_project(project_id)
    if project is None or project["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project
