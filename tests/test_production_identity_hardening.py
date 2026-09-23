"""Security regressions using isolated databases and real JWT signature verification."""
from __future__ import annotations

import json
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app import config, db, directory, http, identity, main, oidc, request_context
from app.repositories import accounts
from app.repositories import identity as identity_store
from app.schemas import ApiTokenCreateRequest
from app.security import UNUSABLE_PASSWORD, password_hash, token_hash
from app.services import auth_service


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv('BIDPROOF_DATABASE_URL', f'sqlite+pysqlite:///{tmp_path / "identity.sqlite3"}')
    monkeypatch.setenv('DATABASE_URL', '')
    db.init_db()


def account(role='ADMIN', workspace='private'):
    user = accounts.create(workspace, uuid.uuid4().hex, password_hash('SecurityTest2026'), role)
    return user, {'workspace_id': workspace, 'user_id': user['user_id'], 'role': role}


def issue(principal, permissions):
    return auth_service.create_token(principal, ApiTokenCreateRequest(name='integration', permissions=permissions))


def test_token_rejects_unknown_empty_and_overprivileged_scopes():
    _, principal = account()
    for permissions in ([], ['unknown:permission'], ['run:read', 'unknown:permission']):
        with pytest.raises(HTTPException) as error:
            issue(principal, permissions)
        assert error.value.status_code == 422
    assert identity_store.list_tokens(principal['workspace_id']) == []


def test_live_demotion_revokes_privileged_token_access_but_keeps_allowed_reads():
    user, principal = account()
    token = issue(principal, ['project:manage', 'run:read'])['token']
    client = TestClient(main.app)
    headers = {'Authorization': f'Bearer {token}'}
    assert client.post('/api/projects', headers=headers, json={'name': 'Before demotion'}).status_code == 201
    db.update_workspace_member(principal['workspace_id'], user['user_id'], role='VIEWER')
    assert client.post('/api/projects', headers=headers, json={'name': 'After demotion'}).status_code == 403
    assert client.get('/api/runs', headers=headers).status_code == 200
    db.update_workspace_member(principal['workspace_id'], user['user_id'], active=False)
    assert client.get('/api/runs', headers=headers).status_code == 401


def test_token_cannot_mint_a_broader_token():
    _, principal = account()
    token = issue(principal, ['token:manage', 'run:read'])['token']
    client = TestClient(main.app)
    denied = client.post('/api/auth/tokens', headers={'Authorization': f'Bearer {token}'},
                         json={'name': 'escalation', 'permissions': ['project:manage']})
    assert denied.status_code == 422
    allowed = client.post('/api/auth/tokens', headers={'Authorization': f'Bearer {token}'},
                          json={'name': 'reader', 'permissions': ['run:read']})
    assert allowed.status_code == 201


def test_legacy_empty_scope_token_grants_nothing():
    user, principal = account()
    db.create_api_token(token_hash=token_hash('legacy-key'), token_prefix='legacy',
                        workspace_id=principal['workspace_id'], user_id=user['user_id'],
                        name='legacy', role='ADMIN', created_by=user['user_id'], permissions=[])
    assert TestClient(main.app).get('/api/runs', headers={'Authorization': 'Bearer legacy-key'}).status_code == 403


def test_promotion_does_not_expand_a_tokens_original_role_ceiling():
    user, principal = account('VIEWER')
    # Model a legacy overbroad stored scope: the original role remains a second ceiling.
    db.create_api_token(token_hash=token_hash('old-viewer-key'), token_prefix='legacy',
                        workspace_id=principal['workspace_id'], user_id=user['user_id'],
                        name='legacy', role='VIEWER', created_by=user['user_id'], permissions=['project:manage', 'run:read'])
    db.update_workspace_member(principal['workspace_id'], user['user_id'], role='ADMIN')
    client = TestClient(main.app)
    headers = {'Authorization': 'Bearer old-viewer-key'}
    assert client.get('/api/runs', headers=headers).status_code == 200
    assert client.post('/api/projects', headers=headers, json={'name': 'escalation'}).status_code == 403
    project = db.create_project(principal['workspace_id'], 'Restricted project', 'RESTRICTED')
    db.replace_project_members(project['project_id'], [{'user_id': 'other-user', 'role': 'REVIEWER'}])
    request = Request({'type': 'http', 'scheme': 'http', 'method': 'GET', 'path': '/',
                       'headers': [(b'authorization', b'Bearer old-viewer-key')],
                       'client': ('192.0.2.2', 5), 'server': ('localhost', 80), 'query_string': b''})
    assert not db.user_can_access_project(identity.principal_of(request), project['project_id'])


