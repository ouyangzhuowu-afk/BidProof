"""OCR cloud egress dual-check policy (factory + final HTTP send).

Default is deny. Cloud OCR may run only when every gate below passes:

1. Master switch BIDPROOF_OCR_EGRESS_ALLOWED=1
2. Mode redacted_only / vpc_private
3. Written approval token BIDPROOF_OCR_EGRESS_APPROVAL (non-empty, T1-/T2- prefix)
4. Approval not expired (BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT when set)
5. Optional doc pin BIDPROOF_OCR_EGRESS_DOC_SHA256 matches the request fingerprint
6. API key present (auth)
7. Destination host on the allow-list (including redirect targets)

Do not enable egress in production without Joe's written T1/T2 approval.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

DEFAULT_ALLOWED_HOSTS = frozenset(
    {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "ocr-vpc.cn-shanghai.aliyuncs.com",
        "ocr-vpc.cn-hangzhou.aliyuncs.com",
        "ocr-vpc.cn-beijing.aliyuncs.com",
    }
)

_APPROVAL_PREFIX = re.compile(r"^(T1|T2)-[A-Za-z0-9._-]{8,}$")


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    reason: str
    mode: str = "never"
    approval_id: str = ""
    endpoint_host: str = ""

    def raise_if_denied(self) -> None:
        if not self.allowed:
            raise EgressDenied(self.reason)


class EgressDenied(RuntimeError):
    """Raised when a cloud OCR send is blocked by policy."""


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def egress_mode() -> str:
    mode = os.getenv("BIDPROOF_OCR_EGRESS_MODE", "never").strip().lower()
    if mode in {"redacted_only", "redacted", "t1"}:
        return "redacted_only"
    if mode in {"vpc_private", "vpc", "t2"}:
        return "vpc_private"
    return "never"


def master_switch_on() -> bool:
    return _env_flag("BIDPROOF_OCR_EGRESS_ALLOWED", "0")


def approval_token() -> str:
    return os.getenv("BIDPROOF_OCR_EGRESS_APPROVAL", "").strip()


def approval_expires_at() -> datetime | None:
    raw = os.getenv("BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT", "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def pinned_doc_sha256() -> str:
    return os.getenv("BIDPROOF_OCR_EGRESS_DOC_SHA256", "").strip().lower()


def allowed_hosts() -> frozenset[str]:
    raw = os.getenv("BIDPROOF_OCR_EGRESS_ALLOWED_HOSTS", "").strip()
    if not raw:
        return DEFAULT_ALLOWED_HOSTS
    hosts = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(hosts) if hosts else DEFAULT_ALLOWED_HOSTS


def api_key_present() -> bool:
    return bool(os.getenv("QWEN_OCR_API_KEY", "").strip())


def host_allowed(url_or_host: str) -> bool:
    value = (url_or_host or "").strip().lower()
    if not value:
        return False
    if "://" not in value:
        host = value.split("/")[0].split(":")[0]
    else:
        host = (urlparse(value).hostname or "").lower()
    if not host:
        return False
    allowed = allowed_hosts()
    if host in allowed:
        return True
    # Allow exact subdomain matches listed with a leading dot convention is unused;
    # vpc endpoints are listed explicitly. Reject everything else.
    return False


def _approval_valid() -> tuple[bool, str]:
    token = approval_token()
    if not token:
        return False, "no_auth_approval"
    if not _APPROVAL_PREFIX.match(token):
        return False, "no_auth_approval"
    expires = approval_expires_at()
    if expires is None and os.getenv("BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT", "").strip():
        return False, "approval_expired_or_invalid"
    if expires is not None:
        now = datetime.now(timezone.utc)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            return False, "approval_expired"
    return True, token


def evaluate_cloud_egress(
    *,
    endpoint: str = "",
    doc_sha256: str | None = None,
    redirect_url: str | None = None,
    require_endpoint: bool = False,
) -> EgressDecision:
    """Single decision used by factory and final HTTP dual-check."""
    mode = egress_mode()
    if not master_switch_on():
        return EgressDecision(False, "egress_disabled", mode=mode)
    if mode == "never":
        return EgressDecision(False, "egress_mode_never", mode=mode)

    ok, approval_or_reason = _approval_valid()
    if not ok:
        return EgressDecision(False, approval_or_reason, mode=mode)

    if not api_key_present():
        return EgressDecision(False, "no_auth_api_key", mode=mode, approval_id=approval_or_reason)

    pin = pinned_doc_sha256()
    if pin:
        provided = (doc_sha256 or "").strip().lower()
        if not provided or provided != pin:
            return EgressDecision(
                False,
                "doc_mismatch",
                mode=mode,
                approval_id=approval_or_reason,
            )

    host = ""
    if endpoint:
        host = (urlparse(endpoint).hostname or "").lower()
        if not host_allowed(endpoint):
            return EgressDecision(
                False,
                "endpoint_not_allowlisted",
                mode=mode,
                approval_id=approval_or_reason,
                endpoint_host=host,
            )
    elif require_endpoint:
        return EgressDecision(
            False,
            "endpoint_missing",
            mode=mode,
            approval_id=approval_or_reason,
        )

    if redirect_url is not None:
        redirect_host = (urlparse(redirect_url).hostname or "").lower()
        if not host_allowed(redirect_url):
            return EgressDecision(
                False,
                "bad_redirect",
                mode=mode,
                approval_id=approval_or_reason,
                endpoint_host=redirect_host or host,
            )

    return EgressDecision(
        True,
        "allowed",
        mode=mode,
        approval_id=approval_or_reason,
        endpoint_host=host,
    )


def cloud_egress_permitted(*, endpoint: str = "", doc_sha256: str | None = None) -> bool:
    return evaluate_cloud_egress(endpoint=endpoint, doc_sha256=doc_sha256).allowed


def assert_factory_cloud_allowed(*, endpoint: str = "", doc_sha256: str | None = None) -> EgressDecision:
    """Factory-time check before constructing a live cloud adapter."""
    decision = evaluate_cloud_egress(endpoint=endpoint, doc_sha256=doc_sha256)
    return decision


def assert_http_send_allowed(
    *,
    endpoint: str,
    doc_sha256: str | None = None,
    redirect_url: str | None = None,
) -> EgressDecision:
    """Final send-time dual-check immediately before HTTP POST."""
    decision = evaluate_cloud_egress(
        endpoint=endpoint,
        doc_sha256=doc_sha256,
        redirect_url=redirect_url,
        require_endpoint=True,
    )
    decision.raise_if_denied()
    return decision


def policy_snapshot() -> dict[str, Any]:
    """Safe diagnostics — never includes API keys or raw approval secrets beyond id."""
    ok, approval = _approval_valid()
    return {
        "egress_allowed_flag": master_switch_on(),
        "egress_mode": egress_mode(),
        "approval_present": ok,
        "approval_id": approval if ok else "",
        "approval_expires_at": os.getenv("BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT", "").strip(),
        "doc_pin_set": bool(pinned_doc_sha256()),
        "api_key_present": api_key_present(),
        "allowed_hosts": sorted(allowed_hosts()),
    }
