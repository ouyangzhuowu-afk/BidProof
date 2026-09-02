"""End-to-end checks against a real PostgreSQL server.

Skipped unless BIDPROOF_TEST_POSTGRES_URL is set, because the rest of the suite runs on
SQLite. Dialect differences that unit tests cannot see -- JSONB storage, ON CONFLICT syntax,
parameter style -- only show up here.

    BIDPROOF_TEST_POSTGRES_URL=postgresql+psycopg://bidproof:PASSWORD@127.0.0.1:5432/bidproof \
        pytest tests/test_postgres_integration.py
"""

import os
import uuid

import pytest
import sqlalchemy as sa

from app import database, db, dbctl


POSTGRES_URL = os.environ.get("BIDPROOF_TEST_POSTGRES_URL", "").strip()

requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set BIDPROOF_TEST_POSTGRES_URL to run the PostgreSQL integration checks",
)


@pytest.fixture(scope="module")
def postgres_url() -> str:
    dbctl.upgrade(POSTGRES_URL)
    return POSTGRES_URL


def _run(run_id: str, workspace_id: str) -> dict:
    return {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "owner_id": "owner",
        "created_at": "2026-09-02T00:00:00+00:00",
        "updated_at": "2026-09-02T00:00:00+00:00",
        "status": "AUDIT",
        "tender_filename": "招标文件.pdf",
        "tender_path": f"/tmp/{run_id}/tender.pdf",
        "evidence_files": [],
        "state": {"status": "AUDIT"},
        "requirements": [{"requirement_id": "REQ-1", "title": "资格要求：提供营业执照", "category": "QUALIFICATION"}],
        "review": {"items": [], "updated_at": "2026-09-02T00:00:00+00:00"},
        "tags": ["重点"],
        "decision": {"note": "缺少页码引用"},
        "favorite": True,
    }


@requires_postgres
def test_migrations_produce_jsonb_columns(postgres_url):
    engine = database.engine_for(postgres_url)

    with engine.connect() as connection:
        types = dict(
            connection.execute(
                sa.text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'runs' AND column_name LIKE '%_json'"
                )
            ).all()
        )

    assert types
    assert set(types.values()) == {"jsonb"}


@requires_postgres
def test_run_documents_round_trip_through_jsonb(postgres_url):
    run_id = f"pg-{uuid.uuid4().hex[:10]}"
    db.save_run(_run(run_id, "pg-tenant"), postgres_url)

    loaded = db.load_run(run_id, postgres_url)

    assert loaded["requirements"][0]["title"] == "资格要求：提供营业执照"
    assert loaded["tags"] == ["重点"]
    assert loaded["decision"]["note"] == "缺少页码引用"
    assert loaded["favorite"] is True
    db.delete_run(run_id, postgres_url)


@requires_postgres
def test_workspace_scoping_is_enforced_by_the_query(postgres_url):
    suffix = uuid.uuid4().hex[:8]
    mine, theirs = f"mine-{suffix}", f"theirs-{suffix}"
    db.save_run(_run(mine, f"tenant-a-{suffix}"), postgres_url)
    db.save_run(_run(theirs, f"tenant-b-{suffix}"), postgres_url)

    scoped = db.list_runs(postgres_url, workspace_id=f"tenant-a-{suffix}")

    assert [run["run_id"] for run in scoped] == [mine]
    db.delete_run(mine, postgres_url)
    db.delete_run(theirs, postgres_url)


@requires_postgres
def test_accuracy_feedback_upsert_replaces_rather_than_duplicates(postgres_url):
    suffix = uuid.uuid4().hex[:8]
    workspace, run_id = f"fb-{suffix}", f"fb-run-{suffix}"
    db.save_run(_run(run_id, workspace), postgres_url)
    payload = {
        "category": "qualification",
        "predicted": "DETECTED",
        "actual": "RELEVANT",
        "requirement_id": "REQ-1",
        "dataset_scope": "PILOT",
        "review_complete": True,
    }

    db.add_accuracy_feedback(workspace, run_id, "reviewer", payload, postgres_url)
    db.add_accuracy_feedback(workspace, run_id, "reviewer", payload, postgres_url)
    metrics = db.accuracy_metrics(workspace, ("PILOT",), postgres_url)

    assert [(item["category"], item["sample_size"]) for item in metrics] == [("QUALIFICATION", 1)]
    db.delete_run(run_id, postgres_url)


@requires_postgres
def test_job_claim_is_atomic(postgres_url):
    suffix = uuid.uuid4().hex[:8]
    job_id = f"job-{suffix}"
    db.create_scan_job(job_id, f"jobs-{suffix}", None, "PENDING", {"tender_path": "x"}, postgres_url)

    first = db.start_scan_job(job_id, postgres_url, attempts=1)
    db.cancel_scan_job(job_id, postgres_url)
    after_cancel = db.start_scan_job(job_id, postgres_url, attempts=2)

    assert first is True
    # A cancelled job must not be restartable, or a cancel would silently be undone.
    assert after_cancel is False
