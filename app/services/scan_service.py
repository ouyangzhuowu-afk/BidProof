"""The scan pipeline: intake, extraction, rule evaluation and persistence.

Interactive requests and queued jobs both land in `create_run`, which takes an already
resolved principal. Before this existed the job worker re-entered the HTTP handler with a
synthetic request, which is why identity had to be replayed through headers.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("bidproof.scan")
from contextlib import ExitStack
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .. import config, presenters
from ..extraction import ExtractionError, extract_file
from ..identity import InternalJobContext
from ..repositories import audit, jobs, projects, runs
from ..rules import extract_requirements, match_evidence
from ..schemas import EvidenceMetadata
from ..state import advance_state, initial_research_state, utc_now
from ..uploads import (
    is_supported,
    remove_tree,
    safe_filename,
    save_upload,
    validate_upload_content,
)


TENDER_SOURCE_ID = "TENDER-001"


def parse_evidence_metadata(raw: str | None) -> dict[str, EvidenceMetadata]:
    import json

    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="evidence_metadata 必须是 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="evidence_metadata 必须是对象")
    result: dict[str, EvidenceMetadata] = {}
    for filename, value in payload.items():
        if not isinstance(filename, str) or not isinstance(value, dict):
            raise HTTPException(status_code=400, detail="evidence_metadata 格式无效")
        result[filename] = EvidenceMetadata(**value)
    return result


def _resolve_project(principal: dict[str, str], project_id: str | None) -> dict:
    project = projects.ensure_default(principal["workspace_id"]) if not project_id else projects.load(project_id)
    if project is None or project["workspace_id"] != principal["workspace_id"]:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project["archived_at"]:
        raise HTTPException(status_code=409, detail="归档项目不能创建新扫描")
    return project


async def create_run(
    *,
    principal: dict[str, str],
    tender: UploadFile,
    evidence: list[UploadFile] | None = None,
    company_name: str = "未填写企业",
    evidence_metadata: str | None = None,
    project_id: str | None = None,
    queued_job_id: str | None = None,
) -> dict:
    """Scan one tender plus its supporting evidence and persist the resulting run.

    `queued_job_id` binds the run to an already queued job; it must only ever come from a
    server-constructed job context, never from client input.
    """
    project = _resolve_project(principal, project_id)
    if not is_supported(tender.filename):
        raise HTTPException(status_code=400, detail="招标文件支持 PDF、DOCX、XLSX、PPTX、TXT、MD")
    metadata = parse_evidence_metadata(evidence_metadata)
    run_id = uuid.uuid4().hex
    job_id = queued_job_id or uuid.uuid4().hex
    if queued_job_id:
        jobs.update(job_id, "RUNNING")
    else:
        jobs.create(job_id, principal["workspace_id"], run_id, "RUNNING")

    run_dir = config.UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    tender_path = run_dir / safe_filename(tender.filename)
    try:
        tender_sha256 = await save_upload(tender, tender_path)
        validate_upload_content(tender_path)
    except HTTPException:
        remove_tree(run_dir)
        jobs.update(job_id, "FAILED", attempts=1, error="UPLOAD_REJECTED")
        raise

    duplicate_run_ids = runs.find_duplicates(principal["workspace_id"], tender_sha256)
    evidence_files: list[dict] = []
    evidence_assets: list[dict] = []
    evidence_pages: list[dict] = []

    for index, upload in enumerate(evidence or [], start=1):
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix.lower()
        if not is_supported(upload.filename):
            remove_tree(run_dir)
            jobs.update(job_id, "FAILED", attempts=1, error="UNSUPPORTED_EVIDENCE_FORMAT", progress_message="企业证据格式不受支持")
            raise HTTPException(status_code=400, detail="企业证据支持 PDF、DOCX、XLSX、PPTX、TXT、MD")
        target = run_dir / safe_filename(upload.filename)
        try:
            sha256 = await save_upload(upload, target)
            validate_upload_content(target)
        except HTTPException:
            remove_tree(run_dir)
            jobs.update(job_id, "FAILED", attempts=1, error="UPLOAD_REJECTED")
            raise
        asset_id = f"EVD-{index:03d}"
        try:
            pages = extract_file(target)
        except ExtractionError as exc:
            remove_tree(run_dir)
            jobs.update(job_id, "FAILED", attempts=1, error="EVIDENCE_EXTRACTION_FAILED", progress_message="企业证据解析失败")
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        for page in pages:
            page["source_filename"] = upload.filename
            page["source_id"] = asset_id
            evidence_pages.append(page)
        file_meta = metadata.get(upload.filename, EvidenceMetadata())
        asset = {
            "asset_id": asset_id,
            "source_id": asset_id,
            "filename": upload.filename,
            "file_type": suffix.lstrip("."),
            "sha256": sha256,
            "category": file_meta.category,
            "valid_until": file_meta.valid_until,
            "pages": len(pages),
            "page_index": presenters.page_index(pages),
            "indexed_at": utc_now(),
        }
        evidence_assets.append(asset)
        evidence_files.append({"filename": upload.filename, "path": str(target), **asset})

    try:
        tender_pages = extract_file(tender_path)
    except ExtractionError as exc:
        remove_tree(run_dir)
        jobs.update(job_id, "FAILED", attempts=1, error="TENDER_EXTRACTION_FAILED", progress_message="招标文件解析失败")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for page in tender_pages:
        page["source_id"] = TENDER_SOURCE_ID

    requirements = extract_requirements(tender_pages)
    if evidence_pages and evidence_files:
        requirements = match_evidence(requirements, evidence_pages, evidence_files)

    source_documents = [
        {
            "source_id": TENDER_SOURCE_ID,
            "role": "tender",
            "filename": tender.filename,
            "file_type": Path(tender.filename).suffix.lower().lstrip("."),
            "sha256": tender_sha256,
            "pages": len(tender_pages),
            "page_index": presenters.page_index(tender_pages),
            "parse_status": "PARSED",
        },
        *[
            {
                "source_id": asset["source_id"],
                "role": "enterprise_evidence",
                "filename": asset["filename"],
                "file_type": asset["file_type"],
                "sha256": asset["sha256"],
                "pages": asset["pages"],
                "page_index": asset["page_index"],
                "parse_status": "PARSED",
            }
            for asset in evidence_assets
        ],
    ]

    state = initial_research_state(run_id)
    state["research_brief"]["company_name"] = company_name
    state["source_registry"] = [
        {
            "source_id": item["source_id"],
            "filename": item["filename"],
            "pages": item["pages"],
            "source_type": item["role"],
        }
        for item in source_documents
    ]
    state["source_documents"] = source_documents
    state["evidence_assets"] = evidence_assets
    state["evidence_matrix"] = requirements
    state["scan_quality"] = presenters.scan_quality(tender_pages, evidence_pages)
    advance_state(state, "AUDIT")

    now = utc_now()
    run = {
        "run_id": run_id,
        "workspace_id": principal["workspace_id"],
        "owner_id": principal["user_id"],
        "parent_run_id": None,
        "version_number": 1,
        "job_id": job_id,
        "assignee_id": principal["user_id"],
        "reviewer_id": None,
        "tags": [],
        "favorite": False,
        "project_id": project["project_id"],
        "tender_sha256": tender_sha256,
        "duplicate_run_ids": duplicate_run_ids,
        "created_at": now,
        "updated_at": now,
        "archived_at": None,
        "status": state["status"],
        "tender_filename": tender.filename,
        "tender_path": str(tender_path),
        "evidence_files": evidence_files,
        "source_documents": source_documents,
        "evidence_assets": evidence_assets,
        "decision": {},
        "state": state,
        "requirements": requirements,
        "review": {"items": [], "updated_at": now},
    }
    runs.save(run)
    jobs.link_run(job_id, run_id)
    jobs.update(job_id, "COMPLETED", attempts=1)
    audit.record(principal["workspace_id"], principal["user_id"], "RUN_CREATED", run_id, {"filename": tender.filename, "version_number": 1})
    return presenters.public_run(run)


async def rescan_run(
    *,
    principal: dict[str, str],
    parent: dict,
    tender: UploadFile,
    evidence: list[UploadFile] | None = None,
    company_name: str = "未填写企业",
    evidence_metadata: str | None = None,
    project_id: str | None = None,
) -> dict:
    created = await create_run(
        principal=principal,
        tender=tender,
        evidence=evidence,
        company_name=company_name,
        evidence_metadata=evidence_metadata,
        project_id=project_id or parent.get("project_id"),
    )
    child = runs.require(created["run_id"])
    child["parent_run_id"] = parent["run_id"]
    child["version_number"] = int(parent.get("version_number", 1)) + 1
    runs.save(child)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "RUN_RESCANNED",
        child["run_id"],
        {"parent_run_id": parent["run_id"], "version_number": child["version_number"]},
    )
    return presenters.public_run(child)


async def stage_job(
    *,
    principal: dict[str, str],
    tender: UploadFile,
    evidence: list[UploadFile] | None,
    company_name: str,
    evidence_metadata: str | None,
    project_id: str | None,
) -> str:
    """Persist uploads to the staging area and queue a job. Returns the job id."""
    if not is_supported(tender.filename):
        raise HTTPException(status_code=400, detail="招标文件格式不受支持")
    job_id = uuid.uuid4().hex
    staging = config.JOB_STAGING_DIR / job_id
    staging.mkdir(parents=True, exist_ok=False)
    tender_target = staging / f"tender-{safe_filename(tender.filename)}"
    try:
        await save_upload(tender, tender_target)
        validate_upload_content(tender_target)
        evidence_records = []
        for index, upload in enumerate(evidence or [], 1):
            if not upload.filename:
                continue
            if not is_supported(upload.filename):
                raise HTTPException(status_code=400, detail="企业证据格式不受支持")
            target = staging / f"evidence-{index:03d}-{safe_filename(upload.filename)}"
            await save_upload(upload, target)
            validate_upload_content(target)
            evidence_records.append({"path": str(target), "filename": upload.filename})
    except Exception:
        remove_tree(staging)
        raise
    payload = {
        "tender_path": str(tender_target),
        "tender_filename": tender.filename,
        "evidence": evidence_records,
        "company_name": company_name,
        "evidence_metadata": evidence_metadata,
        "user_id": principal["user_id"],
        "role": principal["role"],
        "project_id": project_id,
    }
    jobs.create(job_id, principal["workspace_id"], None, "PENDING", payload)
    jobs.update(job_id, "PENDING", progress_total=max(2, len(evidence_records) + 2), progress_message="文件已接收，等待解析")
    audit.record(principal["workspace_id"], principal["user_id"], "SCAN_JOB_QUEUED", None, {"job_id": job_id, "filename": tender.filename})
    return job_id


async def process_job(job_id: str) -> None:
    """Execute one queued scan job.

    Runs under the identity captured when the job was queued, rebuilt as an InternalJobContext
    so the principal is explicit rather than reconstructed from request headers.
    """
    job = jobs.load(job_id)
    if job is None:
        return
    payload = job["payload"]
    if job.get("status") == "CANCELLED" or job.get("cancel_requested"):
        staged_tender = payload.get("tender_path")
        if staged_tender:
            remove_tree(Path(staged_tender).parent)
        return
    attempts = int(job.get("attempts", 0)) + 1
    progress_total = max(2, len(payload.get("evidence", [])) + 2)
    if not jobs.start(job_id, attempts=attempts, progress_total=progress_total, progress_message="准备解析文件"):
        return
    jobs.update(job_id, "RUNNING", attempts=attempts, progress_current=0, progress_total=progress_total, progress_message="准备解析文件")
    context = InternalJobContext(
        workspace_id=job["workspace_id"],
        user_id=payload.get("user_id", "local-owner"),
        role=payload.get("role", "OWNER"),
        job_id=job_id,
    )
    try:
        with ExitStack() as stack:
            tender_handle = stack.enter_context(Path(payload["tender_path"]).open("rb"))
            tender = UploadFile(filename=payload["tender_filename"], file=tender_handle)
            evidence_uploads = []
            for item in payload.get("evidence", []):
                handle = stack.enter_context(Path(item["path"]).open("rb"))
                evidence_uploads.append(UploadFile(filename=item["filename"], file=handle))
            jobs.update(job_id, "RUNNING", progress_current=1, progress_total=progress_total, progress_message="解析招标文件与企业证据")
            if (jobs.load(job_id) or {}).get("status") == "CANCELLED":
                remove_tree(Path(payload["tender_path"]).parent)
                return
            result = await create_run(
                principal=context.principal(),
                tender=tender,
                evidence=evidence_uploads,
                company_name=payload.get("company_name", "未填写企业"),
                evidence_metadata=payload.get("evidence_metadata"),
                project_id=payload.get("project_id"),
                queued_job_id=context.job_id,
            )
        jobs.link_run(job_id, result["run_id"])
        jobs.update(job_id, "RUNNING", attempts=attempts, progress_current=max(1, progress_total - 1), progress_total=progress_total, progress_message="保存证据链结果")
        jobs.update(job_id, "COMPLETED", attempts=attempts, progress_current=progress_total, progress_total=progress_total, progress_message="扫描完成")
        audit.record(job["workspace_id"], payload.get("user_id", "local-owner"), "SCAN_JOB_COMPLETED", result["run_id"], {"job_id": job_id, "attempts": attempts})
        remove_tree(Path(payload["tender_path"]).parent)
    except Exception as exc:
        logger.exception("process_job %s failed: %s", job_id, exc)
        current_job = jobs.load(job_id) or {}
        if current_job.get("status") == "CANCELLED" or current_job.get("cancel_requested"):
            return
        jobs.update(
            job_id,
            "FAILED",
            attempts=attempts,
            error=current_job.get("error") or type(exc).__name__,
            progress_current=0,
            progress_total=progress_total,
            progress_message=current_job.get("progress_message") or "处理失败，可重试",
        )
        audit.record(job["workspace_id"], payload.get("user_id", "local-owner"), "SCAN_JOB_FAILED", None, {"job_id": job_id, "attempts": attempts, "error": type(exc).__name__})
