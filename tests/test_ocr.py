import json

import fitz
import pytest

from app.extraction import extract_pdf, ocr_page_image
from app.ocr import (
    DisabledOCRAdapter,
    HybridOCRAdapter,
    OCRResult,
    OCRUnavailable,
    QwenVLOCRAdapter,
    get_ocr_adapter,
    sanitize_ocr_text,
)


def test_ocr_is_disabled_without_provider_or_key(monkeypatch):
    monkeypatch.delenv("BID_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    assert isinstance(get_ocr_adapter(), DisabledOCRAdapter)


def test_blank_page_records_disabled_ocr_and_remains_unresolved(tmp_path, monkeypatch):
    monkeypatch.delenv("BID_OCR_PROVIDER", raising=False)
    monkeypatch.delenv("QWEN_OCR_API_KEY", raising=False)
    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path)

    assert pages[0]["ocr_required"] is True
    assert pages[0]["ocr_status"] == "DISABLED"
    assert pages[0]["text"] == ""


def test_enabled_adapter_failure_is_fail_closed(tmp_path):
    class FailingAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            raise OCRUnavailable("provider unavailable")

    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path, ocr_adapter=FailingAdapter())

    assert pages[0]["ocr_status"] == "FAILED"
    assert pages[0]["has_text"] is False
    assert pages[0]["text"] == ""


def test_qwen_adapter_parses_openai_compatible_response(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "识别结果"}}]}).encode()

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.headers["Authorization"]
        seen["timeout"] = timeout
        seen["payload"] = json.loads(request.data.decode())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = QwenVLOCRAdapter("secret", endpoint="https://example.invalid/ocr", timeout_seconds=5)

    result = adapter.extract(b"png", 2)

    assert result == OCRResult(text="识别结果", provider="qwen-vl-ocr")
    assert seen["authorization"] == "Bearer secret"
    assert seen["payload"]["model"] == "qwen-vl-ocr"
    assert "data:image/png;base64," in seen["payload"]["messages"][0]["content"][1]["image_url"]["url"]


def test_sanitize_ocr_text_strips_html_fences():
    raw = "```html\n<html><body><p>目录</p><p>第一章 招标公告 1</p></body></html>\n```"
    assert sanitize_ocr_text(raw) == "目录\n第一章 招标公告 1"


def test_qwen_adapter_marks_html_dump_low_confidence(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            body = {
                "choices": [
                    {
                        "message": {
                            "content": "```html\n<html><body>"
                            + "".join(f"<p>条目{i}</p>" for i in range(8))
                            + "</body></html>\n```"
                        }
                    }
                ]
            }
            return json.dumps(body).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response())
    adapter = QwenVLOCRAdapter("secret", endpoint="https://example.invalid/ocr")
    result = adapter.extract(b"png", 1)
    assert "条目0" in result.text
    assert "<p>" not in result.text
    assert result.confidence == 0.35


def test_qwen_adapter_retries_transient_errors(monkeypatch):
    calls = {"n": 0}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "重试成功"}}]}).encode()

    def fake_urlopen(request, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("temporary")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("app.ocr.time.sleep", lambda *_: None)
    adapter = QwenVLOCRAdapter("secret", endpoint="https://example.invalid/ocr", max_attempts=3)
    assert adapter.extract(b"png", 1).text == "重试成功"
    assert calls["n"] == 2


def test_hybrid_falls_back_when_primary_fails():
    class Boom:
        enabled = True

        def extract(self, image_bytes, page_number):
            raise OCRUnavailable("primary down")

    class Ok:
        enabled = True

        def extract(self, image_bytes, page_number):
            return OCRResult(text="本地结果", confidence=0.9, provider="paddleocr")

    hybrid = HybridOCRAdapter(Boom(), Ok())
    result = hybrid.extract(b"png", 1)
    assert result.text == "本地结果"
    assert result.provider.startswith("hybrid:")


def test_hybrid_blocks_cloud_fallback_without_egress_allow(monkeypatch):
    monkeypatch.setenv("BID_OCR_PROVIDER", "hybrid")
    monkeypatch.setenv("BID_OCR_PRIMARY", "disabled")
    monkeypatch.setenv("BID_OCR_FALLBACK", "qwen")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    assert isinstance(get_ocr_adapter(), DisabledOCRAdapter)


def test_rapidocr_adapter_from_png_bytes(monkeypatch):
    from app.ocr import RapidOCRAdapter

    pytest = __import__("pytest")
    pytest.importorskip("numpy")

    class FakeEngine:
        def __call__(self, array):
            return ([[None, "医疗器械经营许可证", 0.97], [None, "注册证", 0.91]], 0.01)

    doc = fitz.open()
    page = doc.new_page(width=32, height=16)
    png = page.get_pixmap().tobytes("png")
    doc.close()

    adapter = RapidOCRAdapter()
    adapter._engine = FakeEngine()
    result = adapter.extract(png, 1)
    assert "医疗器械经营许可证" in result.text
    assert result.provider == "rapidocr"
    assert result.confidence and result.confidence > 0.9


def test_ocr_lines_become_localized_blocks_and_emit_metrics(tmp_path, monkeypatch):
    from app.ocr_privacy import OCRLine
    from app import observability

    observability.reset_for_tests()
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")

    class LinedAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            return OCRResult(
                text="营业执照\n医疗器械经营许可证",
                confidence=0.95,
                provider="rapidocr",
                lines=(
                    OCRLine(text="营业执照", confidence=0.96, bbox=(15.0, 30.0, 150.0, 50.0)),
                    OCRLine(text="医疗器械经营许可证", confidence=0.94, bbox=(15.0, 60.0, 280.0, 80.0)),
                ),
            )

    path = tmp_path / "scan-like.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path, ocr_adapter=LinedAdapter())
    page = pages[0]
    assert page["ocr_status"] == "EXTRACTED"
    assert len(page["blocks"]) == 2
    assert page["blocks"][0]["locator"]["kind"] == "ocr_line"
    assert page["blocks"][0]["locator"]["page"] == 1
    # Image px → PDF points at default scale 1.5
    assert page["blocks"][0]["bbox"] == pytest.approx([10.0, 20.0, 100.0, 50.0 / 1.5])
    metrics = observability.prometheus_text()
    assert 'bidproof_ocr_pages_total{provider="rapidocr",egress="none"}' in metrics


def test_ocr_page_tiling_stitches_when_full_page_looks_truncated(monkeypatch, tmp_path):
    monkeypatch.setenv("BID_OCR_TILE_ENABLED", "1")
    monkeypatch.setenv("BID_OCR_TILE_STRIPS", "3")

    class TruncatingThenTiles:
        enabled = True
        calls = 0

        def extract(self, image_bytes, page_number):
            self.calls += 1
            if self.calls == 1:
                return OCRResult(text="短", confidence=0.35, provider="mock")
            return OCRResult(text=f"条带{self.calls}", confidence=0.9, provider="mock")

    path = tmp_path / "tall.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    doc = fitz.open(path)
    page = doc[0]
    adapter = TruncatingThenTiles()
    result = ocr_page_image(page, adapter, 1)
    doc.close()

    assert "条带" in result.text
    assert "+tiles" in result.provider
    assert adapter.calls >= 4
