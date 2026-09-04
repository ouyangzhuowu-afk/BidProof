"""The single definition of the BidProof schema.

Both the SQLite development/test databases and the PostgreSQL production database are built
from this metadata, and the Alembic baseline is generated from it, so there is no second place
where columns can drift.

Python still sees UTC ISO-8601 strings. PostgreSQL stores TIMESTAMPTZ so range queries and
future monthly partitions can use native time types; SQLite keeps TEXT for the same values.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator


metadata = sa.MetaData()


class IsoTimestamp(TypeDecorator):
    """ISO-8601 strings in application code; TIMESTAMPTZ on PostgreSQL, TEXT on SQLite."""

    impl = sa.Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(sa.DateTime(timezone=True))
        return dialect.type_descriptor(sa.Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value
            text = str(value).replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return value



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
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_workspaces_created_at", "created_at"),
)


users = sa.Table(
    "users",
    metadata,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_users_workspace"), nullable=False),
    sa.Column("username", sa.Text, nullable=False),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("active", sa.Integer, nullable=False, server_default="1"),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.UniqueConstraint("workspace_id", "username", name="uq_users_workspace_username"),
    sa.Index("idx_users_workspace", "workspace_id"),
    sa.Index("idx_users_username", "username"),
)


workspace_members = sa.Table(
    "workspace_members",
    metadata,
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_members_workspace"), primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_workspace_members_user", "user_id"),
)


projects = sa.Table(
    "projects",
    metadata,
    sa.Column("project_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_projects_workspace"), nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("code", sa.Text, nullable=False),
    sa.Column("archived_at", IsoTimestamp()),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Column("updated_at", IsoTimestamp(), nullable=False),
    sa.UniqueConstraint("workspace_id", "code", name="uq_projects_workspace_code"),
    sa.Index("idx_projects_workspace", "workspace_id"),
)


runs = sa.Table(
    "runs",
    metadata,
    sa.Column("run_id", sa.Text, primary_key=True),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Column("updated_at", IsoTimestamp(), nullable=False),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("archived_at", IsoTimestamp()),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_runs_workspace"), nullable=False, server_default="local"),
    sa.Column("owner_id", sa.Text, nullable=False, server_default="local-owner"),
    sa.Column("parent_run_id", sa.Text, sa.ForeignKey("runs.run_id", ondelete="SET NULL", name="fk_runs_parent")),
    sa.Column("version_number", sa.Integer, nullable=False, server_default="1"),
    sa.Column("job_id", sa.Text),
    sa.Column("assignee_id", sa.Text),
    sa.Column("reviewer_id", sa.Text),
    sa.Column("tags_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("favorite", sa.Integer, nullable=False, server_default="0"),
    sa.Column("project_id", sa.Text, sa.ForeignKey("projects.project_id", ondelete="SET NULL", name="fk_runs_project")),
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
    sa.Column("requirement_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("unresolved_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("blocker_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("fatal_risk_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
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
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_jobs_workspace"), nullable=False),
    sa.Column("run_id", sa.Text, sa.ForeignKey("runs.run_id", ondelete="SET NULL", name="fk_jobs_run")),
    sa.Column("status", sa.Text, nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("error", sa.Text),
    sa.Column("progress_current", sa.Integer, nullable=False, server_default="0"),
    sa.Column("progress_total", sa.Integer, nullable=False, server_default="0"),
    sa.Column("progress_message", sa.Text, nullable=False, server_default=""),
    sa.Column("cancel_requested", sa.Integer, nullable=False, server_default="0"),
    sa.Column("payload_json", json_column(), nullable=False, server_default="{}"),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Column("updated_at", IsoTimestamp(), nullable=False),
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
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    # Who and from where, so an event can be tied to a session during an investigation.
    sa.Column("actor_ip", sa.Text),
    sa.Column("user_agent", sa.Text),
    sa.Column("request_id", sa.Text),
    sa.Column("outcome", sa.Text, nullable=False, server_default="SUCCESS"),
    sa.Column("prev_hash", sa.Text),
    sa.Column("event_hash", sa.Text),
    sa.Index("idx_audit_workspace_created", "workspace_id", "created_at"),
    sa.Index("idx_audit_workspace_run", "workspace_id", "run_id"),
    sa.Index("idx_audit_request", "request_id"),
    sa.Index("idx_audit_type_created", "event_type", "created_at"),
)


api_tokens = sa.Table(
    "api_tokens",
    metadata,
    sa.Column("token_id", sa.Text, primary_key=True),
    # Only the digest is stored; the plaintext is shown once at creation.
    sa.Column("token_hash", sa.Text, nullable=False, unique=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_tokens_workspace"), nullable=False),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    # Empty means the token inherits the full role; otherwise it is intersected with the role.
    sa.Column("permissions_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("token_prefix", sa.Text, nullable=False, server_default=""),
    sa.Column("expires_at", IsoTimestamp()),
    sa.Column("revoked_at", IsoTimestamp()),
    sa.Column("last_used_at", IsoTimestamp()),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_api_tokens_workspace", "workspace_id"),
)


user_mfa = sa.Table(
    "user_mfa",
    metadata,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("secret", sa.Text, nullable=False),
    sa.Column("confirmed_at", IsoTimestamp()),
    # Highest TOTP counter already accepted, so a captured code cannot be replayed.
    sa.Column("last_counter", sa.Integer, nullable=False, server_default="0"),
    sa.Column("recovery_codes_json", json_column(), nullable=False, server_default="[]"),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
)


identity_bindings = sa.Table(
    "identity_bindings",
    metadata,
    sa.Column("binding_id", sa.Text, primary_key=True),
    sa.Column("user_id", sa.Text, nullable=False),
    # "OIDC" or "LDAP", plus the issuer or directory URL that vouched for the subject.
    sa.Column("provider", sa.Text, nullable=False),
    sa.Column("issuer", sa.Text, nullable=False),
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Column("last_seen_at", IsoTimestamp()),
    sa.UniqueConstraint("provider", "issuer", "subject", name="uq_identity_binding_subject"),
    sa.Index("idx_identity_bindings_user", "user_id"),
)


login_flows = sa.Table(
    "login_flows",
    metadata,
    sa.Column("state", sa.Text, primary_key=True),
    sa.Column("provider", sa.Text, nullable=False),
    sa.Column("code_verifier", sa.Text, nullable=False),
    sa.Column("redirect_uri", sa.Text, nullable=False),
    sa.Column("nonce", sa.Text, nullable=False),
    sa.Column("expires_at", IsoTimestamp(), nullable=False),
    sa.Column("consumed_at", IsoTimestamp()),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
)


rate_limit_hits = sa.Table(
    "rate_limit_hits",
    metadata,
    sa.Column("hit_id", sa.Text, primary_key=True),
    # Scope names the protected action; bucket is the client identity within it.
    sa.Column("scope", sa.Text, nullable=False),
    sa.Column("bucket", sa.Text, nullable=False),
    sa.Column("occurred_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_rate_limit_scope_bucket", "scope", "bucket", "occurred_at"),
)


comments = sa.Table(
    "comments",
    metadata,
    sa.Column("comment_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_comments_workspace"), nullable=False),
    sa.Column("run_id", sa.Text, sa.ForeignKey("runs.run_id", ondelete="CASCADE", name="fk_comments_run"), nullable=False),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_comments_workspace_run", "workspace_id", "run_id"),
)


remediations = sa.Table(
    "remediations",
    metadata,
    sa.Column("remediation_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_remediations_workspace"), nullable=False),
    sa.Column("run_id", sa.Text, sa.ForeignKey("runs.run_id", ondelete="CASCADE", name="fk_remediations_run"), nullable=False),
    sa.Column("requirement_id", sa.Text),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("owner_id", sa.Text),
    sa.Column("due_date", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="OPEN"),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Column("updated_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_remediations_workspace_run", "workspace_id", "run_id"),
    sa.Index("idx_remediations_workspace_due", "workspace_id", "due_date"),
)


accuracy_feedback = sa.Table(
    "accuracy_feedback",
    metadata,
    sa.Column("feedback_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_feedback_workspace"), nullable=False),
    sa.Column("run_id", sa.Text, sa.ForeignKey("runs.run_id", ondelete="CASCADE", name="fk_feedback_run"), nullable=False),
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
    sa.Column("created_at", IsoTimestamp(), nullable=False),
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
    sa.Column("expires_at", IsoTimestamp(), nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_auth_sessions_user", "user_id"),
)


auth_action_tokens = sa.Table(
    "auth_action_tokens",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, sa.ForeignKey("workspaces.workspace_id", ondelete="CASCADE", name="fk_action_workspace"), nullable=False),
    sa.Column("purpose", sa.Text, nullable=False),
    sa.Column("username", sa.Text),
    sa.Column("user_id", sa.Text),
    sa.Column("role", sa.Text),
    sa.Column("expires_at", IsoTimestamp(), nullable=False),
    sa.Column("used_at", IsoTimestamp()),
    sa.Column("created_by", sa.Text, nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_auth_action_tokens_invite", "purpose", "username"),
    sa.Index("idx_auth_action_tokens_reset", "purpose", "user_id"),
)


project_members = sa.Table(
    "project_members",
    metadata,
    sa.Column("project_id", sa.Text, sa.ForeignKey("projects.project_id", ondelete="CASCADE", name="fk_project_members_project"), primary_key=True),
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("role", sa.Text, nullable=False, server_default="REVIEWER"),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.Index("idx_project_members_user", "user_id"),
)


idempotency_keys = sa.Table(
    "idempotency_keys",
    metadata,
    sa.Column("record_id", sa.Text, primary_key=True),
    sa.Column("workspace_id", sa.Text, nullable=False),
    sa.Column("idempotency_key", sa.Text, nullable=False),
    sa.Column("method", sa.Text, nullable=False),
    sa.Column("path", sa.Text, nullable=False),
    sa.Column("request_hash", sa.Text, nullable=False),
    sa.Column("status_code", sa.Integer, nullable=False),
    sa.Column("response_json", json_column(), nullable=False),
    sa.Column("created_at", IsoTimestamp(), nullable=False),
    sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_idempotency_workspace_key"),
    sa.Index("idx_idempotency_created", "created_at"),
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
    "user_mfa": ("recovery_codes_json",),
    "api_tokens": ("permissions_json",),
    "idempotency_keys": ("response_json",),
}
