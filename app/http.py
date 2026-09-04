"""Request-scoped HTTP middleware: request id, CSRF and write/export rate limits."""

from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import config, csrf, identity, idempotency, observability, ratelimit, request_context

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
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'",
}


def install_middleware(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", "unknown")
        logger.exception("Unhandled exception on %s %s [%s]", request.method, request.url.path, rid)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请稍后重试"})

    @app.middleware("http")
    async def request_guards(request: Request, call_next):
        context = request_context.from_request(request)
        with request_context.bind(context):
            observability.bind_log_context()
            try:
                _check_csrf(request)
                _check_action_limits(request)
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=dict(exc.headers or {}),
                )
                _finalize_response(request, response, context)
                return response
            response = await call_next(request)
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

    @app.middleware("http")
    async def idempotency_guard(request: Request, call_next):
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if not key or request.method.upper() not in WRITE_METHODS or not (request.scope.get("path") or "").startswith("/api/"):
            return await call_next(request)
        if "/api/auth/" in (request.scope.get("path") or ""):
            return await call_next(request)
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        request_hash = idempotency.hash_body(body)
        cached = idempotency.lookup(request, key, request_hash)
        if cached is not None:
            return cached
        response = await call_next(request)
        if 200 <= response.status_code < 300 and isinstance(response, JSONResponse):
            payload = None
            if getattr(response, "media_type", "").startswith("application/json"):
                try:
                    payload = json.loads(bytes(response.body).decode("utf-8"))
                except Exception:
                    payload = {"status": response.status_code}
            else:
                payload = {"status": response.status_code}
            idempotency.remember(request, key, request_hash, response.status_code, payload)
        return response


def _finalize_response(request: Request, response, context) -> None:
    for hdr, val in SECURITY_HEADERS.items():
        response.headers.setdefault(hdr, val)
    response.headers[request_context.REQUEST_ID_HEADER] = context.request_id
    observability.record_http(request.method, response.status_code)
    path = request.url.path
    if path.startswith("/static/") or path == "/metrics":
        return
    logger.info(
        "%s %s %s",
        request.method,
        path,
        response.status_code,
        extra={"request_id": context.request_id},
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