def test_forwarded_headers_cannot_reset_login_limit(monkeypatch):
    user, _ = account()
    monkeypatch.setattr(identity, 'LOGIN_ATTEMPT_LIMIT', 3)
    client = TestClient(main.app)
    statuses = [client.post('/api/auth/login', headers={'X-Forwarded-For': f'203.0.113.{index}',
                    'X-Real-IP': f'198.51.100.{index}'},
                    json={'username': user['username'], 'password': 'WrongPassword123'}).status_code
                for index in range(3)]
    assert statuses == [401, 401, 429]


def test_raw_forwarded_scheme_is_not_cookie_security_authority(monkeypatch):
    request = Request({'type': 'http', 'scheme': 'http', 'method': 'GET', 'path': '/',
                       'headers': [(b'x-forwarded-proto', b'https'), (b'x-forwarded-for', b'evil')],
                       'client': ('192.0.2.1', 5), 'server': ('localhost', 80), 'query_string': b''})
    monkeypatch.setattr(config, 'ENVIRONMENT', 'development')
    assert identity.request_is_secure(request) is False
    assert request_context.client_ip(request) == '192.0.2.1'
    monkeypatch.setattr(config, 'ENVIRONMENT', 'production')
    assert identity.request_is_secure(request) is True


def test_federated_subject_cannot_claim_local_owner_by_username(monkeypatch):
    user, _ = account('OWNER', 'other-tenant')
    monkeypatch.setattr(config, 'FEDERATED_WORKSPACE_ID', 'federated-tenant')
    with pytest.raises(HTTPException) as error:
        auth_service._provision_federated_user(user['username'], 'REVIEWER', provider='OIDC',
                                               issuer='https://idp.example', subject='new-subject')
    assert error.value.status_code == 409
    assert identity_store.load_binding('OIDC', 'https://idp.example', 'new-subject') is None
    assert accounts.by_id(user['user_id'])['role'] == 'OWNER'


def test_federated_jit_requires_explicit_workspace_and_low_privilege(monkeypatch):
    account('OWNER', 'sso-tenant')
    monkeypatch.setattr(config, 'FEDERATED_WORKSPACE_ID', '')
    with pytest.raises(HTTPException) as error:
        auth_service._provision_federated_user('sso-new', 'REVIEWER', provider='LDAP', issuer='ldaps://directory', subject='new-dn')
    assert error.value.status_code == 503
    monkeypatch.setattr(config, 'FEDERATED_WORKSPACE_ID', 'sso-tenant')
    with pytest.raises(HTTPException) as error:
        auth_service._provision_federated_user('sso-new', 'OWNER', provider='LDAP', issuer='ldaps://directory', subject='new-dn')
    assert error.value.status_code == 403
    created = auth_service._provision_federated_user('sso-new', 'REVIEWER', provider='LDAP', issuer='ldaps://directory', subject='new-dn')
    assert created['workspace_id'] == 'sso-tenant'
    assert created['password_hash'] == UNUSABLE_PASSWORD
    again = auth_service._provision_federated_user('renamed', 'VIEWER', provider='LDAP', issuer='ldaps://directory', subject='new-dn')
    assert again['user_id'] == created['user_id']
    assert again['role'] == 'REVIEWER'


@pytest.fixture
def signing_provider(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid='current-key', alg='RS256', use='sig')
    settings = oidc.OIDCSettings(issuer='https://idp.example', client_id='bidproof', client_secret='server-only')
    document = {'issuer': settings.issuer, 'authorization_endpoint': settings.issuer + '/authorize',
                'token_endpoint': settings.issuer + '/token', 'jwks_uri': settings.issuer + '/keys'}
    monkeypatch.setattr(oidc, '_read_json', lambda *args, **kwargs: {'keys': [jwk]})
    def sign(**overrides):
        now = int(time.time())
        claims = {'iss': settings.issuer, 'aud': settings.client_id, 'iat': now, 'exp': now + 60,
                  'sub': 'verified-subject', 'nonce': 'nonce', 'preferred_username': 'new-provider-user'}
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'current-key'})
    return settings, document, sign, key


