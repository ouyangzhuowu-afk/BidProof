"""Application assembly.

Routes live in `app.api`, workflows in `app.services`, and data access in
`app.repositories`. This module only wires them together.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .api import register_routers
from .repositories import jobs
from .services import scan_service


logger = logging.getLogger(__name__)

VERSION = "0.3.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if config.TRUSTED_HEADERS_IGNORED:
        logger.warning(
            "BIDPROOF_ALLOW_TRUSTED_HEADERS is set but ignored because BIDPROOF_ENV=%s; "
            "self-asserted identity headers are only honoured under BIDPROOF_ENV=test",
            config.ENVIRONMENT,
        )
    # Jobs left PENDING or RUNNING by a previous process are re-driven here. P4 replaces this
    # in-process recovery with a durable queue consumed by a separate worker.
    tasks = [asyncio.create_task(scan_service.process_job(job["job_id"])) for job in jobs.recoverable()]
    yield
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(title="Bid Evidence Agent", version=VERSION, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=config.PROJECT_ROOT / "static"), name="static")
    register_routers(app)
    return app


app = create_app()
