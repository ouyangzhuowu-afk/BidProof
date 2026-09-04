"""Application assembly.

Routes live in `app.api`, workflows in `app.services`, and data access in
`app.repositories`. This module only wires them together.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .api import register_routers
from .http import install_middleware


logger = logging.getLogger("bidproof")

VERSION = "0.4.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from . import db, license, observability, queue

    observability.configure()
    license.check_on_startup()
    try:
        cleaned = db.cleanup_expired()
        logger.info("Startup cleanup: %s", cleaned)
    except Exception:
        logger.exception("Startup cleanup failed")
    if config.TRUSTED_HEADERS_IGNORED:
        logger.warning(
            "BIDPROOF_ALLOW_TRUSTED_HEADERS is set but ignored because BIDPROOF_ENV=%s; "
            "self-asserted identity headers are only honoured under BIDPROOF_ENV=test",
            config.ENVIRONMENT,
        )
    tasks = await queue.start_inline_recovery()
    yield
    await queue.stop_inline_recovery(tasks)


def create_app() -> FastAPI:
    production = config.ENVIRONMENT == "production"
    app = FastAPI(
        title="Bid Evidence Agent",
        version=VERSION,
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    install_middleware(app)
    app.mount("/static", StaticFiles(directory=config.PROJECT_ROOT / "static"), name="static")
    register_routers(app)
    return app


app = create_app()
