"""SQLite must survive FastAPI's worker threads.

The synchronous routes run in a thread pool, so several requests reach the database at the
same time. A single shared connection made two threads drive one sqlite3 cursor, which raised
"sqlite3.InterfaceError: bad parameter or other API misuse". Opening a scan result fires half
a dozen requests at once, so reviewers saw 500s and then a 401 from the follow-up session
lookup, which the workbench reported as "登录状态已过期" and threw them back to the login
dialog in the middle of a task.
"""

import threading

import sqlalchemy as sa

from app import database, db, models


def _sqlite_url(tmp_path, name="concurrency.sqlite3") -> str:
    return f"sqlite+pysqlite:///{(tmp_path / name).as_posix()}"


def test_sqlite_file_engine_does_not_share_one_connection(tmp_path):
    """Two overlapping requests must not read and write through the same connection."""
    engine = database.engine_for(_sqlite_url(tmp_path))

    with engine.connect() as first, engine.connect() as second:
        assert first.connection.dbapi_connection is not second.connection.dbapi_connection


def test_in_memory_sqlite_keeps_a_single_connection():
    """The in-memory special case is deliberate: a new connection would open an empty database."""
    engine = database.engine_for("sqlite+pysqlite:///:memory:")

    assert database.is_in_memory_sqlite("sqlite+pysqlite:///:memory:")
    assert not database.is_in_memory_sqlite("sqlite+pysqlite:///pilot.sqlite3")
    with engine.connect() as first, engine.connect() as second:
        assert first.connection.dbapi_connection is second.connection.dbapi_connection


def test_concurrent_requests_keep_the_database_usable(tmp_path):
    """Overlapping reads and writes must all succeed, and the session must stay valid."""
    url = _sqlite_url(tmp_path)
    db.init_db(url)
    owner = db.create_user("workspace-a", "owner-a", "hash", "OWNER", url)
    token = "session-token-hash"
    db.create_auth_session(token, owner["user_id"], "2999-01-01T00:00:00+00:00", url)

    workers = 8
    rounds = 15
    barrier = threading.Barrier(workers)
    failures: list[str] = []
    lock = threading.Lock()

    def reader():
        barrier.wait()
        for _ in range(rounds):
            try:
                # The session lookup is the read that returned a spurious 401 while another
                # thread was writing through the same connection.
                user = db.load_session_user(token, "2000-01-01T00:00:00+00:00", url)
                assert user is not None and user["user_id"] == owner["user_id"]
                db.list_runs(url, workspace_id="workspace-a")
            except Exception as error:  # noqa: BLE001 - the failure text is the assertion
                with lock:
                    failures.append(f"{type(error).__name__}: {error}")
                return

    def writer(prefix):
        barrier.wait()
        for index in range(rounds):
            try:
                with db.connect(url) as connection:
                    connection.execute(
                        models.projects.insert().values(
                            project_id=f"project-{prefix}-{index}",
                            workspace_id="workspace-a",
                            name=f"project {prefix}-{index}",
                            code=f"PRJ-{prefix}-{index}",
                            created_at="2026-01-01T00:00:00+00:00",
                            updated_at="2026-01-01T00:00:00+00:00",
                        )
                    )
            except Exception as error:  # noqa: BLE001 - the failure text is the assertion
                with lock:
                    failures.append(f"{type(error).__name__}: {error}")
                return

    threads = [threading.Thread(target=reader) for _ in range(workers - 2)]
    threads += [threading.Thread(target=writer, args=(prefix,)) for prefix in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert failures == []
    with db.connect(url) as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(models.projects)).scalar() == rounds * 2
