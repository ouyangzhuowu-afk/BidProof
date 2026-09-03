"""Engine construction and dialect behaviour.

One SQLAlchemy engine per database URL, cached for the process. PostgreSQL is the recommended
production backend; SQLite remains supported for development, tests and single-node installs
where an extra service is unwelcome.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool

from . import config
from .models import metadata


DATABASE_URL_ENV = "BIDPROOF_DATABASE_URL"
POOL_SIZE = int(os.environ.get("BIDPROOF_DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.environ.get("BIDPROOF_DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT_SECONDS = int(os.environ.get("BIDPROOF_DB_POOL_TIMEOUT", "30"))
SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("BIDPROOF_SQLITE_BUSY_TIMEOUT_MS", "5000"))

_engines: dict[str, Engine] = {}


def _json_dumps(value: object) -> str:
    # Chinese tender text stays readable in the stored JSON and in database dumps.
    return json.dumps(value, ensure_ascii=False)


def normalize_database_url(url: str) -> str:
    """Accept PaaS-style URLs and pin PostgreSQL to the installed psycopg3 driver.

    Render and similar hosts inject `postgres://` or `postgresql://`. SQLAlchemy's default
    `postgresql://` dialect expects psycopg2, which this image does not install.
    """
    url = url.strip()
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def configured_url() -> str:
    """The configured database URL, defaulting to the SQLite file under the data root."""
    configured = os.environ.get(DATABASE_URL_ENV, "").strip() or os.environ.get("DATABASE_URL", "").strip()
    return normalize_database_url(configured) or url_for_path(config.DB_PATH)


def url_for_path(path: Path | str) -> str:
    return f"sqlite+pysqlite:///{Path(path).as_posix()}"


def is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def engine_for(target: Path | str | None = None) -> Engine:
    """Return the cached engine for a URL, a SQLite file path, or the configured default."""
    if target is None:
        url = configured_url()
    elif isinstance(target, Path):
        url = url_for_path(target)
    elif "://" in target:
        url = target
    else:
        url = url_for_path(target)
    if url not in _engines:
        _engines[url] = _create_engine(url)
    return _engines[url]


def _create_engine(url: str) -> Engine:
    if is_sqlite(url):
        engine = sa.create_engine(
            url,
            future=True,
            json_serializer=_json_dumps,
            # A single shared connection keeps SQLite's one-writer model predictable and lets
            # WAL and busy_timeout apply consistently.
            poolclass=StaticPool,
            connect_args={"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000},
        )
        sa.event.listen(engine, "connect", _apply_sqlite_pragmas)
        return engine
    return sa.create_engine(
        url,
        future=True,
        json_serializer=_json_dumps,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        # Recycle before a typical proxy or firewall idle timeout drops the socket.
        pool_recycle=1800,
        pool_pre_ping=True,
    )


def _apply_sqlite_pragmas(connection, _record) -> None:
    cursor = connection.cursor()
    try:
        # WAL lets readers proceed during a write; without it concurrent requests surface as
        # SQLITE_BUSY errors.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def create_schema(target: Path | str | None = None) -> None:
    """Create any missing tables and indexes from the metadata.

    Used for development, tests and first install. Versioned changes to an existing deployment
    go through Alembic, which is generated from the same metadata.
    """
    engine = engine_for(target)
    metadata.create_all(engine, checkfirst=True)
    _add_columns_missing_from_metadata(engine)


def _add_columns_missing_from_metadata(engine: Engine) -> None:
    """Bring a pre-Alembic database up to the current column set.

    Pilot SQLite files were created before this metadata existed and before Alembic was
    introduced. Deriving the additions from the metadata means there is no second hand-written
    list of columns to keep in step.
    """
    inspector = sa.inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                connection.execute(sa.text(f"ALTER TABLE {table.name} ADD COLUMN {_column_ddl(column, engine)}"))


def _column_ddl(column: sa.Column, engine: Engine) -> str:
    column_type = column.type.compile(engine.dialect)
    clause = f"{column.name} {column_type}"
    if column.server_default is not None:
        default = column.server_default.arg
        literal = default if str(default).lstrip("-").isdigit() else f"'{default}'"
        clause += f" NOT NULL DEFAULT {literal}" if not column.nullable else f" DEFAULT {literal}"
    return clause


def dispose_all() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
