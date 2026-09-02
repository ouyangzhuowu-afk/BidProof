"""Credential and token primitives.

Kept free of framework and storage imports so the hashing parameters can be reviewed and
changed in one place.
"""

from __future__ import annotations

import base64
import hashlib
import secrets


PBKDF2_ITERATIONS = 240_000
SESSION_TOKEN_BYTES = 32
ACTION_TOKEN_BYTES = 32


def password_hash(password: str, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = password_hash(password, base64.urlsafe_b64decode(salt), int(iterations)).split("$", 3)[3]
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    """Hash a bearer-style token so only the digest is ever persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def new_action_token() -> str:
    return secrets.token_urlsafe(ACTION_TOKEN_BYTES)
