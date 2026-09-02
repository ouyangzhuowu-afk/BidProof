"""Workspace member administration."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..identity import ADMIN_ROLES, principal_of, require_role
from ..repositories import workspaces
from ..schemas import MemberCreateRequest, MemberUpdateRequest
from ..services import auth_service


router = APIRouter(prefix="/api/members", tags=["members"])


@router.get("")
def get_members(request: Request) -> dict:
    principal = principal_of(request)
    return {"workspace_id": principal["workspace_id"], "members": workspaces.members(principal["workspace_id"])}


@router.post("", status_code=201)
def create_member(request: Request, payload: MemberCreateRequest) -> dict:
    principal = principal_of(request)
    require_role(principal, ADMIN_ROLES)
    return auth_service.create_member(principal, payload)


@router.patch("/{user_id}")
def update_member(request: Request, user_id: str, payload: MemberUpdateRequest) -> dict:
    principal = principal_of(request)
    require_role(principal, ADMIN_ROLES)
    return auth_service.update_member(principal, user_id, payload)


@router.post("/{user_id}/password-reset", status_code=201)
def issue_member_password_reset(request: Request, user_id: str) -> dict:
    principal = principal_of(request)
    require_role(principal, ADMIN_ROLES)
    return auth_service.issue_password_reset(principal, user_id)
