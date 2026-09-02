"""Optional OCR adapters with fail-closed behavior.

The default adapter is disabled. Credentials are read only from the process
environment and are never included in result payloads or exception messages.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol


class OCRUnavailable(RuntimeError):
    """Raised when an OCR provider cannot return a trustworthy result."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None = None
    provider: str = "unknown"


class OCRAdapter(Protocol):
    enabled: bool

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult: ...


class DisabledOCRAdapter:
    enabled = False

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        raise OCRUnavailable("OCR is disabled")


class QwenVLOCRAdapter:
    enabled = True

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        model: str = "qwen-vl-ocr",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Qwen OCR API key is required")
        self._api_key = api_key
        self._endpoint = endpoint
        self._model = model
        self._timeout_seconds = max(1.0, min(timeout_seconds, 120.0))

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        image_data = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "请只提取图片中的原文，保留中文、数字、标点和换行。"
                                "不要总结、不要补写图片中没有的内容。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OCRUnavailable(f"Qwen OCR request failed on page {page_number}") from exc
        try:
            result = json.loads(body.decode("utf-8"))
            text = _response_text(result)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise OCRUnavailable(f"Qwen OCR returned an invalid response on page {page_number}") from exc
        if not text.strip():
            raise OCRUnavailable(f"Qwen OCR returned no text on page {page_number}")
        return OCRResult(text=text.strip(), provider="qwen-vl-ocr")


def get_ocr_adapter() -> OCRAdapter:
    provider = os.getenv("BID_OCR_PROVIDER", "disabled").strip().lower()
    if provider in {"qwen", "qwen-vl-ocr", "qwen_vl_ocr"}:
        api_key = os.getenv("QWEN_OCR_API_KEY", "")
        if not api_key:
            return DisabledOCRAdapter()
        try:
            timeout = float(os.getenv("QWEN_OCR_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout = 30.0
        return QwenVLOCRAdapter(
            api_key=api_key,
            endpoint=os.getenv(
                "QWEN_OCR_ENDPOINT",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
            model=os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr"),
            timeout_seconds=timeout,
        )
    return DisabledOCRAdapter()


def _response_text(payload: dict[str, Any]) -> str:
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    raise TypeError("unsupported OCR response content")
