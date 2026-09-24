"""Unified verification first sign-in. Only verified identities create isolated workspaces."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy.exc
from fastapi import HTTPException, Request, Response

from .. import auth_delivery, config, ratelimit, uow
from ..repositories import accounts, audit, challenges, workspaces
from ..repositories import identity as identities
from ..security import UNUSABLE_PASSWORD
from . import auth_service

logger = logging.getLogger("bidproof.auth")
OTP_SECONDS = 300
RESEND_SECONDS = 60
SEND_IP = ratelimit.Limit("otp-send-ip", 20, 3600)
SEND_ADDRESS = ratelimit.Limit("otp-send-identity", 5, 3600)
VERIFY_IP = ratelimit.Limit("otp-verify-ip", 100, 3600)


def fail(status: int, code: str, message: str, retry: int | None = None):
    raise HTTPException(status, {"code": code, "message": message},
                        headers={"Retry-After": str(retry)} if retry is not None else None)


def normalize(channel: str, value: str) -> str:
    value = re.sub(r"\s+", "", value)
    if channel == "email":
        value = value.casefold()
        if (not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", value)
                or len(value) > 254 or len(value.split("@")[0]) > 64 or ".." in value):
            fail(422, "INVALID_IDENTIFIER", "请输入有效的邮箱地址")
    elif channel == "sms":
        if re.fullmatch(r"1[3-9][0-9]{9}", value):
            value = "+86" + value
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            fail(422, "INVALID_IDENTIFIER", "请输入完整手机号，海外号码需包含国家区号")
    else:
        fail(422, "INVALID_IDENTIFIER", "请选择邮箱或手机号")
    return value


def digest(purpose: str, value: str) -> str:
    secret = auth_delivery.otp_secret()
    if len(secret) < 32:
        fail(503, "CHANNEL_UNAVAILABLE", "验证码登录尚未开通，请使用账号密码")
    return hmac.new(secret.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def _limit(limit: ratelimit.Limit, bucket: str) -> None:
    retry = challenges.consume_limit(limit.scope, bucket, limit.max_hits, limit.window_seconds)
    if retry:
        fail(429, "OTP_RATE_LIMIT", "验证码请求较多，请稍后重试", retry)



def request_challenge(request: Request, channel: str, raw_identifier: str) -> dict:
    identifier = normalize(channel, raw_identifier)
    if not auth_delivery.enabled(channel):
        fail(503, "CHANNEL_UNAVAILABLE", "此验证方式尚未开通，请选择其他方式")
    if channel == "sms":
        allowed = [item.strip() for item in auth_delivery.setting("SMS_ALLOWED_PREFIXES").split(",") if item.strip()]
        if not any(identifier.startswith(prefix) and re.fullmatch(r"\+[1-9][0-9]{0,3}", prefix) for prefix in allowed):
            fail(422, "INVALID_IDENTIFIER", "暂不支持此地区的手机号，请使用邮箱")
    ip = request.client.host if request.client else "unknown"
    address_digest = digest("identity", channel + ":" + identifier)
    _limit(SEND_IP, digest("ip", ip))
    # Reserve before counting identity hits: accidental double-clicks only cost cooldown,
    # while attempts to send to many recipients still consume the IP quota.
    now = datetime.now(UTC)
    challenge_id = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    retry = challenges.reserve({
        "challenge_id": challenge_id, "channel": channel, "identifier": identifier,
        "identifier_digest": address_digest, "code_digest": digest("code", challenge_id + ":" + code),
        "created_at": now.isoformat(), "expires_at": (now + timedelta(seconds=OTP_SECONDS)).isoformat(),
    }, now, RESEND_SECONDS)
    if retry:
        fail(429, "OTP_COOLDOWN", "验证码已发送，请稍后再获取", retry)
    try:
        _limit(SEND_ADDRESS, address_digest)
        auth_delivery.send(channel, identifier, code)
    except auth_delivery.DeliveryError:
        challenges.mark_delivery(challenge_id, successful=False)
        logger.warning("otp_delivery_failed", extra={"channel": channel})
        fail(503, "DELIVERY_UNAVAILABLE", "验证码暂时发送失败，请稍后重试", RESEND_SECONDS)
    except HTTPException:
        challenges.mark_delivery(challenge_id, successful=False)
        raise
    challenges.mark_delivery(challenge_id, successful=True)
    if channel == "email":
        local, domain = identifier.split("@")
        masked = local[:1] + "***@" + domain
    else:
        masked = identifier[:3] + " **** " + identifier[-4:]
    return {"challenge_id": challenge_id, "channel": channel, "masked_identifier": masked,
            "expires_in": OTP_SECONDS, "resend_after": RESEND_SECONDS}


def verify_challenge(request: Request, response: Response, challenge_id: str, code: str) -> dict:
    ip = request.client.host if request.client else "unknown"
    _limit(VERIFY_IP, digest("ip", ip))
    result, record = challenges.verify(challenge_id, digest("code", challenge_id + ":" + code), datetime.now(UTC))
    if result == "locked":
        fail(429, "OTP_LOCKED", "验证码尝试次数已用完，请重新获取", RESEND_SECONDS)
    if result == "expired":
        fail(410, "OTP_EXPIRED", "验证码已过期或已使用，请重新获取")
    if result != "verified" or record is None:
        fail(401, "OTP_INCORRECT", "验证码不正确，请检查后重试")
    user = verified_user("EMAIL" if record["channel"] == "email" else "PHONE", "bidproof", record["identifier"], record["identifier"])
    return auth_service._complete_login(request, response, user)


def verified_user(provider: str, issuer: str, subject: str, username: str) -> dict:
    """Never infer ownership from an existing mutable username or a matching email claim."""
    binding = identities.load_binding(provider, issuer, subject)
    if binding:
        user = accounts.by_id(binding["user_id"])
        if user is None or not bool(user.get("active", 1)):
            fail(403, "ACCOUNT_DISABLED", "账号已停用，请联系管理员")
        return user
    if not config.PERSONAL_SIGNUP:
        fail(403, "SIGNUP_CLOSED", "当前未开放新账号，请使用已有账号或联系管理员")
    if accounts.by_username(username):
        fail(409, "ACCOUNT_LINK_REQUIRED", "此邮箱或账号已有密码登录记录，请先使用原登录方式")
    workspace_id = uuid.uuid4().hex
    try:
        with uow.transaction():
            user = accounts.create(workspace_id, username, UNUSABLE_PASSWORD, "OWNER")
            workspaces.ensure(workspace_id, user["user_id"], "OWNER", "我的工作区")
            identities.bind_new(user["user_id"], provider, issuer, subject)
    except sqlalchemy.exc.IntegrityError:
        # Concurrent successful challenges may race to create the same verified identity.
        # The unique provider/issuer/subject binding rolls the losing workspace back.
        binding = identities.load_binding(provider, issuer, subject)
        user = accounts.by_id(binding["user_id"]) if binding else None
        if user is None or not bool(user.get("active", 1)):
            fail(409, "ACCOUNT_LINK_REQUIRED", "账号状态已更新，请重新登录")
        return user
    audit.record(workspace_id, user["user_id"], "AUTH_VERIFIED_SIGNUP", None, {"provider": provider})
    return user
