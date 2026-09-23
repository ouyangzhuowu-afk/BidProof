"""Readiness fails closed when a live process cannot safely serve new work."""
from __future__ import annotations

import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

from app import config, db, dbctl, main


@pytest.fixture
def probe_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "JOB_RUNNER", "worker")
    monkeypatch.setattr(db, "ping", lambda: True)
    monkeypatch.setattr(dbctl, "current_revision", lambda: "current-schema")
    monkeypatch.setattr(dbctl, "head_revision", lambda: "current-schema")
    heartbeat = tmp_path / "worker-heartbeat"
    heartbeat.write_text("alive", encoding="utf-8")
    return TestClient(main.app), heartbeat


def not_ready(client):
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert response.headers["cache-control"] == "no-store"
    return response


def test_current_schema_writable_storage_and_live_worker_are_ready(probe_environment):
    client, _ = probe_environment
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"


def test_database_failure_is_not_ready_without_disclosing_driver_details(probe_environment, monkeypatch):
    client, _ = probe_environment
    def offline():
        raise RuntimeError("postgresql://sensitive-host/internal-path?secret=hidden")
    monkeypatch.setattr(db, "ping", offline)
    response = not_ready(client)
    assert "sensitive-host" not in response.text
    assert client.get("/healthz").status_code == 200


def test_false_database_probe_is_not_ready(probe_environment, monkeypatch):
    client, _ = probe_environment
    monkeypatch.setattr(db, "ping", lambda: False)
    not_ready(client)


def test_missing_or_outdated_migration_rejects_new_traffic(probe_environment, monkeypatch):
    client, _ = probe_environment
    monkeypatch.setattr(dbctl, "current_revision", lambda: "older-schema")
    not_ready(client)
    monkeypatch.setattr(dbctl, "current_revision", lambda: None)
    not_ready(client)


@pytest.mark.parametrize("state", ["missing", "stale"])
def test_worker_must_have_a_recent_heartbeat(probe_environment, state):
    client, heartbeat = probe_environment
    if state == "missing":
        heartbeat.unlink()
    else:
        old = time.time() - 120
        os.utime(heartbeat, (old, old))
    not_ready(client)


def test_unwritable_storage_is_not_ready_without_exposing_paths(probe_environment, monkeypatch):
    client, _ = probe_environment
    def blocked(*args, **kwargs):
        raise PermissionError("/private/company-materials permission denied")
    monkeypatch.setattr(tempfile, "TemporaryFile", blocked)
    response = not_ready(client)
    assert "company-materials" not in response.text


def test_development_inline_does_not_require_worker_or_migration_stamp(probe_environment, monkeypatch):
    client, heartbeat = probe_environment
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "JOB_RUNNER", "inline")
    monkeypatch.setattr(dbctl, "current_revision", lambda: None)
    heartbeat.unlink()
    assert client.get("/readyz").status_code == 200


def test_probe_handles_heartbeat_disappearance_between_exists_and_stat(probe_environment, monkeypatch):
    client, heartbeat = probe_environment
    original = type(heartbeat).stat
    def race(path, *args, **kwargs):
        if path == heartbeat:
            raise FileNotFoundError("worker stopped during probe")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(type(heartbeat), "stat", race)
    not_ready(client)
