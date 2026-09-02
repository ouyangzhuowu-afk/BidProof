"""Liveness and operational health."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from .. import config, observability
from ..config import PROJECT_ROOT
from ..authz import Permission, require
from ..identity import principal_of
from ..services import workspace_service


router = APIRouter()


@router.get("/", include_in_schema=False)
def landing() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "static" / "landing.html")


@router.get("/app", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "static" / "index.html")


@router.get("/healthz")
def healthz(request: Request, detail: bool = Query(default=False)) -> dict:
    if not detail:
        # Liveness stays anonymous for load balancers and carries no operational state.
        return {"status": "ok", "service": "bid-evidence-agent"}
    # Detail names the database, backup recency and failed job counts.
    principal = principal_of(request)
    require(principal, Permission.HEALTH_DETAIL_READ)
    return workspace_service.health_detail()


@router.get("/metrics", include_in_schema=False)
def metrics(request: Request) -> PlainTextResponse:
    if not config.METRICS_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")
    principal = principal_of(request)
    require(principal, Permission.METRICS_READ)
    return PlainTextResponse(observability.prometheus_text(), media_type="text/plain; version=0.0.4")
