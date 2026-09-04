"""Workspace settings, retention, backups, notifications, metrics and the evidence index."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from .. import config
from ..authz import Permission, require
from ..identity import principal_of
from ..repositories import audit, workspaces
from ..schemas import WorkspaceSettingsRequest
from ..services import workspace_service
from work.backup_restore import create_backup, list_backup_records, record_backup_verification


router = APIRouter(tags=["admin"])


@router.get("/api/workspace/settings")
def workspace_settings(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    return workspaces.settings(principal["workspace_id"])


@router.patch("/api/workspace/settings")
def save_workspace_settings(request: Request, payload: WorkspaceSettingsRequest) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_MANAGE)
    settings = workspaces.update_settings(principal["workspace_id"], payload.retention_days)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "WORKSPACE_SETTINGS_UPDATED",
        None,
        {"retention_days": payload.retention_days},
    )
    return settings


@router.get("/api/workspace/usage")
def get_workspace_usage(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    return {"workspace_id": principal["workspace_id"], **workspaces.usage(principal["workspace_id"])}


@router.get("/api/workspace/privacy")
def get_workspace_privacy(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    return workspace_service.privacy(principal["workspace_id"])


@router.get("/api/notifications")
def get_notifications(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    return workspace_service.notifications(principal["workspace_id"])


@router.get("/api/accuracy/metrics")
def get_accuracy_metrics(request: Request, include_test: bool = Query(default=False)) -> dict:
    principal = principal_of(request)
    require(principal, Permission.METRICS_READ)
    return workspace_service.accuracy(principal["workspace_id"], include_test)


@router.get("/api/retention/preview")
def retention_preview(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.WORKSPACE_READ)
    cutoff, run_ids = workspace_service.retention_candidates(principal["workspace_id"])
    return {"workspace_id": principal["workspace_id"], "cutoff": cutoff, "count": len(run_ids), "run_ids": run_ids}


@router.post("/api/retention/purge")
def purge_retention(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RETENTION_MANAGE)
    return workspace_service.purge_retention(principal)


@router.get("/api/evidence")
def list_evidence(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1),
    valid_before: str | None = Query(default=None),
) -> dict:
    principal = principal_of(request)
    require(principal, Permission.RUN_READ)
    return workspace_service.evidence_index(principal["workspace_id"], category, q, valid_before)


@router.get("/api/backups")
def get_backups(request: Request) -> dict:
    require(principal_of(request), Permission.BACKUP_MANAGE)
    return {
        "backups": list_backup_records(config.BACKUP_ROOT),
        "restore_boundary": "恢复会替换运行中数据，仅允许离线运维命令执行。",
    }


@router.post("/api/backups", status_code=201)
def create_project_backup(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.BACKUP_MANAGE)
    backup = create_backup(backup_root=config.BACKUP_ROOT)
    verification = record_backup_verification(backup)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "BACKUP_CREATED",
        None,
        {"backup_id": backup.name, "valid": verification["valid"]},
    )
    return verification


@router.post("/api/backups/{backup_id}/verify")
def verify_project_backup(request: Request, backup_id: str) -> dict:
    principal = principal_of(request)
    require(principal, Permission.BACKUP_MANAGE)
    if Path(backup_id).name != backup_id:
        raise HTTPException(status_code=400, detail="备份编号无效")
    backup = config.BACKUP_ROOT / backup_id
    if not backup.is_dir():
        raise HTTPException(status_code=404, detail="备份不存在")
    verification = record_backup_verification(backup)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "BACKUP_VERIFIED",
        None,
        {"backup_id": backup_id, "valid": verification["valid"]},
    )
    return verification


@router.get("/api/audit/chain")
def audit_chain(request: Request) -> dict:
    principal = principal_of(request)
    require(principal, Permission.AUDIT_READ)
    return audit.verify_chain(principal["workspace_id"])


@router.get("/api/audit/export")
def export_audit(request: Request) -> FileResponse:
    principal = principal_of(request)
    require(principal, Permission.AUDIT_EXPORT)
    snapshot = audit.export_worm_snapshot(principal["workspace_id"])
    return FileResponse(snapshot, media_type="application/json", filename=snapshot.name)
