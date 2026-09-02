"""The single definition of the BidProof schema.

Both the SQLite development/test databases and the PostgreSQL production database are built
from this metadata, and the Alembic baseline is generated from it, so there is no second place
where columns can drift.

Timestamps are stored as ISO-8601 strings rather than native timestamp types. That is what the
existing pilot data contains, and changing it is a data migration in its own right.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


metadata = sa.MetaData()


def json_column() -> sa.types.TypeEngine:
    """JSONB on PostgreSQL, JSON-encoded text on SQLite.

    The `runs` table keeps whole documents (state, requirements, review) in these columns.
    JSONB makes them indexable and queryable on PostgreSQL; on SQLite they behave exactly like
    the TEXT columns the pilot data already uses.
    """
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


workspaces = sa.Table(
    "workspaces",
    metadata,
    sa.Column("workspace_id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("retention_days", sa.Integer, nullable=False, server_default="365"),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_workspaces_created_at", "created_at"),
)


users = sa.Table(
    "users",
    metadata,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("username", sa.Text, nullable=False, unique=True),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("active", sa.Integer, nullable=False, server_default="1"),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_users_workspace", "workspace_id"),
)


workspace_members = sa.Table(
    "workspace_members",
    metadata,
    sa.Column("workspace_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
)


projects = sa.Table(
    "projects",
    metadata,
    sa.Column("project_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("archived_at", sa.Text),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.UniqueConstraint("workspace_id", "code", name="uq_projects_workspace_code"),
    sa.Index("idx_projects_workspace", "workspace_id"),
)


runs = sa.Table(
    "runs",
    metadata,
    sa.Column("run_id", sa.Text, primary_key=True),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("archived_at", sa.Text),
    sa.Column("workspace_id", sa.Text, nullable=False, server_default="local"),
    sa.Column("owner_id", sa.Text, nullable=False, server_default="local-owner"),
    sa.Column("parent_run_id", sa.Text),
    sa.Column("version_number", sa.Integer, nullable=False, server_default="1"),
    sa.Column("job_id", sa.Text),
    sa.Column("assignee_id", sa.Text),
    sa.Column("reviewer_id", sa.Text),
    sa.Column("tags_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("favorite", sa.Integer, nullable=False, server_default="0"),
    sa.Column("project_id", sa.Text),
    sa.Column("tender_sha256", sa.Text),
    sa.Column("duplicate_run_ids_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("tender_filename", sa.Text, nullable=False),
    sa.Column("tender_path", sa.Text, nullable=False),
    sa.Column("evidence_files", json_column(), nullable=False),
    sa.Column("state_json", json_column(), nullable=False),
    sa.Column("requirements_json", json_column(), nullable=False),
    sa.Column("review_json", json_column(), nullable=False),
    sa.Column("source_documents_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("evidence_assets_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("decision_json", json_column(), nullable=False, server_default="{}"),
    # The listing query filters by workspace and orders by recency; retention scans archived
    # rows; duplicate detection looks up the tender digest.
    sa.Index("idx_runs_workspace_created", "workspace_id", "created_at"),
    sa.Index("idx_runs_workspace_updated", "workspace_id", "updated_at"),
    sa.Index("idx_runs_workspace_archived", "workspace_id", "archived_at"),
    sa.Index("idx_runs_workspace_sha", "workspace_id", "tender_sha256"),
    sa.Index("idx_runs_project", "project_id"),
)


scan_jobs = sa.Table(
    "scan_jobs",
    metadata,
    sa.Column("job_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("run_id", sa.Text),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("error", sa.Text),
    sa.Column("progress_current", sa.Integer, nullable=False, server_default="0"),
    sa.Column("progress_total", sa.Integer, nullable=False, server_default="0"),
    sa.Column("progress_message", sa.Text, nullable=False, server_default=""),
    sa.Column("cancel_requested", sa.Integer, nullable=False, server_default="0"),
    sa.Column("payload_json", json_column(), nullable=False, server_default="{}"),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.Index("idx_scan_jobs_workspace_created", "workspace_id", "created_at"),
    # Startup recovery and, from P4, the queue claim both scan by status.
    sa.Index("idx_scan_jobs_status_created", "status", "created_at"),
    sa.Index("idx_scan_jobs_run", "run_id"),
)


audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("event_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("run_id", sa.Text),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("payload_json", json_column(), nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_audit_workspace_created", "workspace_id", "created_at"),
    sa.Index("idx_audit_workspace_run", "workspace_id", "run_id"),
)


comments = sa.Table(
    "comments",
    metadata,
    sa.Column("comment_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_comments_workspace_run", "workspace_id", "run_id"),
)


remediations = sa.Table(
    "remediations",
    metadata,
    sa.Column("remediation_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("requirement_id", sa.Text),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("owner_id", sa.Text),
    sa.Column("due_date", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="OPEN"),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Column("updated_at", sa.Text, nullable=False),
    sa.Index("idx_remediations_workspace_run", "workspace_id", "run_id"),
    sa.Index("idx_remediations_workspace_due", "workspace_id", "due_date"),
)


accuracy_feedback = sa.Table(
    "accuracy_feedback",
    metadata,
    sa.Column("feedback_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("run_id", sa.Text, nullable=False),
    sa.Column("requirement_id", sa.Text),
    sa.Column("feedback_key", sa.Text, nullable=False, server_default=""),
    sa.Column("category", sa.Text, nullable=False),
    sa.Column("predicted", sa.Text, nullable=False),
    sa.Column("actual", sa.Text, nullable=False),
    sa.Column("locator_label", sa.Text),
    sa.Column("quote", sa.Text),
    sa.Column("note", sa.Text, nullable=False),
    sa.Column("reviewer_id", sa.Text, nullable=False),
    sa.Column("dataset_scope", sa.Text, nullable=False, server_default="TEST"),
    sa.Column("review_complete", sa.Integer, nullable=False, server_default="0"),
    sa.Column("created_at", sa.Text, nullable=False),
    # One label per reviewer per finding; re-submitting replaces it rather than double counting.
    sa.Index(
        "idx_accuracy_feedback_key",
        "workspace_id",
        "run_id",
        "reviewer_id",
        "feedback_key",
        unique=True,
    ),
    sa.Index("idx_accuracy_feedback_scope", "workspace_id", "dataset_scope"),
)


auth_sessions = sa.Table(
    "auth_sessions",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("expires_at", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_auth_sessions_user", "user_id"),
)


auth_action_tokens = sa.Table(
    "auth_action_tokens",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("username", sa.Text),
    sa.Column("user_id", sa.Text),
    sa.Column("role", sa.Text),
    sa.Column("expires_at", sa.Text, nullable=False),
    sa.Column("used_at", sa.Text),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", sa.Text, nullable=False),
    sa.Index("idx_auth_action_tokens_invite", "purpose", "username"),
    sa.Index("idx_auth_action_tokens_reset", "purpose", "user_id"),
)


JSON_COLUMNS: dict[str, tuple[str, ...]] = {
    "runs": (
        "tags_json",
        "duplicate_run_ids_json",
        "evidence_files",
        "state_json",
        "requirements_json",
        "review_json",
        "source_documents_json",
        "evidence_assets_json",
        "decision_json",
    ),
    "scan_jobs": ("payload_json",),
    "audit_events": ("payload_json",),
}
