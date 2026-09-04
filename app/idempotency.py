"""Idempotency-Key support for mutating API calls."""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import db, request_context


def _workspace(request: Request) -> str:
    header = request.headers.get("x-workspace-id") or ""
    if header.strip():
        return header.strip()
    return f"ip:{request_context.client_ip(request) or 'unknown'}"


def lookup(request: Request, key: str, request_hash: str) -> JSONResponse | None:
    row = db.load_idempotency(_workspace(request), key)
    if row is None:
        return None
    if row.get("request_hash") != request_hash or row.get("method") != request.method.upper() or row.get("path") != request.url.path:
        raise HTTPException(status_code=409, detail="Idempotency-Key 已用于不同请求")
    return JSONResponse(status_code=int(row["status_code"]), content=row.get("response_json") or {})


def remember(request: Request, key: str, request_hash: str, status_code: int, payload: object) -> None:
    try:
        db.store_idempotency(
            _workspace(request),
            key,
            request.method.upper(),
            request.url.path,
            request_hash,
            status_code,
            payload,
        )
    except Exception:
        return


def hash_body(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
