"""Schema lifecycle commands.

`python -m app.dbctl upgrade` is what deployments run. It handles the case the plain Alembic
command cannot: a pilot database whose tables were created before Alembic existed, which has
no version row and would otherwise fail on CREATE TABLE.
"""

from __future__ import annotations

import argparse
import sys

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from .config import PROJECT_ROOT
from .database import configured_url, engine_for


ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
VERSION_TABLE = "alembic_version"
# Present in every database created by the pilot code, so its existence distinguishes
# "already has data" from "empty, create everything".
SENTINEL_TABLE = "runs"


def _config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", url)
    return config


def baseline_revision() -> str:
    script = ScriptDirectory(str(MIGRATIONS_DIR))
    bases = script.get_bases()
    if len(bases) != 1:
        raise RuntimeError(f"expected exactly one migration base, found {bases}")
    return bases[0]


def head_revision() -> str:
    heads = ScriptDirectory(str(MIGRATIONS_DIR)).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one migration head, found {heads}")
    return heads[0]


def current_revision(url: str | None = None) -> str | None:
    from alembic.runtime.migration import MigrationContext

    engine = engine_for(url or configured_url())
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def current_state(url: str) -> dict[str, bool]:
    inspector = sa.inspect(engine_for(url))
    tables = set(inspector.get_table_names())
    return {
        "versioned": VERSION_TABLE in tables,
        "populated": SENTINEL_TABLE in tables,
    }


def upgrade(url: str | None = None) -> str:
    """Bring a database to the current revision. Returns what was done."""
    target = url or configured_url()
    state = current_state(target)
    config = _config(target)
    if not state["versioned"] and state["populated"]:
        # Adopt the existing schema at the baseline instead of trying to recreate its tables.
        command.stamp(config, baseline_revision())
        command.upgrade(config, "head")
        return "adopted"
    command.upgrade(config, "head")
    return "upgraded"


def revision(message: str, url: str | None = None) -> None:
    command.revision(_config(url or configured_url()), message=message, autogenerate=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BidProof schema lifecycle")
    parser.add_argument("action", choices=("upgrade", "current", "revision"))
    parser.add_argument("--url", default=None, help="Target database URL (defaults to BIDPROOF_DATABASE_URL)")
    parser.add_argument("--message", default="schema change", help="Revision message for the revision action")
    arguments = parser.parse_args(argv)

    target = arguments.url or configured_url()
    if arguments.action == "upgrade":
        print(f"{upgrade(target)}: {_redacted(target)}")
    elif arguments.action == "current":
        command.current(_config(target), verbose=True)
    else:
        revision(arguments.message, target)
    return 0


def _redacted(url: str) -> str:
    return str(sa.engine.make_url(url).render_as_string(hide_password=True))


if __name__ == "__main__":
    sys.exit(main())
