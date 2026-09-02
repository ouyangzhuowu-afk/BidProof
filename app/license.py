"""Deployment license gate.

On-premise installs may run without a key. When `BIDPROOF_LICENSE_REQUIRED=1`, startup refuses
to serve until `BIDPROOF_LICENSE_KEY` is present and well-formed, so an image cannot be copied
into a second estate by accident.
"""

from __future__ import annotations

from . import config


LICENSE_PREFIX = "bp-lic-"


class LicenseError(RuntimeError):
    pass


def valid_key(key: str) -> bool:
    cleaned = key.strip()
    return cleaned.startswith(LICENSE_PREFIX) and len(cleaned) >= 16


def check_on_startup() -> None:
    if not config.LICENSE_REQUIRED:
        return
    if not valid_key(config.LICENSE_KEY):
        raise LicenseError("BIDPROOF_LICENSE_REQUIRED=1 but BIDPROOF_LICENSE_KEY is missing or malformed")
