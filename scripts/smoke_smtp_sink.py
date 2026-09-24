"""Loopback SMTP sink for the local auth smoke test.

Accepts the one message the app sends, writes "<recipient> <code>" to
$BIDPROOF_SMOKE_OTP_PATH (default: %TEMP%/bidproof-smoke/otp.txt) and forwards nothing.
Only ever bound to 127.0.0.1 by scripts/start-smoke.ps1.
"""
from __future__ import annotations

import os
import re
import socketserver
import sys
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2525
OUT = Path(os.environ.get("BIDPROOF_SMOKE_OTP_PATH")
           or Path(tempfile.gettempdir()) / "bidproof-smoke" / "otp.txt")


class SMTP(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.wfile.write(b"220 bidproof smoke sink\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            verb = line.split(b" ", 1)[0].strip().upper()
            if verb in (b"EHLO", b"HELO"):
                self.wfile.write(b"250 localhost\r\n")
            elif verb == b"DATA":
                self.wfile.write(b"354 End with dot\r\n")
                body: list[bytes] = []
                while True:
                    row = self.rfile.readline()
                    if row in (b".\r\n", b""):
                        break
                    body.append(row[1:] if row.startswith(b"..") else row)
                message = BytesParser(policy=policy.default).parsebytes(b"".join(body))
                part = message.get_body(preferencelist=("plain",))
                match = re.search(r"验证码是：(\d{6})", (part.get_content() if part else "") or "")
                if match:
                    OUT.parent.mkdir(parents=True, exist_ok=True)
                    OUT.write_text(f"{message['To']} {match[1]}", encoding="utf-8")
                    print(f"sink captured code for {message['To']}", flush=True)
                self.wfile.write(b"250 Accepted\r\n")
            elif verb == b"QUIT":
                self.wfile.write(b"221 Bye\r\n")
                return
            else:
                self.wfile.write(b"250 OK\r\n")


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), SMTP) as sink:
        print(f"sink listening on 127.0.0.1:{PORT} -> {OUT}", flush=True)
        sink.serve_forever()

