"""Audit trail writes and reads.

P3 extends the recorded envelope with request IP, user agent and request id.
"""

from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib
import json

from .. import config, db


def record(
    workspace_id: str,
    user_id: str,
    event_type: str,
    run_id: str | None = None,
    payload: dict | None = None,
    *,
    outcome: str = "SUCCESS",
) -> None:
    db.record_audit_event(workspace_id, user_id, event_type, run_id, payload, outcome=outcome)


def events(workspace_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
    return db.list_audit_events(workspace_id, run_id)


def verify_chain(workspace_id: str) -> dict[str, Any]:
    return db.verify_audit_chain(workspace_id)


def export_worm_snapshot(workspace_id: str) -> Path:
    """Write an append-only JSON snapshot. Existing digest files are never overwritten."""
    events = db.list_audit_events(workspace_id)
    chain = db.verify_audit_chain(workspace_id)
    body = json.dumps({"chain": chain, "events": events}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    dest = config.DATA_DIR / "audit-worm" / f"{workspace_id}-{digest}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(body, encoding="utf-8")
    return dest
