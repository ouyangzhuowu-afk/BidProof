"""RFC 6238 time-based one-time passwords.

Implemented against the standard with the standard library so enabling MFA does not add a
dependency to an air-gapped install.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


DIGITS = 6
PERIOD_SECONDS = 30
# One step either side, which covers clock skew between the server and an authenticator app.
DEFAULT_TOLERANCE_STEPS = 1
SECRET_BYTES = 20
RECOVERY_CODE_COUNT = 8


def new_secret() -> str:
    """A base32 secret in the form authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def new_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]


def counter_at(moment: float | None = None, period: int = PERIOD_SECONDS) -> int:
    return int((moment if moment is not None else time.time()) // period)


def code_for_counter(secret: str, counter: int, digits: int = DIGITS) -> str:
    key = base64.b32decode(_pad(secret), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def verify(
    secret: str,
    code: str,
    *,
    last_counter: int = 0,
    moment: float | None = None,
    tolerance: int = DEFAULT_TOLERANCE_STEPS,
) -> int | None:
    """Return the counter a code belongs to, or None if it is invalid or already used.

    Codes at or below `last_counter` are rejected so a code observed in transit cannot be
    replayed within its validity window.
    """
    submitted = code.strip().replace(" ", "")
    if not submitted.isdigit():
        return None
    current = counter_at(moment)
    for step in range(-tolerance, tolerance + 1):
        candidate = current + step
        if candidate <= last_counter:
            continue
        if hmac.compare_digest(code_for_counter(secret, candidate), submitted):
            return candidate
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "BidProof") -> str:
    """The otpauth:// URI an authenticator app scans."""
    label = quote(f"{issuer}:{account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer, safe='')}"
        f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD_SECONDS}"
    )


def _pad(secret: str) -> str:
    padding = "=" * (-len(secret) % 8)
    return secret + padding
