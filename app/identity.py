"""Who is calling, and what they are allowed to do.

Every route resolves its principal through this module so the identity rules -- session
cookies, API tokens, the test-only header affordance, and the server-side job context -- have
exactly one implementation.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response

from . import config, csrf, ratelimit
from .db import create_auth_session, ensure_workspace, load_auth_action_token, load_session_user
from .repositories import identity as identity_store
from .security import new_session_token, token_hash
from .state import utc_now


MUTATING_ROLES = {"OWNER", "ADMIN", "REVIEWER"}
ADMIN_ROLES = {"OWNER", "ADMIN"}
SESSION_COOKIE = "bidproof_session"
SESSION_HOURS = 12
LOGIN_ATTEMPT_LIMIT = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_LIMIT", "5"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))
BEARER_PREFIX = "bearer "


@dataclass(frozen=True)
class InternalJobContext:
    """Call context for a background scan job.

    Identity is carried as already-verified fields rather than request headers, so a queued
    job can never be used to replay or escalate a client-supplied identity.
    """

    workspace_id: str
    user_id: str
    role: str
    job_id: str
    headers: dict[str, str] = field(default_factory=dict)

    def principal(self) -> dict[str, str]:
        return {"workspace_id": self.workspace_id, "user_id": self.user_id, "role": self.role}


CallContext = Request | InternalJobContext


def principal_of(request: CallContext) -> dict[str, Any]:
    if isinstance(request, InternalJobContext):
        return request.principal()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        user = load_session_user(token_hash(token), utc_now())
        if user:
            return {
                "workspace_id": user["workspace_id"],
                "user_id": user["user_id"],
                "role": user["role"],
                "auth_method": "session",
            }
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
    bearer = _bearer_token(request)
    if bearer:
        return _principal_from_api_token(request, bearer)
    has_explicit_trusted_identity = any(
        header in request.headers
        for header in ("X-Workspace-ID", "X-User-ID", "X-User-Role")
    )
    if config.ALLOW_TRUSTED_HEADERS and (has_explicit_trusted_identity or _no_accounts_yet()):
        return trusted_header_principal(request)
    raise HTTPException(status_code=401, detail="请先登录")


def authenticated_by_cookie(request: Request) -> bool:
    return bool(request.cookies.get(SESSION_COOKIE))


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    if header[:7].lower() != BEARER_PREFIX:
        return None
    token = header[7:].strip()
    return token or None


def _principal_from_api_token(request: Request, token: str) -> dict[str, Any]:
    bucket = f"{_client_host(request)}:token"
    ratelimit.enforce(ratelimit.TOKEN_AUTH, bucket, detail="令牌校验过于频繁，请稍后再试")
    record = identity_store.load_token_by_hash(token_hash(token), utc_now())
    if record is None:
        ratelimit.register_failure(ratelimit.TOKEN_AUTH, bucket, detail="令牌校验过于频繁，请稍后再试")
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    identity_store.touch_token(record["token_id"])
    permissions = record.get("permissions_json") or []
    principal: dict[str, Any] = {
        "workspace_id": record["workspace_id"],
        "user_id": record["user_id"],
        "role": record["role"],
        "auth_method": "token",
        "token_id": record["token_id"],
    }
    if permissions:
        principal["permissions"] = permissions
    return principal


def _no_accounts_yet() -> bool:
    from .db import count_users

    return count_users() == 0


def trusted_header_principal(request: Request) -> dict[str, str]:
    workspace_id = request.headers.get("X-Workspace-ID", "local").strip() or "local"
    user_id = request.headers.get("X-User-ID", "local-owner").strip() or "local-owner"
    role = request.headers.get("X-User-Role", "OWNER").strip().upper() or "OWNER"
    ensure_workspace(workspace_id, user_id, role)
    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "auth_method": "trusted",
    }


def job_id_of(request: CallContext) -> str | None:
    """Return the queued job this call belongs to, or None for a direct client request.

    A client-supplied job id would let any caller drive another workspace's job state, so only
    a server-constructed job context can bind a run to an existing job.
    """
    return request.job_id if isinstance(request, InternalJobContext) else None


def require_role(principal: dict[str, Any], roles: set[str] = MUTATING_ROLES) -> None:
    if principal["role"] not in roles:
        raise HTTPException(status_code=403, detail="当前角色没有执行此操作的权限")


def issue_session(response: Response, user_id: str, secure: bool) -> None:
    token = new_session_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    create_auth_session(token_hash(token), user_id, expires.isoformat())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_HOURS * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    csrf.issue(response, secure=secure)


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    csrf.clear(response)


def request_is_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https"


def session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def bootstrap_locked() -> bool:
    return config.ENVIRONMENT == "production" and not config.BOOTSTRAP_TOKEN


def active_auth_action(raw_token: str, purpose: str | None = None) -> dict:
    action = load_auth_action_token(token_hash(raw_token))
    expired = not action or action.get("used_at") or action["expires_at"] <= utc_now()
    if expired or (purpose and action["purpose"] != purpose):
        raise HTTPException(status_code=410, detail="链接无效、已使用或已过期")
    return action


def login_attempt_key(request: Request, username: str) -> str:
    return f"{_client_host(request)}:{username.strip().casefold()}"


def _client_host(request: Request) -> str:
    from . import request_context

    return request_context.client_ip(request) or "unknown"


def _login_limit() -> ratelimit.Limit:
    return ratelimit.Limit(
        scope=ratelimit.LOGIN.scope,
        max_hits=LOGIN_ATTEMPT_LIMIT,
        window_seconds=LOGIN_ATTEMPT_WINDOW_SECONDS,
    )


def enforce_login_rate_limit(key: str, now: float | None = None) -> None:
    ratelimit.enforce(_login_limit(), key, detail="登录尝试过多，请稍后再试")


def record_failed_login(key: str, now: float | None = None) -> None:
    ratelimit.register_failure(_login_limit(), key, detail="登录尝试过多，请稍后再试")


def clear_login_attempts(key: str) -> None:
    ratelimit.clear(_login_limit(), key)


def monotonic_now() -> float:
    return time.monotonic()
