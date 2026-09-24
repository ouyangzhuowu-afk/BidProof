from fastapi.testclient import TestClient

from app import main


def test_public_root_presents_bidproof_product_and_routes_users_to_workspace():
    response = TestClient(main.app).get("/")

    assert response.status_code == 200
    assert "BidProof 投标材料检查" in response.text
    assert 'href="/app"' in response.text
    assert 'data-demo-play' in response.text
    assert "检查这份示例" in response.text
    assert "合成示例" in response.text
    assert "mail.qq.com" not in response.text
    assert "mailto:" not in response.text



def test_app_entrypoint_contains_workspace_and_account_lifecycle_dialogs():
    response = TestClient(main.app).get("/app")

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    assert "BidProof 企业证据工作台" in response.text
    assert 'id="auth-panel"' in response.text
    assert 'id="account-action-panel"' in response.text
    assert 'id="current-user"' in response.text
