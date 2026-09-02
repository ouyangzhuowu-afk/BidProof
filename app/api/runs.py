"""Run creation, listing, inspection and review."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse

from .. import presenters
from ..authz import Permission, require
from ..identity import principal_of
from ..repositories import audit, collaboration, runs
from ..schemas import (
    AccuracyFeedbackRequest,
    BulkRunRequest,
    CommentRequest,
    DecisionRequest,
    RemediationCreateRequest,
    RemediationUpdateRequest,
    ReviewRequest,
    RunMetadataRequest,
)
from ..services import run_service, scan_service


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
async def create_run(
    request: Request,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_CREATE)
    return await scan_service.create_run(
        principal=principal,
        tender=tender,
        evidence=evidence,
        company_name=company_name,
        evidence_metadata=evidence_metadata,
        project_id=project_id,
    )


@router.get("")
def list_runs(
    request: Request,
    include_archived: bool = Query(default=False),
    project_id: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=80),
    favorite: bool | None = Query(default=None),
    assignee_id: str | None = Query(default=None, max_length=120),
    reviewer_id: str | None = Query(default=None, max_length=120),
    sort: str = Query(default="updated_desc", pattern="^(updated_desc|filename)$"),
) -> list[dict]:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    return run_service.listing(
        principal,
        include_archived=include_archived,
        project_id=project_id,
        search=search,
        tag=tag,
        favorite=favorite,
        assignee_id=assignee_id,
        reviewer_id=reviewer_id,
        sort=sort,
    )


@router.post("/bulk")
def bulk_manage_runs(request: Request, payload: BulkRunRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_DELETE if payload.action == "DELETE" else Permission.RUN_UPDATE)
    return run_service.bulk_manage(principal, payload)


@router.get("/{run_id}")
def get_run(request: Request, run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    return presenters.public_run(runs.require_scoped(run_id, principal))


@router.get("/{run_id}/files/{source_id}")
def download_run_file(request: Request, run_id: str, source_id: str) -> FileResponse:
    principal = principal_of(request)
    require(principal, Permission.EVIDENCE_DOWNLOAD)
    run = runs.require_scoped(run_id, principal)
    path, filename = run_service.source_file(run, source_id)
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.post("/{run_id}/rescan")
async def rescan_run(
    request: Request,
    run_id: str,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_CREATE)
    parent = runs.require_scoped(run_id, principal)
    return await scan_service.rescan_run(
        principal=principal,
        parent=parent,
        tender=tender,
        evidence=evidence,
        company_name=company_name,
        evidence_metadata=evidence_metadata,
        project_id=project_id,
    )


@router.get("/{run_id}/diff/{other_run_id}")
def diff_runs(request: Request, run_id: str, other_run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    current = runs.require_scoped(run_id, principal)
    other = runs.require_scoped(other_run_id, principal)
    return run_service.diff(current, other)


@router.get("/{run_id}/audit")
def get_run_audit(request: Request, run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.AUDIT_READ)
    runs.require_scoped(run_id, principal)
    return {"run_id": run_id, "events": audit.events(principal["workspace_id"], run_id)}


@router.patch("/{run_id}/metadata")
def update_run_metadata(request: Request, run_id: str, payload: RunMetadataRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_UPDATE)
    return run_service.update_metadata(principal, runs.require_scoped(run_id, principal), payload)


@router.post("/{run_id}/comments")
def create_comment(request: Request, run_id: str, payload: CommentRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_UPDATE)
    runs.require_scoped(run_id, principal)
    comment = collaboration.add_comment(principal["workspace_id"], run_id, principal["user_id"], payload.body.strip())
    audit.record(principal["workspace_id"], principal["user_id"], "COMMENT_ADDED", run_id, {"comment_id": comment["comment_id"]})
    return comment


@router.get("/{run_id}/comments")
def get_comments(request: Request, run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    runs.require_scoped(run_id, principal)
    return {"run_id": run_id, "comments": collaboration.comments(principal["workspace_id"], run_id)}


@router.post("/{run_id}/remediations", status_code=201)
def create_run_remediation(request: Request, run_id: str, payload: RemediationCreateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_UPDATE)
    return run_service.create_remediation(principal, runs.require_scoped(run_id, principal), payload)


@router.get("/{run_id}/remediations")
def get_run_remediations(request: Request, run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    runs.require_scoped(run_id, principal)
    return {"remediations": collaboration.remediations(principal["workspace_id"], run_id)}


@router.post("/{run_id}/accuracy-feedback")
def create_accuracy_feedback(request: Request, run_id: str, payload: AccuracyFeedbackRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_REVIEW)
    return run_service.add_accuracy_feedback(principal, runs.require_scoped(run_id, principal), payload)


@router.get("/{run_id}/requirements")
def list_requirements(
    request: Request,
    run_id: str,
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    run = runs.require_scoped(run_id, principal)
    return run_service.requirements(run, category, status, severity)


@router.get("/{run_id}/evidence")
def list_run_evidence(request: Request, run_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    run = runs.require_scoped(run_id, principal)
    return {"run_id": run_id, "assets": run.get("evidence_assets", [])}


@router.post("/{run_id}/review")
async def review_run(request: Request, run_id: str, payload: ReviewRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_REVIEW)
    return run_service.review(principal, runs.require_scoped(run_id, principal), payload)


@router.post("/{run_id}/decision")
def save_decision(request: Request, run_id: str, payload: DecisionRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_DECIDE)
    return run_service.record_decision(principal, runs.require_scoped(run_id, principal), payload)


@router.delete("/{run_id}")
def remove_run(request: Request, run_id: str) -> dict[str, str]:
    principal = principal_of(request)
    require(principal, Permission.RUN_DELETE)
    return run_service.delete(principal, runs.require_scoped(run_id, principal))


remediation_router = APIRouter(prefix="/api/remediations", tags=["runs"])


@remediation_router.patch("/{remediation_id}")
def patch_remediation(request: Request, remediation_id: str, payload: RemediationUpdateRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_UPDATE)
    item = collaboration.require_scoped_remediation(remediation_id, principal)
    updated = collaboration.update_remediation(remediation_id, payload.model_dump(exclude_unset=True))
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "REMEDIATION_UPDATED",
        item["run_id"],
        {"remediation_id": remediation_id, "status": updated["status"]},
    )
    return updated
