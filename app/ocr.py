"""Optional OCR adapters with fail-closed behavior.

The default adapter is disabled. Credentials are read only from the process
environment and are never included in result payloads or exception messages.

Providers (BID_OCR_PROVIDER):
  disabled  — no network / no local model (default)
  qwen      — DashScope Qwen-VL-OCR (egress)
  paddle    — local PaddleOCR if installed (optional extra)
  hybrid    — primary then fallback (BID_OCR_PRIMARY / BID_OCR_FALLBACK)

For hospital / medical-device tenders, prefer paddle or hybrid with local
primary unless the customer has written approval for cloud egress.
"""

from __future__ import annotations

import base64
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .ocr_privacy import OCRLine, parse_lines_from_rapid_rows


logger = logging.getLogger("bidproof.ocr")


class OCRUnavailable(RuntimeError):
    """Raised when an OCR provider cannot return a trustworthy result."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None = None
    provider: str = "unknown"
    lines: tuple[OCRLine, ...] = ()


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
        max_attempts: int = 3,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Qwen OCR API key is required")
        self._api_key = api_key
        self._endpoint = endpoint
        self._model = model
        self._timeout_seconds = max(1.0, min(timeout_seconds, 120.0))
        self._max_attempts = max(1, min(max_attempts, 5))

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
                                "不要总结、不要补写、不要输出 HTML 或 Markdown 代码块。"
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
        body: bytes | None = None
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                    body = response.read()
                break
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
                retryable = True
                if isinstance(exc, urllib.error.HTTPError) and exc.code in {400, 401, 403}:
                    retryable = False
                if not retryable or attempt >= self._max_attempts:
                    raise OCRUnavailable(f"Qwen OCR request failed on page {page_number}") from exc
                delay = min(8.0, 0.5 * (2 ** (attempt - 1)))
                logger.warning(
                    "qwen_ocr_retry",
                    extra={"page": page_number, "attempt": attempt, "delay": delay},
                )
                time.sleep(delay)
        if body is None:
            raise OCRUnavailable(f"Qwen OCR request failed on page {page_number}") from last_error
        try:
            result = json.loads(body.decode("utf-8"))
            text = _response_text(result)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise OCRUnavailable(f"Qwen OCR returned an invalid response on page {page_number}") from exc
        cleaned = sanitize_ocr_text(text)
        if not cleaned:
            raise OCRUnavailable(f"Qwen OCR returned no text on page {page_number}")
        confidence = 0.35 if _looks_truncated_or_markup(text, cleaned) else None
        return OCRResult(text=cleaned, confidence=confidence, provider="qwen-vl-ocr", lines=())


def _image_bytes_to_rgb_array(image_bytes: bytes):
    """Decode PNG/JPEG bytes to an HxWx3 uint8 array without requiring OpenCV."""
    import numpy as np

    try:
        import fitz

        pixmap = fitz.Pixmap(image_bytes)
        if pixmap.alpha:
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        if pixmap.n == 1:
            array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.h, pixmap.w)
            return np.stack([array, array, array], axis=-1)
        array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.h, pixmap.w, pixmap.n)
        return array[:, :, :3]
    except Exception:
        try:
            from PIL import Image
            import io

            return np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        except ImportError as exc:
            raise OCRUnavailable("OCR adapters require PyMuPDF or pillow to decode page images") from exc


class PaddleOCRAdapter:
    """Local CN OCR. Optional dependency — not imported unless this provider is selected.

    License: Apache-2.0 (PaddleOCR). Install size is large (paddlepaddle + models).
    Alternative: keep cloud Qwen, or Tesseract (weaker on Chinese tenders).
    """

    enabled = True

    def __init__(self, lang: str = "ch") -> None:
        self._lang = lang
        self._engine = None

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:
            raise OCRUnavailable(
                "PaddleOCR is not installed; pip install with optional extra 'ocr' or set BID_OCR_PROVIDER=qwen"
            ) from exc
        # use_angle_cls helps rotated scan pages common in hospital fax/photocopies
        self._engine = PaddleOCR(use_angle_cls=True, lang=self._lang, show_log=False)
        return self._engine

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        try:
            import numpy as np
            from PIL import Image
            import io
        except ImportError as exc:
            raise OCRUnavailable("PaddleOCR adapter requires pillow and numpy") from exc
        try:
            engine = self._ensure_engine()
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            array = np.array(image)
            raw = engine.ocr(array, cls=True)
        except OCRUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 — vendor SDK failures must stay fail-closed
            raise OCRUnavailable(f"PaddleOCR failed on page {page_number}") from exc
        lines: list[str] = []
        confidences: list[float] = []
        for block in raw or []:
            for item in block or []:
                if not item or len(item) < 2:
                    continue
                payload = item[1]
                if isinstance(payload, (list, tuple)) and payload:
                    text = str(payload[0]).strip()
                    if text:
                        lines.append(text)
                    if len(payload) > 1:
                        try:
                            confidences.append(float(payload[1]))
                        except (TypeError, ValueError):
                            pass
        text = "\n".join(lines).strip()
        if not text:
            raise OCRUnavailable(f"PaddleOCR returned no text on page {page_number}")
        confidence = sum(confidences) / len(confidences) if confidences else None
        ocr_lines = tuple(parse_lines_from_rapid_rows(raw[0] if raw else []))
        return OCRResult(text=text, confidence=confidence, provider="paddleocr", lines=ocr_lines)


class RapidOCRAdapter:
    """Windows-friendly local OCR via ONNX Runtime (PP-OCR exported models).

    Prefer this on NVIDIA RTX 50-series (Blackwell) under native Windows, where
    paddlepaddle-gpu has reported zero-detection bugs. License: Apache-2.0.
    Models should be pre-cached; do not download during customer document jobs.
    """

    enabled = True

    def __init__(self) -> None:
        self._engine = None

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except ImportError:
            try:
                from rapidocr import RapidOCR  # type: ignore
            except ImportError as exc:
                raise OCRUnavailable(
                    "RapidOCR is not installed; pip install rapidocr-onnxruntime onnxruntime "
                    "(or use WSL + PaddleOCR). See outputs/LOCAL_OCR_OPTIONS.md"
                ) from exc
        model_dir = os.getenv("BID_OCR_MODEL_DIR", "").strip()
        kwargs: dict[str, Any] = {}
        if model_dir:
            # Older rapidocr_onnxruntime accepts explicit model paths via config; newer
            # builds read env. Passing nothing uses package defaults (may auto-fetch once).
            kwargs["config_path"] = os.getenv("BID_OCR_RAPID_CONFIG", "") or None
        try:
            self._engine = RapidOCR(**{k: v for k, v in kwargs.items() if v})
        except TypeError:
            self._engine = RapidOCR()
        return self._engine

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        try:
            import numpy as np
            import fitz
        except ImportError as exc:
            raise OCRUnavailable("RapidOCR adapter requires pymupdf and numpy") from exc
        try:
            engine = self._ensure_engine()
            pixmap = fitz.Pixmap(image_bytes)
            if pixmap.alpha:
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
            raw = engine(array)
        except OCRUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OCRUnavailable(f"RapidOCR failed on page {page_number}") from exc

        # rapidocr_onnxruntime → (result, elapse); result is list of [box, text, score]
        # rapidocr ≥1.4 may return an object with .txts / .scores
        lines: list[str] = []
        confidences: list[float] = []
        rows = raw[0] if isinstance(raw, tuple) else raw
        if hasattr(rows, "txts") and rows.txts is not None:
            for text, score in zip(rows.txts, rows.scores or []):
                if text and str(text).strip():
                    lines.append(str(text).strip())
                    try:
                        confidences.append(float(score))
                    except (TypeError, ValueError):
                        pass
        else:
            for item in rows or []:
                if not item:
                    continue
                if len(item) >= 3:
                    text, score = item[1], item[2]
                elif len(item) == 2 and isinstance(item[1], str):
                    text, score = item[1], None
                else:
                    continue
                if text and str(text).strip():
                    lines.append(str(text).strip())
                    if score is not None:
                        try:
                            confidences.append(float(score))
                        except (TypeError, ValueError):
                            pass
        text = "\n".join(lines).strip()
        if not text:
            raise OCRUnavailable(f"RapidOCR returned no text on page {page_number}")
        confidence = sum(confidences) / len(confidences) if confidences else None
        ocr_lines = tuple(parse_lines_from_rapid_rows(rows))
        return OCRResult(text=text, confidence=confidence, provider="rapidocr", lines=ocr_lines)


class HybridOCRAdapter:
    """Try primary; on hard failure or empty-ish low-confidence, try fallback."""

    enabled = True

    def __init__(self, primary: OCRAdapter, fallback: OCRAdapter | None) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        primary_error: Exception | None = None
        primary_result: OCRResult | None = None
        try:
            primary_result = self._primary.extract(image_bytes, page_number)
        except OCRUnavailable as exc:
            primary_error = exc
        if primary_result is not None and not _should_try_fallback(primary_result):
            return primary_result
        if self._fallback is None or not getattr(self._fallback, "enabled", False):
            if primary_result is not None:
                return primary_result
            raise OCRUnavailable(f"Hybrid OCR unavailable on page {page_number}") from primary_error
        try:
            fallback_result = self._fallback.extract(image_bytes, page_number)
        except OCRUnavailable:
            if primary_result is not None:
                return primary_result
            raise
        if primary_result is None:
            return OCRResult(
                text=fallback_result.text,
                confidence=fallback_result.confidence,
                provider=f"hybrid:{fallback_result.provider}",
                lines=fallback_result.lines,
            )
        # Prefer the longer cleaned text when primary looked truncated.
        chosen = fallback_result if len(fallback_result.text) > len(primary_result.text) * 1.1 else primary_result
        return OCRResult(
            text=chosen.text,
            confidence=chosen.confidence,
            provider=f"hybrid:{primary_result.provider}+{fallback_result.provider}",
            lines=chosen.lines,
        )


def sanitize_ocr_text(text: str) -> str:
    """Strip model wrappers (fences / HTML) without inventing missing page content."""
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:html|markdown|text|json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    if re.search(r"</?(html|body|div|p|h[1-6]|table|tr|td|br)\b", value, flags=re.IGNORECASE):
        value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
        value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _looks_truncated_or_markup(raw: str, cleaned: str) -> bool:
    raw_l = (raw or "").lower()
    if "```html" in raw_l or "<html" in raw_l or raw_l.count("</p>") >= 5:
        return True
    return bool(cleaned) and len(cleaned) < 500 and ("<html" in raw_l or "```" in raw_l)


def _should_try_fallback(result: OCRResult) -> bool:
    if result.confidence is not None and result.confidence < 0.5:
        return True
    return len(result.text.strip()) < 40


def _env_flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def _build_named_adapter(name: str) -> OCRAdapter:
    key = name.strip().lower()
    if key in {"", "disabled", "off", "none"}:
        return DisabledOCRAdapter()
    if key in {"qwen", "qwen-vl-ocr", "qwen_vl_ocr"}:
        api_key = os.getenv("QWEN_OCR_API_KEY", "")
        if not api_key:
            return DisabledOCRAdapter()
        try:
            timeout = float(os.getenv("QWEN_OCR_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout = 30.0
        try:
            attempts = int(os.getenv("QWEN_OCR_MAX_ATTEMPTS", "3"))
        except ValueError:
            attempts = 3
        return QwenVLOCRAdapter(
            api_key=api_key,
            endpoint=os.getenv(
                "QWEN_OCR_ENDPOINT",
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            ),
            model=os.getenv("QWEN_OCR_MODEL", "qwen-vl-ocr"),
            timeout_seconds=timeout,
            max_attempts=attempts,
        )
    if key in {"paddle", "paddleocr"}:
        return PaddleOCRAdapter(lang=os.getenv("PADDLE_OCR_LANG", "ch"))
    if key in {"rapid", "rapidocr", "onnx"}:
        return RapidOCRAdapter()
    raise ValueError(f"Unknown OCR provider: {name}")


def get_cloud_ocr_adapter() -> OCRAdapter:
    """Cloud adapter used only after the T1 redaction gate in extraction."""
    if not _env_flag("BIDPROOF_OCR_EGRESS_ALLOWED", "0"):
        return DisabledOCRAdapter()
    mode = os.getenv("BIDPROOF_OCR_EGRESS_MODE", "never").strip().lower()
    if mode not in {"redacted_only", "redacted", "t1", "vpc_private", "vpc", "t2"}:
        return DisabledOCRAdapter()
    return _build_named_adapter(os.getenv("BID_OCR_CLOUD_PROVIDER", "qwen").strip() or "qwen")


def get_local_ocr_adapter() -> OCRAdapter:
    """Local-only adapter (never Qwen), used as the first pass before escalation."""
    provider = os.getenv("BID_OCR_PROVIDER", "disabled").strip().lower()
    if provider in {"hybrid", "auto"}:
        primary = os.getenv("BID_OCR_PRIMARY", "rapid" if os.name == "nt" else "paddle").strip()
        if primary in {"qwen", "qwen-vl-ocr", "qwen_vl_ocr"}:
            primary = "rapid" if os.name == "nt" else "paddle"
        adapter = _build_named_adapter(primary)
        return adapter if adapter.enabled else DisabledOCRAdapter()
    if provider in {"qwen", "qwen-vl-ocr", "qwen_vl_ocr"}:
        # Do not use cloud as the "local" pass under T1 orchestration.
        return DisabledOCRAdapter()
    try:
        adapter = _build_named_adapter(provider)
    except ValueError:
        return DisabledOCRAdapter()
    return adapter


def get_ocr_adapter() -> OCRAdapter:
    provider = os.getenv("BID_OCR_PROVIDER", "disabled").strip().lower()
    if provider in {"hybrid", "auto"}:
        # Windows + Blackwell: default primary to RapidOCR (ONNX). Paddle stays for WSL/Linux.
        # Cloud fallback is NOT used here for T1 — escalation goes through redaction in extraction.
        default_primary = "rapid" if os.name == "nt" else "paddle"
        primary_name = os.getenv("BID_OCR_PRIMARY", default_primary).strip() or default_primary
        fallback_name = os.getenv("BID_OCR_FALLBACK", "disabled").strip() or "disabled"
        if fallback_name in {"qwen", "qwen-vl-ocr", "qwen_vl_ocr"}:
            # Force cloud out of naive hybrid; T1 path owns cloud calls.
            fallback_name = "disabled"
        primary = _build_named_adapter(primary_name)
        fallback = _build_named_adapter(fallback_name)
        if not primary.enabled and fallback.enabled:
            return fallback
        if primary.enabled:
            return HybridOCRAdapter(primary, fallback if fallback.enabled else None)
        return DisabledOCRAdapter()
    try:
        adapter = _build_named_adapter(provider)
    except ValueError:
        return DisabledOCRAdapter()
    return adapter


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
