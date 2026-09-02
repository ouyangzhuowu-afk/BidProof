"""Run persistence and the workspace-scoped lookups every route must use."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .. import db


def load(run_id: str) -> dict[str, Any] | None:
    return db.load_run(run_id)


def save(run: dict[str, Any]) -> None:
    db.save_run(run)


def delete(run_id: str) -> bool:
    return db.delete_run(run_id)


def list_for_workspace(workspace_id: str) -> list[dict[str, Any]]:
    """Runs belonging to one workspace, newest first.

    The predicate is applied in SQL, so another tenant's documents are never loaded into this
    request in the first place.
    """
    return db.list_runs(workspace_id=workspace_id)


def require(run_id: str) -> dict[str, Any]:
    run = db.load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return run


def require_scoped(run_id: str, principal: dict[str, str]) -> dict[str, Any]:
    """Load a run only if it belongs to the caller's workspace.

    Answers 404 rather than 403 so a caller cannot use the status code to discover that a run
    id exists in another workspace.
    """
    run = require(run_id)
    if run.get("workspace_id", "local") != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return run


def find_duplicates(workspace_id: str, tender_sha256: str) -> list[str]:
    return db.find_duplicate_run_ids(workspace_id, tender_sha256)


def expired_archived_ids(workspace_id: str, cutoff: str) -> list[str]:
    return db.list_expired_archived_run_ids(workspace_id, cutoff)