def test_oidc_verifies_real_signature_and_required_claims(signing_provider):
    settings, document, sign, _ = signing_provider
    assert oidc.verify_id_token(sign(), settings, document, nonce='nonce')['sub'] == 'verified-subject'
    for overrides in ({'iss': 'https://different.example'}, {'aud': 'other'}, {'nonce': 'replayed'},
                      {'exp': int(time.time()) - 1000}, {'aud': ['bidproof', 'other']}, {'azp': 'other'}):
        with pytest.raises(oidc.OIDCError):
            oidc.verify_id_token(sign(**overrides), settings, document, nonce='nonce')


def test_oidc_rejects_wrong_signature_none_algorithm_and_unknown_key(signing_provider):
    settings, document, sign, _ = signing_provider
    claims = jwt.decode(sign(), options={'verify_signature': False})
    unrelated_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_tokens = [jwt.encode(claims, unrelated_key, algorithm='RS256', headers={'kid': 'current-key'}),
                  jwt.encode(claims, '', algorithm='none', headers={'kid': 'current-key'}),
                  jwt.encode(claims, unrelated_key, algorithm='RS256', headers={'kid': 'missing-key'})]
    for token in bad_tokens:
        with pytest.raises(oidc.OIDCError):
            oidc.verify_id_token(token, settings, document, nonce='nonce')


def test_oidc_callback_is_bound_to_starting_browser(signing_provider, monkeypatch):
    settings, document, sign, _ = signing_provider
    account('OWNER', 'oidc-tenant')
    monkeypatch.setattr(config, 'PUBLIC_ORIGIN', 'https://app.example')
    monkeypatch.setattr(config, 'FEDERATED_WORKSPACE_ID', 'oidc-tenant')
    monkeypatch.setattr(oidc, 'settings_from_env', lambda: settings)
    monkeypatch.setattr(oidc, 'fetch_discovery', lambda settings: document)
    client = TestClient(main.app, base_url='https://app.example')
    started = client.get('/api/auth/oidc/start', follow_redirects=False)
    assert started.status_code == 302
    params = parse_qs(urlsplit(started.headers['location']).query)
    state, nonce = params['state'][0], params['nonce'][0]
    assert client.cookies.get('bidproof_oidc_flow') == state
    assert params['redirect_uri'] == ['https://app.example/api/auth/oidc/callback']
    monkeypatch.setattr(oidc, 'redeem_code', lambda *args, **kwargs: {'id_token': sign(nonce=nonce)})
    callback = f'/api/auth/oidc/callback?code=provider-code&state={state}'
    assert TestClient(main.app, base_url='https://app.example').get(callback).status_code == 401
    completed = client.get(callback, follow_redirects=False)
    assert completed.status_code == 303
    assert client.cookies.get(identity.SESSION_COOKIE)
    assert client.cookies.get('bidproof_oidc_flow') is None
    assert client.get(callback, follow_redirects=False).status_code == 401


def test_oidc_and_ldap_reject_insecure_provider_configuration():
    with pytest.raises(oidc.OIDCError):
        oidc.validate_settings(oidc.OIDCSettings(issuer='http://idp.example', client_id='x', client_secret='secret'))
    with pytest.raises(oidc.OIDCError):
        oidc.token_request(oidc.OIDCSettings('https://idp.example', 'x', 'secret'),
                           {'token_endpoint': 'http://idp.example/token'}, code='x', redirect_uri='https://app.example/cb', verifier='y')
    with pytest.raises(directory.DirectoryError):
        directory.authenticate(directory.DirectorySettings('ldap://directory', 'uid={username}', use_tls=False),
                               'alice', 'secret', connector=lambda *args: {'dn': 'alice'})


@pytest.mark.parametrize('path', ['/api/projects', '/api/v1/projects'])
def test_unsupported_idempotency_never_executes_or_replays_writes(path):
    user, principal = account()
    client = TestClient(main.app)
    headers = {'X-Workspace-ID': principal['workspace_id'], 'X-User-ID': user['user_id'],
               'X-User-Role': 'ADMIN', 'Idempotency-Key': 'same-key'}
    for _ in range(2):
        result = client.post(path, headers=headers, json={'name': 'must-not-exist'})
        assert result.status_code == 501
        assert result.headers.get('X-Request-ID')
    with db.engine().connect() as connection:
        assert connection.execute(db.projects.select().where(db.projects.c.name == 'must-not-exist')).first() is None


