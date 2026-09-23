"""Fence scan execution with a per-attempt lease.

Revision ID: d2e3f4a5b6c7
Revises: c9d0e1f2a3b4
"""
import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("scan_jobs")}
    if "lease_token" not in columns:
        op.add_column("scan_jobs", sa.Column("lease_token", sa.Text, nullable=True))


def downgrade():
    op.drop_column("scan_jobs", "lease_token")
