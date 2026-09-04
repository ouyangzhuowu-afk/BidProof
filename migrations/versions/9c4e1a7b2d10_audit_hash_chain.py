"""audit hash chain and member user index

Revision ID: 9c4e1a7b2d10
Revises: 2dbb331b707a
Create Date: 2026-09-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9c4e1a7b2d10"
down_revision: Union[str, None] = "2dbb331b707a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    if "audit_events" in sa.inspect(op.get_bind()).get_table_names():
        present = _columns("audit_events")
        if "prev_hash" not in present:
            op.add_column("audit_events", sa.Column("prev_hash", sa.Text(), nullable=True))
        if "event_hash" not in present:
            op.add_column("audit_events", sa.Column("event_hash", sa.Text(), nullable=True))
    if "workspace_members" in sa.inspect(op.get_bind()).get_table_names():
        if "idx_workspace_members_user" not in _indexes("workspace_members"):
            op.create_index("idx_workspace_members_user", "workspace_members", ["user_id"])


def downgrade() -> None:
    if "idx_workspace_members_user" in _indexes("workspace_members"):
        op.drop_index("idx_workspace_members_user", table_name="workspace_members")
    present = _columns("audit_events")
    if "event_hash" in present:
        op.drop_column("audit_events", "event_hash")
    if "prev_hash" in present:
        op.drop_column("audit_events", "prev_hash")
