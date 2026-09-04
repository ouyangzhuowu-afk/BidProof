"""Optional application-layer encryption for stored JSON documents.

Set `BIDPROOF_FIELD_ENCRYPTION_KEY` to enable. The key is stretched to a Fernet key so
customers can supply a passphrase (BYOK) rather than a raw 32-byte token.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Any

_fernet = None
_loaded = False


def _client():
    global _fernet, _loaded
    if _loaded:
        return _fernet
    _loaded = True
    secret = os.environ.get("BIDPROOF_FIELD_ENCRYPTION_KEY", "").strip()
    if not secret:
        return None
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


def protect(value: Any) -> Any:
    client = _client()
    if client is None or value is None:
        return value
    import json

    token = client.encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8")).decode("ascii")
    return {"_enc": "fernet", "v": token}


def reveal(value: Any) -> Any:
    if not isinstance(value, dict) or value.get("_enc") != "fernet":
        return value
    client = _client()
    if client is None:
        raise RuntimeError("stored field is encrypted but BIDPROOF_FIELD_ENCRYPTION_KEY is not set")
    import json

    return json.loads(client.decrypt(value["v"].encode("ascii")))
