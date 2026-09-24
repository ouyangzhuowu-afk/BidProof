"""Persist passwordless challenges and atomic resend guards."""
from alembic import op

from app.models import auth_challenges, auth_delivery_guards, auth_rate_limits

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    auth_rate_limits.create(op.get_bind(), checkfirst=True)
    auth_delivery_guards.create(op.get_bind(), checkfirst=True)
    auth_challenges.create(op.get_bind(), checkfirst=True)


def downgrade():
    auth_challenges.drop(op.get_bind(), checkfirst=True)
    auth_delivery_guards.drop(op.get_bind(), checkfirst=True)
    auth_rate_limits.drop(op.get_bind(), checkfirst=True)
