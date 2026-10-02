"""Dual-check OCR egress: real HTTP send count must stay 0 without approval."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import fitz
import pytest

from app.egress_policy import (
    EgressDenied,
    assert_http_send_allowed,
    evaluate_cloud_egress,
    host_allowed,
)
from app.ocr import (
    DisabledOCRAdapter,
    OCRUnavailable,
    QwenVLOCRAdapter,
    get_cloud_ocr_adapter,
    get_ocr_adapter,
    set_cloud_doc_sha256,
    clear_cloud_doc_sha256,
)
from app.ocr_privacy import OCRLine, classify_page_for_egress
from work import ocr_batch


DASH_SCOPE = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DOC_SHA = "a" * 64


def _approve(monkeypatch, *, expires: str | None = None, doc_pin: str | None = None) -> None:
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_APPROVAL", "T1-JOE-WRITTEN-APPROVAL")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret-key-for-tests")
    monkeypatch.setenv("QWEN_OCR_ENDPOINT", DASH_SCOPE)
    if expires is not None:
        monkeypatch.setenv("BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT", expires)
    else:
        monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT", raising=False)
    if doc_pin is not None:
        monkeypatch.setenv("BIDPROOF_OCR_EGRESS_DOC_SHA256", doc_pin)
    else:
        monkeypatch.delenv("BIDPROOF_OCR_EGRESS_DOC_SHA256", raising=False)


@pytest.fixture(autouse=True)
def _clear_doc_pin():
    clear_cloud_doc_sha256()
    yield
    clear_cloud_doc_sha256()


def _counting_urlopen(counter: dict):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "云端结果"}}]}).encode()

    def fake_open(request, timeout=None):
        counter["n"] += 1
        return Response()

    return fake_open


def test_default_off_blocks_factory_and_send(monkeypatch):
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_ALLOWED", raising=False)
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    decision = evaluate_cloud_egress(endpoint=DASH_SCOPE)
    assert decision.allowed is False
    assert decision.reason == "egress_disabled"
    assert isinstance(get_cloud_ocr_adapter(), DisabledOCRAdapter)
    with pytest.raises(EgressDenied):
        assert_http_send_allowed(endpoint=DASH_SCOPE)


def test_no_auth_approval_blocks_even_when_switch_on(monkeypatch):
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    decision = evaluate_cloud_egress(endpoint=DASH_SCOPE)
    assert decision.allowed is False
    assert decision.reason == "no_auth_approval"
    assert isinstance(get_cloud_ocr_adapter(), DisabledOCRAdapter)


def test_expired_approval_blocks_send(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _approve(monkeypatch, expires=past)
    decision = evaluate_cloud_egress(endpoint=DASH_SCOPE)
    assert decision.allowed is False
    assert decision.reason == "approval_expired"
    assert isinstance(get_cloud_ocr_adapter(), DisabledOCRAdapter)


def test_doc_mismatch_blocks_send(monkeypatch):
    _approve(monkeypatch, doc_pin=DOC_SHA)
    set_cloud_doc_sha256("b" * 64)
    decision = evaluate_cloud_egress(endpoint=DASH_SCOPE, doc_sha256="b" * 64)
    assert decision.allowed is False
    assert decision.reason == "doc_mismatch"
    assert isinstance(get_cloud_ocr_adapter(), DisabledOCRAdapter)

    sends = {"n": 0}
    monkeypatch.setattr("urllib.request.build_opener", lambda *a, **k: type("O", (), {"open": staticmethod(_counting_urlopen(sends))})())
    adapter = QwenVLOCRAdapter("secret", endpoint=DASH_SCOPE)
    with pytest.raises(OCRUnavailable, match="egress denied"):
        adapter.extract(b"png", 1)
    assert sends["n"] == 0


def test_direct_qwen_provider_never_sends(monkeypatch):
    monkeypatch.setenv("BID_OCR_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    sends = {"n": 0}
    monkeypatch.setattr("urllib.request.urlopen", _counting_urlopen(sends))
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *a, **k: type("O", (), {"open": staticmethod(_counting_urlopen(sends))})(),
    )
    assert isinstance(get_ocr_adapter(), DisabledOCRAdapter)
    assert sends["n"] == 0


def test_hybrid_primary_fallback_qwen_never_sends(monkeypatch):
    monkeypatch.setenv("BID_OCR_PROVIDER", "hybrid")
    monkeypatch.setenv("BID_OCR_PRIMARY", "disabled")
    monkeypatch.setenv("BID_OCR_FALLBACK", "qwen")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    # Even with switch on, hybrid must not use cloud without written approval path.
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    sends = {"n": 0}
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *a, **k: type("O", (), {"open": staticmethod(_counting_urlopen(sends))})(),
    )
    assert isinstance(get_ocr_adapter(), DisabledOCRAdapter)
    assert sends["n"] == 0


def test_work_script_ocr_batch_stays_local(monkeypatch, tmp_path):
    monkeypatch.setenv("BID_OCR_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_OCR_API_KEY", "secret")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "1")
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_MODE", "redacted_only")
    monkeypatch.delenv("BIDPROOF_OCR_EGRESS_APPROVAL", raising=False)
    sends = {"n": 0}
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *a, **k: type("O", (), {"open": staticmethod(_counting_urlopen(sends))})(),
    )
    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
    summary = ocr_batch.run(path, tmp_path / "out")
    assert summary["adapter_enabled"] is False
    assert summary["egress"] == "local_only"
    assert sends["n"] == 0


def test_bad_redirect_blocks_send(monkeypatch):
    _approve(monkeypatch)
    assert host_allowed(DASH_SCOPE) is True
    assert host_allowed("https://evil.example/steal") is False
    decision = evaluate_cloud_egress(
        endpoint=DASH_SCOPE,
        redirect_url="https://evil.example/steal",
    )
    assert decision.allowed is False
    assert decision.reason == "bad_redirect"

    sends = {"n": 0}

    class EvilRedirectOpener:
        def open(self, request, timeout=None):
            # Simulate redirect handler raising via policy check path
            raise EgressDenied("bad_redirect")

    monkeypatch.setattr("urllib.request.build_opener", lambda *a, **k: EvilRedirectOpener())
    adapter = QwenVLOCRAdapter("secret", endpoint=DASH_SCOPE)
    with pytest.raises(OCRUnavailable, match="egress denied|bad_redirect"):
        adapter.extract(b"png", 1)
    assert sends["n"] == 0


def test_classify_unknown_when_ocr_or_bbox_missing():
    missing = classify_page_for_egress(local_text="", lines=(), ocr_available=False)
    assert missing.page_types == ["UNKNOWN"]
    assert missing.block_escalation is True

    no_bbox = classify_page_for_egress(
        local_text="目录 第一章",
        lines=(OCRLine(text="联系人: 沈女士 电话 13800138000", confidence=0.9, bbox=None),),
        ocr_available=True,
    )
    assert "UNKNOWN" in no_bbox.page_types
    assert no_bbox.block_escalation is True


def test_approved_factory_still_dual_checks_http(monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    _approve(monkeypatch, expires=future)
    adapter = get_cloud_ocr_adapter()
    assert adapter.enabled is True

    sends = {"n": 0}
    monkeypatch.setattr(
        "urllib.request.build_opener",
        lambda *a, **k: type("O", (), {"open": staticmethod(_counting_urlopen(sends))})(),
    )
    # Clear approval after factory — send-time dual-check must still deny.
    monkeypatch.setenv("BIDPROOF_OCR_EGRESS_ALLOWED", "0")
    with pytest.raises(OCRUnavailable, match="egress denied"):
        adapter.extract(b"png", 1)
    assert sends["n"] == 0
