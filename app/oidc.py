"""OpenID Connect authorization code flow with PKCE.

On-premise customers authenticate against their own identity provider. This performs
discovery, builds the authorization request, exchanges the code, and validates the returned
id_token's issuer, audience, expiry and nonce before any account is touched.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen


DISCOVERY_SUFFIX = "/.well-known/openid-configuration"
DEFAULT_SCOPES = "openid profile email"
# Tolerated clock difference between this host and the provider when checking exp/iat.
CLOCK_SKEW_SECONDS = 120


class OIDCError(RuntimeError):
    """Configuration or protocol failure. Never carries a token or secret."""


@dataclass(frozen=True)
class OIDCSettings:
    issuer: str
    client_id: str
    client_secret: str
    scopes: str = DEFAULT_SCOPES
    username_claim: str = "preferred_username"
    default_role: str = "REVIEWER"

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.client_id)


def settings_from_env() -> OIDCSettings:
    return OIDCSettings(
        issuer=os.environ.get("BIDPROOF_OIDC_ISSUER", "").strip().rstrip("/"),
        client_id=os.environ.get("BIDPROOF_OIDC_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("BIDPROOF_OIDC_CLIENT_SECRET", "").strip(),
        scopes=os.environ.get("BIDPROOF_OIDC_SCOPES", DEFAULT_SCOPES).strip() or DEFAULT_SCOPES,
        username_claim=os.environ.get("BIDPROOF_OIDC_USERNAME_CLAIM", "preferred_username").strip(),
        default_role=os.environ.get("BIDPROOF_OIDC_DEFAULT_ROLE", "REVIEWER").strip().upper(),
    )


def new_state() -> str:
    return secrets.token_urlsafe(24)


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def new_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    """S256 challenge, so an intercepted code cannot be redeemed without the verifier."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def discovery_url(issuer: str) -> str:
    return f"{issuer.rstrip('/')}{DISCOVERY_SUFFIX}"


def authorization_url(
    settings: OIDCSettings,
    document: dict,
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    verifier: str,
) -> str:
    endpoint = document.get("authorization_endpoint")
    if not endpoint:
        raise OIDCError("provider discovery document has no authorization_endpoint")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.client_id,
            "redirect_uri": redirect_uri,
            "scope": settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return f"{endpoint}?{query}"


def token_request(
    settings: OIDCSettings,
    document: dict,
    *,
    code: str,
    redirect_uri: str,
    verifier: str,
) -> tuple[str, dict[str, str]]:
    endpoint = document.get("token_endpoint")
    if not endpoint:
        raise OIDCError("provider discovery document has no token_endpoint")
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.client_id,
        "code_verifier": verifier,
    }
    if settings.client_secret:
        form["client_secret"] = settings.client_secret
    return endpoint, form


def decode_id_token_claims(id_token: str) -> dict:
    """Read the claim set out of a JWT without verifying its signature.

    Signature verification requires the provider's JWKS. The claims are only trusted after
    `validate_claims`, and the token itself was received directly from the provider's token
    endpoint over TLS in the authorization code flow.
    """
    parts = id_token.split(".")
    if len(parts) != 3:
        raise OIDCError("id_token is not a JWT")
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, TypeError) as exc:
        raise OIDCError("id_token payload is not valid JSON") from exc


def validate_claims(
    claims: dict,
    settings: OIDCSettings,
    *,
    nonce: str,
    now: float | None = None,
) -> dict:
    """Check issuer, audience, expiry and nonce. Returns the claims when they hold."""
    moment = now if now is not None else time.time()
    issuer = str(claims.get("iss", "")).rstrip("/")
    if issuer != settings.issuer.rstrip("/"):
        raise OIDCError("id_token issuer does not match the configured provider")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if settings.client_id not in [str(item) for item in audiences if item is not None]:
        raise OIDCError("id_token audience does not include this client")
    expires_at = claims.get("exp")
    if not isinstance(expires_at, (int, float)) or moment > float(expires_at) + CLOCK_SKEW_SECONDS:
        raise OIDCError("id_token has expired")
    issued_at = claims.get("iat")
    if isinstance(issued_at, (int, float)) and float(issued_at) - CLOCK_SKEW_SECONDS > moment:
        raise OIDCError("id_token was issued in the future")
    if not claims.get("sub"):
        raise OIDCError("id_token has no subject")
    # Binds the response to the authorization request this server started.
    if str(claims.get("nonce", "")) != nonce:
        raise OIDCError("id_token nonce does not match the login attempt")
    return claims


def username_from_claims(claims: dict, settings: OIDCSettings) -> str:
    for key in (settings.username_claim, "preferred_username", "email", "sub"):
        value = str(claims.get(key, "")).strip()
        if value:
            return value
    raise OIDCError("id_token has no usable username claim")


def fetch_discovery(settings: OIDCSettings, *, opener=None) -> dict:
    url = discovery_url(settings.issuer)
    return _read_json(url, opener=opener)


def redeem_code(
    settings: OIDCSettings,
    document: dict,
    *,
    code: str,
    redirect_uri: str,
    verifier: str,
    opener=None,
) -> dict:
    endpoint, form = token_request(
        settings,
        document,
        code=code,
        redirect_uri=redirect_uri,
        verifier=verifier,
    )
    return _post_form(endpoint, form, opener=opener)


def _read_json(url: str, *, opener=None, timeout: int = 10) -> dict:
    request = UrlRequest(url, headers={"Accept": "application/json", "User-Agent": "BidProof"})
    fetch = opener or urlopen
    with fetch(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise OIDCError("provider response is not a JSON object")
    return payload


def _post_form(url: str, form: dict[str, str], *, opener=None, timeout: int = 10) -> dict:
    body = urlencode(form).encode("utf-8")
    request = UrlRequest(
        url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "BidProof",
        },
    )
    fetch = opener or urlopen
    with fetch(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise OIDCError("token response is not a JSON object")
    return payload
