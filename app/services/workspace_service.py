"""Workspace-level operations: retention, notifications, accuracy metrics and health."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import config, db
from ..repositories import audit, collaboration, jobs, runs, workspaces
from ..uploads import remove_tree
from ..state import utc_now
from work.backup_restore import list_backup_records


ACCURACY_MIN_SAMPLE_SIZE = 20
NOTIFICATION_DUE_WINDOW_DAYS = 3
NOTIFICATION_LIMIT = 50


def privacy(workspace_id: str) -> dict:
    settings = workspaces.settings(workspace_id) or {"retention_days": 365}
    return {
        "workspace_id": workspace_id,
        "retention_days": settings["retention_days"],
        "uploaded_content_is_data": True,
        "boundary": "BidProof 不提供法律意见 (not legal advice)；上传内容按企业数据处理，权限和保留策略由企业管理员配置。",
        "deletion": "永久删除会移除任务、评论、反馈、作业和上传文件；备份副本需按运维策略单独处理。",
    }


def retention_candidates(workspace_id: str) -> tuple[str, list[str]]:
    settings = workspaces.settings(workspace_id) or {"retention_days": 365}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(settings["retention_days"]))).isoformat()
    return cutoff, runs.expired_archived_ids(workspace_id, cutoff)


def purge_retention(principal: dict[str, str]) -> dict:
    cutoff, run_ids = retention_candidates(principal["workspace_id"])
    deleted = 0
    for run_id in run_ids:
        run = runs.require_scoped(run_id, principal)
        if runs.delete(run_id):
            remove_tree(Path(run["tender_path"]).parent)
            deleted += 1
    audit.record(principal["workspace_id"], principal["user_id"], "RETENTION_PURGE", None, {"cutoff": cutoff, "deleted": deleted})
    return {"cutoff": cutoff, "deleted": deleted, "run_ids": run_ids}


def notifications(workspace_id: str) -> dict:
    today = datetime.now(timezone.utc).date()
    items: list[dict] = []
    for item in collaboration.workspace_remediations(workspace_id):
        if item["status"] in {"DONE", "CANCELLED"} or not item.get("due_date"):
            continue
        try:
            due = datetime.fromisoformat(item["due_date"]).date()
        except ValueError:
            continue
        delta = (due - today).days
        if delta <= NOTIFICATION_DUE_WINDOW_DAYS:
            items.append({
                "type": "REMEDIATION_OVERDUE" if delta < 0 else "REMEDIATION_DUE",
                "severity": "danger" if delta < 0 else "warning",
                "run_id": item["run_id"],
                "remediation_id": item["remediation_id"],
                "title": item["title"],
                "message": "已逾期" if delta < 0 else ("今天到期" if delta == 0 else f"{delta} 天后到期"),
            })
    for job in jobs.list_for_workspace(workspace_id, limit=NOTIFICATION_LIMIT):
        if job.get("status") == "FAILED":
            items.append({
                "type": "SCAN_JOB_FAILED",
                "severity": "danger",
                "job_id": job["job_id"],
                "run_id": job.get("run_id"),
                "title": "扫描作业失败",
                "message": job.get("progress_message") or job.get("error") or "可在作业页重试",
            })
    return {"workspace_id": workspace_id, "count": len(items), "notifications": items[:NOTIFICATION_LIMIT]}


def accuracy(workspace_id: str, include_test: bool) -> dict:
    scopes = ("TEST", "PILOT", "ENTERPRISE") if include_test else ("PILOT", "ENTERPRISE")
    categories = collaboration.accuracy_metrics(workspace_id, scopes=scopes)
    overall_counts = {
        key: sum(item[key] for item in categories)
        for key in ("tp", "fp", "fn", "tn", "sample_size", "detected_total", "labeled_detected")
    }
    precision_denominator = overall_counts["tp"] + overall_counts["fp"]
    recall_denominator = overall_counts["tp"] + overall_counts["fn"]
    false_positive_denominator = overall_counts["fp"] + overall_counts["tn"]
    overall_coverage = overall_counts["labeled_detected"] / overall_counts["detected_total"] if overall_counts["detected_total"] else None
    review_population_complete = bool(categories) and all(item["review_population_complete"] for item in categories)
    measurable = (
        overall_coverage == 1
        and overall_counts["sample_size"] >= ACCURACY_MIN_SAMPLE_SIZE
        and review_population_complete
    )
    overall = {
        **overall_counts,
        "precision": round(overall_counts["tp"] / precision_denominator, 4) if precision_denominator else None,
        "recall": round(overall_counts["tp"] / recall_denominator, 4) if recall_denominator else None,
        "false_discovery_rate": round(overall_counts["fp"] / precision_denominator, 4) if precision_denominator else None,
        "false_positive_rate": round(overall_counts["fp"] / false_positive_denominator, 4) if false_positive_denominator else None,
        "miss_rate": round(overall_counts["fn"] / recall_denominator, 4) if recall_denominator else None,
        "coverage": round(overall_coverage, 4) if overall_coverage is not None else None,
        "review_population_complete": review_population_complete,
        "included_scopes": list(scopes),
        "measurement_status": "MEASURABLE" if measurable else "INSUFFICIENT",
    }
    return {
        "workspace_id": workspace_id,
        "overall": overall,
        "categories": categories,
        "boundary": "默认排除测试标签；检测项覆盖不足、样本少于 20 或漏项复核不完整时，指标状态保持 INSUFFICIENT，不能代表生产准确率。",
    }


def health_detail() -> dict:
    response: dict = {"status": "ok", "service": "bid-evidence-agent"}
    try:
        db.ping()
        response["database"] = "ok"
    except Exception:
        response["status"] = "degraded"
        response["database"] = "error"
    backups = list_backup_records(config.BACKUP_ROOT)
    verified = next((item for item in backups if item["valid"]), None)
    response["backup_status"] = "verified" if verified else ("unverified" if backups else "missing")
    response["last_backup_at"] = backups[0]["created_at"] if backups else None
    response["last_verified_backup_at"] = verified["verified_at"] if verified else None
    response["job_counts"] = jobs.status_counts()
    response["failed_jobs"] = response["job_counts"].get("FAILED", 0)
    response["backup_age_hours"] = None
    if verified and verified.get("verified_at"):
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(verified["verified_at"])
            response["backup_age_hours"] = round(age.total_seconds() / 3600, 2)
        except ValueError:
            response["backup_age_hours"] = None
    reasons = []
    if not verified:
        reasons.append("NO_VERIFIED_BACKUP")
    if response["failed_jobs"]:
        reasons.append("FAILED_SCAN_JOBS")
    response["degraded_reasons"] = reasons
    if reasons:
        response["status"] = "degraded"
    return response


def evidence_index(workspace_id: str, category: str | None, query: str | None, valid_before: str | None) -> dict:
    assets: list[dict] = []
    for run in runs.list_for_workspace(workspace_id):
        assets.extend({**asset, "run_id": run["run_id"]} for asset in run.get("evidence_assets", []))
    if category:
        assets = [asset for asset in assets if asset.get("category") == category.upper()]
    if query:
        needle = query.casefold()
        assets = [asset for asset in assets if needle in asset.get("filename", "").casefold()]
    if valid_before:
        assets = [asset for asset in assets if asset.get("valid_until") and asset["valid_until"] <= valid_before]
    return {"count": len(assets), "assets": assets}


def touch(run: dict) -> str:
    """Stamp and persist an updated run, returning the timestamp used."""
    now = utc_now()
    run["updated_at"] = now
    runs.save(run)
    return now
