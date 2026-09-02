"""Per-request context.

An audit row, a log line and an error response for the same request all need to name the same
identifier. It is held in a context variable so services can reach it without threading a
request object through the call chain.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from fastapi import Request


REQUEST_ID_HEADER = "X-Request-ID"
FORWARDED_FOR_HEADER = "X-Forwarded-For"
REAL_IP_HEADER = "X-Real-IP"


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    client_ip: str | None = None
    user_agent: str | None = None
    method: str | None = None
    path: str | None = None


_EMPTY = RequestContext(request_id="")
_current: ContextVar[RequestContext] = ContextVar("bidproof_request_context", default=_EMPTY)


def new_request_id() -> str:
    return uuid.uuid4().hex


def current() -> RequestContext:
    return _current.get()


@contextmanager
def bind(context: RequestContext):
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)


def from_request(request: Request) -> RequestContext:
    """Build the context for an incoming request.

    An inbound request id is reused so a trace can be followed across the reverse proxy, but
    it is length-capped because it ends up in stored audit rows.
    """
    inbound = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    return RequestContext(
        request_id=inbound[:64] or new_request_id(),
        client_ip=client_ip(request),
        user_agent=(request.headers.get("User-Agent") or "")[:400] or None,
        method=request.method,
        path=request.url.path,
    )


def client_ip(request: Request) -> str | None:
    """The caller's address, preferring proxy headers when the app runs behind one.

    Only the left-most entry of X-Forwarded-For is used; the rest are appended by intermediate
    hops and are not more trustworthy than the first.
    """
    forwarded = request.headers.get(FORWARDED_FOR_HEADER)
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:64]
    real_ip = (request.headers.get(REAL_IP_HEADER) or "").strip()
    if real_ip:
        return real_ip[:64]
    return request.client.host if request.client else None
