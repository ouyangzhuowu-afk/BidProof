import fitz

from app.ocr import OCRResult, get_cloud_ocr_adapter, get_ocr_adapter
from app.ocr_privacy import (
    OCRLine,
    classify_page_text,
    redact_png_bytes,
    should_escalate_to_cloud,
)
from app.extraction import extract_pdf


def test_classify_blocks_license_and_contact_pages():
    risk = classify_page_text("投标人须提供医疗器械经营许可证复印件并加盖公章。")
    assert risk.block_escalation
    assert "license_scan" in risk.block_reasons or "seal" in risk.block_reasons


def test_classify_toc_is_escalation_hint_not_block():
    risk = classify_page_text("目录\n第一章 磋商邀请 ................ 1\n第二章 采购需求 .............. 8")
    assert not risk.block_escalation
    assert "toc" in risk.escalate_hints


def test_should_escalate_requires_egress_flags(monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    risk = classify_page_text("目录 第一章")
    ok, reason = should_escalate_to_cloud(local_text="短", local_confidence=0.2, risk=risk)
    assert ok is False
    assert reason == "egress_disabled"


def test_should_escalate_when_t1_enabled_and_low_confidence(monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    risk = classify_page_text("目录 第一章 磋商须知")
    ok, reason = should_escalate_to_cloud(local_text="x" * 20, local_confidence=0.3, risk=risk)
    assert ok is True
    assert "low_confidence" in reason or "hint:toc" in reason


def test_redact_masks_phone_line_bbox():
    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    page.insert_text((20, 100), "hello")
    png = page.get_pixmap(alpha=False).tobytes("png")
    doc.close()
    lines = [OCRLine(text="联系人: 沈女士 电话 13800138000", confidence=0.9, bbox=(10, 80, 180, 120))]
    result = redact_png_bytes(png, lines)
    assert result.masked_line_count == 1
    assert result.header_footer_masked is True
    assert result.clean is True
    assert result.content_sha256 != __import__("hashlib").sha256(png).hexdigest()


def test_cloud_adapter_disabled_without_t1_mode(monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "never")
    monkeypatch.setenv("BID_OCR_PROVIDER", "disabled")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    assert get_cloud_ocr_adapter().enabled is False


def test_t1_escalation_sends_only_redacted_image(monkeypatch, tmp_path):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.setenv("BID_OCR_PROVIDER", "rapid")
    monkeypatch.setenv("BID_OCR_CLOUD_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    monkeypatch.setenv("BID_OCR_TILE_ENABLED", "0")

    seen = {"cloud_calls": 0, "payload_len": 0}

    class LocalAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            return OCRResult(
                text="目录\n短",
                confidence=0.2,
                provider="rapidocr",
                lines=(OCRLine(text="目录", confidence=0.9, bbox=(10, 40, 80, 60)),),
            )

    class CloudAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            seen["cloud_calls"] += 1
            seen["payload_len"] = len(image_bytes)
            # Must receive a PNG (redacted), not empty.
            assert image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
            return OCRResult(text="目录\n第一章 磋商邀请\n第二章 采购需求\n" + ("条款 " * 40), provider="qwen-vl-ocr")

    monkeypatch.setattr("app.extraction.get_cloud_ocr_adapter", lambda: CloudAdapter())

    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path, ocr_adapter=LocalAdapter())
    assert seen["cloud_calls"] == 1
    assert pages[0]["ocr_egress"] == "redacted_cloud"
    assert pages[0]["ocr_egress_mode"] == "redacted_only"
    assert "第一章" in pages[0]["text"]
    assert "redacted:qwen" in pages[0]["ocr_provider"]


def test_t1_blocks_license_page_from_cloud(monkeypatch, tmp_path):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.setenv("BID_OCR_TILE_ENABLED", "0")

    class LocalAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            return OCRResult(
                text="请提供医疗器械经营许可证复印件并加盖公章",
                confidence=0.2,
                provider="rapidocr",
            )

    calls = {"n": 0}

    class CloudAdapter:
        enabled = True

        def extract(self, image_bytes, page_number):
            calls["n"] += 1
            return OCRResult(text="should-not-run", provider="qwen-vl-ocr")

    monkeypatch.setattr("app.extraction.get_cloud_ocr_adapter", lambda: CloudAdapter())

    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path, ocr_adapter=LocalAdapter())
    assert calls["n"] == 0
    assert pages[0]["ocr_egress"] == "blocked_sensitive_page"
