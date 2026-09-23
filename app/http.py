"""Request-scoped HTTP middleware: request id, CSRF and write/export rate limits."""

from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config, csrf, identity, observability, ratelimit, request_context

logger = logging.getLogger("bidproof.http")


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


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
}


def install_middleware(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled exception on %s %s [%s]", request.method, request.url.path, rid)
        response = JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试", "request_id": rid})
        response.headers.update(SECURITY_HEADERS)
        response.headers[request_context.REQUEST_ID_HEADER] = rid
        return response

    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        request.state.started_at = time.perf_counter()
        context = request_context.from_request(request)
        with request_context.bind(context):
            observability.bind_log_context()
            try:
                _check_csrf(request)
                _check_action_limits(request)
                _reject_unsupported_idempotency(request)
                response = await call_next(request)
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=dict(exc.headers or {}),
                )
                _finalize_response(request, response, context)
                return response
            except Exception:
                logger.exception("request_failed")
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "服务器内部错误，请稍后重试", "request_id": context.request_id},
                )
            if request.method.upper() in csrf.SAFE_METHODS and csrf.COOKIE_NAME not in request.cookies:
                csrf.issue(response, secure=identity.request_is_secure(request))
            _finalize_response(request, response, context)
            return response

    @app.middleware("http")
    async def api_v1_alias(request: Request, call_next):
        path = request.scope.get("path") or ""
        if path in {"/api/v1/healthz", "/api/v1/healthz/"}:
            request.scope["path"] = "/healthz"
        elif path.startswith("/api/v1/") or path == "/api/v1":
            request.scope["path"] = "/api/" + path[len("/api/v1/") :] if path.startswith("/api/v1/") else "/api"
        return await call_next(request)

    if config.ENVIRONMENT == "production" and config.ALLOWED_HOSTS:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.ALLOWED_HOSTS), www_redirect=False)


def _reject_unsupported_idempotency(request: Request) -> None:
    """Reject explicitly instead of silently performing duplicate or cross-tenant writes.

    The old cache ran before authentication and keyed on caller-controlled workspace headers.
    Atomic, authenticated request claims are not yet supported. No request body is buffered.
    """
    if (request.headers.get("Idempotency-Key") is not None
            and request.method.upper() in WRITE_METHODS and request.url.path.startswith("/api/")):
        if not request.url.path.startswith("/api/auth/"):
            identity.principal_of(request)
        raise HTTPException(status_code=501, detail="此版本不支持 Idempotency-Key；请求未执行，请勿自动重试写入")


def _finalize_response(request: Request, response, context) -> None:
    for hdr, val in SECURITY_HEADERS.items():
        response.headers.setdefault(hdr, val)
    response.headers[request_context.REQUEST_ID_HEADER] = context.request_id
    if config.ENVIRONMENT == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    observability.record_http(request.method, response.status_code)
    path = request.url.path
    if path.startswith("/static/") or path == "/metrics":
        return
    logger.info(
        "%s %s %s",
        request.method,
        path,
        response.status_code,
        extra={"request_id": context.request_id, "status_code": response.status_code,
               "duration_ms": round((time.perf_counter() - request.state.started_at) * 1000, 2)},
    )


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
        ratelimit.enforce(ratelimit.EXPORT, bucket, detail="导出过于频繁，请稍后再试", consume=True)
        return
    if method in WRITE_METHODS and path.startswith("/api/"):
        ratelimit.enforce(ratelimit.WRITE, bucket, detail="写入过于频繁，请稍后再试", consume=True)
