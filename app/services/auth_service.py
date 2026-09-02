"""Account lifecycle: bootstrap, login, trial join, invitations, resets and members."""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from .. import config, identity
from ..repositories import accounts, audit, workspaces
from ..schemas import (
    MIN_PASSWORD_LENGTH,
    AuthActionCompleteRequest,
    AuthBootstrapRequest,
    InvitationCreateRequest,
    LoginRequest,
    MemberCreateRequest,
    MemberUpdateRequest,
    PasswordChangeRequest,
    TrialJoinRequest,
)
from ..security import new_action_token, password_hash, token_hash, verify_password
from ..state import utc_now


INVITATION_VALID_HOURS = 72
RESET_VALID_HOURS = 1


def _account_response(user: dict, workspace_id: str) -> dict:
    return {
        "user_id": user["user_id"],
        "workspace_id": workspace_id,
        "username": user["username"],
        "role": user["role"],
    }


def status(request: Request) -> dict:
    users = accounts.count()
    trial_join_enabled = bool(config.TRIAL_JOIN_CODE) and users > 0
    if users == 0:
        return {
            "setup_required": True,
            "authenticated": False,
            "bootstrap_token_required": config.ENVIRONMENT == "production",
            "bootstrap_locked": identity.bootstrap_locked(),
            "trial_join_enabled": False,
        }
    token = identity.session_token(request)
    user = accounts.session_user(token_hash(token), utc_now()) if token else None
    return {
        "setup_required": False,
        "authenticated": bool(user),
        "trial_join_enabled": trial_join_enabled,
        "user": _account_response(user, user["workspace_id"]) if user else None,
    }


def bootstrap(request: Request, response: Response, payload: AuthBootstrapRequest) -> dict:
    if accounts.count() > 0:
        raise HTTPException(status_code=409, detail="管理员已经初始化")
    if identity.bootstrap_locked():
        raise HTTPException(status_code=503, detail="生产环境尚未配置初始化令牌，请联系运维人员")
    if config.ENVIRONMENT == "production" and not secrets.compare_digest(payload.bootstrap_token or "", config.BOOTSTRAP_TOKEN):
        raise HTTPException(status_code=403, detail="初始化令牌无效")
    workspace_id = uuid.uuid4().hex
    user = accounts.create(workspace_id, payload.username.strip(), password_hash(payload.password), "OWNER")
    workspaces.ensure(workspace_id, user["user_id"], "OWNER", payload.workspace_name.strip())
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(workspace_id, user["user_id"], "AUTH_BOOTSTRAPPED", None, {"username": user["username"]})
    return _account_response(user, workspace_id)


def login(request: Request, response: Response, payload: LoginRequest) -> dict:
    now = identity.monotonic_now()
    attempt_key = identity.login_attempt_key(request, payload.username)
    identity.enforce_login_rate_limit(attempt_key, now)
    user = accounts.by_username(payload.username.strip())
    # An under-length password cannot match a hash stored under the policy, so short-circuit
    # before the PBKDF2 work while still answering with the same 401 as any bad credential.
    meets_policy = len(payload.password) >= MIN_PASSWORD_LENGTH
    if not user or not bool(user.get("active", 1)) or not meets_policy or not verify_password(payload.password, user["password_hash"]):
        identity.record_failed_login(attempt_key, now)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    identity.clear_login_attempts(attempt_key)
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(user["workspace_id"], user["user_id"], "AUTH_LOGIN")
    return _account_response(user, user["workspace_id"])


def trial_join(request: Request, response: Response, payload: TrialJoinRequest) -> dict:
    """Self-serve join for team pilots when BIDPROOF_TRIAL_JOIN_CODE is configured."""
    if not config.TRIAL_JOIN_CODE:
        raise HTTPException(status_code=403, detail="试用加入未开放")
    now = identity.monotonic_now()
    attempt_key = identity.login_attempt_key(request, f"trial:{payload.username}")
    identity.enforce_login_rate_limit(attempt_key, now)
    submitted = payload.join_code.strip()
    if len(submitted) != len(config.TRIAL_JOIN_CODE) or not secrets.compare_digest(submitted, config.TRIAL_JOIN_CODE):
        identity.record_failed_login(attempt_key, now)
        raise HTTPException(status_code=403, detail="试用加入码无效或未开放")
    workspace_id = workspaces.primary_id()
    if not workspace_id:
        raise HTTPException(status_code=503, detail="企业空间尚未初始化，请先完成管理员开通")
    username = payload.username.strip()
    if accounts.by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录")
    try:
        user = accounts.create(workspace_id, username, password_hash(payload.password), "REVIEWER")
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录") from exc
    workspaces.ensure(workspace_id, user["user_id"], "REVIEWER")
    identity.clear_login_attempts(attempt_key)
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(workspace_id, user["user_id"], "AUTH_TRIAL_JOINED", None, {"username": user["username"], "role": "REVIEWER"})
    return _account_response(user, workspace_id)


def logout(request: Request, response: Response) -> dict:
    token = identity.session_token(request)
    if token:
        accounts.delete_session(token_hash(token))
    identity.clear_session(response)
    return {"logged_out": True}


