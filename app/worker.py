"""Independent scan worker.

Usage: `python -m app.worker`

The API enqueues PENDING rows; this process claims them. Running it as a separate container
means a crash of the HTTP process cannot drop a job that already returned 202.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time

from . import config, observability
from .job_runner import beat_worker
from .queue import run_one
from .repositories import jobs

logger = logging.getLogger("bidproof.worker")
_stop = False


def _request_stop(*_args) -> None:
    global _stop
    _stop = True


async def loop() -> None:
    from . import license

    observability.configure()
    config.validate_runtime_security()
    license.check_on_startup()
    requeued = jobs.requeue_stale(config.JOB_STALE_SECONDS)
    if requeued:
        logger.info("requeued_stale_jobs", extra={"count": requeued})
    while not _stop:
        beat_worker()
        jobs.requeue_stale(config.JOB_STALE_SECONDS)
        job_id = await run_one()
        if job_id is None:
            await asyncio.sleep(config.JOB_POLL_SECONDS)


def main() -> None:
    if "--healthcheck" in sys.argv:
        heartbeat = config.DATA_DIR / "worker-heartbeat"
        raise SystemExit(0 if heartbeat.exists() and time.time() - heartbeat.stat().st_mtime < 30 else 1)
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    asyncio.run(loop())


if __name__ == "__main__":
    main()
