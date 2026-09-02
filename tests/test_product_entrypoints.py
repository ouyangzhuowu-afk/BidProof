from fastapi.testclient import TestClient

from app import main


def test_public_root_presents_bidproof_product_and_routes_users_to_workspace():
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert "BidProof 投标资格与废标风险扫描" in response.text
    assert 'href="/app"' in response.text
    assert "申请企业试用" in response.text
    assert response.text.count("https://mail.qq.com/cgi-bin/qm_share") == 2
    assert "email=contact%40marketcase.net" in response.text
    assert "mailto:" not in response.text
    assert "outlook" not in response.text.lower()


def test_app_entrypoint_contains_workspace_and_account_lifecycle_dialogs():
    response = TestClient(main.app).get("/app")

    assert response.status_code == 200
    assert "BidProof 企业证据工作台" in response.text
    assert 'id="auth-panel"' in response.text
    assert 'id="account-action-panel"' in response.text
    assert 'id="current-user"' in response.text
