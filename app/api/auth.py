"""Authentication and account lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from ..identity import ADMIN_ROLES, principal_of, require_role
from ..schemas import (
    AuthActionCompleteRequest,
    AuthBootstrapRequest,
    InvitationCreateRequest,
    LoginRequest,
    PasswordChangeRequest,
    TrialJoinRequest,
)
from ..services import auth_service


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(request: Request) -> dict:
    return auth_service.status(request)


@router.post("/bootstrap")
def bootstrap_auth(request: Request, response: Response, payload: AuthBootstrapRequest) -> dict:
    return auth_service.bootstrap(request, response, payload)


@router.post("/login")
def login(request: Request, response: Response, payload: LoginRequest) -> dict:
    return auth_service.login(request, response, payload)


@router.post("/trial-join", status_code=201)
def trial_join(request: Request, response: Response, payload: TrialJoinRequest) -> dict:
    return auth_service.trial_join(request, response, payload)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    return auth_service.logout(request, response)


@router.post("/password")
def change_password(request: Request, payload: PasswordChangeRequest) -> dict:
    return auth_service.change_password(principal_of(request), payload)


@router.post("/invitations", status_code=201)
def create_invitation(request: Request, payload: InvitationCreateRequest) -> dict:
    principal = principal_of(request)
    require_role(principal, ADMIN_ROLES)
    return auth_service.create_invitation(principal, payload)


@router.get("/action")
def inspect_auth_action(token: str = Query(min_length=20, max_length=500)) -> dict:
    return auth_service.inspect_action(token)


@router.post("/activate")
def activate_invitation(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    return auth_service.activate_invitation(request, response, payload)


@router.post("/reset-password")
def complete_password_reset(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    return auth_service.complete_password_reset(request, response, payload)
