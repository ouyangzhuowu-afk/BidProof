"""Add listing counters, row revision, and workspace-scoped usernames.

Revision ID: a1b2c3d4e5f6
Revises: 9c4e1a7b2d10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9c4e1a7b2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("runs")}
    with op.batch_alter_table("runs") as batch:
        if "requirement_count" not in existing:
            batch.add_column(sa.Column("requirement_count", sa.Integer(), nullable=False, server_default="0"))
        if "unresolved_count" not in existing:
            batch.add_column(sa.Column("unresolved_count", sa.Integer(), nullable=False, server_default="0"))
        if "blocker_count" not in existing:
            batch.add_column(sa.Column("blocker_count", sa.Integer(), nullable=False, server_default="0"))
        if "fatal_risk_count" not in existing:
            batch.add_column(sa.Column("fatal_risk_count", sa.Integer(), nullable=False, server_default="0"))
        if "revision" not in existing:
            batch.add_column(sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    inspector = sa.inspect(bind)
    unique_names = {constraint["name"] for constraint in inspector.get_unique_constraints("users") if constraint.get("name")}
    unnamed_username = any(
        list(constraint.get("column_names") or []) == ["username"] and not constraint.get("name")
        for constraint in inspector.get_unique_constraints("users")
    )
    named_username = next(
        (
            constraint["name"]
            for constraint in inspector.get_unique_constraints("users")
            if list(constraint.get("column_names") or []) == ["username"] and constraint.get("name")
        ),
        None,
    )
    index_names = {index["name"] for index in inspector.get_indexes("users")}
    if named_username or unnamed_username:
        extra = [sa.UniqueConstraint("username", name="username")] if unnamed_username else []
        with op.batch_alter_table("users", reflect_args=extra) as batch:
            batch.drop_constraint(named_username or "username", type_="unique")
            if "idx_users_username" not in index_names:
                batch.create_index("idx_users_username", ["username"])
            if "uq_users_workspace_username" not in unique_names:
                batch.create_unique_constraint("uq_users_workspace_username", ["workspace_id", "username"])
    else:
        with op.batch_alter_table("users") as batch:
            if "idx_users_username" not in index_names:
                batch.create_index("idx_users_username", ["username"])
            if "uq_users_workspace_username" not in unique_names:
                batch.create_unique_constraint("uq_users_workspace_username", ["workspace_id", "username"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_workspace_username", type_="unique")
        batch.drop_index("idx_users_username")
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("revision")
        batch.drop_column("fatal_risk_count")
        batch.drop_column("blocker_count")
        batch.drop_column("unresolved_count")
        batch.drop_column("requirement_count")
