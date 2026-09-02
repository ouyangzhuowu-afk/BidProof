import io
from pathlib import Path
import zipfile

from app.extraction import extract_file
from app.reporting import _locator_label as report_locator_label
from app.rules import extract_requirements, match_evidence


def _write_zip(path: Path, files: dict[str, str]) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    path.write_bytes(buffer.getvalue())


def test_docx_distinguishes_paragraphs_and_table_cells(tmp_path):
    path = tmp_path / "requirements.docx"
    _write_zip(path, {
        "word/document.xml": """
        <w:document xmlns:w="urn:word"><w:body>
          <w:p><w:r><w:t>资格要求：依法注册</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>投标保证金 10 万元</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
        </w:body></w:document>
        """,
    })

    pages = extract_file(path)

    assert pages[0]["locator"] == {"kind": "paragraph", "label": "段落 1", "index": 1}
    assert pages[1]["locator"] == {
        "kind": "table_cell",
        "label": "表格 1 · 第 1 行 · 第 1 列",
        "table": 1,
        "row": 1,
        "column": 1,
    }
    requirements = extract_requirements(pages)
    assert {item["source"]["locator"]["kind"] for item in requirements} == {"paragraph", "table_cell"}


def test_xlsx_preserves_sheet_name_and_cell_coordinate(tmp_path):
    path = tmp_path / "evidence.xlsx"
    _write_zip(path, {
        "xl/workbook.xml": """
        <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <sheets><sheet name="资质清单" sheetId="1" r:id="rId1"/></sheets>
        </workbook>
        """,
        "xl/worksheets/sheet1.xml": """
        <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
          <sheetData><row r="17"><c r="B17" t="inlineStr"><is><t>营业执照有效</t></is></c></row></sheetData>
        </worksheet>
        """,
    })

    page = extract_file(path)[0]

    assert page["locator"] == {"kind": "sheet", "label": "工作表“资质清单”", "index": 1, "sheet_name": "资质清单"}
    assert page["blocks"][0]["locator"] == {
        "kind": "cell",
        "label": "工作表“资质清单” · B17",
        "sheet": 1,
        "sheet_name": "资质清单",
        "cell": "B17",
    }
    requirement = {
        "requirement_id": "REQ-0001",
        "category": "QUALIFICATION",
        "title": "资格要求：提供营业执照",
        "source": {"page": 1, "locator": {"kind": "page", "label": "第 1 页"}, "quote": "资格要求"},
        "evidence": [],
        "status": "UNKNOWN",
    }
    matched = match_evidence([requirement], [page], "evidence.xlsx")
    assert matched[0]["evidence"][0]["locator"]["label"] == "工作表“资质清单” · B17"


def test_pptx_and_text_use_slide_blocks_and_line_numbers(tmp_path):
    pptx = tmp_path / "deck.pptx"
    _write_zip(pptx, {
        "ppt/slides/slide1.xml": """
        <p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:cSld><p:spTree>
          <p:sp><p:txBody><a:p><a:r><a:t>项目经验</a:t></a:r></a:p><a:p><a:r><a:t>人员证书</a:t></a:r></a:p></p:txBody></p:sp>
        </p:spTree></p:cSld></p:sld>
        """,
    })
    text = tmp_path / "notes.txt"
    text.write_text("第一行\n资格要求：提供营业执照\n第三行", encoding="utf-8")

    slide = extract_file(pptx)[0]
    lines = extract_file(text)[0]

    assert [block["locator"]["label"] for block in slide["blocks"]] == ["幻灯片 1 · 文本块 1", "幻灯片 1 · 文本块 2"]
    assert [block["locator"]["label"] for block in lines["blocks"]] == ["第 1 行", "第 2 行", "第 3 行"]
    requirements = extract_requirements([lines])
    assert requirements[0]["source"]["locator"]["label"] == "第 2 行"


def test_non_page_locator_is_never_rendered_as_a_page():
    item = {"page": 9, "locator": {"kind": "paragraph", "label": "段落 9", "index": 9}}
    assert report_locator_label(item) == "段落 9"
    assert "页" not in report_locator_label(item)


def test_report_columns_use_locator_language_for_non_page_sources():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    assert '"tender_locator"' in source
    assert '"evidence_locators"' in source
    assert "<th>招标定位</th>" in source
    assert "<th>企业证据定位</th>" in source
