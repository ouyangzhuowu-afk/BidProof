"""Bound request bodies before multipart parsing, including requests without Content-Length."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import uuid

from starlette.responses import JSONResponse

REQUEST_TIMEOUT_SECONDS = int(os.environ.get("BIDPROOF_REQUEST_TIMEOUT_SECONDS", "120"))
MAX_REQUEST_BYTES = int(os.environ.get("BIDPROOF_MAX_REQUEST_BYTES", str(110 * 1024 * 1024)))


class RequestBudgetMiddleware:
    def __init__(self, app, max_bytes: int = MAX_REQUEST_BYTES):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await self._reject(scope, receive, send, 400, "请求长度无效")
        if declared < 0 or declared > self.max_bytes:
            return await self._reject(scope, receive, send, 413, "请求文件总量超过限制，请分批上传")
        # Spill to a temporary file; do not join a 100MB multipart body in memory.
        with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as body:
            size = 0
            deadline = time.monotonic() + REQUEST_TIMEOUT_SECONDS
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0, deadline - time.monotonic()))
                except TimeoutError:
                    return await self._reject(scope, receive, send, 408, "上传超时，请检查网络后重试")
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_bytes:
                    return await self._reject(scope, receive, send, 413, "请求文件总量超过限制，请分批上传")
                try:
                    body.write(chunk)
                except OSError:
                    return await self._reject(scope, receive, send, 503, "上传暂存空间不足，请稍后重试")
                if not message.get("more_body", False):
                    break
            body.seek(0)
            replayed = 0

            async def replay():
                nonlocal replayed
                if replayed >= size and replayed > 0:
                    return await receive()
                chunk = body.read(65536)
                replayed += len(chunk)
                # Empty requests must also produce exactly one request event.
                more = replayed < size
                if not size:
                    replayed = 1
                return {"type": "http.request", "body": chunk, "more_body": more}

            await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope, receive, send, status, detail):
        from .http import SECURITY_HEADERS

        rid = uuid.uuid4().hex
        response = JSONResponse({"detail": detail, "request_id": rid}, status_code=status,
                                headers={**SECURITY_HEADERS, "X-Request-ID": rid})
        await response(scope, receive, send)
