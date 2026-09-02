"""Contract tests for the identity boundary hardened in P0.

Self-asserted identity headers are a test affordance. Any other environment must ignore them,
background jobs must not be able to replay a client identity, and operational health detail
must not be readable anonymously.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import identity, main
from app.db import create_scan_job, load_scan_job
from app.schemas import MIN_PASSWORD_LENGTH
from app.services import scan_service


ROOT = Path(__file__).resolve().parents[1]


def _config_in_env(**overrides: str) -> dict:
    environment = os.environ.copy()
    environment.update(overrides)
    command = (
        "import json; from app.config import ALLOW_TRUSTED_HEADERS, TRUSTED_HEADERS_IGNORED, ENVIRONMENT; "
        "print(json.dumps({'allow': ALLOW_TRUSTED_HEADERS, 'ignored': TRUSTED_HEADERS_IGNORED, 'env': ENVIRONMENT}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_trusted_headers_are_only_honoured_under_the_test_environment(tmp_path):
    data_root = {"BIDPROOF_DATA_ROOT": str(tmp_path / "runtime")}

    enabled = _config_in_env(BIDPROOF_ALLOW_TRUSTED_HEADERS="1", BIDPROOF_ENV="test", **data_root)
    development = _config_in_env(BIDPROOF_ALLOW_TRUSTED_HEADERS="1", BIDPROOF_ENV="development", **data_root)
    production = _config_in_env(BIDPROOF_ALLOW_TRUSTED_HEADERS="1", BIDPROOF_ENV="production", **data_root)

    assert enabled["allow"] is True
    assert enabled["ignored"] is False
    assert development["allow"] is False
    assert production["allow"] is False
    # An operator who sets the flag in a real environment gets told it was dropped.
    assert development["ignored"] is True
    assert production["ignored"] is True


def test_development_environment_rejects_forged_identity_headers(tmp_path):
    environment = os.environ.copy()
    environment["BIDPROOF_DATA_ROOT"] = str(tmp_path / "dev-runtime")
    environment["BIDPROOF_ENV"] = "development"
    environment["BIDPROOF_ALLOW_TRUSTED_HEADERS"] = "1"
    command = (
        "from fastapi.testclient import TestClient; from app.main import app; "
        "client=TestClient(app); "
        "response=client.get('/api/runs', headers={'X-Workspace-ID':'forged','X-User-Role':'OWNER'}); "
        "print(response.status_code)"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "401"


def test_health_liveness_stays_anonymous_and_carries_no_operational_state():
    client = TestClient(main.app)

    liveness = client.get("/healthz")

    assert liveness.status_code == 200
    assert liveness.json()["status"] == "ok"
    # A load balancer must be able to probe this without learning anything about the estate.
    assert set(liveness.json()) == {"status", "service"}


def test_health_detail_is_readable_by_an_authenticated_caller():
    client = TestClient(main.app)

    detail = client.get(
        "/healthz?detail=true",
        headers={"X-Workspace-ID": "health-scope", "X-User-ID": "health-owner", "X-User-Role": "OWNER"},
    )

    assert detail.status_code == 200
    assert detail.json()["database"] == "ok"


def test_health_detail_is_refused_anonymously_in_a_real_environment(tmp_path):
    """Asserted out of process because the in-process suite runs with the test affordances on."""
    environment = os.environ.copy()
    environment["BIDPROOF_DATA_ROOT"] = str(tmp_path / "health-runtime")
    environment["BIDPROOF_ENV"] = "production"
    environment["BIDPROOF_ALLOW_TRUSTED_HEADERS"] = "0"
    command = (
        "from fastapi.testclient import TestClient; from app.main import app; "
        "client=TestClient(app); "
        "print(client.get('/healthz').status_code, client.get('/healthz?detail=true').status_code)"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "200 401"


def test_client_cannot_bind_a_run_to_an_arbitrary_scan_job(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(
        scan_service,
        "extract_file",
        lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}],
    )
    victim = {"X-Workspace-ID": "job-victim", "X-User-ID": "victim", "X-User-Role": "OWNER"}
    attacker = {"X-Workspace-ID": "job-attacker", "X-User-ID": "attacker", "X-User-Role": "OWNER"}
    create_scan_job("victim-job", "job-victim", None, "PENDING", {"tender_path": "victim.pdf"})

    created = client.post(
        "/api/runs",
        headers={**attacker, "X-BidProof-Job-ID": "victim-job"},
        files={"tender": ("tender.txt", "资格要求".encode("utf-8"), "text/plain")},
    )

    assert created.status_code == 200
    # The forged header must be ignored: the victim job stays PENDING and a fresh job is used.
    assert load_scan_job("victim-job")["status"] == "PENDING"
    client.delete(f"/api/runs/{created.json()['run_id']}", headers=attacker)
    assert client.get("/api/jobs", headers=victim).json()["jobs"][0]["job_id"] == "victim-job"


def test_internal_job_context_carries_verified_identity_not_headers():
    context = identity.InternalJobContext(
        workspace_id="queued-workspace",
        user_id="queued-user",
        role="REVIEWER",
        job_id="queued-job",
    )

    assert identity.principal_of(context) == {
        "workspace_id": "queued-workspace",
        "user_id": "queued-user",
        "role": "REVIEWER",
    }
    # Identity is not reachable through headers, so it cannot be spoofed or replayed.
    assert context.headers == {}
    assert identity.job_id_of(context) == "queued-job"


def test_under_length_password_fails_as_unauthorized_not_validation_error():
    client = TestClient(main.app)

    response = client.post("/api/auth/login", json={"username": "nobody", "password": "short"})

    assert len("short") < MIN_PASSWORD_LENGTH
    assert response.status_code == 401
    assert response.json()["detail"] == "用户名或密码错误"
