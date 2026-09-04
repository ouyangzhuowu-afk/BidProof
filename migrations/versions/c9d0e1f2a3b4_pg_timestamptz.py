"""Store timestamps as TIMESTAMPTZ on PostgreSQL.

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIMESTAMP_COLUMNS = (
    ("workspaces", "created_at"),
    ("users", "created_at"),
    ("workspace_members", "created_at"),
    ("projects", "archived_at"),
    ("projects", "created_at"),
    ("projects", "updated_at"),
    ("runs", "created_at"),
    ("runs", "updated_at"),
    ("runs", "archived_at"),
    ("scan_jobs", "created_at"),
    ("scan_jobs", "updated_at"),
    ("audit_events", "created_at"),
    ("api_tokens", "expires_at"),
    ("api_tokens", "revoked_at"),
    ("api_tokens", "last_used_at"),
    ("api_tokens", "created_at"),
    ("user_mfa", "confirmed_at"),
    ("user_mfa", "created_at"),
    ("identity_bindings", "created_at"),
    ("identity_bindings", "last_seen_at"),
    ("login_flows", "expires_at"),
    ("login_flows", "consumed_at"),
    ("login_flows", "created_at"),
    ("rate_limit_hits", "occurred_at"),
    ("comments", "created_at"),
    ("remediations", "created_at"),
    ("remediations", "updated_at"),
    ("accuracy_feedback", "created_at"),
    ("auth_sessions", "expires_at"),
    ("auth_sessions", "created_at"),
    ("auth_action_tokens", "expires_at"),
    ("auth_action_tokens", "used_at"),
    ("auth_action_tokens", "created_at"),
    ("project_members", "created_at"),
    ("idempotency_keys", "created_at"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column in TIMESTAMP_COLUMNS:
        if table not in tables:
            continue
        present = {item["name"] for item in inspector.get_columns(table)}
        if column not in present:
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE {table} ALTER COLUMN {column} TYPE TIMESTAMPTZ '
                f"USING CASE WHEN {column} IS NULL THEN NULL "
                f"ELSE CAST(replace({column}::text, 'Z', '+00:00') AS TIMESTAMPTZ) END"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, column in TIMESTAMP_COLUMNS:
        op.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE TEXT USING {column}::text"))
