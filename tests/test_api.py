from fastapi.testclient import TestClient
import fitz

from app import main
from app.services import scan_service


def test_healthz():
    client = TestClient(main.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    aliased = client.get("/api/v1/healthz")
    assert aliased.status_code == 200
    assert aliased.json() == response.json()


def test_upload_accepts_supported_text_tender(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(scan_service, "extract_file", lambda _path: [{"page": 1, "text": "资格要求", "has_text": True, "char_count": 4, "blocks": []}])
    response = client.post("/api/runs", files={"tender": ("tender.txt", "资格要求".encode("utf-8"), "text/plain")})
    assert response.status_code == 200
    client.delete(f"/api/runs/{response.json()['run_id']}")


def test_upload_rejects_unsupported_format():
    client = TestClient(main.app)
    response = client.post("/api/runs", files={"tender": ("tender.doc", b"legacy", "application/msword")})
    assert response.status_code == 400


def _pdf_bytes(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontfile=r"C:\Windows\Fonts\msyh.ttc")
    data = document.tobytes()
    document.close()
    return data


def test_upload_review_and_delete_lifecycle(monkeypatch):
    client = TestClient(main.app)
    def fake_extract(path):
        if path.suffix.lower() == ".pdf":
            return [{"page": 1, "text": "投标人资格要求：提供营业执照。投标截止时间：2026年9月1日。", "has_text": True, "char_count": 28}]
        return [{"page": 1, "text": "本公司营业执照及软件服务能力证明。", "has_text": True, "char_count": 18}]
    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    response = client.post(
        "/api/runs",
        data={"company_name": "示例软件服务有限公司"},
        files=[
            ("tender", ("tender.pdf", _pdf_bytes("投标人资格要求：提供营业执照。投标截止时间：2026年9月1日。"), "application/pdf")),
            ("evidence", ("company.txt", "本公司营业执照及软件服务能力证明。".encode("utf-8"), "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["requirements"]
    requirement = run["requirements"][0]
    reviewed = client.post(
        f"/api/runs/{run['run_id']}/review",
        json={"requirement_id": requirement["requirement_id"], "decision": "NEEDS_REVIEW", "note": "人工核对原件"},
    )
    assert reviewed.status_code == 200
    deleted = client.delete(f"/api/runs/{run['run_id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/runs/{run['run_id']}").status_code == 404


def test_structured_indexes_filters_and_manual_decision(monkeypatch):
    client = TestClient(main.app)

    def fake_extract(path):
        if path.name == "tender.pdf":
            return [{"page": 1, "text": "投标人资格要求：提供营业执照。出现以下情形的，否决投标。", "has_text": True, "char_count": 30}]
        return [{"page": 2, "text": "本公司营业执照已提供。", "has_text": True, "char_count": 12}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    response = client.post(
        "/api/runs",
        data={
            "company_name": "索引测试企业",
            "evidence_metadata": '{"certificate.txt":{"category":"CREDENTIAL","valid_until":"2027-12-31"}}',
        },
        files=[
            ("tender", ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")),
            ("evidence", ("certificate.txt", "营业执照".encode("utf-8"), "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["source_documents"][0]["sha256"]
    assert run["evidence_assets"][0]["category"] == "CREDENTIAL"

    summaries = client.get("/api/runs").json()
    assert any(item["run_id"] == run["run_id"] for item in summaries)
    filtered = client.get(f"/api/runs/{run['run_id']}/requirements?category=QUALIFICATION")
    assert filtered.status_code == 200
    assert all(item["category"] == "QUALIFICATION" for item in filtered.json()["requirements"])
    evidence = client.get(f"/api/runs/{run['run_id']}/evidence")
    assert evidence.json()["assets"][0]["valid_until"] == "2027-12-31"
    indexed = client.get("/api/evidence?category=CREDENTIAL&q=certificate")
    assert any(item["run_id"] == run["run_id"] for item in indexed.json()["assets"])

    decision = client.post(
        f"/api/runs/{run['run_id']}/decision",
        json={"decision": "HOLD", "note": "等待原件复核", "unresolved_requirement_ids": [run["requirements"][0]["requirement_id"]]},
    )
    assert decision.status_code == 200
    assert decision.json()["decision"]["decision"] == "HOLD"
    assert client.delete(f"/api/runs/{run['run_id']}").status_code == 200


def test_pass_review_requires_two_page_citations(monkeypatch):
    client = TestClient(main.app)

    def fake_extract(_path):
        return [{"page": 4, "text": "资格要求：提供营业执照。", "has_text": True, "char_count": 12}]

    monkeypatch.setattr(scan_service, "extract_file", fake_extract)
    response = client.post(
        "/api/runs",
        files={"tender": ("tender.pdf", _pdf_bytes("资格要求"), "application/pdf")},
    )
    run = response.json()
    reviewed = client.post(
        f"/api/runs/{run['run_id']}/review",
        json={"requirement_id": run["requirements"][0]["requirement_id"], "decision": "PASS"},
    )
    assert reviewed.status_code == 422
    client.delete(f"/api/runs/{run['run_id']}")
