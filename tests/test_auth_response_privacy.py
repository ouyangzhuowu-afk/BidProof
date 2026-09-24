from fastapi.testclient import TestClient

from app import main


def test_authentication_documents_and_errors_are_not_cacheable():
    client = TestClient(main.app)
    for response in (client.get('/app'), client.get('/api/auth/status'),
                     client.get('/api/v1/auth/status'),
                     client.post('/api/auth/challenges', json={'channel': 'email', 'identifier': 'invalid'}),
                     client.get('/api/auth/oauth/unknown/start', follow_redirects=False)):
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['referrer-policy'] == 'no-referrer'
