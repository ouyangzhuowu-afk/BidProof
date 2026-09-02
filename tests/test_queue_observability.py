"""Durable job queue, structured logs, optional metrics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import config, db, main, observability
from app.db import create_scan_job, init_db, load_scan_job, scan_jobs, update_scan_job
from tests.conftest import TEST_AUTH_HEADERS


def test_claim_next_takes_the_oldest_pending_job_once(tmp_path):
    database = tmp_path / "queue.sqlite3"
    init_db(database)
    create_scan_job("older", "ws", None, "PENDING", {}, database)
    create_scan_job("newer", "ws", None, "PENDING", {}, database)

    first = db.claim_next_scan_job(database)
    second = db.claim_next_scan_job(database)
    third = db.claim_next_scan_job(database)

    assert first["job_id"] == "older"
    assert first["status"] == "RUNNING"
    assert second["job_id"] == "newer"
    assert third is None
    assert load_scan_job("older", database)["status"] == "RUNNING"


def test_stale_running_jobs_are_returned_to_pending(tmp_path):
    database = tmp_path / "stale.sqlite3"
    init_db(database)
    create_scan_job("fresh", "ws", None, "RUNNING", {}, database)
    create_scan_job("stale", "ws", None, "RUNNING", {}, database)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    update_scan_job("stale", "RUNNING", path=database)
    with db.connect(database) as connection:
        connection.execute(
            scan_jobs.update()
            .where(scan_jobs.c.job_id == "stale")
            .values(updated_at=stale_time)
        )

    moved = db.requeue_stale_scan_jobs(30, database)

    assert moved == 1
    assert load_scan_job("stale", database)["status"] == "PENDING"
    assert load_scan_job("fresh", database)["status"] == "RUNNING"


def test_worker_dispatch_leaves_jobs_pending(monkeypatch):
    monkeypatch.setattr(config, "JOB_RUNNER", "worker")
    client = TestClient(main.app)
    response = client.post(
        "/api/jobs",
        headers=TEST_AUTH_HEADERS,
        files={"tender": ("queued.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<>\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}", headers=TEST_AUTH_HEADERS).json()
    assert job["status"] == "PENDING"


def test_inline_dispatch_still_runs_before_the_client_observes_the_job(monkeypatch):
    monkeypatch.setattr(config, "JOB_RUNNER", "inline")
    client = TestClient(main.app)
    response = client.post(
        "/api/jobs",
        headers=TEST_AUTH_HEADERS,
        files={"tender": ("broken.txt", "资格要求", "text/plain")},
    )

    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}", headers=TEST_AUTH_HEADERS).json()
    assert job["status"] == "FAILED"


def test_json_logs_include_the_request_id(monkeypatch, capsys):
    monkeypatch.setattr(config, "JSON_LOGS", True)
    observability.reset_for_tests()
    observability.configure()
    client = TestClient(main.app)

    response = client.get("/healthz", headers={"X-Request-ID": "trace-from-proxy"})
    captured = capsys.readouterr().out
    lines = [json.loads(line) for line in captured.splitlines() if line.startswith("{")]

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-from-proxy"
    matching = [row for row in lines if row.get("path") == "/healthz" and row.get("request_id") == "trace-from-proxy"]
    assert matching
    observability.reset_for_tests()


def test_metrics_are_absent_until_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(config, "METRICS_ENABLED", False)
    client = TestClient(main.app)

    assert client.get("/metrics", headers=TEST_AUTH_HEADERS).status_code == 404


def test_metrics_require_auth_and_emit_prometheus_text(monkeypatch):
    monkeypatch.setattr(config, "METRICS_ENABLED", True)
    observability.reset_for_tests()
    client = TestClient(main.app)
    client.get("/healthz")

    denied = client.get("/metrics", headers={"Authorization": "Bearer not-a-real-token"})
    allowed = client.get("/metrics", headers=TEST_AUTH_HEADERS)

    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert "bidproof_http_requests_total" in allowed.text
    assert 'bidproof_http_requests_total{method="GET",code="200"}' in allowed.text


def test_license_gate_is_silent_unless_required(monkeypatch):
    from app.license import LicenseError, check_on_startup, valid_key

    assert valid_key("bp-lic-example-key")
    assert not valid_key("not-a-license")
    monkeypatch.setattr(config, "LICENSE_REQUIRED", False)
    check_on_startup()
    monkeypatch.setattr(config, "LICENSE_REQUIRED", True)
    monkeypatch.setattr(config, "LICENSE_KEY", "")
    try:
        check_on_startup()
        raise AssertionError("expected LicenseError")
    except LicenseError:
        pass


def test_metrics_are_not_in_the_public_openapi_surface():
    operations = {
        f"{method.upper()} {path}"
        for path, item in main.app.openapi()["paths"].items()
        for method in item
        if method in {"get", "post", "patch", "delete", "put"}
    }
    assert "GET /metrics" not in operations
    assert len(operations) == 69
