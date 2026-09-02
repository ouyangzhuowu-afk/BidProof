"""Account lifecycle: bootstrap, login, trial join, invitations, resets and members."""

from __future__ import annotations

import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from .. import config, directory, identity, oidc, totp
from ..authz import permissions_for
from ..repositories import accounts, audit, identity as identity_store, workspaces
from ..schemas import (
    MIN_PASSWORD_LENGTH,
    ApiTokenCreateRequest,
    AuthActionCompleteRequest,
    AuthBootstrapRequest,
    InvitationCreateRequest,
    LoginRequest,
    MemberCreateRequest,
    MemberUpdateRequest,
    MfaCodeRequest,
    PasswordChangeRequest,
    TrialJoinRequest,
)
from ..security import UNUSABLE_PASSWORD, new_action_token, password_hash, password_is_usable, token_hash, verify_password
from ..state import utc_now


INVITATION_VALID_HOURS = 72
RESET_VALID_HOURS = 1
MFA_CHALLENGE_MINUTES = 5
OIDC_FLOW_MINUTES = 10
API_TOKEN_PREFIX = "bp_"


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
            "oidc_enabled": oidc.settings_from_env().enabled,
            "mfa_enabled": False,
        }
    token = identity.session_token(request)
    user = accounts.session_user(token_hash(token), utc_now()) if token else None
    mfa_enabled = bool(user and (identity_store.load_mfa(user["user_id"]) or {}).get("confirmed_at"))
    return {
        "setup_required": False,
        "authenticated": bool(user),
        "trial_join_enabled": trial_join_enabled,
        "oidc_enabled": oidc.settings_from_env().enabled,
        "user": _account_response(user, user["workspace_id"]) if user else None,
        "mfa_enabled": mfa_enabled,
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
    username = payload.username.strip()
    user = accounts.by_username(username)
    meets_policy = len(payload.password) >= MIN_PASSWORD_LENGTH
    if user and not bool(user.get("active", 1)):
        _fail_login(attempt_key, user, username)
    if user and password_is_usable(user.get("password_hash")):
        if not meets_policy or not verify_password(payload.password, user["password_hash"]):
            _fail_login(attempt_key, user, username)
    else:
        federated = _directory_login(username, payload.password) if meets_policy else None
        if federated is None:
            _fail_login(attempt_key, user, username)
        user = federated
    identity.clear_login_attempts(attempt_key)
    return _complete_login(request, response, user)


def _fail_login(attempt_key: str, user: dict | None, username: str) -> None:
    audit.record(
        user["workspace_id"] if user else "-",
        user["user_id"] if user else "anonymous",
        "AUTH_LOGIN_FAILED",
        None,
        {"username": username},
        outcome="FAILURE",
    )
    identity.record_failed_login(attempt_key)
    raise HTTPException(status_code=401, detail="用户名或密码错误")


def _complete_login(request: Request, response: Response, user: dict) -> dict:
    mfa = identity_store.load_mfa(user["user_id"])
    if mfa and mfa.get("confirmed_at"):
        challenge = secrets.token_urlsafe(24)
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=MFA_CHALLENGE_MINUTES)).isoformat()
        identity_store.start_flow(challenge, "MFA", nonce=user["user_id"], expires_at=expires_at)
        return {"mfa_required": True, "mfa_token": challenge, "username": user["username"]}
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(user["workspace_id"], user["user_id"], "AUTH_LOGIN")
    return _account_response(user, user["workspace_id"])


def _directory_login(username: str, password: str) -> dict | None:
    settings = directory.settings_from_env()
    if not settings.enabled:
        return None
    try:
        attributes = directory.authenticate(settings, username, password)
    except directory.DirectoryError as exc:
        raise HTTPException(status_code=503, detail="目录服务不可用") from exc
    if not attributes:
        return None
    return _provision_federated_user(
        username,
        directory.role_from_attributes(settings, attributes),
        provider="LDAP",
        issuer=settings.server_uri,
        subject=str(attributes.get("dn") or username),
    )