def change_password(principal: dict[str, str], payload: PasswordChangeRequest) -> dict:
    user = accounts.by_id(principal["user_id"])
    if user is None or user.get("workspace_id") != principal["workspace_id"] or not bool(user.get("active", 1)):
        raise HTTPException(status_code=401, detail="当前账号无效")
    if not verify_password(payload.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="当前密码错误")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    if not accounts.set_password(user["user_id"], password_hash(payload.new_password)):
        raise HTTPException(status_code=404, detail="账号不存在")
    audit.record(principal["workspace_id"], principal["user_id"], "AUTH_PASSWORD_CHANGED")
    return {"changed": True, "sessions_revoked": True}


def create_invitation(principal: dict[str, str], payload: InvitationCreateRequest) -> dict:
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以邀请管理员")
    username = payload.username.strip()
    if accounts.by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    raw_token = new_action_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=INVITATION_VALID_HOURS)).isoformat()
    accounts.create_action_token(
        token_hash(raw_token),
        principal["workspace_id"],
        "INVITE",
        expires_at,
        principal["user_id"],
        username=username,
        role=payload.role,
    )
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_INVITATION_CREATED",
        None,
        {"username": username, "role": payload.role, "expires_at": expires_at},
    )
    return {
        "username": username,
        "role": payload.role,
        "expires_at": expires_at,
        "activation_path": f"/app?auth_action=activate&token={raw_token}",
    }


def inspect_action(token: str) -> dict:
    action = identity.active_auth_action(token)
    username = action.get("username")
    if action["purpose"] == "RESET":
        user = accounts.by_id(action.get("user_id") or "")
        username = user["username"] if user else None
    if not username:
        raise HTTPException(status_code=410, detail="链接关联账号不存在")
    return {"action": action["purpose"], "username": username, "role": action.get("role")}


def activate_invitation(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    action = identity.active_auth_action(payload.token, "INVITE")
    if accounts.by_username(action["username"]):
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录")
    if not accounts.consume_action_token(token_hash(payload.token), utc_now()):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    try:
        user = accounts.create(action["workspace_id"], action["username"], password_hash(payload.password), action["role"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在，请直接登录") from exc
    workspaces.ensure(action["workspace_id"], user["user_id"], action["role"])
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(action["workspace_id"], user["user_id"], "MEMBER_INVITATION_ACCEPTED", None, {"role": action["role"]})
    return _account_response(user, action["workspace_id"])


def issue_password_reset(principal: dict[str, str], user_id: str) -> dict:
    member = accounts.by_id(user_id)
    if member is None or member["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member["role"] == "OWNER" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以重置所有者密码")
    raw_token = new_action_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=RESET_VALID_HOURS)).isoformat()
    accounts.create_action_token(
        token_hash(raw_token),
        principal["workspace_id"],
        "RESET",
        expires_at,
        principal["user_id"],
        user_id=user_id,
        role=member["role"],
    )
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_PASSWORD_RESET_CREATED",
        None,
        {"member_id": user_id, "expires_at": expires_at},
    )
    return {"username": member["username"], "expires_at": expires_at, "reset_path": f"/app?auth_action=reset&token={raw_token}"}


def complete_password_reset(request: Request, response: Response, payload: AuthActionCompleteRequest) -> dict:
    action = identity.active_auth_action(payload.token, "RESET")
    user = accounts.by_id(action.get("user_id") or "")
    if user is None or user["workspace_id"] != action["workspace_id"] or not bool(user.get("active", 1)):
        raise HTTPException(status_code=410, detail="链接关联账号不存在或已停用")
    if not accounts.consume_action_token(token_hash(payload.token), utc_now()):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    accounts.set_password(user["user_id"], password_hash(payload.password))
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(action["workspace_id"], user["user_id"], "AUTH_PASSWORD_RESET_COMPLETED")
    return _account_response(user, user["workspace_id"])


def create_member(principal: dict[str, str], payload: MemberCreateRequest) -> dict:
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以创建管理员")
    try:
        user = accounts.create(principal["workspace_id"], payload.username.strip(), password_hash(payload.password), payload.role)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    workspaces.ensure(principal["workspace_id"], user["user_id"], payload.role)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_CREATED",
        None,
        {"member_id": user["user_id"], "username": user["username"], "role": payload.role},
    )
    return {key: value for key, value in user.items() if key != "password_hash"} | {"active": True}


def update_member(principal: dict[str, str], user_id: str, payload: MemberUpdateRequest) -> dict:
    members = {item["user_id"]: item for item in workspaces.members(principal["workspace_id"])}
    target = members.get(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="成员不存在")
    if target["role"] == "OWNER" and target["user_id"] != principal["user_id"]:
        raise HTTPException(status_code=403, detail="管理员不能修改所有者")
    if user_id == principal["user_id"] and payload.active is False:
        raise HTTPException(status_code=400, detail="不能停用当前账号")
    if payload.role == "ADMIN" and principal["role"] != "OWNER":
        raise HTTPException(status_code=403, detail="只有所有者可以授予管理员角色")
    updated = workspaces.update_member(principal["workspace_id"], user_id, payload.role, payload.active)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "MEMBER_UPDATED",
        None,
        {"member_id": user_id, "role": updated["role"], "active": updated["active"]},
    )
    return updated
