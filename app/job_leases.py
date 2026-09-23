"""Atomic execution ownership. A reclaimed job never accepts its old worker's result."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from . import db
from .models import scan_jobs


class LeaseLost(RuntimeError):
    """The job was cancelled, completed, or handed to a different attempt."""


def attempt_run_id(job_id: str, token: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_OID, f"bidproof:{job_id}:{token}").hex


def retry(job_id: str, *, path=None) -> bool:
    with db.connect(path) as connection:
        result = connection.execute(sa.update(scan_jobs).where(
            scan_jobs.c.job_id == job_id, scan_jobs.c.status.in_(("FAILED", "PENDING")),
            scan_jobs.c.cancel_requested == 0, scan_jobs.c.attempts < db.MAX_JOB_ATTEMPTS,
        ).values(status="PENDING", lease_token=None, error=None,
                 progress_message="已重新排队", updated_at=datetime.now(UTC).isoformat()))
        return result.rowcount == 1


def claim(job_id: str | None = None, *, path=None) -> dict | None:
    bound = db.engine(path)
    query = sa.select(scan_jobs).where(
        scan_jobs.c.status == "PENDING", scan_jobs.c.cancel_requested == 0,
        scan_jobs.c.attempts < db.MAX_JOB_ATTEMPTS,
    ).order_by(scan_jobs.c.created_at, scan_jobs.c.job_id).limit(1)
    if job_id is not None:
        query = query.where(scan_jobs.c.job_id == job_id)
    with bound.begin() as connection:
        if bound.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        row = connection.execute(query).mappings().first()
        if row is None:
            return None
        token = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        updated = connection.execute(sa.update(scan_jobs).where(
            scan_jobs.c.job_id == row["job_id"], scan_jobs.c.status == "PENDING",
            scan_jobs.c.cancel_requested == 0,
        ).values(status="RUNNING", lease_token=token, attempts=scan_jobs.c.attempts + 1,
                 updated_at=now, error=None, progress_message="准备解析文件"))
        if updated.rowcount != 1:
            return None
        result = dict(row)
        result.update(status="RUNNING", lease_token=token, attempts=row["attempts"] + 1,
                      updated_at=now)
        result["payload"] = result.pop("payload_json")
        return result


def update(job_id: str, token: str, *, path=None, **fields) -> bool:
    fields["updated_at"] = datetime.now(UTC).isoformat()
    with db.connect(path) as connection:
        result = connection.execute(sa.update(scan_jobs).where(
            scan_jobs.c.job_id == job_id, scan_jobs.c.status == "RUNNING",
            scan_jobs.c.cancel_requested == 0, scan_jobs.c.lease_token == token,
        ).values(**fields))
        return result.rowcount == 1


def fence_publication(job_id: str, token: str | None, *, path=None) -> None:
    """Call inside the same transaction that inserts the run and marks completion.

    The conditional UPDATE holds the row lock until publication commits, so cancellation
    and publication have a single ordering on both SQLite and PostgreSQL.
    """
    with db.connect(path) as connection:
        condition = [scan_jobs.c.job_id == job_id, scan_jobs.c.status == "RUNNING",
                     scan_jobs.c.cancel_requested == 0]
        condition.append(scan_jobs.c.lease_token == token if token else scan_jobs.c.lease_token.is_(None))
        result = connection.execute(sa.update(scan_jobs).where(*condition).values(
            updated_at=datetime.now(UTC).isoformat()))
        if result.rowcount != 1:
            raise LeaseLost("Scan execution no longer owns this job")