def _provision_federated_user(
    username: str,
    role: str,
    *,
    provider: str,
    issuer: str,
    subject: str,
) -> dict:
    binding = identity_store.load_binding(provider, issuer, subject)
    if binding:
        user = accounts.by_id(binding["user_id"])
        if user is None or not bool(user.get("active", 1)):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        identity_store.remember_binding(user["user_id"], provider, issuer, subject)
        return user
    existing = accounts.by_username(username)
    if existing:
        if not bool(existing.get("active", 1)):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        identity_store.remember_binding(existing["user_id"], provider, issuer, subject)
        return existing
    workspace_id = workspaces.primary_id()
    if not workspace_id:
        raise HTTPException(status_code=503, detail="企业空间尚未初始化，请先完成管理员开通")
    user = accounts.create(workspace_id, username, UNUSABLE_PASSWORD, role)
    workspaces.ensure(workspace_id, user["user_id"], role)
    identity_store.remember_binding(user["user_id"], provider, issuer, subject)
    audit.record(
        workspace_id,
        user["user_id"],
        "AUTH_FEDERATED_PROVISIONED",
        None,
        {"username": username, "provider": provider, "role": role},
    )
    return user


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


def verify_mfa_login(request: Request, response: Response, payload: MfaCodeRequest) -> dict:
    if not payload.mfa_token:
        raise HTTPException(status_code=400, detail="缺少二次验证令牌")
    bucket = identity.login_attempt_key(request, f"mfa:{payload.mfa_token[:12]}")
    flow = identity_store.load_flow(payload.mfa_token, "MFA", utc_now())
    if flow is None:
        from .. import ratelimit

        ratelimit.register_failure(ratelimit.MFA, bucket, detail="验证码尝试过多，请稍后再试")
        raise HTTPException(status_code=401, detail="二次验证已过期，请重新登录")
    user = accounts.by_id(flow.get("nonce") or "")
    if user is None or not bool(user.get("active", 1)):
        raise HTTPException(status_code=401, detail="二次验证已过期，请重新登录")
    _accept_mfa_code(user["user_id"], payload.code, bucket)
    identity_store.consume_flow(payload.mfa_token, "MFA", utc_now())
    identity.issue_session(response, user["user_id"], identity.request_is_secure(request))
    audit.record(user["workspace_id"], user["user_id"], "AUTH_LOGIN", None, {"mfa": True})
    return _account_response(user, user["workspace_id"])


def enroll_mfa(principal: dict) -> dict:
    user = accounts.by_id(principal["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="当前账号无效")
    existing = identity_store.load_mfa(user["user_id"])
    if existing and existing.get("confirmed_at"):
        raise HTTPException(status_code=409, detail="已启用二次验证")
    secret = totp.new_secret()
    recovery_codes = totp.new_recovery_codes()
    identity_store.save_mfa(user["user_id"], secret, [token_hash(code.casefold()) for code in recovery_codes])
    audit.record(principal["workspace_id"], principal["user_id"], "AUTH_MFA_ENROLLED")
    return {
        "secret": secret,
        "otpauth_url": totp.provisioning_uri(secret, user["username"]),
        "recovery_codes": recovery_codes,
    }


def confirm_mfa(principal: dict, payload: MfaCodeRequest) -> dict:
    record = identity_store.load_mfa(principal["user_id"])
    if record is None:
        raise HTTPException(status_code=400, detail="请先开始二次验证绑定")
    if record.get("confirmed_at"):
        return {"mfa_enabled": True}
    counter = totp.verify(record["secret"], payload.code, last_counter=int(record.get("last_counter") or 0))
    if counter is None:
        raise HTTPException(status_code=401, detail="验证码无效")
    identity_store.confirm_mfa(principal["user_id"], counter)
    audit.record(principal["workspace_id"], principal["user_id"], "AUTH_MFA_CONFIRMED")
    return {"mfa_enabled": True}


def disable_mfa(principal: dict, payload: MfaCodeRequest) -> dict:
    _accept_mfa_code(principal["user_id"], payload.code, f"mfa:{principal['user_id']}")
    identity_store.delete_mfa(principal["user_id"])
    audit.record(principal["workspace_id"], principal["user_id"], "AUTH_MFA_DISABLED")
    return {"mfa_enabled": False}


def _accept_mfa_code(user_id: str, code: str, bucket: str) -> None:
    from .. import ratelimit

    ratelimit.enforce(ratelimit.MFA, bucket, detail="验证码尝试过多，请稍后再试")
    record = identity_store.load_mfa(user_id)
    if record is None or not record.get("confirmed_at"):
        raise HTTPException(status_code=400, detail="尚未启用二次验证")
    counter = totp.verify(record["secret"], code, last_counter=int(record.get("last_counter") or 0))
    if counter is not None:
        identity_store.update_mfa(user_id, counter)
        ratelimit.clear(ratelimit.MFA, bucket)
        return
    remaining = list(record.get("recovery_codes_json") or [])
    submitted = token_hash(code.strip().casefold())
    matched = next((digest for digest in remaining if secrets.compare_digest(digest, submitted)), None)
    if matched is None:
        ratelimit.register_failure(ratelimit.MFA, bucket, detail="验证码尝试过多，请稍后再试")
        raise HTTPException(status_code=401, detail="验证码无效")
    remaining.remove(matched)
    identity_store.update_mfa(user_id, int(record.get("last_counter") or 0), remaining)
    ratelimit.clear(ratelimit.MFA, bucket)


def start_oidc(request: Request) -> str:
    settings = oidc.settings_from_env()
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="未配置企业身份提供方")
    try:
        document = oidc.fetch_discovery(settings)
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=503, detail="身份提供方不可用") from exc
    state = oidc.new_state()
    nonce = oidc.new_nonce()
    verifier = oidc.new_code_verifier()
    redirect_uri = _oidc_redirect_uri(request)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OIDC_FLOW_MINUTES)).isoformat()
    identity_store.start_flow(
        state,
        "OIDC",
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        nonce=nonce,
        expires_at=expires_at,
    )
    try:
        return oidc.authorization_url(
            settings, document, redirect_uri=redirect_uri, state=state, nonce=nonce, verifier=verifier
        )
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=503, detail="身份提供方不可用") from exc


