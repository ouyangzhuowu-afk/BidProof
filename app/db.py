"""Data access implemented with SQLAlchemy Core.

Every statement is built from `app.models`, so the same code runs on SQLite and PostgreSQL.
Functions accept an optional `path_or_url` naming a specific database; omitting it uses the
configured default.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Connection, Engine

from .database import create_schema, engine_for
from .models import (
    accuracy_feedback,
    api_tokens,
    audit_events,
    auth_action_tokens,
    auth_sessions,
    comments,
    identity_bindings,
    login_flows,
    projects,
    remediations,
    runs as runs_table,
    scan_jobs,
    user_mfa,
    users,
    workspace_members,
    workspaces,
)


ACCURACY_MIN_SAMPLE_SIZE = 20

_schema_ready: set[str] = set()
_schema_in_progress: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def engine(path: Path | str | None = None) -> Engine:
    """Return the engine for a database, creating its schema on first use.

    Doing it here rather than at application import means every entrypoint -- the API, a
    worker, a CLI or a test -- gets a ready database without importing the web app for its
    side effects.
    """
    resolved = engine_for(path)
    key = str(resolved.url)
    if key not in _schema_ready and key not in _schema_in_progress:
        _schema_in_progress.add(key)
        try:
            create_schema(path)
            _schema_ready.add(key)
        finally:
            _schema_in_progress.discard(key)
    return resolved


def connect(path: Path | str | None = None) -> Connection:
    """A transactional connection. Use as a context manager; it commits on clean exit."""
    return engine(path).begin()


def init_db(path: Path | str | None = None) -> None:
    """Create or reconcile the schema for a database."""
    resolved = engine_for(path)
    create_schema(path)
    _schema_ready.add(str(resolved.url))


def ping(path: Path | str | None = None) -> bool:
    with engine(path).connect() as connection:
        return connection.execute(sa.select(sa.literal(1))).scalar() == 1


def upsert(
    table: sa.Table,
    values: dict[str, Any],
    conflict_columns: Sequence[str],
    update_columns: Sequence[str],
    dialect_name: str,
):
    """Build an INSERT ... ON CONFLICT DO UPDATE for a dialect.

    SQLite and PostgreSQL both support ON CONFLICT but expose it through separate constructs,
    so the dialect has to be chosen explicitly rather than inferred from a generic insert.
    """
    dialect_insert = sqlite.insert if dialect_name == "sqlite" else postgresql.insert
    statement = dialect_insert(table).values(**values)
    return statement.on_conflict_do_update(
        index_elements=list(conflict_columns),
        set_={name: statement.excluded[name] for name in update_columns},
    )


def _upsert_for(
    table: sa.Table,
    values: dict[str, Any],
    conflict_columns: Sequence[str],
    update_columns: Sequence[str],
    bound: Engine,
):
    return upsert(table, values, conflict_columns, update_columns, bound.dialect.name)


def _rows(result: sa.CursorResult) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings()]


def _row(result: sa.CursorResult) -> dict[str, Any] | None:
    row = result.mappings().first()
    return dict(row) if row else None


# --------------------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------------------

_RUN_STORAGE_FIELDS = (
    "run_id",
    "created_at",
    "updated_at",
    "status",
    "archived_at",
    "workspace_id",
    "owner_id",
    "parent_run_id",
    "version_number",
    "job_id",
    "assignee_id",
    "reviewer_id",
    "tags_json",
    "favorite",
    "project_id",
    "tender_sha256",
    "duplicate_run_ids_json",
    "tender_filename",
    "tender_path",
    "evidence_files",
    "state_json",
    "requirements_json",
    "review_json",
    "source_documents_json",
    "evidence_assets_json",
    "decision_json",
)


def _run_to_storage(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "status": run["status"],
        "archived_at": run.get("archived_at"),
        "workspace_id": run.get("workspace_id", "local"),
        "owner_id": run.get("owner_id", "local-owner"),
        "parent_run_id": run.get("parent_run_id"),
        "version_number": run.get("version_number", 1),
        "job_id": run.get("job_id"),
        "assignee_id": run.get("assignee_id"),
        "reviewer_id": run.get("reviewer_id"),
        "tags_json": run.get("tags", []),
        "favorite": int(bool(run.get("favorite", False))),
        "project_id": run.get("project_id"),
        "tender_sha256": run.get("tender_sha256"),
        "duplicate_run_ids_json": run.get("duplicate_run_ids", []),
        "tender_filename": run["tender_filename"],
        "tender_path": run["tender_path"],
        "evidence_files": run["evidence_files"],
        "state_json": run["state"],
        "requirements_json": run["requirements"],
        "review_json": run["review"],
        "source_documents_json": run.get("source_documents", []),
        "evidence_assets_json": run.get("evidence_assets", []),
        "decision_json": run.get("decision", {}),
    }


def _run_from_storage(row: dict[str, Any]) -> dict[str, Any]:
    run = dict(row)
    run["state"] = run.pop("state_json")
    run["requirements"] = run.pop("requirements_json")
    run["review"] = run.pop("review_json")
    run["source_documents"] = run.pop("source_documents_json")
    run["evidence_assets"] = run.pop("evidence_assets_json")
    run["decision"] = run.pop("decision_json")
    run["tags"] = run.pop("tags_json")
    run["duplicate_run_ids"] = run.pop("duplicate_run_ids_json")
    run["favorite"] = bool(run.get("favorite"))
    return run


def save_run(run: dict[str, Any], path: Path | str | None = None) -> None:
    bound = engine(path)
    values = _run_to_storage(run)
    with bound.begin() as connection:
        connection.execute(
            _upsert_for(
                runs_table,
                values,
                ("run_id",),
                [name for name in _RUN_STORAGE_FIELDS if name != "run_id"],
                bound,
            )
        )


def load_run(run_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        row = _row(connection.execute(sa.select(runs_table).where(runs_table.c.run_id == run_id)))
    return _run_from_storage(row) if row else None


def list_runs(path: Path | str | None = None, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
    """Load runs newest first, optionally restricted to one workspace.

    The workspace predicate runs in SQL. Reading every tenant's rows and filtering them in
    Python was both an N+1 and a way for one workspace's documents to reach another's request.
    """
    statement = sa.select(runs_table).order_by(runs_table.c.created_at.desc())
    if workspace_id is not None:
        statement = statement.where(runs_table.c.workspace_id == workspace_id)
    with engine(path).connect() as connection:
        return [_run_from_storage(row) for row in _rows(connection.execute(statement))]


def update_review(run_id: str, review: dict[str, Any], path: Path | str | None = None) -> dict[str, Any] | None:
    run = load_run(run_id, path)
    if run is None:
        return None
    run["review"] = review
    run["updated_at"] = review["updated_at"]
    save_run(run, path)
    return run


def delete_run(run_id: str, path: Path | str | None = None) -> bool:
    with connect(path) as connection:
        for table in (comments, remediations, accuracy_feedback, scan_jobs):
            connection.execute(sa.delete(table).where(table.c.run_id == run_id))
        result = connection.execute(sa.delete(runs_table).where(runs_table.c.run_id == run_id))
    return result.rowcount > 0


def find_duplicate_run_ids(workspace_id: str, tender_sha256: str, path: Path | str | None = None) -> list[str]:
    statement = (
        sa.select(runs_table.c.run_id)
        .where(runs_table.c.workspace_id == workspace_id, runs_table.c.tender_sha256 == tender_sha256)
        .order_by(runs_table.c.created_at.desc())
    )
    with engine(path).connect() as connection:
        return [row[0] for row in connection.execute(statement)]


def list_expired_archived_run_ids(workspace_id: str, cutoff: str, path: Path | str | None = None) -> list[str]:
    statement = (
        sa.select(runs_table.c.run_id)
        .where(
            runs_table.c.workspace_id == workspace_id,
            runs_table.c.archived_at.is_not(None),
            runs_table.c.archived_at < cutoff,
        )
        .order_by(runs_table.c.archived_at)
    )
    with engine(path).connect() as connection:
        return [row[0] for row in connection.execute(statement)]


# --------------------------------------------------------------------------------------
# Workspaces, projects and members
# --------------------------------------------------------------------------------------

def ensure_workspace(workspace_id: str, user_id: str, role: str, name: str | None = None, path: Path | str | None = None) -> None:
    bound = engine(path)
    now = _now()
    with bound.begin() as connection:
        insert = sqlite.insert if bound.dialect.name == "sqlite" else postgresql.insert
        connection.execute(
            insert(workspaces)
            .values(workspace_id=workspace_id, name=name or workspace_id, created_at=now)
            .on_conflict_do_nothing(index_elements=["workspace_id"])
        )
        connection.execute(
            _upsert_for(
                workspace_members,
                {"workspace_id": workspace_id, "user_id": user_id, "role": role, "created_at": now},
                ("workspace_id", "user_id"),
                ("role",),
                bound,
            )
        )


def primary_workspace_id(path: Path | str | None = None) -> str | None:
    statement = sa.select(workspaces.c.workspace_id).order_by(workspaces.c.created_at.asc()).limit(1)
    with engine(path).connect() as connection:
        row = connection.execute(statement).first()
    return str(row[0]) if row else None


def get_workspace_settings(workspace_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    statement = sa.select(
        workspaces.c.workspace_id,
        workspaces.c.name,
        workspaces.c.retention_days,
        workspaces.c.created_at,
    ).where(workspaces.c.workspace_id == workspace_id)
    with engine(path).connect() as connection:
        return _row(connection.execute(statement))


def update_workspace_settings(workspace_id: str, retention_days: int, path: Path | str | None = None) -> dict[str, Any] | None:
    with connect(path) as connection:
        connection.execute(
            sa.update(workspaces).where(workspaces.c.workspace_id == workspace_id).values(retention_days=retention_days)
        )
    return get_workspace_settings(workspace_id, path)


def workspace_usage(workspace_id: str, path: Path | str | None = None) -> dict[str, int]:
    tables = {
        "runs": runs_table,
        "members": users,
        "scan_jobs": scan_jobs,
        "audit_events": audit_events,
        "feedback": accuracy_feedback,
        "remediations": remediations,
    }
    with engine(path).connect() as connection:
        return {
            label: int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(table).where(table.c.workspace_id == workspace_id)
                ).scalar_one()
            )
            for label, table in tables.items()
        }


def create_project(workspace_id: str, name: str, code: str, path: Path | str | None = None) -> dict[str, Any]:
    now = _now()
    item = {
        "project_id": _new_id(),
        "workspace_id": workspace_id,
        "name": name,
        "code": code.upper(),
        "archived_at": None,
        "created_at": now,
        "updated_at": now,
    }
    with connect(path) as connection:
        connection.execute(sa.insert(projects).values(**item))
    return item


def ensure_default_project(workspace_id: str, path: Path | str | None = None) -> dict[str, Any]:
    statement = sa.select(projects).where(projects.c.workspace_id == workspace_id, projects.c.code == "DEFAULT")
    with engine(path).connect() as connection:
        row = _row(connection.execute(statement))
    return row if row else create_project(workspace_id, "默认项目", "DEFAULT", path)


def list_projects(workspace_id: str, include_archived: bool = False, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = sa.select(projects).where(projects.c.workspace_id == workspace_id)
    if not include_archived:
        statement = statement.where(projects.c.archived_at.is_(None))
    with engine(path).connect() as connection:
        return _rows(connection.execute(statement.order_by(projects.c.created_at)))


def load_project(project_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(connection.execute(sa.select(projects).where(projects.c.project_id == project_id)))


def update_project(project_id: str, name: str | None = None, archived: bool | None = None, path: Path | str | None = None) -> dict[str, Any] | None:
    project = load_project(project_id, path)
    if project is None:
        return None
    project["name"] = name or project["name"]
    if archived is not None:
        project["archived_at"] = _now() if archived else None
    project["updated_at"] = _now()
    with connect(path) as connection:
        connection.execute(
            sa.update(projects)
            .where(projects.c.project_id == project_id)
            .values(name=project["name"], archived_at=project["archived_at"], updated_at=project["updated_at"])
        )
    return project


# --------------------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------------------

def record_audit_event(
    workspace_id: str,
    user_id: str,
    event_type: str,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
    path: Path | str | None = None,
    *,
    outcome: str = "SUCCESS",
) -> str:
    from .request_context import current

    context = current()
    event_id = _new_id()
    with connect(path) as connection:
        connection.execute(
            sa.insert(audit_events).values(
                event_id=event_id,
                workspace_id=workspace_id,
                run_id=run_id,
                user_id=user_id,
                event_type=event_type,
                payload_json=payload or {},
                created_at=_now(),
                actor_ip=context.client_ip,
                user_agent=context.user_agent,
                request_id=context.request_id or None,
                outcome=outcome,
            )
        )
    return event_id


def list_audit_events(workspace_id: str, run_id: str | None = None, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = sa.select(audit_events).where(audit_events.c.workspace_id == workspace_id)
    if run_id:
        statement = statement.where(audit_events.c.run_id == run_id)
    with engine(path).connect() as connection:
        rows = _rows(connection.execute(statement.order_by(audit_events.c.created_at.desc())))
    for row in rows:
        row["payload"] = row.pop("payload_json")
    return rows


# --------------------------------------------------------------------------------------
# Scan jobs
# --------------------------------------------------------------------------------------

_JOB_UPSERT_FIELDS = (
    "workspace_id",
    "run_id",
    "status",
    "attempts",
    "error",
    "payload_json",
    "created_at",
    "updated_at",
)


def create_scan_job(
    job_id: str,
    workspace_id: str,
    run_id: str | None,
    status: str = "PENDING",
    payload: dict[str, Any] | None = None,
    path: Path | str | None = None,
) -> None:
    bound = engine(path)
    now = _now()
    values = {
        "job_id": job_id,
        "workspace_id": workspace_id,
        "run_id": run_id,
        "status": status,
        "attempts": 0,
        "error": None,
        "payload_json": payload or {},
        "created_at": now,
        "updated_at": now,
    }
    with bound.begin() as connection:
        connection.execute(_upsert_for(scan_jobs, values, ("job_id",), _JOB_UPSERT_FIELDS, bound))


def update_scan_job(
    job_id: str,
    status: str,
    attempts: int | None = None,
    error: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    progress_message: str | None = None,
    cancel_requested: bool | None = None,
    path: Path | str | None = None,
) -> None:
    values: dict[str, Any] = {"status": status, "error": error, "updated_at": _now()}
    if attempts is not None:
        values["attempts"] = attempts
    if progress_current is not None:
        values["progress_current"] = progress_current
    if progress_total is not None:
        values["progress_total"] = progress_total
    if progress_message is not None:
        values["progress_message"] = progress_message
    if cancel_requested is not None:
        values["cancel_requested"] = int(bool(cancel_requested))
    # A cancelled job only accepts a further write that keeps it cancelled.
    guard = sa.or_(scan_jobs.c.status != "CANCELLED", sa.literal(status) == "CANCELLED")
    with connect(path) as connection:
        connection.execute(sa.update(scan_jobs).where(scan_jobs.c.job_id == job_id, guard).values(**values))


def load_scan_job(job_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        row = _row(connection.execute(sa.select(scan_jobs).where(scan_jobs.c.job_id == job_id)))
    if row is None:
        return None
    row["payload"] = row.pop("payload_json")
    return row


def cancel_scan_job(job_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    """Atomically cancel a pending or running scan job."""
    with connect(path) as connection:
        connection.execute(
            sa.update(scan_jobs)
            .where(scan_jobs.c.job_id == job_id, scan_jobs.c.status.in_(("PENDING", "RUNNING")))
            .values(
                status="CANCELLED",
                cancel_requested=1,
                error=None,
                progress_message="已取消",
                updated_at=_now(),
            )
        )
    return load_scan_job(job_id, path)


def start_scan_job(
    job_id: str,
    path: Path | str | None = None,
    *,
    attempts: int | None = None,
    progress_total: int | None = None,
    progress_message: str | None = None,
) -> bool:
    """Atomically move a queued job to RUNNING; cancelled jobs cannot restart."""
    values: dict[str, Any] = {"status": "RUNNING", "updated_at": _now()}
    if attempts is not None:
        values["attempts"] = attempts
    if progress_total is not None:
        values["progress_total"] = progress_total
    if progress_message is not None:
        values["progress_message"] = progress_message
    with connect(path) as connection:
        result = connection.execute(
            sa.update(scan_jobs)
            .where(
                scan_jobs.c.job_id == job_id,
                scan_jobs.c.status.in_(("PENDING", "RUNNING")),
                scan_jobs.c.cancel_requested == 0,
            )
            .values(**values)
        )
    return result.rowcount == 1


def link_scan_job(job_id: str, run_id: str, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(sa.update(scan_jobs).where(scan_jobs.c.job_id == job_id).values(run_id=run_id))


def _jobs_from_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs = []
    for row in rows:
        item = dict(row)
        item["payload"] = item.pop("payload_json")
        jobs.append(item)
    return jobs


def requeue_stale_scan_jobs(max_age_seconds: int, path: Path | str | None = None) -> int:
    """Return crashed RUNNING jobs to PENDING so another worker can claim them.

    `updated_at` is an ISO timestamp; jobs newer than the cutoff are assumed to still be live.
    """
    cutoff = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - max_age_seconds, timezone.utc
    ).isoformat()
    with connect(path) as connection:
        result = connection.execute(
            sa.update(scan_jobs)
            .where(
                scan_jobs.c.status == "RUNNING",
                scan_jobs.c.cancel_requested == 0,
                scan_jobs.c.updated_at < cutoff,
            )
            .values(status="PENDING", progress_message="工作进程中断，已重新排队", updated_at=_now())
        )
    return int(result.rowcount or 0)


def claim_next_scan_job(path: Path | str | None = None) -> dict[str, Any] | None:
    """Atomically take the oldest PENDING job.

    PostgreSQL uses SKIP LOCKED so two workers never claim the same row. SQLite has no skip
    locked; the follow-up UPDATE ... WHERE status='PENDING' is the exclusion.
    """
    bound = engine(path)
    pending = (
        sa.select(scan_jobs)
        .where(scan_jobs.c.status == "PENDING", scan_jobs.c.cancel_requested == 0)
        .order_by(scan_jobs.c.created_at, scan_jobs.c.job_id)
        .limit(1)
    )
    with bound.begin() as connection:
        if bound.dialect.name == "postgresql":
            pending = pending.with_for_update(skip_locked=True)
        row = _row(connection.execute(pending))
        if row is None:
            return None
        claimed = connection.execute(
            sa.update(scan_jobs)
            .where(scan_jobs.c.job_id == row["job_id"], scan_jobs.c.status == "PENDING")
            .values(status="RUNNING", updated_at=_now())
        )
        if claimed.rowcount != 1:
            return None
    loaded = load_scan_job(row["job_id"], path)
    return loaded


def list_recoverable_jobs(path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(scan_jobs)
        .where(scan_jobs.c.status.in_(("PENDING", "RUNNING")))
        .order_by(scan_jobs.c.created_at)
    )
    with engine(path).connect() as connection:
        return _jobs_from_rows(_rows(connection.execute(statement)))


def list_scan_jobs(workspace_id: str, limit: int = 100, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(scan_jobs)
        .where(scan_jobs.c.workspace_id == workspace_id)
        .order_by(scan_jobs.c.created_at.desc())
        .limit(limit)
    )
    with engine(path).connect() as connection:
        return _jobs_from_rows(_rows(connection.execute(statement)))


def scan_job_status_counts(path: Path | str | None = None) -> dict[str, int]:
    statement = sa.select(scan_jobs.c.status, sa.func.count().label("count")).group_by(scan_jobs.c.status)
    with engine(path).connect() as connection:
        return {row[0]: int(row[1]) for row in connection.execute(statement)}


# --------------------------------------------------------------------------------------
# Collaboration
# --------------------------------------------------------------------------------------

def add_comment(workspace_id: str, run_id: str, user_id: str, body: str, path: Path | str | None = None) -> dict[str, Any]:
    comment = {
        "comment_id": _new_id(),
        "workspace_id": workspace_id,
        "run_id": run_id,
        "user_id": user_id,
        "body": body,
        "created_at": _now(),
    }
    with connect(path) as connection:
        connection.execute(sa.insert(comments).values(**comment))
    return comment


def list_comments(workspace_id: str, run_id: str, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(comments)
        .where(comments.c.workspace_id == workspace_id, comments.c.run_id == run_id)
        .order_by(comments.c.created_at.desc())
    )
    with engine(path).connect() as connection:
        return _rows(connection.execute(statement))


def create_remediation(workspace_id: str, run_id: str, payload: dict[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    now = _now()
    item = {
        "remediation_id": _new_id(),
        "workspace_id": workspace_id,
        "run_id": run_id,
        "requirement_id": payload.get("requirement_id"),
        "title": payload["title"].strip(),
        "owner_id": payload.get("owner_id"),
        "due_date": payload.get("due_date"),
        "status": payload.get("status", "OPEN"),
        "note": payload.get("note", ""),
        "created_at": now,
        "updated_at": now,
    }
    with connect(path) as connection:
        connection.execute(sa.insert(remediations).values(**item))
    return item


def list_remediations(workspace_id: str, run_id: str, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(remediations)
        .where(remediations.c.workspace_id == workspace_id, remediations.c.run_id == run_id)
        .order_by(remediations.c.status, remediations.c.due_date, remediations.c.created_at)
    )
    with engine(path).connect() as connection:
        return _rows(connection.execute(statement))


def list_workspace_remediations(workspace_id: str, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(remediations)
        .where(remediations.c.workspace_id == workspace_id)
        .order_by(remediations.c.due_date, remediations.c.created_at)
    )
    with engine(path).connect() as connection:
        return _rows(connection.execute(statement))


def load_remediation(remediation_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(
            connection.execute(sa.select(remediations).where(remediations.c.remediation_id == remediation_id))
        )


def update_remediation(remediation_id: str, payload: dict[str, Any], path: Path | str | None = None) -> dict[str, Any] | None:
    current = load_remediation(remediation_id, path)
    if current is None:
        return None
    merged = {**current, **{key: value for key, value in payload.items() if value is not None}}
    merged["updated_at"] = _now()
    with connect(path) as connection:
        connection.execute(
            sa.update(remediations)
            .where(remediations.c.remediation_id == remediation_id)
            .values(
                title=merged["title"],
                owner_id=merged["owner_id"],
                due_date=merged["due_date"],
                status=merged["status"],
                note=merged["note"],
                updated_at=merged["updated_at"],
            )
        )
    return load_remediation(remediation_id, path)


# --------------------------------------------------------------------------------------
# Accuracy feedback
# --------------------------------------------------------------------------------------

_FEEDBACK_UPDATE_FIELDS = (
    "category",
    "predicted",
    "actual",
    "locator_label",
    "quote",
    "note",
    "dataset_scope",
    "review_complete",
    "created_at",
)


def add_accuracy_feedback(
    workspace_id: str,
    run_id: str,
    reviewer_id: str,
    payload: dict[str, Any],
    path: Path | str | None = None,
) -> dict[str, Any]:
    bound = engine(path)
    category = payload["category"].upper()
    if payload["predicted"] == "DETECTED":
        feedback_key = f"detected:{payload.get('requirement_id', '')}"
    else:
        fingerprint = "|".join((category, (payload.get("locator_label") or "").strip(), (payload.get("quote") or "").strip()))
        feedback_key = f"missed:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()}"
    values = {
        "feedback_id": _new_id(),
        "workspace_id": workspace_id,
        "run_id": run_id,
        "requirement_id": payload.get("requirement_id"),
        "feedback_key": feedback_key,
        "category": category,
        "predicted": payload["predicted"],
        "actual": payload["actual"],
        "locator_label": payload.get("locator_label"),
        "quote": payload.get("quote"),
        "note": payload.get("note", ""),
        "reviewer_id": reviewer_id,
        "dataset_scope": payload.get("dataset_scope", "PILOT"),
        "review_complete": int(bool(payload.get("review_complete", False))),
        "created_at": _now(),
    }
    with bound.begin() as connection:
        connection.execute(
            _upsert_for(
                accuracy_feedback,
                values,
                ("workspace_id", "run_id", "reviewer_id", "feedback_key"),
                _FEEDBACK_UPDATE_FIELDS,
                bound,
            )
        )
        saved = _row(
            connection.execute(
                sa.select(accuracy_feedback).where(
                    accuracy_feedback.c.workspace_id == workspace_id,
                    accuracy_feedback.c.run_id == run_id,
                    accuracy_feedback.c.reviewer_id == reviewer_id,
                    accuracy_feedback.c.feedback_key == feedback_key,
                )
            )
        )
    return saved or values


def accuracy_metrics(
    workspace_id: str,
    scopes: tuple[str, ...] = ("PILOT", "ENTERPRISE"),
    path: Path | str | None = None,
) -> list[dict[str, Any]]:
    if not scopes:
        return []
    label_statement = (
        sa.select(
            accuracy_feedback.c.run_id,
            accuracy_feedback.c.category,
            accuracy_feedback.c.predicted,
            accuracy_feedback.c.actual,
            accuracy_feedback.c.review_complete,
            sa.func.count().label("count"),
        )
        .where(
            accuracy_feedback.c.workspace_id == workspace_id,
            accuracy_feedback.c.dataset_scope.in_(scopes),
        )
        .group_by(
            accuracy_feedback.c.run_id,
            accuracy_feedback.c.category,
            accuracy_feedback.c.predicted,
            accuracy_feedback.c.actual,
            accuracy_feedback.c.review_complete,
        )
    )
    with engine(path).connect() as connection:
        rows = _rows(connection.execute(label_statement))
        scope_run_ids = {row["run_id"] for row in rows}
        run_rows = (
            _rows(
                connection.execute(
                    sa.select(runs_table.c.run_id, runs_table.c.requirements_json).where(
                        runs_table.c.workspace_id == workspace_id,
                        runs_table.c.run_id.in_(scope_run_ids),
                    )
                )
            )
            if scope_run_ids
            else []
        )

    detected_totals: dict[str, int] = {}
    for run_row in run_rows:
        for requirement in run_row["requirements_json"]:
            category = requirement.get("category", "UNCLASSIFIED")
            detected_totals[category] = detected_totals.get(category, 0) + 1

    grouped: dict[str, dict[str, int]] = {}
    observed_runs: dict[str, set[str]] = {}
    incomplete_runs: dict[str, set[str]] = {}
    for row in rows:
        category = row["category"]
        counts = grouped.setdefault(category, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        observed_runs.setdefault(category, set()).add(row["run_id"])
        if not row["review_complete"]:
            incomplete_runs.setdefault(category, set()).add(row["run_id"])
        key = (
            "tp" if row["predicted"] == "DETECTED" and row["actual"] == "RELEVANT"
            else "fp" if row["predicted"] == "DETECTED" and row["actual"] == "NOT_RELEVANT"
            else "fn" if row["predicted"] == "MISSED" and row["actual"] == "RELEVANT"
            else "tn"
        )
        counts[key] += row["count"]

    result = []
    for category in sorted(set(grouped) | set(detected_totals)):
        counts = grouped.get(category, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        precision_denominator = counts["tp"] + counts["fp"]
        recall_denominator = counts["tp"] + counts["fn"]
        false_positive_denominator = counts["fp"] + counts["tn"]
        detected_total = detected_totals.get(category, 0)
        labeled_detected = precision_denominator
        coverage = labeled_detected / detected_total if detected_total else None
        sample_size = sum(counts.values())
        review_population_complete = bool(observed_runs.get(category)) and not incomplete_runs.get(category)
        measurable = coverage == 1 and sample_size >= ACCURACY_MIN_SAMPLE_SIZE and review_population_complete
        result.append({
            "category": category,
            **counts,
            "precision": round(counts["tp"] / precision_denominator, 4) if precision_denominator else None,
            "recall": round(counts["tp"] / recall_denominator, 4) if recall_denominator else None,
            "false_discovery_rate": round(counts["fp"] / precision_denominator, 4) if precision_denominator else None,
            "miss_rate": round(counts["fn"] / recall_denominator, 4) if recall_denominator else None,
            "false_positive_rate": round(counts["fp"] / false_positive_denominator, 4) if false_positive_denominator else None,
            "false_negative_rate": round(counts["fn"] / recall_denominator, 4) if recall_denominator else None,
            "sample_size": sample_size,
            "detected_total": detected_total,
            "labeled_detected": labeled_detected,
            "coverage": round(coverage, 4) if coverage is not None else None,
            "review_population_complete": review_population_complete,
            "complete_review_runs": len(observed_runs.get(category, set()) - incomplete_runs.get(category, set())),
            "included_scopes": list(scopes),
            "measurement_status": "MEASURABLE" if measurable else "INSUFFICIENT",
        })
    return result


# --------------------------------------------------------------------------------------
# Accounts, sessions and action tokens
# --------------------------------------------------------------------------------------

def count_users(path: Path | str | None = None) -> int:
    with engine(path).connect() as connection:
        return int(connection.execute(sa.select(sa.func.count()).select_from(users)).scalar_one())


def create_user(workspace_id: str, username: str, password_hash: str, role: str, path: Path | str | None = None) -> dict[str, Any]:
    user = {
        "user_id": _new_id(),
        "workspace_id": workspace_id,
        "username": username,
        "password_hash": password_hash,
        "role": role,
        "active": 1,
        "created_at": _now(),
    }
    try:
        with connect(path) as connection:
            connection.execute(sa.insert(users).values(**user))
    except sa.exc.IntegrityError as exc:
        # Callers catch sqlite3.IntegrityError to answer 409 on a duplicate username.
        raise _integrity_error(exc) from exc
    return user


def _integrity_error(exc: sa.exc.IntegrityError) -> Exception:
    import sqlite3

    return sqlite3.IntegrityError(str(exc.orig))


def list_workspace_members(workspace_id: str, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(
            users.c.user_id,
            users.c.workspace_id,
            users.c.username,
            users.c.role,
            users.c.active,
            users.c.created_at,
        )
        .where(users.c.workspace_id == workspace_id)
        .order_by(users.c.created_at)
    )
    with engine(path).connect() as connection:
        return [{**row, "active": bool(row["active"])} for row in _rows(connection.execute(statement))]


def update_workspace_member(
    workspace_id: str,
    user_id: str,
    role: str | None = None,
    active: bool | None = None,
    path: Path | str | None = None,
) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = _row(
            connection.execute(
                sa.select(users).where(users.c.workspace_id == workspace_id, users.c.user_id == user_id)
            )
        )
        if row is None:
            return None
        next_role = role or row["role"]
        next_active = int(active) if active is not None else int(row["active"])
        connection.execute(sa.update(users).where(users.c.user_id == user_id).values(role=next_role, active=next_active))
        connection.execute(
            sa.update(workspace_members)
            .where(workspace_members.c.workspace_id == workspace_id, workspace_members.c.user_id == user_id)
            .values(role=next_role)
        )
        if not next_active:
            connection.execute(sa.delete(auth_sessions).where(auth_sessions.c.user_id == user_id))
        updated = _row(
            connection.execute(
                sa.select(
                    users.c.user_id,
                    users.c.workspace_id,
                    users.c.username,
                    users.c.role,
                    users.c.active,
                    users.c.created_at,
                ).where(users.c.user_id == user_id)
            )
        )
    return {**updated, "active": bool(updated["active"])}


def load_user_by_username(username: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(connection.execute(sa.select(users).where(users.c.username == username)))


def load_user_by_id(user_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(connection.execute(sa.select(users).where(users.c.user_id == user_id)))


def update_user_password(user_id: str, password_hash: str, path: Path | str | None = None) -> bool:
    with connect(path) as connection:
        result = connection.execute(sa.update(users).where(users.c.user_id == user_id).values(password_hash=password_hash))
        connection.execute(sa.delete(auth_sessions).where(auth_sessions.c.user_id == user_id))
    return bool(result.rowcount)


def create_auth_session(token_hash: str, user_id: str, expires_at: str, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(
            sa.insert(auth_sessions).values(
                token_hash=token_hash,
                user_id=user_id,
                expires_at=expires_at,
                created_at=_now(),
            )
        )


def load_session_user(token_hash: str, now: str, path: Path | str | None = None) -> dict[str, Any] | None:
    statement = (
        sa.select(users)
        .select_from(auth_sessions.join(users, users.c.user_id == auth_sessions.c.user_id))
        .where(
            auth_sessions.c.token_hash == token_hash,
            auth_sessions.c.expires_at > now,
            users.c.active == 1,
        )
    )
    with engine(path).connect() as connection:
        return _row(connection.execute(statement))


def delete_auth_session(token_hash: str, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(sa.delete(auth_sessions).where(auth_sessions.c.token_hash == token_hash))


def create_auth_action_token(
    token_hash: str,
    workspace_id: str,
    purpose: str,
    expires_at: str,
    created_by: str,
    *,
    username: str | None = None,
    user_id: str | None = None,
    role: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    created_at = _now()
    with connect(path) as connection:
        # Issuing a new link invalidates any outstanding one for the same account.
        if purpose == "INVITE" and username:
            connection.execute(
                sa.update(auth_action_tokens)
                .where(
                    auth_action_tokens.c.purpose == "INVITE",
                    auth_action_tokens.c.username == username,
                    auth_action_tokens.c.used_at.is_(None),
                )
                .values(used_at=created_at)
            )
        if purpose == "RESET" and user_id:
            connection.execute(
                sa.update(auth_action_tokens)
                .where(
                    auth_action_tokens.c.purpose == "RESET",
                    auth_action_tokens.c.user_id == user_id,
                    auth_action_tokens.c.used_at.is_(None),
                )
                .values(used_at=created_at)
            )
        connection.execute(
            sa.insert(auth_action_tokens).values(
                token_hash=token_hash,
                workspace_id=workspace_id,
                purpose=purpose,
                username=username,
                user_id=user_id,
                role=role,
                expires_at=expires_at,
                used_at=None,
                created_by=created_by,
                created_at=created_at,
            )
        )
    return {
        "token_hash": token_hash,
        "workspace_id": workspace_id,
        "purpose": purpose,
        "username": username,
        "user_id": user_id,
        "role": role,
        "expires_at": expires_at,
        "used_at": None,
        "created_by": created_by,
        "created_at": created_at,
    }


def load_auth_action_token(token_hash: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(
            connection.execute(sa.select(auth_action_tokens).where(auth_action_tokens.c.token_hash == token_hash))
        )


def consume_auth_action_token(token_hash: str, consumed_at: str, path: Path | str | None = None) -> bool:
    with connect(path) as connection:
        result = connection.execute(
            sa.update(auth_action_tokens)
            .where(
                auth_action_tokens.c.token_hash == token_hash,
                auth_action_tokens.c.used_at.is_(None),
                auth_action_tokens.c.expires_at > consumed_at,
            )
            .values(used_at=consumed_at)
        )
    return bool(result.rowcount)


# --------------------------------------------------------------------------------------
# API tokens, MFA, identity bindings and login flows
# --------------------------------------------------------------------------------------

def create_api_token(
    *,
    token_hash: str,
    token_prefix: str,
    workspace_id: str,
    user_id: str,
    name: str,
    role: str,
    created_by: str,
    permissions: list[str] | None = None,
    expires_at: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    row = {
        "token_id": _new_id(),
        "token_hash": token_hash,
        "token_prefix": token_prefix,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "name": name,
        "role": role,
        "permissions_json": permissions or [],
        "expires_at": expires_at,
        "revoked_at": None,
        "last_used_at": None,
        "created_by": created_by,
        "created_at": _now(),
    }
    with connect(path) as connection:
        connection.execute(sa.insert(api_tokens).values(**row))
    return _public_api_token(row)


def _public_api_token(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_id": row["token_id"],
        "token_prefix": row.get("token_prefix", ""),
        "name": row["name"],
        "role": row["role"],
        "permissions": row.get("permissions_json") or [],
        "workspace_id": row["workspace_id"],
        "user_id": row["user_id"],
        "expires_at": row.get("expires_at"),
        "revoked_at": row.get("revoked_at"),
        "last_used_at": row.get("last_used_at"),
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


def list_api_tokens(workspace_id: str, path: Path | str | None = None) -> list[dict[str, Any]]:
    statement = (
        sa.select(api_tokens)
        .where(api_tokens.c.workspace_id == workspace_id)
        .order_by(api_tokens.c.created_at.desc())
    )
    with engine(path).connect() as connection:
        return [_public_api_token(row) for row in _rows(connection.execute(statement))]


def load_api_token_by_hash(token_digest: str, now: str, path: Path | str | None = None) -> dict[str, Any] | None:
    statement = (
        sa.select(api_tokens, users.c.active, users.c.username)
        .select_from(api_tokens.join(users, users.c.user_id == api_tokens.c.user_id))
        .where(
            api_tokens.c.token_hash == token_digest,
            api_tokens.c.revoked_at.is_(None),
            users.c.active == 1,
        )
    )
    with engine(path).connect() as connection:
        row = _row(connection.execute(statement))
    if row is None:
        return None
    expires_at = row.get("expires_at")
    if expires_at and expires_at <= now:
        return None
    return row


def touch_api_token(token_id: str, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(sa.update(api_tokens).where(api_tokens.c.token_id == token_id).values(last_used_at=_now()))


def revoke_api_token(workspace_id: str, token_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    now = _now()
    with connect(path) as connection:
        row = _row(
            connection.execute(
                sa.select(api_tokens).where(
                    api_tokens.c.workspace_id == workspace_id,
                    api_tokens.c.token_id == token_id,
                )
            )
        )
        if row is None:
            return None
        connection.execute(sa.update(api_tokens).where(api_tokens.c.token_id == token_id).values(revoked_at=now))
    return _public_api_token({**row, "revoked_at": now})


def load_user_mfa(user_id: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(connection.execute(sa.select(user_mfa).where(user_mfa.c.user_id == user_id)))


def upsert_user_mfa(
    user_id: str,
    secret: str,
    recovery_codes: list[str],
    path: Path | str | None = None,
) -> dict[str, Any]:
    row = {
        "user_id": user_id,
        "secret": secret,
        "confirmed_at": None,
        "last_counter": 0,
        "recovery_codes_json": recovery_codes,
        "created_at": _now(),
    }
    bound = engine(path)
    with connect(path) as connection:
        connection.execute(
            _upsert_for(
                user_mfa,
                row,
                ("user_id",),
                ("secret", "confirmed_at", "last_counter", "recovery_codes_json"),
                bound,
            )
        )
    return row


def confirm_user_mfa(user_id: str, last_counter: int, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(
            sa.update(user_mfa)
            .where(user_mfa.c.user_id == user_id)
            .values(confirmed_at=_now(), last_counter=last_counter)
        )


def update_user_mfa_counter(
    user_id: str,
    last_counter: int,
    recovery_codes: list[str] | None = None,
    path: Path | str | None = None,
) -> None:
    values: dict[str, Any] = {"last_counter": last_counter}
    if recovery_codes is not None:
        values["recovery_codes_json"] = recovery_codes
    with connect(path) as connection:
        connection.execute(sa.update(user_mfa).where(user_mfa.c.user_id == user_id).values(**values))


def delete_user_mfa(user_id: str, path: Path | str | None = None) -> None:
    with connect(path) as connection:
        connection.execute(sa.delete(user_mfa).where(user_mfa.c.user_id == user_id))


def load_identity_binding(provider: str, issuer: str, subject: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(
            connection.execute(
                sa.select(identity_bindings).where(
                    identity_bindings.c.provider == provider,
                    identity_bindings.c.issuer == issuer,
                    identity_bindings.c.subject == subject,
                )
            )
        )


def upsert_identity_binding(
    user_id: str,
    provider: str,
    issuer: str,
    subject: str,
    path: Path | str | None = None,
) -> dict[str, Any]:
    existing = load_identity_binding(provider, issuer, subject, path)
    now = _now()
    if existing:
        with connect(path) as connection:
            connection.execute(
                sa.update(identity_bindings)
                .where(identity_bindings.c.binding_id == existing["binding_id"])
                .values(last_seen_at=now)
            )
        return {**existing, "last_seen_at": now}
    row = {
        "binding_id": _new_id(),
        "user_id": user_id,
        "provider": provider,
        "issuer": issuer,
        "subject": subject,
        "created_at": now,
        "last_seen_at": now,
    }
    with connect(path) as connection:
        connection.execute(sa.insert(identity_bindings).values(**row))
    return row


def create_login_flow(
    state: str,
    provider: str,
    *,
    code_verifier: str = "",
    redirect_uri: str = "",
    nonce: str = "",
    expires_at: str,
    path: Path | str | None = None,
) -> dict[str, Any]:
    row = {
        "state": state,
        "provider": provider,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "nonce": nonce,
        "expires_at": expires_at,
        "consumed_at": None,
        "created_at": _now(),
    }
    with connect(path) as connection:
        connection.execute(sa.insert(login_flows).values(**row))
    return row


def load_login_flow(state: str, provider: str, now: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with engine(path).connect() as connection:
        return _row(
            connection.execute(
                sa.select(login_flows).where(
                    login_flows.c.state == state,
                    login_flows.c.provider == provider,
                    login_flows.c.consumed_at.is_(None),
                    login_flows.c.expires_at > now,
                )
            )
        )


def consume_login_flow(state: str, provider: str, now: str, path: Path | str | None = None) -> dict[str, Any] | None:
    with connect(path) as connection:
        row = _row(
            connection.execute(
                sa.select(login_flows).where(
                    login_flows.c.state == state,
                    login_flows.c.provider == provider,
                    login_flows.c.consumed_at.is_(None),
                    login_flows.c.expires_at > now,
                )
            )
        )
        if row is None:
            return None
        connection.execute(sa.update(login_flows).where(login_flows.c.state == state).values(consumed_at=now))
    return row
