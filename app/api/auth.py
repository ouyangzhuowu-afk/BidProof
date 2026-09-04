"""Authentication and account lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from ..authz import Permission, require
from ..identity import principal_of
from ..schemas import (
    ApiTokenCreateRequest,
    AuthActionCompleteRequest,
    AuthBootstrapRequest,
    InvitationCreateRequest,
    LoginRequest,
    MfaCodeRequest,
    PasswordChangeRequest,
    PersonalRegisterRequest,
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


@router.post("/register", status_code=201)
def register_personal(request: Request, response: Response, payload: PersonalRegisterRequest) -> dict:
    return auth_service.register_personal(request, response, payload)


@router.post("/trial-join", status_code=201)
def trial_join(request: Request, response: Response, payload: TrialJoinRequest) -> dict:
    return auth_service.trial_join(request, response, payload)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    return auth_service.logout(request, response)


@router.post("/password")
def change_password(request: Request, response: Response, payload: PasswordChangeRequest) -> dict:
    return auth_service.change_password(request, response, principal_of(request), payload)


@router.post("/invitations", status_code=201)
def create_invitation(request: Request, payload: InvitationCreateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.MEMBER_MANAGE)
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


@router.get("/oidc/start")
def oidc_start(request: Request) -> RedirectResponse:
    return RedirectResponse(auth_service.start_oidc(request), status_code=302)


@router.get("/oidc/callback")
def oidc_callback(
    request: Request,
    code: str = Query(default="", max_length=2000),
    state: str = Query(default="", max_length=200),
) -> RedirectResponse:
    redirect = RedirectResponse("/app", status_code=303)
    result = auth_service.complete_oidc(request, redirect, code, state)
    if result.get("mfa_required"):
        return RedirectResponse(f"/app?mfa_token={result['mfa_token']}", status_code=303)
    return redirect


@router.post("/mfa/enroll")
def enroll_mfa(request: Request) -> dict:
    return auth_service.enroll_mfa(principal_of(request))


@router.post("/mfa/confirm")
def confirm_mfa(request: Request, payload: MfaCodeRequest) -> dict:
    return auth_service.confirm_mfa(principal_of(request), payload)


@router.post("/mfa/verify")
def verify_mfa(request: Request, response: Response, payload: MfaCodeRequest) -> dict:
    return auth_service.verify_mfa_login(request, response, payload)


@router.post("/mfa/disable")
def disable_mfa(request: Request, payload: MfaCodeRequest) -> dict:
    return auth_service.disable_mfa(principal_of(request), payload)


@router.get("/tokens")
def list_tokens(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.TOKEN_MANAGE)
    return auth_service.list_tokens(principal)


@router.post("/tokens", status_code=201)
def create_token(request: Request, payload: ApiTokenCreateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.TOKEN_MANAGE)
    return auth_service.create_token(principal, payload)


@router.delete("/tokens/{token_id}")
def revoke_token(request: Request, token_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.TOKEN_MANAGE)
    return auth_service.revoke_token(principal, token_id)


@router.get("/sessions")
def list_sessions(request: Request) -> dict:
    return auth_service.list_sessions(request)


@router.delete("/sessions/{session_id}")
def revoke_session(request: Request, session_id: str) -> dict:
    return auth_service.revoke_session(request, session_id)


@router.post("/sessions/revoke-others")
def revoke_other_sessions(request: Request) -> dict:
    return auth_service.revoke_other_sessions(request)
