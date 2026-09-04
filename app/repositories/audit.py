"""Audit trail writes and reads.

P3 extends the recorded envelope with request IP, user agent and request id.
"""

from __future__ import annotations

from typing import Any

from .. import db


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
