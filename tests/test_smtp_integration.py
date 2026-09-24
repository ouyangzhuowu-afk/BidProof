"""Opt-in loopback SMTP acceptance; exercises the real adapter without external mail."""
import os
import queue
import re
import socketserver
import threading
from email import policy
from email.parser import BytesParser

import pytest
from fastapi.testclient import TestClient

from app import config, db, main

pytestmark = pytest.mark.skipif(os.environ.get('BIDPROOF_TEST_SMTP') != '1', reason='loopback SMTP acceptance is opt-in')


def test_real_smtp_delivery_through_first_login_and_single_use(tmp_path, monkeypatch):
    mailbox = queue.Queue()

    class SMTP(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 local acceptance sink\r\n')
            while line := self.rfile.readline():
                verb = line.split(b' ', 1)[0].strip().upper()
                if verb in (b'EHLO', b'HELO'):
                    self.wfile.write(b'250 localhost\r\n')
                elif verb == b'RCPT':
                    assert b'@example.test>' in line.lower(), 'only synthetic recipient allowed'
                    self.wfile.write(b'250 OK\r\n')
                elif verb == b'DATA':
                    self.wfile.write(b'354 End with dot\r\n')
                    body = []
                    while (row := self.rfile.readline()) != b'.\r\n':
                        if not row:
                            return
                        body.append(row[1:] if row.startswith(b'..') else row)
                    mailbox.put(b''.join(body))
                    self.wfile.write(b'250 Accepted locally\r\n')
                elif verb == b'QUIT':
                    self.wfile.write(b'221 Bye\r\n')
                    return
                else:
                    self.wfile.write(b'250 OK\r\n')

    with socketserver.TCPServer(('127.0.0.1', 0), SMTP) as sink:
        worker = threading.Thread(target=sink.serve_forever, daemon=True)
        worker.start()
        try:
            monkeypatch.setenv('BIDPROOF_DATABASE_URL', f'sqlite+pysqlite:///{tmp_path / "smtp.sqlite3"}')
            monkeypatch.setenv('DATABASE_URL', '')
            monkeypatch.setenv('BIDPROOF_OTP_SECRET', 'only-for-local-acceptance-' * 3)
            monkeypatch.setenv('BIDPROOF_SMTP_HOST', '127.0.0.1')
            monkeypatch.setenv('BIDPROOF_SMTP_PORT', str(sink.server_address[1]))
            monkeypatch.setenv('BIDPROOF_SMTP_FROM', 'login@example.test')
            monkeypatch.setenv('BIDPROOF_SMTP_SECURITY', 'plain')
            monkeypatch.setenv('BIDPROOF_SMTP_USERNAME', '')
            monkeypatch.setattr(config, 'PERSONAL_SIGNUP', True)
            db.init_db()
            client = TestClient(main.app)
            assert client.get('/api/auth/status').json()['passwordless']['email']
            sent = client.post('/api/auth/challenges', json={'channel': 'email', 'identifier': 'smtpcheck@example.test'})
            assert sent.status_code == 200, sent.text
            message = BytesParser(policy=policy.default).parsebytes(mailbox.get(timeout=2))
            assert message['To'] == 'smtpcheck@example.test'
            code = re.search(r'验证码是：(\d{6})', message.get_body(preferencelist=('plain',)).get_content())[1]
            assert code not in sent.text
            proof = {'challenge_id': sent.json()['challenge_id'], 'code': code}
            verified = client.post('/api/auth/challenges/verify', json=proof)
            assert verified.status_code == 200, verified.text
            assert client.get('/api/auth/status').json()['authenticated']
            assert client.get('/api/runs').json() == []
            assert client.post('/api/auth/challenges/verify', json=proof).status_code == 410
            assert mailbox.empty()
        finally:
            sink.shutdown()
            worker.join(timeout=2)
