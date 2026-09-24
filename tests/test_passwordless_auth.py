"""Passwordless flows use real database state and an injected delivery boundary only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app import auth_delivery, config, db, main, oidc
from app.models import (
    auth_challenges,
    auth_delivery_guards,
    identity_bindings,
    login_flows,
    users,
    workspaces,
)
from app.repositories import accounts, challenges
from app.repositories import identity as identities
from app.security import password_hash
from app.services import passwordless_service as service


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BIDPROOF_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'auth.sqlite3'}")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("BIDPROOF_OTP_SECRET", "test-server-secret-" * 3)
    monkeypatch.setenv("BIDPROOF_SMTP_HOST", "localhost")
    monkeypatch.setenv("BIDPROOF_SMTP_FROM", "login@example.test")
    monkeypatch.setenv("BIDPROOF_SMTP_SECURITY", "plain")
    monkeypatch.setenv("BIDPROOF_TWILIO_ACCOUNT_SID", "AC" + "a" * 32)
    monkeypatch.setenv("BIDPROOF_TWILIO_AUTH_TOKEN", "test-provider-secret")
    monkeypatch.setenv("BIDPROOF_TWILIO_FROM", "+12025550123")
    monkeypatch.setenv("BIDPROOF_SMS_ALLOWED_PREFIXES", "+86")
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True)
    db.init_db()


@pytest.fixture
def delivered(monkeypatch):
    messages = []
    monkeypatch.setattr(auth_delivery, "send", lambda channel, target, code: messages.append((channel, target, code)))
    return messages


def request_code(client, address="person@example.test", channel="email"):
    return client.post("/api/auth/challenges", json={"identifier": address, "channel": channel})


def verify(client, challenge, code):
    return client.post("/api/auth/challenges/verify", json={"challenge_id": challenge, "code": code})


def expire_cooldown():
    with db.engine().begin() as connection:
        connection.execute(sa.update(auth_delivery_guards).values(sent_at=(datetime.now(UTC) - timedelta(seconds=61)).isoformat()))


def test_new_email_then_returning_login_uses_same_isolated_workspace(delivered):
    client = TestClient(main.app)
    first = request_code(client, "  Person@Example.test ")
    assert first.status_code == 200
    outcome = first.json()
    code = delivered[-1][2]
    assert code not in first.text
    assert outcome["masked_identifier"] == "p***@example.test"
    assert outcome["resend_after"] == 60 and outcome["expires_in"] == 300
    with db.engine().connect() as connection:
        row = connection.execute(sa.select(auth_challenges)).mappings().one()
        assert row["code_digest"] != code and len(row["code_digest"]) == 64
    logged_in = verify(client, outcome["challenge_id"], code)
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["role"] == "OWNER"
    assert client.get("/api/auth/status").json()["authenticated"]
    assert len(db.list_workspace_members(logged_in.json()["workspace_id"])) == 1
    assert verify(client, outcome["challenge_id"], code).status_code == 410
    client.post("/api/auth/logout")
    expire_cooldown()
    second = request_code(client).json()
    returning = verify(client, second["challenge_id"], delivered[-1][2])
    assert returning.json()["user_id"] == logged_in.json()["user_id"]
    assert accounts.count() == 1


def test_phone_normalization_region_guard_and_separate_tenants(delivered):
    client = TestClient(main.app)
    assert request_code(client, "+12025550111", "sms").status_code == 422
    sms = request_code(client, "138 0013 8000", "sms")
    assert sms.status_code == 200
    assert delivered[-1][1] == "+8613800138000"
    phone_user = verify(client, sms.json()["challenge_id"], delivered[-1][2]).json()
    email = request_code(client)
    email_user = verify(client, email.json()["challenge_id"], delivered[-1][2]).json()
    assert phone_user["workspace_id"] != email_user["workspace_id"]


@pytest.mark.parametrize("value", ["wrong", "a@@example.test", "a..b@example.test", "a@-bad.test", "a\r\nBcc:other@example.test"])
def test_invalid_email_never_calls_provider(value, delivered):
    assert request_code(TestClient(main.app), value).status_code == 422
    assert not delivered


def test_invalid_code_six_ascii_digits_only(delivered):
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    for code in ("12345", "1234567", "１２３４５６", "abcdef"):
        assert verify(client, challenge, code).status_code == 422


def test_cooldown_retry_header_and_resend_invalidates_old_code(delivered):
    client = TestClient(main.app)
    first = request_code(client).json()
    old = delivered[-1][2]
    cooldown = request_code(client)
    assert cooldown.status_code == 429
    assert 1 <= int(cooldown.headers["Retry-After"]) <= 61
    assert len(delivered) == 1
    expire_cooldown()
    second = request_code(client).json()
    assert verify(client, first["challenge_id"], old).status_code == 410
    assert verify(client, second["challenge_id"], delivered[-1][2]).status_code == 200


def test_expiry_and_attempt_budget(delivered):
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    code = delivered[-1][2]
    incorrect = "000000" if code != "000000" else "111111"
    assert [verify(client, challenge, incorrect).status_code for _ in range(5)] == [401, 401, 401, 401, 429]
    assert verify(client, challenge, code).status_code == 429
    assert accounts.count() == 0
    expire_cooldown()
    challenge = request_code(client).json()["challenge_id"]
    with db.engine().begin() as connection:
        connection.execute(sa.update(auth_challenges).values(expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()))
    assert verify(client, challenge, delivered[-1][2]).status_code == 410


def test_parallel_code_consume_has_one_winner(delivered):
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    digest = service.digest("code", challenge + ":" + delivered[-1][2])
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: challenges.verify(challenge, digest, datetime.now(UTC))[0], range(6)))
    assert results.count("verified") == 1
    assert results.count("expired") == 5


def test_delivery_failure_never_creates_usable_challenge(monkeypatch, delivered):
    def fail(*_args):
        raise auth_delivery.DeliveryError("private provider details")
    monkeypatch.setattr(auth_delivery, "send", fail)
    response = request_code(TestClient(main.app))
    assert response.status_code == 503
    assert "private" not in response.text
    with db.engine().connect() as connection:
        row = connection.execute(sa.select(auth_challenges)).mappings().one()
        assert row["consumed_at"] and row["delivered"] == 0


def test_existing_email_looking_owner_cannot_be_taken_over(delivered):
    local = accounts.create("existing-private", "person@example.test", password_hash("OwnerPass2026"), "OWNER")
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    result = verify(client, challenge, delivered[-1][2])
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "ACCOUNT_LINK_REQUIRED"
    assert client.get("/api/auth/status").json()["authenticated"] is False
    assert accounts.by_id(local["user_id"])["workspace_id"] == "existing-private"
    with db.engine().connect() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(identity_bindings)).scalar_one() == 0


def test_verified_login_preserves_mfa(monkeypatch, delivered):
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    first = verify(client, challenge, delivered[-1][2]).json()
    identities.save_mfa(first["user_id"], "JBSWY3DPEHPK3PXP", [])
    identities.confirm_mfa(first["user_id"], 0)
    client.post("/api/auth/logout")
    expire_cooldown()
    challenge = request_code(client).json()["challenge_id"]
    result = verify(client, challenge, delivered[-1][2])
    assert result.status_code == 200 and result.json()["mfa_required"] is True
    assert client.get("/api/auth/status").json()["authenticated"] is False


def test_closed_signup_and_disabled_accounts_cannot_create_session(monkeypatch, delivered):
    client = TestClient(main.app)
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", False)
    challenge = request_code(client).json()["challenge_id"]
    assert verify(client, challenge, delivered[-1][2]).status_code == 403
    assert accounts.count() == 0
    monkeypatch.setattr(config, "PERSONAL_SIGNUP", True)
    expire_cooldown()
    challenge = request_code(client).json()["challenge_id"]
    user = verify(client, challenge, delivered[-1][2]).json()
    client.post("/api/auth/logout")
    with db.engine().begin() as connection:
        connection.execute(sa.update(users).where(users.c.user_id == user["user_id"]).values(active=0))
    expire_cooldown()
    challenge = request_code(client).json()["challenge_id"]
    assert verify(client, challenge, delivered[-1][2]).status_code == 403


def test_identity_insert_failure_rolls_back_user_and_workspace(monkeypatch, delivered):
    def fail(*_args):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(identities, "bind_new", fail)
    client = TestClient(main.app, raise_server_exceptions=False)
    challenge = request_code(client).json()["challenge_id"]
    assert verify(client, challenge, delivered[-1][2]).status_code == 500
    assert accounts.count() == 0
    with db.engine().connect() as connection:
        assert connection.execute(sa.select(sa.func.count()).select_from(workspaces)).scalar_one() == 0


def test_send_quotas_persist_and_ignore_forged_forwarded_ip(delivered):
    client = TestClient(main.app)
    results = [client.post("/api/auth/challenges", headers={"X-Forwarded-For": f"192.0.2.{n}"},
                           json={"channel": "email", "identifier": f"person{n}@example.test"}).status_code for n in range(21)]
    assert results[:20] == [200] * 20
    assert results[-1] == 429
    assert request_code(TestClient(main.app), "new@example.test").status_code == 429


def test_status_hides_unconfigured_and_insecure_production_delivery(monkeypatch):
    client = TestClient(main.app)
    assert client.get("/api/auth/status").json()["passwordless"]["email"]
    monkeypatch.delenv("BIDPROOF_OTP_SECRET")
    assert not client.get("/api/auth/status").json()["passwordless"]["email"]
    monkeypatch.setenv("BIDPROOF_OTP_SECRET", "a" * 40)
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    assert not auth_delivery.enabled("email")


def configure_github(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_ORIGIN", "https://bid.example.test")
    monkeypatch.setenv("BIDPROOF_GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("BIDPROOF_GITHUB_CLIENT_SECRET", "server-secret")


def test_github_browser_binding_pkce_replay_and_mfa(monkeypatch):
    configure_github(monkeypatch)
    exchanges = []
    def exchange(url, form, **_kwargs):
        exchanges.append((url, form))
        return {"access_token": "private-access-token"}
    monkeypatch.setattr(oidc, "_post_form", exchange)
    monkeypatch.setattr(oidc, "_fetch_json", lambda request, **_kwargs: {"id": 1234, "login": "mutable-display"})
    client = TestClient(main.app, follow_redirects=False)
    start = client.get("/api/auth/oauth/github/start")
    assert start.status_code == 302
    query = parse_qs(urlsplit(start.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "server-secret" not in start.text + start.headers["location"]
    state = query["state"][0]
    thief = TestClient(main.app, follow_redirects=False)
    assert thief.get("/api/auth/oauth/github/callback", params={"state": state, "code": "code"}).headers["location"] == "/app?auth_error=expired"
    assert not exchanges
    callback = client.get("/api/auth/oauth/github/callback", params={"state": state, "code": "code"})
    assert callback.headers["location"] == "/app"
    assert exchanges[0][1]["code_verifier"]
    assert client.get("/api/auth/status").json()["authenticated"] is True
    assert client.get("/api/auth/oauth/github/callback", params={"state": state, "code": "code"}).headers["location"] == "/app?auth_error=expired"
    user = client.get("/api/auth/status").json()["user"]
    identities.save_mfa(user["user_id"], "JBSWY3DPEHPK3PXP", [])
    identities.confirm_mfa(user["user_id"], 0)
    client.post("/api/auth/logout")
    start = client.get("/api/auth/oauth/github/start")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    outcome = client.get("/api/auth/oauth/github/callback", params={"state": state, "code": "new-code"})
    assert outcome.headers["location"].startswith("/app?mfa_token=")
    assert not client.get("/api/auth/status").json()["authenticated"]


def test_oauth_cancellation_consumes_flow_and_no_open_redirect(monkeypatch):
    configure_github(monkeypatch)
    client = TestClient(main.app, follow_redirects=False)
    start = client.get("/api/auth/oauth/github/start?next=https://evil.test")
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    cancelled = client.get("/api/auth/oauth/github/callback", params={"state": state, "error": "access_denied"})
    assert cancelled.headers["location"] == "/app?auth_error=cancelled"
    with db.engine().connect() as connection:
        flow = connection.execute(sa.select(login_flows).where(login_flows.c.state == state)).mappings().one()
        assert flow["consumed_at"]
    assert client.get("/api/auth/oauth/unknown/start").headers["location"] == "/app?auth_error=unavailable"


def test_google_uses_signed_id_token_subject(monkeypatch):
    import time

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    monkeypatch.setattr(config, "PUBLIC_ORIGIN", "https://bid.example.test")
    monkeypatch.setenv("BIDPROOF_GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("BIDPROOF_GOOGLE_CLIENT_SECRET", "google-secret")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    document = {"issuer": "https://accounts.google.com",
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token", "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs"}
    monkeypatch.setattr(oidc, "fetch_discovery", lambda _settings: document)
    monkeypatch.setattr(oidc, "_read_json", lambda *_args, **_kwargs: {
        "keys": [{**jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "google-test", "alg": "RS256"}]})
    client = TestClient(main.app, follow_redirects=False)
    start = client.get("/api/auth/oauth/google/start")
    query = parse_qs(urlsplit(start.headers["location"]).query)
    claims = {"iss": document["issuer"], "aud": "google-client", "sub": "immutable-subject",
              "iat": int(time.time()), "exp": int(time.time()) + 300, "nonce": query["nonce"][0],
              "email": "a@example.test", "email_verified": True}
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "google-test"})
    monkeypatch.setattr(oidc, "redeem_code", lambda *_args, **_kwargs: {"id_token": token})
    callback = client.get("/api/auth/oauth/google/callback", params={"state": query["state"][0], "code": "code"})
    assert callback.headers["location"] == "/app"
    binding = identities.load_binding("SOCIAL_GOOGLE", document["issuer"], "immutable-subject")
    assert binding and client.get("/api/auth/status").json()["user"]["user_id"] == binding["user_id"]
    assert identities.load_binding("EMAIL", "bidproof", "a@example.test") is None
    client.post("/api/auth/logout")
    # A valid signature with the wrong audience cannot create a session.
    start = client.get("/api/auth/oauth/google/start")
    query = parse_qs(urlsplit(start.headers["location"]).query)
    bad = jwt.encode({**claims, "aud": "another-client", "nonce": query["nonce"][0]}, key, algorithm="RS256", headers={"kid": "google-test"})
    monkeypatch.setattr(oidc, "redeem_code", lambda *_args, **_kwargs: {"id_token": bad})
    callback = client.get("/api/auth/oauth/google/callback", params={"state": query["state"][0], "code": "code"})
    assert callback.headers["location"] == "/app?auth_error=provider"
    assert not client.get("/api/auth/status").json()["authenticated"]


def test_smtp_adapter_sends_plain_text_through_tls_and_reports_refusal(monkeypatch):
    observed = []
    class SMTP:
        def __init__(self, host, port, **options):
            observed.append((host, port, options))
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def starttls(self, **options):
            observed.append(("tls", options))
        def login(self, username, password):
            observed.append(("auth", username, password))
        def send_message(self, message):
            observed.append(message)
            return {}
    monkeypatch.setenv("BIDPROOF_SMTP_SECURITY", "starttls")
    monkeypatch.setenv("BIDPROOF_SMTP_USERNAME", "mail-user")
    monkeypatch.setenv("BIDPROOF_SMTP_PASSWORD", "mail-secret")
    monkeypatch.setattr(auth_delivery.smtplib, "SMTP", SMTP)
    auth_delivery.send("email", "recipient@example.test", "123456")
    assert observed[1][0] == "tls"
    assert observed[2] == ("auth", "mail-user", "mail-secret")
    assert observed[-1]["To"] == "recipient@example.test"
    assert "123456" in observed[-1].get_content()
    assert observed[-1].get_content_type() == "text/plain"


def test_twilio_adapter_posts_exact_recipient_and_never_accepts_failed_delivery(monkeypatch):
    observed = []
    def accepted(request, **options):
        observed.append(request)
        return {"sid": "SMtest", "status": "queued"}
    monkeypatch.setattr(oidc, "_fetch_json", accepted)
    auth_delivery.send("sms", "+8613800138000", "123456")
    request = observed[0]
    assert request.full_url == "https://api.twilio.com/2010-04-01/Accounts/AC" + "a" * 32 + "/Messages.json"
    form = parse_qs(request.data.decode())
    assert form["To"] == ["+8613800138000"]
    assert "123456" in form["Body"][0]
    monkeypatch.setattr(oidc, "_fetch_json", lambda *_args, **_kwargs: {"sid": "SMtest", "status": "failed"})
    with pytest.raises(auth_delivery.DeliveryError):
        auth_delivery.send("sms", "+8613800138000", "123456")


def test_concurrent_rate_limit_never_overissues_and_window_resets():
    from app.models import auth_rate_limits

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda _: challenges.consume_limit("test", "shared-ip", 3, 60), range(12)))
    assert outcomes.count(0) == 3
    with db.engine().begin() as connection:
        connection.execute(sa.update(auth_rate_limits).values(
            window_started_at=(datetime.now(UTC) - timedelta(seconds=61)).isoformat()))
    assert challenges.consume_limit("test", "shared-ip", 3, 60) == 0


def test_resend_https_adapter_is_config_gated_and_keeps_content_server_side(monkeypatch):
    import json

    monkeypatch.setenv("BIDPROOF_EMAIL_PROVIDER", "resend")
    monkeypatch.delenv("BIDPROOF_RESEND_API_KEY", raising=False)
    assert not auth_delivery.enabled("email")
    monkeypatch.setenv("BIDPROOF_RESEND_API_KEY", "re_private")
    monkeypatch.setenv("BIDPROOF_EMAIL_FROM", "BidProof <login@example.test>")
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    assert auth_delivery.enabled("email")
    sent = []
    def accept(request, **_options):
        sent.append(request)
        return {"id": "accepted-email-id"}
    monkeypatch.setattr(oidc, "_fetch_json", accept)
    auth_delivery.send("email", "person@example.test", "123456")
    assert sent[0].full_url == "https://api.resend.com/emails"
    assert sent[0].get_header("Authorization") == "Bearer re_private"
    payload = json.loads(sent[0].data)
    assert payload["to"] == ["person@example.test"] and "123456" in payload["text"]
    assert "html" not in payload
    monkeypatch.setattr(oidc, "_fetch_json", lambda *_args, **_kwargs: {"message": "refused"})
    with pytest.raises(auth_delivery.DeliveryError):
        auth_delivery.send("email", "person@example.test", "123456")


def test_secret_rotation_invalidates_pending_codes_but_keeps_identity(monkeypatch, delivered):
    client = TestClient(main.app)
    challenge = request_code(client).json()["challenge_id"]
    user = verify(client, challenge, delivered[-1][2]).json()
    client.post("/api/auth/logout")
    expire_cooldown()
    old = request_code(client).json()["challenge_id"]
    old_code = delivered[-1][2]
    monkeypatch.setenv("BIDPROOF_OTP_SECRET", "a-new-server-secret-" * 3)
    assert verify(client, old, old_code).status_code == 401
    new = request_code(client).json()["challenge_id"]
    returning = verify(client, new, delivered[-1][2])
    assert returning.status_code == 200 and returning.json()["user_id"] == user["user_id"]
    assert accounts.count() == 1


def test_parallel_first_signups_cannot_leave_orphan_workspaces(monkeypatch):
    import threading

    real_create = accounts.create
    barrier = threading.Barrier(4)
    def concurrent_create(*args, **kwargs):
        barrier.wait(timeout=10)
        return real_create(*args, **kwargs)
    monkeypatch.setattr(accounts, "create", concurrent_create)
    with ThreadPoolExecutor(max_workers=4) as executor:
        outcomes = list(executor.map(lambda _: service.verified_user(
            "EMAIL", "bidproof", "same@example.test", "same@example.test"), range(4)))
    assert len({user["user_id"] for user in outcomes}) == 1
    with db.engine().connect() as connection:
        for table in (users, workspaces, identity_bindings):
            assert connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 1
    user = outcomes[0]
    assert len(db.list_workspace_members(user["workspace_id"])) == 1