def complete_oidc(request: Request, response: Response, code: str, state: str) -> dict:
    settings = oidc.settings_from_env()
    if not settings.enabled:
        raise HTTPException(status_code=404, detail="未配置企业身份提供方")
    flow = identity_store.consume_flow(state, "OIDC", utc_now())
    if flow is None or not code:
        raise HTTPException(status_code=401, detail="登录已过期，请重试")
    try:
        document = oidc.fetch_discovery(settings)
        token_payload = oidc.redeem_code(
            settings,
            document,
            code=code,
            redirect_uri=flow["redirect_uri"],
            verifier=flow["code_verifier"],
        )
        id_token = str(token_payload.get("id_token") or "")
        claims = oidc.validate_claims(oidc.decode_id_token_claims(id_token), settings, nonce=flow["nonce"])
        username = oidc.username_from_claims(claims, settings)
    except oidc.OIDCError as exc:
        raise HTTPException(status_code=401, detail="企业身份校验失败") from exc
    user = _provision_federated_user(
        username,
        settings.default_role if settings.default_role in {"OWNER", "ADMIN", "REVIEWER", "VIEWER"} else "REVIEWER",
        provider="OIDC",
        issuer=settings.issuer,
        subject=str(claims["sub"]),
    )
    return _complete_login(request, response, user)


def _oidc_redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/api/auth/oidc/callback"


def list_tokens(principal: dict) -> dict:
    return {"tokens": identity_store.list_tokens(principal["workspace_id"])}


def create_token(principal: dict, payload: ApiTokenCreateRequest) -> dict:
    allowed = {item.value for item in permissions_for(principal["role"])}
    requested = [item for item in payload.permissions if item in allowed]
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    expires_at = None
    if payload.expires_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=payload.expires_days)).isoformat()
    record = identity_store.create_token(
        token_hash=token_hash(raw),
        token_prefix=raw[:10],
        workspace_id=principal["workspace_id"],
        user_id=principal["user_id"],
        name=payload.name.strip(),
        role=principal["role"],
        created_by=principal["user_id"],
        permissions=requested,
        expires_at=expires_at,
    )
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "AUTH_TOKEN_CREATED",
        None,
        {"token_id": record["token_id"], "name": record["name"]},
    )
    return {**record, "token": raw}


def revoke_token(principal: dict, token_id: str) -> dict:
    record = identity_store.revoke_token(principal["workspace_id"], token_id)
    if record is None:
        raise HTTPException(status_code=404, detail="令牌不存在")
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "AUTH_TOKEN_REVOKED",
        None,
        {"token_id": token_id},
    )
    return record
