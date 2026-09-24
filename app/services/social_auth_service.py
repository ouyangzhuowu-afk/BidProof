"""Google OIDC and GitHub OAuth: authorization code + PKCE, browser-bound one-use state."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest

from fastapi import Request, Response

from .. import auth_delivery, config, identity, oidc
from ..repositories import challenges
from ..repositories import identity as identities
from ..state import utc_now
from . import auth_service, passwordless_service

PROVIDERS = {"google": "Google", "github": "GitHub"}
FLOW_SECONDS = 600


def _credentials(provider: str) -> tuple[str, str]:
    return (auth_delivery.setting(provider.upper() + "_CLIENT_ID"),
            auth_delivery.setting(provider.upper() + "_CLIENT_SECRET"))


def available() -> list[dict]:
    return [{"id": key, "label": label, "url": f"/api/auth/oauth/{key}/start"}
            for key, label in PROVIDERS.items() if config.PUBLIC_ORIGIN and all(_credentials(key))]


def _require(provider: str) -> tuple[str, str]:
    if provider not in {item["id"] for item in available()}:
        passwordless_service.fail(503, "PROVIDER_UNAVAILABLE", "此登录方式尚未配置，请使用邮箱或密码")
    return _credentials(provider)


def _google_settings() -> oidc.OIDCSettings:
    client, secret = _credentials("google")
    return oidc.OIDCSettings(issuer="https://accounts.google.com", client_id=client,
                             client_secret=secret, username_claim="email")


def start(request: Request, response: Response, provider: str) -> str:
    client, _secret = _require(provider)
    ip = request.client.host if request.client else "unknown"
    retry = challenges.consume_limit("oauth-start", hashlib.sha256(ip.encode()).hexdigest(), 30, 3600)
    if retry:
        passwordless_service.fail(429, "PROVIDER_UNAVAILABLE", "登录请求较多，请稍后再试", retry)
    identities.purge_expired_flows("SOCIAL_" + provider.upper(), utc_now())
    state, nonce, verifier = oidc.new_state(), oidc.new_nonce(), oidc.new_code_verifier()
    callback = config.PUBLIC_ORIGIN + f"/api/auth/oauth/{provider}/callback"
    if provider == "google":
        try:
            settings = _google_settings()
            url = oidc.authorization_url(settings, oidc.fetch_discovery(settings),
                                         redirect_uri=callback, state=state, nonce=nonce, verifier=verifier)
        except oidc.OIDCError:
            passwordless_service.fail(503, "PROVIDER_UNAVAILABLE", "Google 暂时不可用，请选择其他登录方式")
    else:
        url = "https://github.com/login/oauth/authorize?" + urlencode({
            "client_id": client, "redirect_uri": callback, "state": state, "scope": "read:user",
            "code_challenge": oidc.code_challenge(verifier), "code_challenge_method": "S256",
        })
    identities.start_flow(state, "SOCIAL_" + provider.upper(), code_verifier=verifier,
                          redirect_uri=callback, nonce=nonce,
                          expires_at=(datetime.now(UTC) + timedelta(seconds=FLOW_SECONDS)).isoformat())
    response.set_cookie("bidproof_social_" + provider, state, max_age=FLOW_SECONDS,
                        httponly=True, secure=identity.request_is_secure(request), samesite="lax",
                        path=f"/api/auth/oauth/{provider}")
    return url


def complete(request: Request, response: Response, provider: str, code: str, state: str, error: str) -> dict:
    client, secret = _require(provider)
    browser_state = request.cookies.get("bidproof_social_" + provider, "")
    if not state or not browser_state or not secrets.compare_digest(state, browser_state):
        passwordless_service.fail(401, "SOCIAL_EXPIRED", "登录来源校验失败，请重新开始")
    response.delete_cookie("bidproof_social_" + provider, path=f"/api/auth/oauth/{provider}")
    flow = identities.consume_flow(state, "SOCIAL_" + provider.upper(), utc_now())
    if flow is None:
        passwordless_service.fail(401, "SOCIAL_EXPIRED", "登录已过期，请重新开始")
    if error:
        passwordless_service.fail(400, "SOCIAL_CANCELLED", "已取消授权，可选择其他登录方式")
    if not code:
        passwordless_service.fail(401, "SOCIAL_EXPIRED", "未收到授权结果，请重新开始")
    try:
        if provider == "google":
            settings = _google_settings()
            document = oidc.fetch_discovery(settings)
            tokens = oidc.redeem_code(settings, document, code=code,
                                      redirect_uri=flow["redirect_uri"], verifier=flow["code_verifier"])
            claims = oidc.verify_id_token(str(tokens.get("id_token") or ""), settings, document, nonce=flow["nonce"])
            subject = str(claims["sub"])
            issuer = settings.issuer
        else:
            tokens = oidc._post_form("https://github.com/login/oauth/access_token", {
                "client_id": client, "client_secret": secret, "code": code,
                "redirect_uri": flow["redirect_uri"], "code_verifier": flow["code_verifier"],
            })
            access_token = tokens.get("access_token")
            if not isinstance(access_token, str) or not access_token or len(access_token) > 2000:
                raise oidc.OIDCError("missing provider token")
            profile = oidc._fetch_json(UrlRequest("https://api.github.com/user", headers={
                "Authorization": "Bearer " + access_token, "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "BidProof",
            }), timeout=10)
            if not isinstance(profile.get("id"), int) or isinstance(profile["id"], bool) or profile["id"] <= 0:
                raise oidc.OIDCError("missing provider subject")
            subject, issuer = str(profile["id"]), "https://github.com"
    except (oidc.OIDCError, ValueError, TypeError, KeyError):
        passwordless_service.fail(401, "SOCIAL_PROVIDER", "授权验证失败，请重新开始或选择其他登录方式")
    # Immutable provider IDs, never email or a mutable display name, own the account.
    username = provider + "-" + hashlib.sha256(subject.encode()).hexdigest()[:16]
    user = passwordless_service.verified_user("SOCIAL_" + provider.upper(), issuer, subject, username)
    return auth_service._complete_login(request, response, user)
