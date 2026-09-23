"""Manual decisions must not overwrite changes made after the reviewer loaded a task."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import main
from app.schemas import DecisionRequest
from app.services import run_service, scan_service
from tests.conftest import TEST_AUTH_HEADERS


def _create_run(client, monkeypatch):
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{
        "page": 1, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 13,
    }])
    response = client.post("/api/runs", files={"tender": ("decision.txt", "资格要求".encode(), "text/plain")})
    assert response.status_code == 200, response.text
    return response.json()


def test_stale_decision_is_rejected_without_overwriting_or_auditing_success(monkeypatch):
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)
    run = _create_run(client, monkeypatch)
    path = f"/api/runs/{run['run_id']}"
    first = client.post(path + "/decision", json={"decision": "HOLD", "note": "先核对原件", "revision": run["revision"]})
    assert first.status_code == 200, first.text
    assert first.json()["revision"] == run["revision"] + 1
    audit_before = client.get(path + "/audit").json()
    stale = client.post(path + "/decision", json={"decision": "CONTINUE", "note": "陈旧界面的决定", "revision": run["revision"]})
    assert stale.status_code == 409
    after = client.get(path).json()
    assert after["decision"]["decision"] == "HOLD"
    assert after["decision"]["note"] == "先核对原件"
    assert after["revision"] == first.json()["revision"]
    assert client.get(path + "/audit").json() == audit_before
    client.delete(path)


def test_decision_with_latest_revision_succeeds_and_invalid_revision_is_rejected(monkeypatch):
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)
    run = _create_run(client, monkeypatch)
    path = f"/api/runs/{run['run_id']}"
    invalid = client.post(path + "/decision", json={"decision": "HOLD", "revision": 0})
    assert invalid.status_code == 422
    assert client.get(path).json()["revision"] == run["revision"]
    for decision in ["HOLD", "CONTINUE"]:
        revision = client.get(path).json()["revision"]
        saved = client.post(path + "/decision", json={"decision": decision, "note": "已核对", "revision": revision})
        assert saved.status_code == 200, saved.text
        assert saved.json()["decision"]["decision"] == decision
        assert saved.json()["revision"] == revision + 1
    client.delete(path)


def test_legacy_development_client_remains_compatible_but_advances_revision(monkeypatch):
    client = TestClient(main.app, headers=TEST_AUTH_HEADERS)
    run = _create_run(client, monkeypatch)
    path = f"/api/runs/{run['run_id']}"
    saved = client.post(path + "/decision", json={"decision": "HOLD", "note": "旧版客户端"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == run["revision"] + 1
    client.delete(path)


def test_production_decision_without_revision_fails_before_any_mutation(monkeypatch):
    monkeypatch.setattr(run_service.config, "ENVIRONMENT", "production")
    state = {"requirements": [], "decision": {"decision": "HOLD"}}
    with pytest.raises(HTTPException) as error:
        run_service.record_decision({}, state, DecisionRequest(decision="CONTINUE"))
    assert error.value.status_code == 422
    assert "revision" in error.value.detail
    assert state == {"requirements": [], "decision": {"decision": "HOLD"}}
