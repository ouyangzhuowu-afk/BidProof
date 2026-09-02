"""Scan job persistence."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .. import db


def create(job_id: str, workspace_id: str, run_id: str | None, status: str, payload: dict | None = None) -> None:
    db.create_scan_job(job_id, workspace_id, run_id, status, payload)


def load(job_id: str) -> dict[str, Any] | None:
    return db.load_scan_job(job_id)


def require_scoped(job_id: str, principal: dict[str, str]) -> dict[str, Any]:
    job = db.load_scan_job(job_id)
    if job is None or job["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="扫描作业不存在")
    return job


def update(job_id: str, status: str, **fields: Any) -> dict[str, Any] | None:
    return db.update_scan_job(job_id, status, **fields)


def start(job_id: str, **fields: Any) -> bool:
    """Claim a job for execution; False means another worker already claimed it."""
    return db.start_scan_job(job_id, **fields)


def claim_next() -> dict[str, Any] | None:
    return db.claim_next_scan_job()


def requeue_stale(max_age_seconds: int) -> int:
    return db.requeue_stale_scan_jobs(max_age_seconds)


def cancel(job_id: str) -> dict[str, Any] | None:
    return db.cancel_scan_job(job_id)


def link_run(job_id: str, run_id: str) -> None:
    db.link_scan_job(job_id, run_id)


def list_for_workspace(workspace_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return db.list_scan_jobs(workspace_id, limit)


def recoverable() -> list[dict[str, Any]]:
    return db.list_recoverable_jobs()


def status_counts() -> dict[str, int]:
    return db.scan_job_status_counts()
