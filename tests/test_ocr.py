import json

import fitz

from app.extraction import extract_pdf
from app.ocr import DisabledOCRAdapter, OCRResult, QwenVLOCRAdapter, get_ocr_adapter


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
            from app.ocr import OCRUnavailable

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
