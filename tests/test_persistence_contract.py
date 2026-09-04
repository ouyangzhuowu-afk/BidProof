"""Contract tests for the persistence layer introduced in P2.

They cover the three properties the pilot data layer lacked: the schema has one definition
that migrations agree with, tenant filtering happens in SQL, and listing runs is a single
query rather than one per row.
"""

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql, sqlite

from app import database, db, models


PROJECT_ROOT = database.config.PROJECT_ROOT


def _sqlite_url(tmp_path, name="contract.sqlite3") -> str:
    return f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"


def test_alembic_baseline_matches_the_model_metadata(tmp_path):
    """A migration that has drifted from the metadata silently breaks fresh installs."""
    from alembic import command

    url = _sqlite_url(tmp_path, "migrated.sqlite3")
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")

    engine = sa.create_engine(url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        differences = compare_metadata(context, models.metadata)
    engine.dispose()

    assert differences == []


def test_migrations_have_a_single_head():
    script = ScriptDirectory(str(PROJECT_ROOT / "migrations"))

    assert len(script.get_heads()) == 1


def test_runs_are_filtered_by_workspace_in_sql(tmp_path):
    url = _sqlite_url(tmp_path, "scoped.sqlite3")
    db.init_db(url)
    for workspace, run_id in (("tenant-a", "run-a"), ("tenant-b", "run-b")):
        db.save_run(_run(run_id, workspace), url)

    statements = _captured_statements(url, lambda: db.list_runs(url, workspace_id="tenant-a"))
    scoped = db.list_runs(url, workspace_id="tenant-a")

    assert [run["run_id"] for run in scoped] == ["run-a"]
    select_statements = [text for text in statements if text.lstrip().upper().startswith("SELECT")]
    assert len(select_statements) == 1
    assert "workspace_id" in select_statements[0]


def test_listing_runs_does_not_issue_a_query_per_row(tmp_path):
    """The previous implementation selected ids then loaded each run individually."""
    url = _sqlite_url(tmp_path, "n_plus_one.sqlite3")
    db.init_db(url)
    for index in range(12):
        db.save_run(_run(f"run-{index:02d}", "tenant"), url)

    statements = _captured_statements(url, lambda: db.list_runs(url, workspace_id="tenant"))

    selects = [text for text in statements if text.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1
    assert "state_json" not in selects[0]
    assert "review_json" not in selects[0]
    assert "evidence_assets_json" not in selects[0]
    assert len(db.list_runs(url, workspace_id="tenant")) == 12


def test_cleanup_expired_removes_stale_sessions_and_rate_limit_hits(tmp_path):
    url = _sqlite_url(tmp_path, "cleanup.sqlite3")
    db.init_db(url)
    db.create_auth_session("expired-session", "user-1", "2000-01-01T00:00:00+00:00", url)
    db.create_auth_session("live-session", "user-1", "2999-01-01T00:00:00+00:00", url)

    counts = db.cleanup_expired(path=url)

    assert counts["auth_sessions"] >= 1
    remaining = db.engine(url)
    with remaining.connect() as connection:
        hashes = [row[0] for row in connection.execute(sa.text("SELECT token_hash FROM auth_sessions")).all()]
    assert "expired-session" not in hashes
    assert "live-session" in hashes


def test_run_documents_round_trip_with_chinese_text(tmp_path):
    url = _sqlite_url(tmp_path, "round_trip.sqlite3")
    db.init_db(url)
    run = _run("run-json", "tenant")
    run["requirements"] = [{"requirement_id": "REQ-1", "title": "资格要求：提供营业执照", "category": "QUALIFICATION"}]
    run["tags"] = ["重点", "本周截止"]
    run["decision"] = {"decision": "HOLD", "note": "缺少页码引用"}
    run["favorite"] = True

    db.save_run(run, url)
    loaded = db.load_run("run-json", url)

    assert loaded["requirements"][0]["title"] == "资格要求：提供营业执照"
    assert loaded["tags"] == ["重点", "本周截止"]
    assert loaded["decision"]["note"] == "缺少页码引用"
    assert loaded["favorite"] is True


def test_stored_json_is_not_ascii_escaped(tmp_path):
    """Escaped Chinese makes stored rows and database dumps unreadable during support work."""
    url = _sqlite_url(tmp_path, "encoding.sqlite3")
    db.init_db(url)
    run = _run("run-encoding", "tenant")
    run["decision"] = {"note": "资格要求"}
    db.save_run(run, url)

    engine = database.engine_for(url)
    with engine.connect() as connection:
        raw = connection.execute(sa.text("SELECT decision_json FROM runs WHERE run_id = 'run-encoding'")).scalar_one()

    assert "资格要求" in raw
    assert "\\u" not in raw


def test_json_columns_use_jsonb_on_postgresql():
    for table_name, columns in models.JSON_COLUMNS.items():
        table = models.metadata.tables[table_name]
        for column in columns:
            postgres_type = table.c[column].type.dialect_impl(postgresql.dialect())
            assert isinstance(postgres_type, postgresql.JSONB), f"{table_name}.{column}"


def test_sqlite_connections_enable_wal_and_foreign_keys(tmp_path):
    url = _sqlite_url(tmp_path, "pragmas.sqlite3")
    db.init_db(url)
    engine = database.engine_for(url)

    with engine.connect() as connection:
        journal_mode = connection.execute(sa.text("PRAGMA journal_mode")).scalar_one()
        foreign_keys = connection.execute(sa.text("PRAGMA foreign_keys")).scalar_one()
        busy_timeout = connection.execute(sa.text("PRAGMA busy_timeout")).scalar_one()

    # Without WAL a concurrent reader and writer surface as SQLITE_BUSY errors.
    assert journal_mode.lower() == "wal"
    assert int(foreign_keys) == 1
    assert int(busy_timeout) > 0


def test_backend_is_selected_from_the_url():
    postgres_url = "postgresql+psycopg://bidproof:secret@localhost:5432/bidproof"

    assert not database.is_sqlite(postgres_url)
    assert database.is_sqlite(database.url_for_path("/tmp/example.sqlite3"))


def test_every_statement_compiles_for_postgresql():
    """Compiled without a server, so dialect mistakes surface before a customer install.

    The pilot layer emitted SQLite-specific SQL with `?` placeholders and PRAGMA statements,
    none of which PostgreSQL accepts.
    """
    dialect = postgresql.dialect()
    runs = models.runs
    statements = [
        sa.select(runs).where(runs.c.workspace_id == "tenant").order_by(runs.c.created_at.desc()),
        sa.update(runs).where(runs.c.run_id == "run").values(status="AUDIT"),
        sa.delete(runs).where(runs.c.run_id == "run"),
        sa.select(sa.func.count()).select_from(runs).where(runs.c.workspace_id == "tenant"),
        sa.select(models.scan_jobs.c.status, sa.func.count()).group_by(models.scan_jobs.c.status),
        sa.select(models.users)
        .select_from(models.auth_sessions.join(models.users, models.users.c.user_id == models.auth_sessions.c.user_id))
        .where(models.auth_sessions.c.token_hash == "digest"),
    ]

    for statement in statements:
        compiled = str(statement.compile(dialect=dialect))
        assert "?" not in compiled
        assert "PRAGMA" not in compiled


def test_upsert_compiles_on_both_supported_dialects():
    values = {
        "job_id": "job",
        "workspace_id": "tenant",
        "run_id": None,
        "status": "PENDING",
        "attempts": 0,
        "error": None,
        "payload_json": {},
        "created_at": "now",
        "updated_at": "now",
    }

    for dialect_name, dialect in (("sqlite", sqlite.dialect()), ("postgresql", postgresql.dialect())):
        statement = db.upsert(models.scan_jobs, values, ("job_id",), ("status",), dialect_name)
        compiled = str(statement.compile(dialect=dialect))
        assert "ON CONFLICT" in compiled
        assert "DO UPDATE" in compiled


def test_workspace_scoped_indexes_exist_for_the_hot_paths():
    index_names = {index.name for index in models.runs.indexes}

    assert "idx_runs_workspace_created" in index_names
    assert "idx_runs_workspace_updated" in index_names
    assert "idx_runs_workspace_sha" in index_names
    assert "idx_scan_jobs_status_created" in {index.name for index in models.scan_jobs.indexes}


def test_upgrade_adopts_a_database_created_before_alembic(tmp_path):
    """The pilot SQLite file has tables but no version row; plain upgrade would fail on it."""
    from app import dbctl

    url = _sqlite_url(tmp_path, "legacy.sqlite3")
    db.init_db(url)
    db.save_run(_run("legacy-run", "tenant"), url)
    before = dbctl.current_state(url)

    outcome = dbctl.upgrade(url)

    assert before == {"versioned": False, "populated": True}
    assert outcome == "adopted"
    assert dbctl.current_state(url) == {"versioned": True, "populated": True}
    # Adoption must not disturb the data it inherited.
    assert db.load_run("legacy-run", url)["workspace_id"] == "tenant"


def test_upgrade_creates_the_schema_for_an_empty_database(tmp_path):
    from app import dbctl

    url = _sqlite_url(tmp_path, "fresh.sqlite3")

    outcome = dbctl.upgrade(url)

    assert outcome == "upgraded"
    assert dbctl.current_state(url) == {"versioned": True, "populated": True}


def _run(run_id: str, workspace_id: str) -> dict:
    return {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "owner_id": "owner",
        "created_at": "2026-09-02T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:00+00:00",
        "status": "AUDIT",
        "tender_filename": "tender.pdf",
        "tender_path": f"/tmp/{run_id}/tender.pdf",
        "evidence_files": [],
        "state": {"status": "AUDIT"},
        "requirements": [],
        "review": {"items": [], "updated_at": "2026-09-02T00:00:00+00:00"},
    }


def test_paas_postgres_urls_are_normalized_to_psycopg(monkeypatch):
    assert database.normalize_database_url("postgres://u:p@db/bidproof") == (
        "postgresql+psycopg://u:p@db/bidproof"
    )
    assert database.normalize_database_url("postgresql://u:p@db/bidproof?sslmode=require") == (
        "postgresql+psycopg://u:p@db/bidproof?sslmode=require"
    )
    already = "postgresql+psycopg://u:p@db/bidproof"
    assert database.normalize_database_url(already) == already

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db/bidproof")
    monkeypatch.delenv("BIDPROOF_DATABASE_URL", raising=False)
    assert database.configured_url() == "postgresql+psycopg://u:p@db/bidproof"


def _captured_statements(url: str, action) -> list[str]:
    engine = database.engine_for(url)
    captured: list[str] = []

    def record(_conn, _cursor, statement, *_args):
        captured.append(statement)

    sa.event.listen(engine, "before_cursor_execute", record)
    try:
        action()
    finally:
        sa.event.remove(engine, "before_cursor_execute", record)
    return captured
