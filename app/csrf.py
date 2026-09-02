"""CSRF protection for cookie-authenticated requests.

SameSite=strict already blocks most cross-site sends, but it is a browser policy rather than a
server-side check: it does not apply to older browsers and does not survive a same-site
subdomain being compromised. A double-submit token gives the server its own signal.

Token-authenticated calls are exempt because a bearer token is not attached automatically by
the browser, so there is nothing for a third-party page to ride on.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response


COOKIE_NAME = "bidproof_csrf"
HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def issue(response: Response, token: str | None = None, *, secure: bool = False) -> str:
    """Set the CSRF cookie. Readable by scripts by design: the page must echo it back."""
    value = token or new_token()
    response.set_cookie(
        COOKIE_NAME,
        value,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return value


def clear(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def requires_check(request: Request, *, authenticated_by_cookie: bool) -> bool:
    return authenticated_by_cookie and request.method.upper() not in SAFE_METHODS


def verify(request: Request) -> None:
    submitted = (request.headers.get(HEADER_NAME) or "").strip()
    expected = (request.cookies.get(COOKIE_NAME) or "").strip()
    if not expected or not submitted or not secrets.compare_digest(submitted, expected):
        raise HTTPException(status_code=403, detail="CSRF 校验失败，请刷新页面后重试")
