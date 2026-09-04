"""Add foreign keys, project ACL, and idempotency keys.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _fk_names(inspector, table: str) -> set[str]:
    return {item["name"] for item in inspector.get_foreign_keys(table) if item.get("name")}


def _ensure_fk(batch, inspector, table: str, name: str, referent: str, local: list[str], remote: list[str], ondelete: str) -> None:
    if name in _fk_names(inspector, table):
        return
    batch.create_foreign_key(name, referent, local, remote, ondelete=ondelete)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "project_members" not in tables:
        op.create_table(
            "project_members",
            sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.project_id", ondelete="CASCADE", name="fk_project_members_project"), primary_key=True),
            sa.Column("user_id", sa.Text(), primary_key=True),
            sa.Column("role", sa.Text(), nullable=False, server_default="REVIEWER"),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
        op.create_index("idx_project_members_user", "project_members", ["user_id"])
    if "idempotency_keys" not in tables:
        op.create_table(
            "idempotency_keys",
            sa.Column("record_id", sa.Text(), primary_key=True),
            sa.Column("workspace_id", sa.Text(), nullable=False),
            sa.Column("idempotency_key", sa.Text(), nullable=False),
            sa.Column("method", sa.Text(), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("request_hash", sa.Text(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("response_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_idempotency_workspace_key"),
        )
        op.create_index("idx_idempotency_created", "idempotency_keys", ["created_at"])

    inspector = sa.inspect(bind)
    with op.batch_alter_table("users") as batch:
        _ensure_fk(batch, inspector, "users", "fk_users_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
    with op.batch_alter_table("workspace_members") as batch:
        _ensure_fk(batch, inspector, "workspace_members", "fk_members_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
    with op.batch_alter_table("projects") as batch:
        _ensure_fk(batch, inspector, "projects", "fk_projects_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
    with op.batch_alter_table("runs") as batch:
        _ensure_fk(batch, inspector, "runs", "fk_runs_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
        _ensure_fk(batch, inspector, "runs", "fk_runs_project", "projects", ["project_id"], ["project_id"], "SET NULL")
        _ensure_fk(batch, inspector, "runs", "fk_runs_parent", "runs", ["parent_run_id"], ["run_id"], "SET NULL")
    with op.batch_alter_table("scan_jobs") as batch:
        _ensure_fk(batch, inspector, "scan_jobs", "fk_jobs_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
        _ensure_fk(batch, inspector, "scan_jobs", "fk_jobs_run", "runs", ["run_id"], ["run_id"], "SET NULL")
    with op.batch_alter_table("comments") as batch:
        _ensure_fk(batch, inspector, "comments", "fk_comments_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
        _ensure_fk(batch, inspector, "comments", "fk_comments_run", "runs", ["run_id"], ["run_id"], "CASCADE")
    with op.batch_alter_table("remediations") as batch:
        _ensure_fk(batch, inspector, "remediations", "fk_remediations_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
        _ensure_fk(batch, inspector, "remediations", "fk_remediations_run", "runs", ["run_id"], ["run_id"], "CASCADE")
    with op.batch_alter_table("accuracy_feedback") as batch:
        _ensure_fk(batch, inspector, "accuracy_feedback", "fk_feedback_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
        _ensure_fk(batch, inspector, "accuracy_feedback", "fk_feedback_run", "runs", ["run_id"], ["run_id"], "CASCADE")
    with op.batch_alter_table("api_tokens") as batch:
        _ensure_fk(batch, inspector, "api_tokens", "fk_tokens_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")
    with op.batch_alter_table("auth_action_tokens") as batch:
        _ensure_fk(batch, inspector, "auth_action_tokens", "fk_action_workspace", "workspaces", ["workspace_id"], ["workspace_id"], "CASCADE")


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("project_members")
