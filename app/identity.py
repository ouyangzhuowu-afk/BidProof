"""Who is calling, and what they are allowed to do.

Every route resolves its principal through this module so the identity rules -- session
cookies, the test-only header affordance, and the server-side job context -- have exactly one
implementation.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from . import config
from .db import create_auth_session, ensure_workspace, load_auth_action_token, load_session_user
from .security import new_session_token, token_hash
from .state import utc_now


MUTATING_ROLES = {"OWNER", "ADMIN", "REVIEWER"}
ADMIN_ROLES = {"OWNER", "ADMIN"}
SESSION_COOKIE = "bidproof_session"
SESSION_HOURS = 12
LOGIN_ATTEMPT_LIMIT = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_LIMIT", "5"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.environ.get("BIDPROOF_LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))

# Process-local, so it does not survive a restart and is not shared between workers. P3 moves
# this to shared storage and extends it beyond the login endpoints.
_login_attempts: dict[str, list[float]] = {}


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


def principal_of(request: CallContext) -> dict[str, str]:
    if isinstance(request, InternalJobContext):
        return request.principal()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        user = load_session_user(token_hash(token), utc_now())
        if user:
            return {"workspace_id": user["workspace_id"], "user_id": user["user_id"], "role": user["role"]}
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
    has_explicit_trusted_identity = any(
        header in request.headers
        for header in ("X-Workspace-ID", "X-User-ID", "X-User-Role")
    )
    if config.ALLOW_TRUSTED_HEADERS and (has_explicit_trusted_identity or _no_accounts_yet()):
        return trusted_header_principal(request)
    raise HTTPException(status_code=401, detail="请先登录")


def _no_accounts_yet() -> bool:
    from .db import count_users

    return count_users() == 0


def trusted_header_principal(request: Request) -> dict[str, str]:
    workspace_id = request.headers.get("X-Workspace-ID", "local").strip() or "local"
    user_id = request.headers.get("X-User-ID", "local-owner").strip() or "local-owner"
    role = request.headers.get("X-User-Role", "OWNER").strip().upper() or "OWNER"
    ensure_workspace(workspace_id, user_id, role)
    return {"workspace_id": workspace_id, "user_id": user_id, "role": role}


def job_id_of(request: CallContext) -> str | None:
    """Return the queued job this call belongs to, or None for a direct client request.

    A client-supplied job id would let any caller drive another workspace's job state, so only
    a server-constructed job context can bind a run to an existing job.
    """
    return request.job_id if isinstance(request, InternalJobContext) else None


def require_role(principal: dict[str, str], roles: set[str] = MUTATING_ROLES) -> None:
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


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


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
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{username.strip().casefold()}"


def _active_login_attempts(key: str, now: float) -> list[float]:
    attempts = [attempt for attempt in _login_attempts.get(key, []) if now - attempt < LOGIN_ATTEMPT_WINDOW_SECONDS]
    if attempts:
        _login_attempts[key] = attempts
    else:
        _login_attempts.pop(key, None)
    return attempts


def _raise_login_rate_limit(attempts: list[float], now: float) -> None:
    retry_after = max(1, int(LOGIN_ATTEMPT_WINDOW_SECONDS - (now - attempts[0])))
    raise HTTPException(
        status_code=429,
        detail="登录尝试过多，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


def enforce_login_rate_limit(key: str, now: float) -> None:
    attempts = _active_login_attempts(key, now)
    if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
        _raise_login_rate_limit(attempts, now)


def record_failed_login(key: str, now: float) -> None:
    attempts = _active_login_attempts(key, now)
    attempts.append(now)
    _login_attempts[key] = attempts
    if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
        _raise_login_rate_limit(attempts, now)


def clear_login_attempts(key: str) -> None:
    _login_attempts.pop(key, None)


def monotonic_now() -> float:
    return time.monotonic()
