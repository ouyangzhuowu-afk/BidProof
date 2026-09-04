"""Liveness and operational health."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

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
    return FileResponse(
        PROJECT_ROOT / "static" / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/privacy")
def public_privacy_page() -> FileResponse:
    """Shown before login so collection notice is not behind authentication."""
    return FileResponse(PROJECT_ROOT / "static" / "privacy.html")


@router.get("/api/privacy")
def public_privacy() -> dict:
    payload = workspace_service.privacy("public")
    payload["data_region"] = config.DATA_REGION
    return payload


@router.get("/api/sample-tender")
def sample_tender(request: Request) -> Response:
    """A one-page public-procurement-style PDF so a new owner can try a scan immediately."""
    principal = principal_of(request)
    require(principal, Permission.RUN_CREATE)
    import fitz

    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "招标文件（样例）\n资格要求：投标人须提供有效营业执照。\n交货期：合同签订后 30 日内。\n",
        fontsize=12,
    )
    payload = document.tobytes()
    document.close()
    return Response(content=payload, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="sample-tender.pdf"'})


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
