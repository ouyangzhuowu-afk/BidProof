"""Durable scan job queue.

Jobs live in `scan_jobs`. A worker claims the oldest PENDING row; PostgreSQL does that with
SKIP LOCKED so two replicas cannot take the same job. The API process only runs jobs itself
when `BIDPROOF_JOB_RUNNER=inline`.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import BackgroundTasks

from . import config, observability
from .repositories import jobs
from .services import scan_service


logger = logging.getLogger("bidproof.queue")


def dispatch(job_id: str, background_tasks: BackgroundTasks | None = None) -> None:
    """Enqueue work. Inline mode runs the job before the HTTP response is fully torn down."""
    if config.JOB_RUNNER != "inline":
        return
    if background_tasks is None:
        return
    background_tasks.add_task(scan_service.process_job, job_id)


async def run_one() -> str | None:
    """Claim and execute a single job. Returns the job id, or None if the queue was empty."""
    claimed = jobs.claim_next()
    if claimed is None:
        return None
    observability.record_job_claim()
    await scan_service.process_job(claimed["job_id"])
    return claimed["job_id"]


async def start_inline_recovery() -> list[asyncio.Task]:
    """Re-drive leftover jobs in the API process, only when this process is the runner."""
    requeued = jobs.requeue_stale(config.JOB_STALE_SECONDS)
    if requeued:
        logger.info("requeued_stale_jobs", extra={"count": requeued})
    if config.JOB_RUNNER != "inline":
        return []
    return [asyncio.create_task(scan_service.process_job(job["job_id"])) for job in jobs.recoverable()]


async def stop_inline_recovery(tasks: list[asyncio.Task]) -> None:
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