def test_idempotency_header_cannot_bypass_auth_or_csrf(monkeypatch):
    user, _ = account()
    monkeypatch.setattr(config, 'ALLOW_TRUSTED_HEADERS', False)
    client = TestClient(main.app)
    headers = {'Idempotency-Key': 'guess', 'X-Workspace-ID': 'other-workspace'}
    assert client.post('/api/projects', headers=headers, json={'name': 'x'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': user['username'], 'password': 'SecurityTest2026'}).status_code == 200
    monkeypatch.setenv('BIDPROOF_ENFORCE_CSRF', '1')
    assert client.post('/api/projects', headers=headers, json={'name': 'x'}).status_code == 403


def test_unhandled_error_retains_correlation_and_security_headers():
    app = FastAPI()
    http.install_middleware(app)
    @app.get('/fail')
    def fail():
        raise RuntimeError('private internal failure')
    response = TestClient(app).get('/fail', headers={'X-Request-ID': 'trace-123'})
    assert response.status_code == 500
    assert response.json()['request_id'] == response.headers['X-Request-ID'] == 'trace-123'
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['Content-Security-Policy']
    assert 'private internal failure' not in response.text


def test_production_config_requires_explicit_secure_origin_and_hosts(monkeypatch):
    monkeypatch.setattr(config, 'ENVIRONMENT', 'production')
    monkeypatch.setattr(config, 'JOB_RUNNER', 'worker')
    monkeypatch.setattr(config, '_TRUSTED_HEADERS_REQUESTED', False)
    monkeypatch.setattr(config, 'TRIAL_JOIN_CODE', '')
    monkeypatch.setattr(config, 'BOOTSTRAP_TOKEN', '')
    monkeypatch.setattr(config, 'PUBLIC_ORIGIN', 'http://app.example')
    monkeypatch.setattr(config, 'ALLOWED_HOSTS', ('app.example',))
    with pytest.raises(RuntimeError, match='HTTPS'):
        config.validate_runtime_security()
    monkeypatch.setattr(config, 'PUBLIC_ORIGIN', 'https://app.example')
    monkeypatch.setattr(config, 'ALLOWED_HOSTS', ('*',))
    with pytest.raises(RuntimeError, match='ALLOWED_HOSTS'):
        config.validate_runtime_security()
    monkeypatch.setattr(config, 'ALLOWED_HOSTS', ('app.example',))
    config.validate_runtime_security()


def test_production_host_allowlist_blocks_host_injection(monkeypatch):
    monkeypatch.setattr(config, 'ENVIRONMENT', 'production')
    monkeypatch.setattr(config, 'ALLOWED_HOSTS', ('app.example',))
    app = FastAPI()
    http.install_middleware(app)
    @app.get('/')
    def index():
        return {'ok': True}
    client = TestClient(app, base_url='https://app.example')
    assert client.get('/').status_code == 200
    assert client.get('/', headers={'Host': 'attacker.example'}).status_code == 400


def test_mfa_competing_snapshots_cannot_reuse_totp_or_recovery_code():
    user, _ = account()
    identity_store.save_mfa(user['user_id'], 'JBSWY3DPEHPK3PXP', ['first', 'second'])
    identity_store.confirm_mfa(user['user_id'], 1)
    first = identity_store.load_mfa(user['user_id'])
    # Two requests have both read and verified the same code against counter 1.
    assert identity_store.consume_mfa(user['user_id'], first, counter=2, recovery_codes=['first', 'second'])
    assert not identity_store.consume_mfa(user['user_id'], first, counter=2, recovery_codes=['first', 'second'])
    recovery = identity_store.load_mfa(user['user_id'])
    assert identity_store.consume_mfa(user['user_id'], recovery, counter=2, recovery_codes=['second'])
    assert not identity_store.consume_mfa(user['user_id'], recovery, counter=2, recovery_codes=['second'])
    assert identity_store.load_mfa(user['user_id'])['recovery_codes_json'] == ['second']


def test_login_flow_consumption_is_one_shot():
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    identity_store.start_flow('one-shot', 'MFA', expires_at=(now + timedelta(minutes=5)).isoformat())
    assert identity_store.consume_flow('one-shot', 'MFA', now.isoformat()) is not None
    assert identity_store.consume_flow('one-shot', 'MFA', now.isoformat()) is None
