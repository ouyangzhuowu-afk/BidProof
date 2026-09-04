"""Operations on an existing run: review, decision, metadata, comparison and bulk actions."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .. import presenters
from ..repositories import audit, collaboration, runs
from ..schemas import (
    AccuracyFeedbackRequest,
    BulkRunRequest,
    DecisionRequest,
    RemediationCreateRequest,
    ReviewRequest,
    RunMetadataRequest,
)
from ..state import advance_state, utc_now
from ..uploads import remove_tree


def bulk_manage(principal: dict[str, str], payload: BulkRunRequest) -> dict:
    updated = 0
    for run_id in dict.fromkeys(payload.run_ids):
        run = runs.load(run_id)
        if run is None or run.get("workspace_id", "local") != principal["workspace_id"]:
            continue
        if payload.action == "DELETE":
            runs.delete(run_id)
            remove_tree(Path(run["tender_path"]).parent)
        else:
            run["archived_at"] = utc_now() if payload.action == "ARCHIVE" else None
            run["updated_at"] = utc_now()
            runs.save(run)
        audit.record(principal["workspace_id"], principal["user_id"], f"RUN_{payload.action}", run_id)
        updated += 1
    return {"action": payload.action, "updated": updated}


def listing(
    principal: dict[str, str],
    *,
    include_archived: bool,
    project_id: str | None,
    search: str | None,
    tag: str | None,
    favorite: bool | None,
    assignee_id: str | None,
    reviewer_id: str | None,
    sort: str,
    after_created_at: str | None = None,
    after_run_id: str | None = None,
) -> list[dict]:
    scoped_runs = runs.list_for_workspace(
        principal["workspace_id"],
        include_archived=include_archived,
        project_id=project_id or None,
        after_created_at=after_created_at,
        after_run_id=after_run_id,
    )
    scoped_runs = [
        run for run in scoped_runs
        if runs.can_access_project(principal, run.get("project_id"))
    ]
    normalized_search = search.strip().casefold() if search else ""
    if normalized_search:
        scoped_runs = [
            run for run in scoped_runs
            if normalized_search in " ".join([
                run.get("tender_filename", ""),
                run.get("run_id", ""),
                *run.get("tags", []),
            ]).casefold()
        ]
    if tag:
        scoped_runs = [run for run in scoped_runs if tag in run.get("tags", [])]
    if favorite is not None:
        scoped_runs = [run for run in scoped_runs if bool(run.get("favorite", False)) is favorite]
    if assignee_id is not None:
        scoped_runs = [run for run in scoped_runs if run.get("assignee_id") == assignee_id]
    if reviewer_id is not None:
        scoped_runs = [run for run in scoped_runs if run.get("reviewer_id") == reviewer_id]
    if sort == "filename":
        scoped_runs.sort(key=lambda run: (run.get("tender_filename", "").casefold(), run["run_id"]))
    else:
        scoped_runs.sort(key=lambda run: (run.get("updated_at", ""), run["run_id"]), reverse=True)
    return [presenters.public_summary(run) for run in scoped_runs]


def source_file(run: dict, source_id: str) -> tuple[Path, str]:
    """Resolve a downloadable source file, refusing anything outside the run directory."""
    if Path(source_id).name != source_id:
        raise HTTPException(status_code=400, detail="文件编号无效")
    candidate_path: str | None = None
    filename: str | None = None
    if source_id == "TENDER-001":
        candidate_path = run.get("tender_path")
        filename = run.get("tender_filename")
    else:
        for asset in run.get("evidence_files", []):
            if asset.get("asset_id") == source_id or asset.get("source_id") == source_id:
                candidate_path = asset.get("path")
                filename = asset.get("filename")
                break
    if not candidate_path:
        raise HTTPException(status_code=404, detail="源文件不存在")
    path = Path(candidate_path).resolve()
    run_root = Path(run.get("tender_path", "")).resolve().parent
    try:
        path.relative_to(run_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="源文件不存在") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="源文件不存在")
    return path, Path(filename or path.name).name


def diff(current: dict, other: dict) -> dict:
    current_items = {presenters.requirement_signature(item): item for item in current.get("requirements", [])}
    other_items = {presenters.requirement_signature(item): item for item in other.get("requirements", [])}
    added = [current_items[key] for key in current_items.keys() - other_items.keys()]
    removed = [other_items[key] for key in other_items.keys() - current_items.keys()]
    changed = [
        {"before": other_items[key], "after": current_items[key]}
        for key in current_items.keys() & other_items.keys()
        if current_items[key].get("status") != other_items[key].get("status")
    ]
    return {
        "run_id": current["run_id"],
        "compared_to": other["run_id"],
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def update_metadata(principal: dict[str, str], run: dict, payload: RunMetadataRequest) -> dict:
    run["assignee_id"] = payload.assignee_id
    run["reviewer_id"] = payload.reviewer_id
    run["tags"] = list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip()))
    run["favorite"] = payload.favorite
    run["updated_at"] = utc_now()
    runs.save(run)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "RUN_METADATA_UPDATED",
        run["run_id"],
        {"assignee_id": payload.assignee_id, "reviewer_id": payload.reviewer_id, "tags": run["tags"], "favorite": payload.favorite},
    )
    return presenters.public_run(run)


def review(principal: dict[str, str], run: dict, payload: ReviewRequest) -> dict:
    requirement = next(
        (item for item in run["requirements"] if item["requirement_id"] == payload.requirement_id),
        None,
    )
    if requirement is None:
        raise HTTPException(status_code=404, detail="要求项不存在")

    old_status = requirement["status"]
    new_status = presenters.resolve_review_status(payload, old_status)
    if new_status == "PASS" and not presenters.has_complete_citation(requirement):
        raise HTTPException(status_code=422, detail="PASS 必须同时具备招标和企业证据页码引用")
    requirement["status"] = new_status
    reviewed_at = utc_now()
    review_item = {
        "requirement_id": payload.requirement_id,
        "decision": payload.decision,
        "old_status": old_status,
        "new_status": new_status,
        "note": payload.note.strip(),
        "reviewed_at": reviewed_at,
    }
    run["review"]["items"].append(review_item)
    run["review"]["updated_at"] = reviewed_at
    run["state"]["review_events"].append(review_item)
    run["state"]["evidence_matrix"] = run["requirements"]
    run["state"] = advance_state(run["state"], "SYNTHESIZE")
    run["status"] = run["state"]["status"]
    run["updated_at"] = reviewed_at
    runs.save(run, expected_revision=payload.revision if payload.revision is not None else run.get("revision"))
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "REQUIREMENT_REVIEWED",
        run["run_id"],
        {"requirement_id": payload.requirement_id, "new_status": new_status},
    )
    return presenters.public_run(run)


def record_decision(principal: dict[str, str], run: dict, payload: DecisionRequest) -> dict:
    known_ids = {item["requirement_id"] for item in run["requirements"]}
    unknown_ids = sorted(set(payload.unresolved_requirement_ids) - known_ids)
    if unknown_ids:
        raise HTTPException(status_code=400, detail=f"未知要求项: {', '.join(unknown_ids)}")
    now = utc_now()
    decision = {
        "decision": payload.decision,
        "note": payload.note.strip(),
        "unresolved_requirement_ids": payload.unresolved_requirement_ids,
        "recorded_at": now,
    }
    run["decision"] = decision
    run["state"]["decision_record"] = decision
    run["state"]["action_plan"] = [
        {"action": payload.decision, "owner": "user", "created_at": now, "note": payload.note.strip()}
    ]
    run["updated_at"] = now
    runs.save(run)
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "RUN_DECISION_RECORDED",
        run["run_id"],
        {"decision": payload.decision, "unresolved_count": len(payload.unresolved_requirement_ids)},
    )
    return presenters.public_run(run)


def create_remediation(principal: dict[str, str], run: dict, payload: RemediationCreateRequest) -> dict:
    if payload.requirement_id and not any(item.get("requirement_id") == payload.requirement_id for item in run.get("requirements", [])):
        raise HTTPException(status_code=400, detail="要求项不存在")
    item = collaboration.create_remediation(principal["workspace_id"], run["run_id"], payload.model_dump())
    audit.record(
        principal["workspace_id"],
        principal["user_id"],
        "REMEDIATION_CREATED",
        run["run_id"],
        {"remediation_id": item["remediation_id"]},
    )
    return item


def add_accuracy_feedback(principal: dict[str, str], run: dict, payload: AccuracyFeedbackRequest) -> dict:
    if payload.predicted == "DETECTED" and not payload.requirement_id:
        raise HTTPException(status_code=422, detail="检测项反馈必须指定要求项")
    if payload.predicted == "MISSED" and (payload.actual != "RELEVANT" or not payload.locator_label or not payload.quote):
        raise HTTPException(status_code=422, detail="漏项反馈必须提供原文定位、原文引用并标记为相关")
    if payload.requirement_id and not any(item.get("requirement_id") == payload.requirement_id for item in run.get("requirements", [])):
        raise HTTPException(status_code=400, detail="要求项不存在")
    item = collaboration.add_accuracy_feedback(principal["workspace_id"], run["run_id"], principal["user_id"], payload.model_dump())
    audit.record(principal["workspace_id"], principal["user_id"], "ACCURACY_FEEDBACK_ADDED", run["run_id"], {
        "feedback_id": item["feedback_id"],
        "category": item["category"],
        "dataset_scope": item["dataset_scope"],
        "review_complete": bool(item["review_complete"]),
    })
    return item


def delete(principal: dict[str, str], run: dict) -> dict[str, str]:
    removed = runs.delete(run["run_id"])
    remove_tree(Path(run["tender_path"]).parent)
    audit.record(principal["workspace_id"], principal["user_id"], "RUN_DELETE", run["run_id"])
    return {"run_id": run["run_id"], "deleted": str(removed).lower()}


def requirements(run: dict, category: str | None, status: str | None, severity: str | None) -> dict:
    items = run["requirements"]
    if category:
        items = [item for item in items if item.get("category") == category.upper()]
    if status:
        items = [item for item in items if item.get("status") == status.upper()]
    if severity:
        items = [item for item in items if item.get("severity") == severity.upper()]
    return {"run_id": run["run_id"], "count": len(items), "requirements": items}
