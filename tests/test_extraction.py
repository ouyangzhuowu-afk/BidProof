import fitz

from app.extraction import extract_pdf


def test_pdf_extraction_keeps_layout_blocks_and_bbox(tmp_path):
    path = tmp_path / "layout.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Mandatory qualification evidence must be supplied.")
    document.save(path)
    document.close()

    pages = extract_pdf(path)

    assert pages[0]["ocr_required"] is False
    assert pages[0]["blocks"]
    assert len(pages[0]["blocks"][0]["bbox"]) == 4


def test_blank_pdf_page_requires_ocr(tmp_path):
    path = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()

    pages = extract_pdf(path)

    assert pages[0]["ocr_required"] is True
    assert pages[0]["has_text"] is False


def test_unicode_nfkc_maps_compatibility_ideographs():
    import unicodedata

    assert unicodedata.normalize("NFKC", "\u2f00\u2f01") == "一丨"
