"""Server-only OTP delivery adapters. Credentials and codes never enter API responses."""
from __future__ import annotations

import base64
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode
from urllib.request import Request

from . import config, oidc


class DeliveryError(RuntimeError):
    pass


def setting(name: str, default: str = "") -> str:
    return os.environ.get("BIDPROOF_" + name, default).strip()


def otp_secret() -> str:
    return setting("OTP_SECRET")


def enabled(channel: str) -> bool:
    if len(otp_secret()) < 32:
        return False
    if channel == "email":
        provider = setting("EMAIL_PROVIDER", "smtp")
        if provider == "resend":
            return bool(setting("RESEND_API_KEY") and setting("EMAIL_FROM"))
        if provider != "smtp":
            return False
        secure = setting("SMTP_SECURITY", "starttls")
        host = setting("SMTP_HOST")
        transport_ok = secure in {"starttls", "tls"} or (
            secure == "plain" and config.ENVIRONMENT != "production" and host in {"localhost", "127.0.0.1", "::1"}
        )
        return bool(host and setting("SMTP_FROM") and transport_ok)
    if channel == "sms":
        return bool(re.fullmatch(r"AC[0-9a-fA-F]{32}", setting("TWILIO_ACCOUNT_SID"))
                    and setting("TWILIO_AUTH_TOKEN") and setting("TWILIO_FROM")
                    and setting("SMS_ALLOWED_PREFIXES"))
    return False


def send(channel: str, identifier: str, code: str) -> None:
    if not enabled(channel):
        raise DeliveryError("delivery channel unavailable")
    try:
        if channel == "email":
            if setting("EMAIL_PROVIDER", "smtp") == "resend":
                _resend(identifier, code)
            else:
                _email(identifier, code)
        else:
            _sms(identifier, code)
    except (OSError, ValueError, smtplib.SMTPException, oidc.OIDCError) as exc:
        # Provider responses may contain recipient addresses; never propagate their bodies.
        raise DeliveryError("delivery provider unavailable") from exc


def _email(recipient: str, code: str) -> None:
    message = EmailMessage()
    message["From"] = setting("SMTP_FROM")
    message["To"] = recipient
    message["Subject"] = "BidProof 登录验证码"
    message.set_content(f"你的 BidProof 验证码是：{code}\n\n5 分钟内有效，请勿转发给他人。\n如果不是你本人操作，请忽略此邮件。")
    security = setting("SMTP_SECURITY", "starttls")
    port = int(setting("SMTP_PORT", "465" if security == "tls" else "587"))
    factory = smtplib.SMTP_SSL if security == "tls" else smtplib.SMTP
    options = {"timeout": 10}
    if security == "tls":
        options["context"] = ssl.create_default_context()
    with factory(setting("SMTP_HOST"), port, **options) as client:
        if security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if setting("SMTP_USERNAME"):
            client.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        refused = client.send_message(message)
        if refused:
            raise DeliveryError("recipient refused")


def _sms(recipient: str, code: str) -> None:
    sid = setting("TWILIO_ACCOUNT_SID")
    credential = base64.b64encode(f"{sid}:{setting('TWILIO_AUTH_TOKEN')}".encode()).decode()
    request = Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=urlencode({"To": recipient, "From": setting("TWILIO_FROM"),
                        "Body": f"[BidProof] 验证码 {code}，5 分钟内有效，请勿转发。"}).encode(),
        headers={"Authorization": "Basic " + credential, "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    result = oidc._fetch_json(request, timeout=10)
    if not result.get("sid") or result.get("status") in {"failed", "undelivered", "canceled"}:
        raise DeliveryError("message not accepted")


def _resend(recipient: str, code: str) -> None:
    # HTTPS delivery works on hosts that block SMTP egress, including Render Free.
    payload = {"from": setting("EMAIL_FROM"), "to": [recipient],
               "subject": "BidProof 登录验证码",
               "text": f"你的 BidProof 验证码是：{code}\n\n5 分钟内有效，请勿转发给他人。\n如果不是你本人操作，请忽略此邮件。"}
    request = Request("https://api.resend.com/emails", data=json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer " + setting("RESEND_API_KEY"),
                               "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "BidProof"},
                      method="POST")
    result = oidc._fetch_json(request, timeout=10)
    if not isinstance(result.get("id"), str) or not result["id"]:
        raise DeliveryError("email not accepted")
