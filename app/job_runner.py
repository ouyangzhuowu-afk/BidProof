"""One scan per child process: bounded lifetime, independent PDF interpreter, fenced writes."""
from __future__ import annotations

import asyncio
import os
import sys
import time

from . import config, db, job_leases
from .uploads import remove_tree

JOB_TIMEOUT_SECONDS = int(os.environ.get("BIDPROOF_JOB_TIMEOUT_SECONDS", "600"))


def beat_worker() -> None:
    (config.DATA_DIR / "worker-heartbeat").touch()


async def _stop(process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.wait()


async def supervise(job: dict) -> None:
    job_id, token = job["job_id"], job["lease_token"]
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.job_runner", job_id, token,
            cwd=str(config.PROJECT_ROOT),
        )
    except OSError:
        job_leases.update(job_id, token, status="FAILED", error="WORKER_START_FAILED",
                          progress_message="处理进程暂时无法启动，请稍后重试")
        return
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    try:
        while process.returncode is None:
            beat_worker()
            if not job_leases.update(job_id, token):
                await _stop(process)
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await _stop(process)
                job_leases.update(job_id, token, status="FAILED", error="SCAN_TIMEOUT",
                                  progress_message="扫描超过处理时限，请拆分文件后重试")
                break
            try:
                await asyncio.wait_for(process.wait(), timeout=min(5, remaining))
            except TimeoutError:
                pass
        # If the child exited without publishing success or an explicit failure, keep the
        # job retryable instead of leaving it RUNNING until its stale timeout.
        job_leases.update(job_id, token, status="FAILED", error="WORKER_EXITED",
                          progress_message="处理进程中断，可重试")
    finally:
        await _stop(process)
        run_id = job_leases.attempt_run_id(job_id, token)
        if db.load_run(run_id) is None:
            remove_tree(config.UPLOAD_DIR / run_id)
        current = db.load_scan_job(job_id) or {}
        if current.get("status") in {"CANCELLED", "COMPLETED"}:
            remove_tree(config.JOB_STAGING_DIR / job_id)


def main() -> None:
    from . import observability
    from .services.scan_service import process_job

    observability.configure()
    if len(sys.argv) != 3:
        raise SystemExit("An internal job id and lease are required")
    asyncio.run(process_job(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
