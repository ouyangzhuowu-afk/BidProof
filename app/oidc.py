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
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.request import Request as UrlRequest

DISCOVERY_SUFFIX = "/.well-known/openid-configuration"
DEFAULT_SCOPES = "openid profile email"
# Tolerated clock difference between this host and the provider when checking exp/iat.
CLOCK_SKEW_SECONDS = 120
ALLOWED_SIGNING_ALGORITHMS = ("RS256", "ES256")
MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024


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
        issuer=os.environ.get("BIDPROOF_OIDC_ISSUER", "").strip(),
        client_id=os.environ.get("BIDPROOF_OIDC_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("BIDPROOF_OIDC_CLIENT_SECRET", "").strip(),
        scopes=os.environ.get("BIDPROOF_OIDC_SCOPES", DEFAULT_SCOPES).strip() or DEFAULT_SCOPES,
        username_claim=os.environ.get("BIDPROOF_OIDC_USERNAME_CLAIM", "preferred_username").strip(),
        default_role=os.environ.get("BIDPROOF_OIDC_DEFAULT_ROLE", "REVIEWER").strip().upper(),
    )


def _https_endpoint(value: object) -> str:
    if not isinstance(value, str):
        raise OIDCError("provider endpoint is missing")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment):
        raise OIDCError("provider endpoints must use HTTPS without embedded credentials")
    return value


def validate_settings(settings: OIDCSettings) -> None:
    _https_endpoint(settings.issuer)
    parsed = urlsplit(settings.issuer)
    if parsed.query or not settings.client_id or settings.default_role not in {"REVIEWER", "VIEWER"}:
        raise OIDCError("OIDC requires an issuer, client id and a non-administrative default role")


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
    endpoint = _https_endpoint(document.get("authorization_endpoint"))
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
    endpoint = _https_endpoint(document.get("token_endpoint"))
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


def verify_id_token(id_token: str, settings: OIDCSettings, document: dict, *, nonce: str, opener=None) -> dict:
    """Verify the provider signature before any claim can identify an account.

    Only RS256 / ES256 providers with HTTPS discovery and JWKS are supported. Other
    algorithms fail closed; no unsigned-token or shared-secret fallback is provided.
    """
    validate_settings(settings)
    if document.get("issuer") != settings.issuer:
        raise OIDCError("provider discovery issuer does not match the configured provider")
    try:
        import jwt
    except ImportError as exc:
        raise OIDCError("OIDC signature verification dependency is unavailable") from exc
    try:
        if not isinstance(id_token, str) or len(id_token) > 64 * 1024:
            raise OIDCError("id_token is invalid")
        header = jwt.get_unverified_header(id_token)
        algorithm = header.get("alg")
        kid = header.get("kid")
        if algorithm not in ALLOWED_SIGNING_ALGORITHMS or not isinstance(kid, str) or not 1 <= len(kid) <= 200:
            raise OIDCError("id_token uses an unsupported signing key or algorithm")
        jwks = _read_json(_https_endpoint(document.get("jwks_uri")), opener=opener)
        keys = jwks.get("keys")
        if not isinstance(keys, list) or len(keys) > 100:
            raise OIDCError("provider signing keys are invalid")
        matches = [key for key in keys if isinstance(key, dict) and key.get("kid") == kid]
        if len(matches) != 1:
            raise OIDCError("id_token signing key is missing or ambiguous")
        key = matches[0]
        if (key.get("use", "sig") != "sig" or key.get("alg", algorithm) != algorithm
                or ("key_ops" in key and "verify" not in key["key_ops"])):
            raise OIDCError("provider key is not an allowed signature verification key")
        signing_key = jwt.PyJWK.from_dict(key, algorithm=algorithm).key
        claims = jwt.decode(
            id_token, signing_key, algorithms=[algorithm], issuer=settings.issuer,
            audience=settings.client_id, leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise OIDCError("id_token signature or claims are invalid") from exc
    return validate_claims(claims, settings, nonce=nonce)


def validate_claims(
    claims: dict,
    settings: OIDCSettings,
    *,
    nonce: str,
    now: float | None = None,
) -> dict:
    """Check issuer, audience, expiry and nonce. Returns the claims when they hold."""
    moment = now if now is not None else time.time()
    issuer = claims.get("iss")
    if issuer != settings.issuer:
        raise OIDCError("id_token issuer does not match the configured provider")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if settings.client_id not in [str(item) for item in audiences if item is not None]:
        raise OIDCError("id_token audience does not include this client")
    if (len(audiences) > 1 or "azp" in claims) and claims.get("azp") != settings.client_id:
        raise OIDCError("id_token authorized party does not match this client")
    expires_at = claims.get("exp")
    if not isinstance(expires_at, (int, float)) or moment > float(expires_at) + CLOCK_SKEW_SECONDS:
        raise OIDCError("id_token has expired")
    issued_at = claims.get("iat")
    if isinstance(issued_at, (int, float)) and float(issued_at) - CLOCK_SKEW_SECONDS > moment:
        raise OIDCError("id_token was issued in the future")
    if not isinstance(claims.get("sub"), str) or not 1 <= len(claims["sub"]) <= 255:
        raise OIDCError("id_token has no subject")
    # Binds the response to the authorization request this server started.
    if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(claims["nonce"], nonce):
        raise OIDCError("id_token nonce does not match the login attempt")
    return claims


def username_from_claims(claims: dict, settings: OIDCSettings) -> str:
    for key in (settings.username_claim, "preferred_username", "email", "sub"):
        value = str(claims.get(key, "")).strip()
        if value:
            return value
    raise OIDCError("id_token has no usable username claim")


def fetch_discovery(settings: OIDCSettings, *, opener=None) -> dict:
    validate_settings(settings)
    url = discovery_url(settings.issuer)
    document = _read_json(url, opener=opener)
    if document.get("issuer") != settings.issuer:
        raise OIDCError("provider discovery issuer does not match the configured provider")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        _https_endpoint(document.get(key))
    return document


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
    request = UrlRequest(_https_endpoint(url), headers={"Accept": "application/json", "User-Agent": "BidProof"})
    return _fetch_json(request, opener=opener, timeout=timeout)


def _post_form(url: str, form: dict[str, str], *, opener=None, timeout: int = 10) -> dict:
    body = urlencode(form).encode("utf-8")
    request = UrlRequest(
        _https_endpoint(url),
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "BidProof",
        },
    )
    return _fetch_json(request, opener=opener, timeout=timeout)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward provider requests or a client secret to a redirect target.
        return None


def _fetch_json(request: UrlRequest, *, opener=None, timeout: int) -> dict:
    fetch = opener or build_opener(_NoRedirect()).open
    try:
        with fetch(request, timeout=timeout) as response:
            raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
        if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
            raise OIDCError("provider response exceeds its size limit")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, URLError, ValueError, UnicodeError) as exc:
        raise OIDCError("identity provider response is unavailable or invalid") from exc
    if not isinstance(payload, dict):
        raise OIDCError("provider response is not a JSON object")
    return payload
