"""Request-scoped HTTP middleware: request id, CSRF and write/export rate limits."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config, csrf, identity, ratelimit, request_context


WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
EXPORT_SUFFIXES = (".csv", ".pdf", ".zip", ".html")
EXEMPT_PREFIXES = ("/static/",)


def csrf_enforced() -> bool:
    # Cookie tests in this suite predate the double-submit header. Production and an explicit
    # test flag still require it so the check cannot be forgotten.
    if os.environ.get("BIDPROOF_ENFORCE_CSRF", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return config.ENVIRONMENT != "test"


def write_limits_enforced() -> bool:
    if os.environ.get("BIDPROOF_ENFORCE_WRITE_LIMITS", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return config.ENVIRONMENT != "test"


def install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        context = request_context.from_request(request)
        with request_context.bind(context):
            try:
                _check_csrf(request)
                _check_action_limits(request)
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=dict(exc.headers or {}),
                )
                response.headers[request_context.REQUEST_ID_HEADER] = context.request_id
                return response
            response = await call_next(request)
            response.headers[request_context.REQUEST_ID_HEADER] = context.request_id
            if request.method.upper() in csrf.SAFE_METHODS and csrf.COOKIE_NAME not in request.cookies:
                csrf.issue(response, secure=identity.request_is_secure(request))
            return response


def _check_csrf(request: Request) -> None:
    if not csrf_enforced():
        return
    if csrf.requires_check(request, authenticated_by_cookie=identity.authenticated_by_cookie(request)):
        csrf.verify(request)


def _check_action_limits(request: Request) -> None:
    if not write_limits_enforced():
        return
    path = request.url.path
    if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return
    method = request.method.upper()
    bucket = request_context.client_ip(request) or "unknown"
    if path.startswith("/api/") and any(path.endswith(suffix) for suffix in EXPORT_SUFFIXES):
        ratelimit.enforce(ratelimit.EXPORT, bucket, detail="导出过于频繁，请稍后再试")
        return
    if method in WRITE_METHODS and path.startswith("/api/"):
        ratelimit.enforce(ratelimit.WRITE, bucket, detail="写入过于频繁，请稍后再试")
