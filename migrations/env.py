"""Alembic environment.

The target metadata and the database URL both come from the application, so migrations and
the running code can never disagree about where the schema lives or what it should contain.
"""

from __future__ import annotations

from alembic import context

from app.database import configured_url, engine_for
from app.models import metadata


target_metadata = metadata


def _target_url() -> str:
    """An explicit `sqlalchemy.url` wins, so an operator can migrate a named database.

    Otherwise fall back to what the application itself would connect to, which keeps
    `alembic upgrade head` correct with no duplicated configuration.
    """
    override = context.config.get_main_option("sqlalchemy.url") or ""
    return override.strip() or configured_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_target_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most column properties in place; batch mode rewrites the table.
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_for(_target_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
