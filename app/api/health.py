"""Liveness and operational health."""

from __future__ import annotations

import html

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)

from .. import config, observability
from ..authz import Permission, require
from ..config import PROJECT_ROOT
from ..identity import principal_of
from ..services import workspace_service

router = APIRouter()


@router.get("/", include_in_schema=False)
def landing() -> HTMLResponse:
    entry = PROJECT_ROOT / "static" / "marketing" / "index.html"
    if not entry.exists():
        return HTMLResponse("产品页面正在构建，请稍后再试。", status_code=503)
    origin = config.PUBLIC_ORIGIN
    source = entry.read_text(encoding="utf-8").replace("__PUBLIC_ORIGIN__", html.escape(origin, quote=True))
    # Local previews are not canonical public deployments.
    return HTMLResponse(source, headers={"Cache-Control": "no-cache"})


@router.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    if not config.PUBLIC_ORIGIN:
        return PlainTextResponse("User-agent: *\nDisallow: /\n")
    return PlainTextResponse("User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\n"
                             f"Sitemap: {config.PUBLIC_ORIGIN}/sitemap.xml\n")


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    urls = "".join(f"<url><loc>{html.escape(config.PUBLIC_ORIGIN + path)}</loc></url>"
                   for path in ("/", "/privacy")) if config.PUBLIC_ORIGIN else ""
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    + urls + '</urlset>', media_type="application/xml")


@router.get("/readyz", include_in_schema=False)
def readyz() -> JSONResponse:
    if not workspace_service.is_ready():
        return JSONResponse({"status": "not_ready"}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"status": "ready"}, headers={"Cache-Control": "no-store"})


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
