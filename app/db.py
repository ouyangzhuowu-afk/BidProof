import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from .config import DB_PATH


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(path: Path = DB_PATH) -> None:
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                archived_at TEXT,
                workspace_id TEXT NOT NULL DEFAULT 'local',
                owner_id TEXT NOT NULL DEFAULT 'local-owner',
                parent_run_id TEXT,
                version_number INTEGER NOT NULL DEFAULT 1,
                job_id TEXT,
                assignee_id TEXT,
                reviewer_id TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                favorite INTEGER NOT NULL DEFAULT 0,
                project_id TEXT,
                tender_sha256 TEXT,
                duplicate_run_ids_json TEXT NOT NULL DEFAULT '[]',
                tender_filename TEXT NOT NULL,
                tender_path TEXT NOT NULL,
                evidence_files TEXT NOT NULL,
                state_json TEXT NOT NULL,
                requirements_json TEXT NOT NULL,
                review_json TEXT NOT NULL,
                source_documents_json TEXT NOT NULL DEFAULT '[]',
                evidence_assets_json TEXT NOT NULL DEFAULT '[]',
                decision_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                retention_days INTEGER NOT NULL DEFAULT 365,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                name TEXT NOT NULL,
                code TEXT NOT NULL,
                archived_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(workspace_id, code)
            );
            CREATE TABLE IF NOT EXISTS workspace_members (
                workspace_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (workspace_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                run_id TEXT,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scan_jobs (
                job_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                run_id TEXT,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                progress_current INTEGER NOT NULL DEFAULT 0,
                progress_total INTEGER NOT NULL DEFAULT 0,
                progress_message TEXT NOT NULL DEFAULT '',
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS remediations (
                remediation_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                requirement_id TEXT,
                title TEXT NOT NULL,
                owner_id TEXT,
                due_date TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accuracy_feedback (
                feedback_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                requirement_id TEXT,
                feedback_key TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                predicted TEXT NOT NULL,
                actual TEXT NOT NULL,
                locator_label TEXT,
                quote TEXT,
                note TEXT NOT NULL,
                reviewer_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_action_tokens (
                token_hash TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                username TEXT,
                user_id TEXT,
                role TEXT,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        columns = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
        for name, definition in {
            "archived_at": "TEXT",
            "workspace_id": "TEXT NOT NULL DEFAULT 'local'",
            "owner_id": "TEXT NOT NULL DEFAULT 'local-owner'",
            "parent_run_id": "TEXT",
            "version_number": "INTEGER NOT NULL DEFAULT 1",
            "job_id": "TEXT",
            "assignee_id": "TEXT",
            "reviewer_id": "TEXT",
            "tags_json": "TEXT NOT NULL DEFAULT '[]'",
            "favorite": "INTEGER NOT NULL DEFAULT 0",
            "project_id": "TEXT",
            "tender_sha256": "TEXT",
            "duplicate_run_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "source_documents_json": "TEXT NOT NULL DEFAULT '[]'",
            "evidence_assets_json": "TEXT NOT NULL DEFAULT '[]'",
            "decision_json": "TEXT NOT NULL DEFAULT '{}'",
        }.items():
            if name not in columns:
                db.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")
        job_columns = {row[1] for row in db.execute("PRAGMA table_info(scan_jobs)").fetchall()}
        if "payload_json" not in job_columns:
            db.execute("ALTER TABLE scan_jobs ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'")
        for name, definition in {
            "progress_current": "INTEGER NOT NULL DEFAULT 0",
            "progress_total": "INTEGER NOT NULL DEFAULT 0",
            "progress_message": "TEXT NOT NULL DEFAULT ''",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in job_columns:
                db.execute(f"ALTER TABLE scan_jobs ADD COLUMN {name} {definition}")
        user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        if "active" not in user_columns:
            db.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
        feedback_columns = {row[1] for row in db.execute("PRAGMA table_info(accuracy_feedback)").fetchall()}
        for name, definition in {
            "feedback_key": "TEXT NOT NULL DEFAULT ''",
            "locator_label": "TEXT",
            "quote": "TEXT",
            "dataset_scope": "TEXT NOT NULL DEFAULT 'TEST'",
            "review_complete": "INTEGER NOT NULL DEFAULT 0",
        }.items():
            if name not in feedback_columns:
                db.execute(f"ALTER TABLE accuracy_feedback ADD COLUMN {name} {definition}")
        workspace_columns = {row[1] for row in db.execute("PRAGMA table_info(workspaces)").fetchall()}
        if "retention_days" not in workspace_columns:
            db.execute("ALTER TABLE workspaces ADD COLUMN retention_days INTEGER NOT NULL DEFAULT 365")
        db.execute("UPDATE accuracy_feedback SET feedback_key = feedback_id WHERE feedback_key = ''")
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_accuracy_feedback_key "
            "ON accuracy_feedback(workspace_id, run_id, reviewer_id, feedback_key)"
        )


def save_run(run: dict[str, Any], path: Path = DB_PATH) -> None:
    with connect(path) as db:
        db.execute(
            """INSERT OR REPLACE INTO runs
            (run_id, created_at, updated_at, status, archived_at, workspace_id, owner_id, parent_run_id, version_number, job_id, assignee_id, reviewer_id, tags_json, favorite, project_id, tender_sha256, duplicate_run_ids_json, tender_filename, tender_path,
             evidence_files, state_json, requirements_json, review_json,
             source_documents_json, evidence_assets_json, decision_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run["run_id"],
                run["created_at"],
                run["updated_at"],
                run["status"],
                run.get("archived_at"),
                run.get("workspace_id", "local"),
                run.get("owner_id", "local-owner"),
                run.get("parent_run_id"),
                run.get("version_number", 1),
                run.get("job_id"),
                run.get("assignee_id"),
                run.get("reviewer_id"),
                json.dumps(run.get("tags", []), ensure_ascii=False),
                int(bool(run.get("favorite", False))),
                run.get("project_id"),
                run.get("tender_sha256"),
                json.dumps(run.get("duplicate_run_ids", []), ensure_ascii=False),
                run["tender_filename"],
                run["tender_path"],
                json.dumps(run["evidence_files"], ensure_ascii=False),
                json.dumps(run["state"], ensure_ascii=False),
                json.dumps(run["requirements"], ensure_ascii=False),
                json.dumps(run["review"], ensure_ascii=False),
                json.dumps(run.get("source_documents", []), ensure_ascii=False),
                json.dumps(run.get("evidence_assets", []), ensure_ascii=False),
                json.dumps(run.get("decision", {}), ensure_ascii=False),
            ),
        )


def load_run(run_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    for field in (
        "evidence_files",
        "state_json",
        "requirements_json",
        "review_json",
        "source_documents_json",
        "evidence_assets_json",
        "decision_json",
        "tags_json",
        "duplicate_run_ids_json",
    ):
        result[field] = json.loads(result[field])
    result["state"] = result.pop("state_json")
    result["requirements"] = result.pop("requirements_json")
    result["review"] = result.pop("review_json")
    result["source_documents"] = result.pop("source_documents_json")
    result["evidence_assets"] = result.pop("evidence_assets_json")
    result["decision"] = result.pop("decision_json")
    result["tags"] = result.pop("tags_json")
    result["duplicate_run_ids"] = result.pop("duplicate_run_ids_json")
    result["favorite"] = bool(result.get("favorite"))
    return result


def list_runs(path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute("SELECT run_id FROM runs ORDER BY created_at DESC").fetchall()
    runs = []
    for row in rows:
        run = load_run(row["run_id"], path)
        if run is not None:
            runs.append(run)
    return runs


def update_review(run_id: str, review: dict[str, Any], path: Path = DB_PATH) -> dict[str, Any] | None:
    run = load_run(run_id, path)
    if run is None:
        return None
    run["review"] = review
    run["updated_at"] = review["updated_at"]
    save_run(run, path)
    return run


def delete_run(run_id: str, path: Path = DB_PATH) -> bool:
    with connect(path) as db:
        db.execute("DELETE FROM comments WHERE run_id = ?", (run_id,))
        db.execute("DELETE FROM remediations WHERE run_id = ?", (run_id,))
        db.execute("DELETE FROM accuracy_feedback WHERE run_id = ?", (run_id,))
        db.execute("DELETE FROM scan_jobs WHERE run_id = ?", (run_id,))
        cursor = db.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
    return cursor.rowcount > 0


def ensure_workspace(workspace_id: str, user_id: str, role: str, name: str | None = None, path: Path = DB_PATH) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute("INSERT OR IGNORE INTO workspaces(workspace_id, name, created_at) VALUES (?, ?, ?)", (workspace_id, name or workspace_id, now))
        db.execute(
            "INSERT INTO workspace_members(workspace_id, user_id, role, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(workspace_id, user_id) DO UPDATE SET role=excluded.role",
            (workspace_id, user_id, role, now),
        )


def create_project(workspace_id: str, name: str, code: str, path: Path = DB_PATH) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    item = {"project_id": uuid.uuid4().hex, "workspace_id": workspace_id, "name": name, "code": code.upper(), "archived_at": None, "created_at": now, "updated_at": now}
    with connect(path) as db:
        db.execute(
            "INSERT INTO projects(project_id, workspace_id, name, code, archived_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            tuple(item.values()),
        )
    return item


def ensure_default_project(workspace_id: str, path: Path = DB_PATH) -> dict[str, Any]:
    with connect(path) as db:
        row = db.execute("SELECT * FROM projects WHERE workspace_id = ? AND code = 'DEFAULT'", (workspace_id,)).fetchone()
    return dict(row) if row else create_project(workspace_id, "默认项目", "DEFAULT", path)


def list_projects(workspace_id: str, include_archived: bool = False, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        query = "SELECT * FROM projects WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if not include_archived:
            query += " AND archived_at IS NULL"
        query += " ORDER BY created_at"
        rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def load_project(project_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    return dict(row) if row else None


def update_project(project_id: str, name: str | None = None, archived: bool | None = None, path: Path = DB_PATH) -> dict[str, Any] | None:
    from datetime import datetime, timezone

    project = load_project(project_id, path)
    if project is None:
        return None
    project["name"] = name or project["name"]
    if archived is not None:
        project["archived_at"] = datetime.now(timezone.utc).isoformat() if archived else None
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute("UPDATE projects SET name = ?, archived_at = ?, updated_at = ? WHERE project_id = ?", (project["name"], project["archived_at"], project["updated_at"], project_id))
    return project


def record_audit_event(workspace_id: str, user_id: str, event_type: str, run_id: str | None = None, payload: dict[str, Any] | None = None, path: Path = DB_PATH) -> str:
    import uuid
    from datetime import datetime, timezone

    event_id = uuid.uuid4().hex
    with connect(path) as db:
        db.execute(
            "INSERT INTO audit_events(event_id, workspace_id, run_id, user_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, workspace_id, run_id, user_id, event_type, json.dumps(payload or {}, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
    return event_id


def list_audit_events(workspace_id: str, run_id: str | None = None, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        if run_id:
            rows = db.execute("SELECT * FROM audit_events WHERE workspace_id = ? AND run_id = ? ORDER BY created_at DESC", (workspace_id, run_id)).fetchall()
        else:
            rows = db.execute("SELECT * FROM audit_events WHERE workspace_id = ? ORDER BY created_at DESC", (workspace_id,)).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        events.append(item)
    return events


def create_scan_job(job_id: str, workspace_id: str, run_id: str | None, status: str = "PENDING", payload: dict[str, Any] | None = None, path: Path = DB_PATH) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute("INSERT OR REPLACE INTO scan_jobs(job_id, workspace_id, run_id, status, attempts, error, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, 0, NULL, ?, ?, ?)", (job_id, workspace_id, run_id, status, json.dumps(payload or {}, ensure_ascii=False), now, now))


def update_scan_job(
    job_id: str,
    status: str,
    attempts: int | None = None,
    error: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    progress_message: str | None = None,
    cancel_requested: bool | None = None,
    path: Path = DB_PATH,
) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        updates = ["status = ?", "error = ?", "updated_at = ?"]
        values: list[Any] = [status, error, now]
        if attempts is not None:
            updates.append("attempts = ?")
            values.append(attempts)
        if progress_current is not None:
            updates.append("progress_current = ?")
            values.append(progress_current)
        if progress_total is not None:
            updates.append("progress_total = ?")
            values.append(progress_total)
        if progress_message is not None:
            updates.append("progress_message = ?")
            values.append(progress_message)
        if cancel_requested is not None:
            updates.append("cancel_requested = ?")
            values.append(int(bool(cancel_requested)))
        values.extend((job_id, status))
        db.execute(
            f"UPDATE scan_jobs SET {', '.join(updates)} WHERE job_id = ? AND (status != 'CANCELLED' OR ? = 'CANCELLED')",
            tuple(values),
        )


def load_scan_job(job_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["payload"] = json.loads(result.pop("payload_json"))
    return result


def cancel_scan_job(job_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    """Atomically cancel a pending or running scan job."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute(
            "UPDATE scan_jobs SET status = 'CANCELLED', cancel_requested = 1, error = NULL, progress_message = '已取消', updated_at = ? WHERE job_id = ? AND status IN ('PENDING', 'RUNNING')",
            (now, job_id),
        )
    return load_scan_job(job_id, path)


def start_scan_job(job_id: str, path: Path = DB_PATH, *, attempts: int | None = None, progress_total: int | None = None, progress_message: str | None = None) -> bool:
    """Atomically move a queued job to RUNNING; cancelled jobs cannot restart."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    assignments = ["status = 'RUNNING'", "updated_at = ?"]
    values: list[Any] = [now]
    if attempts is not None:
        assignments.append("attempts = ?")
        values.append(attempts)
    if progress_total is not None:
        assignments.append("progress_total = ?")
        values.append(progress_total)
    if progress_message is not None:
        assignments.append("progress_message = ?")
        values.append(progress_message)
    values.append(job_id)
    with connect(path) as db:
        cursor = db.execute(
            f"UPDATE scan_jobs SET {', '.join(assignments)} WHERE job_id = ? AND status IN ('PENDING', 'RUNNING') AND cancel_requested = 0",
            tuple(values),
        )
    return cursor.rowcount == 1


def link_scan_job(job_id: str, run_id: str, path: Path = DB_PATH) -> None:
    with connect(path) as db:
        db.execute("UPDATE scan_jobs SET run_id = ? WHERE job_id = ?", (run_id, job_id))


def list_recoverable_jobs(path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute("SELECT job_id FROM scan_jobs WHERE status IN ('PENDING', 'RUNNING') ORDER BY created_at").fetchall()
    return [job for row in rows if (job := load_scan_job(row["job_id"], path)) is not None]


def list_scan_jobs(workspace_id: str, limit: int = 100, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute(
            "SELECT job_id FROM scan_jobs WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace_id, limit),
        ).fetchall()
    return [job for row in rows if (job := load_scan_job(row["job_id"], path)) is not None]


def find_duplicate_run_ids(workspace_id: str, tender_sha256: str, path: Path = DB_PATH) -> list[str]:
    with connect(path) as db:
        rows = db.execute(
            "SELECT run_id FROM runs WHERE workspace_id = ? AND tender_sha256 = ? ORDER BY created_at DESC",
            (workspace_id, tender_sha256),
        ).fetchall()
    return [row["run_id"] for row in rows]


def get_workspace_settings(workspace_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT workspace_id, name, retention_days, created_at FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
    return dict(row) if row else None


def update_workspace_settings(workspace_id: str, retention_days: int, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        db.execute("UPDATE workspaces SET retention_days = ? WHERE workspace_id = ?", (retention_days, workspace_id))
    return get_workspace_settings(workspace_id, path)


def list_expired_archived_run_ids(workspace_id: str, cutoff: str, path: Path = DB_PATH) -> list[str]:
    with connect(path) as db:
        rows = db.execute(
            "SELECT run_id FROM runs WHERE workspace_id = ? AND archived_at IS NOT NULL AND archived_at < ? ORDER BY archived_at",
            (workspace_id, cutoff),
        ).fetchall()
    return [row["run_id"] for row in rows]


def add_comment(workspace_id: str, run_id: str, user_id: str, body: str, path: Path = DB_PATH) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    comment = {"comment_id": uuid.uuid4().hex, "workspace_id": workspace_id, "run_id": run_id, "user_id": user_id, "body": body, "created_at": datetime.now(timezone.utc).isoformat()}
    with connect(path) as db:
        db.execute("INSERT INTO comments(comment_id, workspace_id, run_id, user_id, body, created_at) VALUES (?, ?, ?, ?, ?, ?)", tuple(comment.values()))
    return comment


def list_comments(workspace_id: str, run_id: str, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM comments WHERE workspace_id = ? AND run_id = ? ORDER BY created_at DESC", (workspace_id, run_id)).fetchall()
    return [dict(row) for row in rows]


def create_remediation(workspace_id: str, run_id: str, payload: dict[str, Any], path: Path = DB_PATH) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "remediation_id": uuid.uuid4().hex,
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
    with connect(path) as db:
        db.execute("INSERT INTO remediations(remediation_id, workspace_id, run_id, requirement_id, title, owner_id, due_date, status, note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tuple(item.values()))
    return item


def list_remediations(workspace_id: str, run_id: str, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM remediations WHERE workspace_id = ? AND run_id = ? ORDER BY status, due_date, created_at", (workspace_id, run_id)).fetchall()
    return [dict(row) for row in rows]


def list_workspace_remediations(workspace_id: str, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute("SELECT * FROM remediations WHERE workspace_id = ? ORDER BY due_date, created_at", (workspace_id,)).fetchall()
    return [dict(row) for row in rows]


def load_remediation(remediation_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM remediations WHERE remediation_id = ?", (remediation_id,)).fetchone()
    return dict(row) if row else None


def update_remediation(remediation_id: str, payload: dict[str, Any], path: Path = DB_PATH) -> dict[str, Any] | None:
    from datetime import datetime, timezone

    current = load_remediation(remediation_id, path)
    if current is None:
        return None
    merged = {**current, **{key: value for key, value in payload.items() if value is not None}}
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        db.execute("UPDATE remediations SET title = ?, owner_id = ?, due_date = ?, status = ?, note = ?, updated_at = ? WHERE remediation_id = ?", (merged["title"], merged["owner_id"], merged["due_date"], merged["status"], merged["note"], merged["updated_at"], remediation_id))
    return load_remediation(remediation_id, path)


def workspace_usage(workspace_id: str, path: Path = DB_PATH) -> dict[str, int]:
    with connect(path) as db:
        counts = {
            "runs": db.execute("SELECT COUNT(*) FROM runs WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
            "members": db.execute("SELECT COUNT(*) FROM users WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
            "scan_jobs": db.execute("SELECT COUNT(*) FROM scan_jobs WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
            "audit_events": db.execute("SELECT COUNT(*) FROM audit_events WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
            "feedback": db.execute("SELECT COUNT(*) FROM accuracy_feedback WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
            "remediations": db.execute("SELECT COUNT(*) FROM remediations WHERE workspace_id = ?", (workspace_id,)).fetchone()[0],
        }
    return {key: int(value) for key, value in counts.items()}


def add_accuracy_feedback(workspace_id: str, run_id: str, reviewer_id: str, payload: dict[str, Any], path: Path = DB_PATH) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    category = payload["category"].upper()
    if payload["predicted"] == "DETECTED":
        feedback_key = f"detected:{payload.get('requirement_id', '')}"
    else:
        fingerprint = "|".join((category, (payload.get("locator_label") or "").strip(), (payload.get("quote") or "").strip()))
        feedback_key = f"missed:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()}"
    item = {
        "feedback_id": uuid.uuid4().hex,
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
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with connect(path) as db:
        db.execute(
            """INSERT INTO accuracy_feedback
            (feedback_id, workspace_id, run_id, requirement_id, feedback_key, category, predicted, actual, locator_label, quote, note, reviewer_id, dataset_scope, review_complete, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, run_id, reviewer_id, feedback_key) DO UPDATE SET
                category=excluded.category,
                predicted=excluded.predicted,
                actual=excluded.actual,
                locator_label=excluded.locator_label,
                quote=excluded.quote,
                note=excluded.note,
                dataset_scope=excluded.dataset_scope,
                review_complete=excluded.review_complete,
                created_at=excluded.created_at""",
            tuple(item.values()),
        )
        saved = db.execute(
            "SELECT * FROM accuracy_feedback WHERE workspace_id = ? AND run_id = ? AND reviewer_id = ? AND feedback_key = ?",
            (workspace_id, run_id, reviewer_id, feedback_key),
        ).fetchone()
    return dict(saved)


def accuracy_metrics(
    workspace_id: str,
    scopes: tuple[str, ...] = ("PILOT", "ENTERPRISE"),
    path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    if not scopes:
        return []
    placeholders = ",".join("?" for _ in scopes)
    with connect(path) as db:
        rows = db.execute(
            f"SELECT run_id, category, predicted, actual, review_complete, COUNT(*) AS count "
            f"FROM accuracy_feedback WHERE workspace_id = ? AND dataset_scope IN ({placeholders}) "
            "GROUP BY run_id, category, predicted, actual, review_complete",
            (workspace_id, *scopes),
        ).fetchall()
        scope_run_ids = {row["run_id"] for row in rows}
        if scope_run_ids:
            run_placeholders = ",".join("?" for _ in scope_run_ids)
            run_rows = db.execute(
                f"SELECT run_id, requirements_json FROM runs WHERE workspace_id = ? AND run_id IN ({run_placeholders})",
                (workspace_id, *scope_run_ids),
            ).fetchall()
        else:
            run_rows = []
    detected_totals: dict[str, int] = {}
    for run_row in run_rows:
        for requirement in json.loads(run_row["requirements_json"]):
            category = requirement.get("category", "UNCLASSIFIED")
            detected_totals[category] = detected_totals.get(category, 0) + 1
    grouped: dict[str, dict[str, int]] = {}
    observed_runs: dict[str, set[str]] = {}
    incomplete_runs: dict[str, set[str]] = {}
    for row in rows:
        counts = grouped.setdefault(row["category"], {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        category = row["category"]
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
            "measurement_status": "MEASURABLE" if coverage == 1 and sample_size >= 20 and review_population_complete else "INSUFFICIENT",
        })
    return result


def count_users(path: Path = DB_PATH) -> int:
    with connect(path) as db:
        return int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])


def primary_workspace_id(path: Path = DB_PATH) -> str | None:
    with connect(path) as db:
        row = db.execute("SELECT workspace_id FROM workspaces ORDER BY created_at ASC LIMIT 1").fetchone()
    return str(row["workspace_id"]) if row else None


def create_user(workspace_id: str, username: str, password_hash: str, role: str, path: Path = DB_PATH) -> dict[str, Any]:
    import uuid
    from datetime import datetime, timezone

    user = {"user_id": uuid.uuid4().hex, "workspace_id": workspace_id, "username": username, "password_hash": password_hash, "role": role, "active": 1, "created_at": datetime.now(timezone.utc).isoformat()}
    with connect(path) as db:
        db.execute("INSERT INTO users(user_id, workspace_id, username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(user.values()))
    return user


def list_workspace_members(workspace_id: str, path: Path = DB_PATH) -> list[dict[str, Any]]:
    with connect(path) as db:
        rows = db.execute(
            "SELECT user_id, workspace_id, username, role, active, created_at FROM users WHERE workspace_id = ? ORDER BY created_at",
            (workspace_id,),
        ).fetchall()
    return [{**dict(row), "active": bool(row["active"])} for row in rows]


def update_workspace_member(
    workspace_id: str,
    user_id: str,
    role: str | None = None,
    active: bool | None = None,
    path: Path = DB_PATH,
) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM users WHERE workspace_id = ? AND user_id = ?", (workspace_id, user_id)).fetchone()
        if row is None:
            return None
        next_role = role or row["role"]
        next_active = int(active) if active is not None else int(row["active"])
        db.execute("UPDATE users SET role = ?, active = ? WHERE user_id = ?", (next_role, next_active, user_id))
        db.execute("UPDATE workspace_members SET role = ? WHERE workspace_id = ? AND user_id = ?", (next_role, workspace_id, user_id))
        if not next_active:
            db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
        updated = db.execute(
            "SELECT user_id, workspace_id, username, role, active, created_at FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return {**dict(updated), "active": bool(updated["active"])}


def load_user_by_username(username: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def load_user_by_id(user_id: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_user_password(user_id: str, password_hash: str, path: Path = DB_PATH) -> bool:
    with connect(path) as db:
        updated = db.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (password_hash, user_id)).rowcount
        db.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    return bool(updated)


def create_auth_session(token_hash: str, user_id: str, expires_at: str, path: Path = DB_PATH) -> None:
    from datetime import datetime, timezone

    with connect(path) as db:
        db.execute("INSERT INTO auth_sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)", (token_hash, user_id, expires_at, datetime.now(timezone.utc).isoformat()))


def load_session_user(token_hash: str, now: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT u.* FROM auth_sessions s JOIN users u ON u.user_id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1", (token_hash, now)).fetchone()
    return dict(row) if row else None


def delete_auth_session(token_hash: str, path: Path = DB_PATH) -> None:
    with connect(path) as db:
        db.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))


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
    path: Path = DB_PATH,
) -> dict[str, Any]:
    from datetime import datetime, timezone

    created_at = datetime.now(timezone.utc).isoformat()
    with connect(path) as db:
        if purpose == "INVITE" and username:
            db.execute(
                "UPDATE auth_action_tokens SET used_at = ? WHERE purpose = 'INVITE' AND username = ? AND used_at IS NULL",
                (created_at, username),
            )
        if purpose == "RESET" and user_id:
            db.execute(
                "UPDATE auth_action_tokens SET used_at = ? WHERE purpose = 'RESET' AND user_id = ? AND used_at IS NULL",
                (created_at, user_id),
            )
        db.execute(
            """INSERT INTO auth_action_tokens
            (token_hash, workspace_id, purpose, username, user_id, role, expires_at, used_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (token_hash, workspace_id, purpose, username, user_id, role, expires_at, created_by, created_at),
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


def load_auth_action_token(token_hash: str, path: Path = DB_PATH) -> dict[str, Any] | None:
    with connect(path) as db:
        row = db.execute("SELECT * FROM auth_action_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
    return dict(row) if row else None


def consume_auth_action_token(token_hash: str, consumed_at: str, path: Path = DB_PATH) -> bool:
    with connect(path) as db:
        updated = db.execute(
            "UPDATE auth_action_tokens SET used_at = ? WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (consumed_at, token_hash, consumed_at),
        ).rowcount
    return bool(updated)
