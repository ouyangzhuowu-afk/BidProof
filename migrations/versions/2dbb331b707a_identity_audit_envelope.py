"""identity audit envelope

Revision ID: 2dbb331b707a
Revises: 50edb6898ab9
Create Date: 2026-09-02 14:12:34.177723
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2dbb331b707a"
down_revision: Union[str, None] = "50edb6898ab9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    present = _tables()

    if "api_tokens" not in present:
        op.create_table(
            "api_tokens",
            sa.Column("token_id", sa.Text(), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("workspace_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("role", sa.Text(), nullable=False),
            sa.Column("permissions_json", json_type, server_default="[]", nullable=False),
            sa.Column("token_prefix", sa.Text(), server_default="", nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.Text(), nullable=True),
            sa.Column("last_used_at", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("token_id"),
            sa.UniqueConstraint("token_hash"),
        )
    if "idx_api_tokens_workspace" not in _indexes("api_tokens"):
        with op.batch_alter_table("api_tokens", schema=None) as batch_op:
            batch_op.create_index("idx_api_tokens_workspace", ["workspace_id"], unique=False)

    if "identity_bindings" not in present:
        op.create_table(
            "identity_bindings",
            sa.Column("binding_id", sa.Text(), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("issuer", sa.Text(), nullable=False),
            sa.Column("subject", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("last_seen_at", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("binding_id"),
            sa.UniqueConstraint("provider", "issuer", "subject", name="uq_identity_binding_subject"),
        )
    if "idx_identity_bindings_user" not in _indexes("identity_bindings"):
        with op.batch_alter_table("identity_bindings", schema=None) as batch_op:
            batch_op.create_index("idx_identity_bindings_user", ["user_id"], unique=False)

    if "login_flows" not in present:
        op.create_table(
            "login_flows",
            sa.Column("state", sa.Text(), nullable=False),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("code_verifier", sa.Text(), nullable=False),
            sa.Column("redirect_uri", sa.Text(), nullable=False),
            sa.Column("nonce", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.Text(), nullable=False),
            sa.Column("consumed_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("state"),
        )

    if "rate_limit_hits" not in present:
        op.create_table(
            "rate_limit_hits",
            sa.Column("hit_id", sa.Text(), nullable=False),
            sa.Column("scope", sa.Text(), nullable=False),
            sa.Column("bucket", sa.Text(), nullable=False),
            sa.Column("occurred_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("hit_id"),
        )
    if "idx_rate_limit_scope_bucket" not in _indexes("rate_limit_hits"):
        with op.batch_alter_table("rate_limit_hits", schema=None) as batch_op:
            batch_op.create_index("idx_rate_limit_scope_bucket", ["scope", "bucket", "occurred_at"], unique=False)

    if "user_mfa" not in present:
        op.create_table(
            "user_mfa",
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("secret", sa.Text(), nullable=False),
            sa.Column("confirmed_at", sa.Text(), nullable=True),
            sa.Column("last_counter", sa.Integer(), server_default="0", nullable=False),
            sa.Column("recovery_codes_json", json_type, server_default="[]", nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("user_id"),
        )

    audit_columns = _columns("audit_events")
    audit_indexes = _indexes("audit_events")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        if "actor_ip" not in audit_columns:
            batch_op.add_column(sa.Column("actor_ip", sa.Text(), nullable=True))
        if "user_agent" not in audit_columns:
            batch_op.add_column(sa.Column("user_agent", sa.Text(), nullable=True))
        if "request_id" not in audit_columns:
            batch_op.add_column(sa.Column("request_id", sa.Text(), nullable=True))
        if "outcome" not in audit_columns:
            batch_op.add_column(sa.Column("outcome", sa.Text(), server_default="SUCCESS", nullable=False))
        if "idx_audit_request" not in audit_indexes:
            batch_op.create_index("idx_audit_request", ["request_id"], unique=False)
        if "idx_audit_type_created" not in audit_indexes:
            batch_op.create_index("idx_audit_type_created", ["event_type", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("idx_audit_type_created")
        batch_op.drop_index("idx_audit_request")
        batch_op.drop_column("outcome")
        batch_op.drop_column("request_id")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("actor_ip")

    op.drop_table("user_mfa")
    with op.batch_alter_table("rate_limit_hits", schema=None) as batch_op:
        batch_op.drop_index("idx_rate_limit_scope_bucket")

    op.drop_table("rate_limit_hits")
    op.drop_table("login_flows")
    with op.batch_alter_table("identity_bindings", schema=None) as batch_op:
        batch_op.drop_index("idx_identity_bindings_user")

    op.drop_table("identity_bindings")
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_index("idx_api_tokens_workspace")

    op.drop_table("api_tokens")
