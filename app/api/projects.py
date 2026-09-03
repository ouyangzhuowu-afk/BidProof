"""Projects that group runs inside a workspace."""

from __future__ import annotations

import sqlalchemy.exc
import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from ..authz import Permission, require
from ..identity import principal_of
from ..repositories import audit, projects
from ..schemas import ProjectCreateRequest, ProjectUpdateRequest


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def get_projects(request: Request, include_archived: bool = Query(default=False)) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    projects.ensure_default(principal["workspace_id"])
    return {
        "workspace_id": principal["workspace_id"],
        "projects": projects.list_for_workspace(principal["workspace_id"], include_archived),
    }


@router.post("", status_code=201)
def add_project(request: Request, payload: ProjectCreateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.PROJECT_MANAGE)
    code = (payload.code or f"PRJ-{uuid.uuid4().hex[:8]}").upper()
    try:
        project = projects.create(principal["workspace_id"], payload.name.strip(), code)
    except sqlalchemy.exc.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="项目编码已存在") from exc
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "PROJECT_CREATED",
        None,
        {"project_id": project["project_id"], "code": project["code"]},
    )
    return project


@router.patch("/{project_id}")
def patch_project(request: Request, project_id: str, payload: ProjectUpdateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.PROJECT_MANAGE)
    projects.require_scoped(project_id, principal)
    updated = projects.update(project_id, payload.name.strip() if payload.name else None, payload.archived)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "PROJECT_UPDATED",
        None,
        {"project_id": project_id, "archived": bool(updated["archived_at"])},
    )
    return updated
