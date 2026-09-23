from pathlib import Path

import fitz
import pytest

from app.extraction import extract_pdf
from app.ocr import OCRAdapter, OCRResult

ROOT = Path(__file__).resolve().parents[1]


class MockRecordingAdapter(OCRAdapter):
    def __init__(self):
        self.enabled = True
        self.calls = []

    def extract(self, image_bytes: bytes, page_number: int) -> OCRResult:
        self.calls.append(page_number)
        return OCRResult(
            text=f"OCR extracted text for page {page_number}",
            provider="mock-ocr",
            confidence=0.95,
        )


def test_pymupdf4llm_extracts_markdown_and_tables_from_fixture():
    fixture_path = ROOT / "work" / "fixtures" / "source2-nanjing.pdf"
    if not fixture_path.is_file():
        pytest.skip("Fixture source2-nanjing.pdf not present")

    pages = extract_pdf(fixture_path)
    assert len(pages) > 0

    first_page = pages[0]
    assert "markdown" in first_page
    assert "tables" in first_page
    assert first_page["has_text"] is True
    assert first_page["ocr_required"] is False
    # Cover page has 45 chars (< 50 threshold), so it is correctly marked sparse
    assert first_page["sparse"] is True

    dense_page = next(p for p in pages if p["char_count"] >= 100)
    assert dense_page["sparse"] is False
    assert dense_page["ocr_required"] is False
    assert len(dense_page["markdown"]) >= 100


def test_synthetic_table_page_markdown(tmp_path):
    path = tmp_path / "table_doc.pdf"
    document = fitz.open()
    page = document.new_page()
    table_text = (
        "Qualification and Mandatory Requirements Table\n\n"
        "| Index | Criteria | Score | Mandatory |\n"
        "| 1     | ISO9001  | 10    | YES       |\n"
        "| 2     | License  | 20    | YES       |\n"
    )
    page.insert_text((72, 72), table_text)
    document.save(path)
    document.close()

    pages = extract_pdf(path)
    assert len(pages) == 1
    p = pages[0]
    assert "markdown" in p
    assert "tables" in p
    assert "Qualification and Mandatory Requirements" in p["markdown"]
    assert p["has_text"] is True
    assert p["ocr_required"] is False
    assert p["sparse"] is False


def test_sparse_page_detection_and_escalation(tmp_path):
    path = tmp_path / "sparse.pdf"
    document = fitz.open()
    page = document.new_page()
    # Sparse text (< 50 chars), e.g. a stamp note
    page.insert_text((72, 72), "Official Seal Only")
    document.save(path)
    document.close()

    adapter = MockRecordingAdapter()
    pages = extract_pdf(path, ocr_adapter=adapter)

    assert len(pages) == 1
    p = pages[0]
    assert p["sparse"] is True
    assert p["low_text_confidence"] is True
    # Sparse page must escalate to OCR
    assert len(adapter.calls) >= 1
    assert adapter.calls[0] == 1
    assert p["ocr_status"] == "EXTRACTED"
    assert "OCR extracted text for page 1" in p["text"]


def test_dense_vector_page_bypasses_ocr(tmp_path):
    path = tmp_path / "dense.pdf"
    document = fitz.open()
    page = document.new_page()
    # Dense text with > 50 characters
    dense_text = (
        "The bidder must possess independent legal personality and valid business license. "
        "The bidder must have sound financial accounting system and good tax payment records. "
        "All required certifications and qualifications must be submitted with valid timestamps."
    )
    page.insert_text((72, 72), dense_text)
    document.save(path)
    document.close()

    adapter = MockRecordingAdapter()
    pages = extract_pdf(path, ocr_adapter=adapter)

    assert len(pages) == 1
    p = pages[0]
    assert p["sparse"] is False
    assert p["low_text_confidence"] is False
    assert p["ocr_required"] is False
    # Adapter must NOT be called for dense vector pages
    assert len(adapter.calls) == 0
    assert "independent legal personality" in p["text"]


def test_sparse_threshold_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("BID_SPARSE_THRESHOLD", "100")
    path = tmp_path / "custom_threshold.pdf"
    document = fitz.open()
    page = document.new_page()
    # 70 chars of text: dense under default 50, but sparse under overridden 100
    text_70 = "This is a sentence designed to test the configurable threshold parameter."
    page.insert_text((72, 72), text_70)
    document.save(path)
    document.close()

    adapter = MockRecordingAdapter()
    pages = extract_pdf(path, ocr_adapter=adapter)
    assert pages[0]["sparse"] is True
    assert len(adapter.calls) >= 1
