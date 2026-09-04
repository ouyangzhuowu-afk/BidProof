"""Background scan job endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from ..authz import Permission, require
from ..identity import principal_of
from ..queue import dispatch
from ..repositories import audit, jobs
from ..services import scan_service


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _without_payload(job: dict) -> dict:
    return {key: value for key, value in job.items() if key != "payload"}


@router.get("")
def get_scan_jobs(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> dict:
    principal = principal_of(request)
    require(principal, Permission.JOB_READ)
    return {
        "workspace_id": principal["workspace_id"],
        "jobs": [_without_payload(job) for job in jobs.list_for_workspace(principal["workspace_id"], limit)],
    }


@router.get("/{job_id}")
def get_scan_job(request: Request, job_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.JOB_READ)
    return _without_payload(jobs.require_scoped(job_id, principal))


@router.get("/{job_id}/events")
async def stream_scan_job(request: Request, job_id: str):
    principal = principal_of(request)
    require(principal, Permission.JOB_READ)
    jobs.require_scoped(job_id, principal)

    async def events():
        delay = 0.75
        while True:
            if await request.is_disconnected():
                break
            job = _without_payload(jobs.require_scoped(job_id, principal))
            yield f"data: {json.dumps(job, ensure_ascii=False)}\n\n"
            if job.get("status") in {"COMPLETED", "FAILED", "CANCELLED", "DEAD"}:
                break
            await asyncio.sleep(delay)
            delay = min(5.0, delay * 1.4)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("", status_code=202)
async def enqueue_scan_job(
    request: Request,
    background_tasks: BackgroundTasks,
    tender: Annotated[UploadFile, File(...)],
    evidence: Annotated[list[UploadFile] | None, File()] = None,
    company_name: Annotated[str, Form()] = "未填写企业",
    evidence_metadata: Annotated[str | None, Form()] = None,
    project_id: Annotated[str | None, Form()] = None,
) -> dict:
    principal = principal_of(request)
    require(principal, Permission.JOB_MANAGE)
    job_id = await scan_service.stage_job(
        principal=principal,
        tender=tender,
        evidence=evidence,
        company_name=company_name,
        evidence_metadata=evidence_metadata,
        project_id=project_id,
    )
    dispatch(job_id, background_tasks)
    return {"job_id": job_id, "status": "PENDING"}


@router.post("/{job_id}/retry", status_code=202)
def retry_scan_job(request: Request, job_id: str, background_tasks: BackgroundTasks) -> dict:
    principal = principal_of(request)
    require(principal, Permission.JOB_MANAGE)
    job = jobs.require_scoped(job_id, principal)
    if job["status"] not in {"FAILED", "PENDING"}:
        raise HTTPException(status_code=409, detail="当前作业状态不可重试")
    if int(job.get("attempts") or 0) >= jobs.MAX_ATTEMPTS:
        raise HTTPException(status_code=409, detail="该作业已超过重试上限")
    jobs.update(job_id, "PENDING", attempts=int(job.get("attempts", 0)), error=None, cancel_requested=False, progress_message="已重新排队")
    dispatch(job_id, background_tasks)
    return {"job_id": job_id, "status": "PENDING"}


@router.post("/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.JOB_MANAGE)
    job = jobs.require_scoped(job_id, principal)
    if job["status"] not in {"PENDING", "RUNNING"}:
        raise HTTPException(status_code=409, detail="当前作业状态不可取消")
    cancelled = jobs.cancel(job_id)
    audit.record(principal["workspace_id"], principal["user_id"], "SCAN_JOB_CANCELLED", job.get("run_id"), {"job_id": job_id})
    return {"job_id": job_id, "status": cancelled["status"] if cancelled else "CANCELLED"}
