"""Report export endpoints for a single run, in bulk, and for the audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from ..authz import Permission, require
from ..identity import principal_of
from ..repositories import runs
from ..schemas import BulkReportRequest
from ..services import report_service


router = APIRouter(tags=["reports"])


def _attachment(run_id: str, extension: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="bidproof-{run_id[:12]}.{extension}"'}


@router.post("/api/runs/bulk/report.zip")
def bulk_report_zip(request: Request, payload: BulkReportRequest) -> Response:
    principal = principal_of(request)
    require(principal, Permission.REPORT_BULK_EXPORT)
    archive = report_service.bulk_pdf_archive(principal, payload.run_ids, payload.format)
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="bidproof-reports.zip"'},
    )


@router.get("/api/runs/{run_id}/report.html", response_class=HTMLResponse)
def export_report_html(request: Request, run_id: str) -> HTMLResponse:
    principal = principal_of(request)
    require(principal, Permission.REPORT_EXPORT)
    run = runs.require_scoped(run_id, principal)
    return HTMLResponse(content=report_service.html_report(run), headers=_attachment(run_id, "html"))


@router.get("/api/runs/{run_id}/report.csv")
def export_report_csv(request: Request, run_id: str) -> Response:
    principal = principal_of(request)
    require(principal, Permission.REPORT_EXPORT)
    run = runs.require_scoped(run_id, principal)
    return Response(
        content=report_service.csv_report(run),
        media_type="text/csv; charset=utf-8",
        headers=_attachment(run_id, "csv"),
    )


@router.get("/api/runs/{run_id}/report.pdf")
def export_report_pdf(request: Request, run_id: str) -> Response:
    principal = principal_of(request)
    require(principal, Permission.REPORT_EXPORT)
    run = runs.require_scoped(run_id, principal)
    return Response(
        content=report_service.pdf_report(run),
        media_type="application/pdf",
        headers=_attachment(run_id, "pdf"),
    )


@router.get("/api/audit/export.csv")
def export_audit_csv(request: Request) -> Response:
    principal = principal_of(request)
    require(principal, Permission.AUDIT_EXPORT)
    return Response(
        content=report_service.audit_csv(principal["workspace_id"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=bidproof-audit.csv"},
    )
