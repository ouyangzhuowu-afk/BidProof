"""Independent ASGI ingress tests: limits apply before application side effects."""
from __future__ import annotations

import asyncio
import json
import tempfile
from typing import Annotated

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from app import request_limits
from app.request_limits import RequestBudgetMiddleware


def exchange(messages, *, headers=(), budget=10, method='POST', inner=None):
    sent, received, invoked = [], [], []
    source = iter(messages)
    async def receive():
        return next(source, {'type': 'http.disconnect'})
    async def send(message):
        sent.append(message)
    async def app(scope, replay, send):
        invoked.append(True)
        while True:
            event = await replay()
            received.append(event)
            if event['type'] == 'http.disconnect' or not event.get('more_body', False):
                break
        if inner:
            await inner(scope, replay, send)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})
    scope = {'type': 'http', 'method': method, 'path': '/upload', 'headers': list(headers)}
    asyncio.run(RequestBudgetMiddleware(app, budget)(scope, receive, send))
    return invoked, received, sent


def event(body, more=False):
    return {'type': 'http.request', 'body': body, 'more_body': more}


@pytest.mark.parametrize('headers,messages', [
    ([(b'content-length', b'11')], [event(b'small')]),
    ([], [event(b'123456', True), event(b'78901')]),
    ([(b'content-length', b'1')], [event(b'123456', True), event(b'78901')]),
    ([(b'transfer-encoding', b'chunked')], [event(b'12345678901')]),
])
def test_over_budget_never_invokes_app_or_accepts_side_effects(headers, messages):
    invoked, _, sent = exchange(messages, headers=headers)
    assert not invoked
    assert sent[0]['status'] == 413
    payload = json.loads(sent[1]['body'])
    assert payload['request_id']
    assert dict(sent[0]['headers'])[b'x-content-type-options'] == b'nosniff'


def test_invalid_content_length_is_rejected_without_reading_body():
    invoked, _, sent = exchange([], headers=[(b'content-length', b'garbage')])
    assert not invoked
    assert sent[0]['status'] == 400


def test_exact_budget_and_empty_body_replay_once_then_disconnect():
    async def after_body(scope, replay, send):
        assert await replay() == {'type': 'http.disconnect'}
    for messages, expected in (([event(b'12345', True), event(b'67890')], b'1234567890'), ([event(b'')], b'')):
        invoked, received, sent = exchange(messages, inner=after_body)
        assert invoked == [True]
        assert b''.join(item.get('body', b'') for item in received) == expected
        assert sent[0]['status'] == 200


def test_disconnected_upload_does_not_invoke_app_and_closes_spool(monkeypatch):
    spools = []
    factory = tempfile.SpooledTemporaryFile
    def track(*args, **kwargs):
        spool = factory(*args, **kwargs)
        spools.append(spool)
        return spool
    monkeypatch.setattr(request_limits.tempfile, 'SpooledTemporaryFile', track)
    invoked, _, sent = exchange([event(b'partial', True), {'type': 'http.disconnect'}])
    assert not invoked and not sent
    assert len(spools) == 1 and spools[0].closed


def test_large_allowed_body_spills_to_disk_and_is_exactly_replayed(monkeypatch):
    spools = []
    factory = tempfile.SpooledTemporaryFile
    def track(*args, **kwargs):
        spool = factory(*args, **kwargs)
        spools.append(spool)
        return spool
    monkeypatch.setattr(request_limits.tempfile, 'SpooledTemporaryFile', track)
    payload = b'a' * (1024 * 1024 + 21)
    invoked, received, sent = exchange([event(payload)], budget=len(payload))
    assert invoked == [True]
    assert b''.join(item['body'] for item in received) == payload
    assert spools[0]._rolled and spools[0].closed
    assert sent[0]['status'] == 200


def test_normal_json_and_multipart_are_not_broken_by_prebuffering():
    app = FastAPI()
    app.add_middleware(RequestBudgetMiddleware, max_bytes=2048)
    @app.post('/json')
    def json_body(body: dict):
        return body
    @app.post('/file')
    async def upload(tender: Annotated[UploadFile, File(...)]):
        return {'filename': tender.filename, 'body': (await tender.read()).decode()}
    client = TestClient(app)
    assert client.post('/json', json={'text': '中文'}).json() == {'text': '中文'}
    result = client.post('/file', files={'tender': ('source.txt', '原文证据', 'text/plain')})
    assert result.status_code == 200
    assert result.json() == {'filename': 'source.txt', 'body': '原文证据'}
    assert client.post('/file', files={'tender': ('source.txt', b'x' * 2049, 'text/plain')}).status_code == 413


def test_delete_body_is_also_bounded():
    invoked, _, sent = exchange([event(b"12345678901")], method="DELETE")
    assert not invoked and sent[0]["status"] == 413


def test_total_upload_deadline_prevents_application_call(monkeypatch):
    monkeypatch.setattr(request_limits, "REQUEST_TIMEOUT_SECONDS", 0)
    invoked, _, sent = exchange([event(b"small")])
    assert not invoked and sent[0]["status"] == 408


def test_full_temporary_disk_returns_sanitized_retryable_error(monkeypatch):
    class FullSpool:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def write(self, _chunk):
            raise OSError("private host path: device full")
    monkeypatch.setattr(request_limits.tempfile, "SpooledTemporaryFile", lambda **_kwargs: FullSpool())
    invoked, _, sent = exchange([event(b"small")])
    assert not invoked and sent[0]["status"] == 503
    assert b"private host path" not in sent[1]["body"]
