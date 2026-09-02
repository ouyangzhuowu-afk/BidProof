from pathlib import Path
from typing import Any
import unicodedata
import re
import zipfile
import xml.etree.ElementTree as ET

from .ocr import OCRAdapter, OCRUnavailable, get_ocr_adapter


class ExtractionError(RuntimeError):
    pass


def extract_pdf(path: Path, ocr_adapter: OCRAdapter | None = None) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise ExtractionError("PyMuPDF is required to extract PDF text") from exc

    pages: list[dict[str, Any]] = []
    adapter = ocr_adapter if ocr_adapter is not None else get_ocr_adapter()
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise ExtractionError(f"Cannot open PDF: {exc}") from exc
    with document:
        for index, page in enumerate(document):
            text = unicodedata.normalize("NFKC", page.get_text("text") or "")
            blocks: list[dict[str, Any]] = []
            try:
                for block_index, raw in enumerate(page.get_text("dict").get("blocks", []), 1):
                    if raw.get("type") != 0:
                        continue
                    block_text = unicodedata.normalize("NFKC", "".join(
                        span.get("text", "")
                        for line in raw.get("lines", [])
                        for span in line.get("spans", [])
                    )).strip()
                    if not block_text:
                        continue
                    bbox = raw.get("bbox")
                    blocks.append(
                        {
                            "text": block_text,
                            "bbox": [float(value) for value in bbox] if bbox and len(bbox) == 4 else None,
                            "locator": {
                                "kind": "page_region",
                                "label": f"第 {index + 1} 页 · 区域 {block_index}",
                                "page": index + 1,
                                "region": block_index,
                                "bbox": [float(value) for value in bbox] if bbox and len(bbox) == 4 else None,
                            },
                        }
                    )
            except (AttributeError, TypeError, ValueError):
                # Text extraction remains usable even when a malformed block is returned.
                blocks = []
            page_data = {
                    "page": index + 1,
                    "locator": {"kind": "page", "label": f"第 {index + 1} 页", "index": index + 1},
                    "text": text,
                    "has_text": bool(text.strip()),
                    "ocr_required": not bool(text.strip()),
                    "low_text_confidence": 0 < len(text.strip()) < 20,
                    "char_count": len(text),
                    "blocks": blocks,
                }
            if adapter.enabled and (page_data["ocr_required"] or page_data["low_text_confidence"]):
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    result = adapter.extract(pixmap.tobytes("png"), index + 1)
                    page_data["text"] = result.text
                    page_data["has_text"] = True
                    page_data["ocr_status"] = "EXTRACTED"
                    page_data["ocr_provider"] = result.provider
                    page_data["ocr_confidence"] = result.confidence
                    page_data["char_count"] = len(result.text)
                    page_data["blocks"] = [{"text": result.text, "bbox": list(page.rect)}]
                except OCRUnavailable as exc:
                    page_data["ocr_status"] = "FAILED"
                    # Keep provider details and credentials out of persisted page metadata.
                    page_data["ocr_error"] = "OCR_UNAVAILABLE"
                    page_data["low_text_confidence"] = True
            elif page_data["ocr_required"]:
                page_data["ocr_status"] = "DISABLED"
            pages.append(page_data)
    return pages


def extract_text_file(path: Path) -> list[dict[str, Any]]:
    text = unicodedata.normalize("NFKC", path.read_text(encoding="utf-8", errors="replace"))
    lines = text.splitlines()
    blocks = [
        {
            "text": value,
            "bbox": None,
            "locator": {"kind": "line_range", "label": f"第 {line_number} 行", "start_line": line_number, "end_line": line_number},
        }
        for line_number, value in enumerate(lines, 1)
        if value.strip()
    ]
    line_count = max(len(lines), 1)
    return [{
        "page": 1,
        "locator": {"kind": "line_range", "label": f"第 1-{line_count} 行", "start_line": 1, "end_line": line_count},
        "text": text,
        "has_text": bool(text.strip()),
        "ocr_required": False,
        "low_text_confidence": False,
        "char_count": len(text),
        "blocks": blocks,
    }]


def extract_ooxml(path: Path) -> list[dict[str, Any]]:
    """Extract text from modern Office Open XML files without a heavyweight Office runtime."""
    try:
        with zipfile.ZipFile(path) as archive:
            if path.suffix.lower() == ".docx":
                xml = archive.read("word/document.xml")
                root = ET.fromstring(xml)
                return _docx_sources(root)
            if path.suffix.lower() == ".xlsx":
                shared = []
                if "xl/sharedStrings.xml" in archive.namelist():
                    shared = [_xml_text(archive.read("xl/sharedStrings.xml"), separator="")]
                    shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                    shared = ["".join(node.itertext()) for node in shared_root.iter() if _local(node.tag) == "si"]
                sheets = sorted(
                    (name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)),
                    key=lambda name: int(re.search(r"(\d+)", name).group(1)),
                )
                sheet_names = _xlsx_sheet_names(archive)
                result = []
                for index, name in enumerate(sheets, 1):
                    sheet_name = sheet_names[index - 1] if index <= len(sheet_names) else None
                    text, cells = _xlsx_sheet_data(archive.read(name), shared, index, sheet_name)
                    locator = {"kind": "sheet", "label": f"工作表“{sheet_name}”" if sheet_name else f"工作表 {index}", "index": index}
                    if sheet_name:
                        locator["sheet_name"] = sheet_name
                    page = _text_page(text, index, locator)
                    page["blocks"] = cells
                    result.append(page)
                return result or [_text_page("", 1, {"kind": "sheet", "label": "工作表 1", "index": 1})]
            if path.suffix.lower() == ".pptx":
                slides = sorted(
                    (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                    key=lambda name: int(re.search(r"(\d+)", name).group(1)),
                )
                result = []
                for index, name in enumerate(slides, 1):
                    text, blocks = _pptx_slide_data(archive.read(name), index)
                    page = _text_page(text, index, {"kind": "slide", "label": f"幻灯片 {index}", "index": index})
                    page["blocks"] = blocks
                    result.append(page)
                return result or [_text_page("", 1, {"kind": "slide", "label": "幻灯片 1", "index": 1})]
    except (KeyError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ExtractionError(f"无法解析 {path.suffix} 文件，请确认它是有效的现代 Office 文件") from exc
    raise ExtractionError(f"Unsupported Office file: {path.suffix}")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_text(payload: bytes, separator: str = "\n") -> str:
    root = ET.fromstring(payload)
    values = ["".join(node.itertext()).strip() for node in root.iter() if _local(node.tag) == "t"]
    return separator.join(value for value in values if value)


def _docx_sources(root: ET.Element) -> list[dict[str, Any]]:
    body = next((node for node in root.iter() if _local(node.tag) == "body"), root)
    sources: list[dict[str, Any]] = []
    paragraph_index = 0
    table_index = 0
    for child in body:
        kind = _local(child.tag)
        if kind == "p":
            value = "".join("".join(node.itertext()) for node in child.iter() if _local(node.tag) == "t").strip()
            if value:
                paragraph_index += 1
                sources.append(_text_page(value, len(sources) + 1, {"kind": "paragraph", "label": f"段落 {paragraph_index}", "index": paragraph_index}))
        elif kind == "tbl":
            table_index += 1
            for row_index, row in enumerate((node for node in child if _local(node.tag) == "tr"), 1):
                for column_index, cell in enumerate((node for node in row if _local(node.tag) == "tc"), 1):
                    value = " ".join(
                        "".join(text.itertext()).strip()
                        for text in cell.iter()
                        if _local(text.tag) == "t" and "".join(text.itertext()).strip()
                    )
                    if value:
                        sources.append(_text_page(value, len(sources) + 1, {
                            "kind": "table_cell",
                            "label": f"表格 {table_index} · 第 {row_index} 行 · 第 {column_index} 列",
                            "table": table_index,
                            "row": row_index,
                            "column": column_index,
                        }))
    return sources or [_text_page("", 1, {"kind": "paragraph", "label": "段落 1", "index": 1})]


def _xlsx_sheet_names(archive: zipfile.ZipFile) -> list[str]:
    if "xl/workbook.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/workbook.xml"))
    return [node.attrib.get("name", "").strip() for node in root.iter() if _local(node.tag) == "sheet"]


def _xlsx_sheet_data(payload: bytes, shared: list[str], sheet_index: int, sheet_name: str | None) -> tuple[str, list[dict[str, Any]]]:
    root = ET.fromstring(payload)
    rows = []
    cells = []
    for row_index, row in enumerate((node for node in root.iter() if _local(node.tag) == "row"), 1):
        values = []
        for column_index, cell in enumerate((node for node in row if _local(node.tag) == "c"), 1):
            value_node = next((node for node in cell if _local(node.tag) in {"v", "t"}), None)
            if value_node is None:
                inline = next((node for node in cell.iter() if _local(node.tag) == "t"), None)
                value = "" if inline is None else "".join(inline.itertext())
            else:
                value = "".join(value_node.itertext())
            if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                value = shared[int(value)]
            value = value.strip()
            coordinate = cell.attrib.get("r") or f"{_column_label(column_index)}{row.attrib.get('r', row_index)}"
            values.append(f"{coordinate}: {value}" if value else "")
            if value:
                locator = {"kind": "cell", "label": f"工作表“{sheet_name}” · {coordinate}" if sheet_name else f"工作表 {sheet_index} · {coordinate}", "sheet": sheet_index, "cell": coordinate}
                if sheet_name:
                    locator["sheet_name"] = sheet_name
                cells.append({"text": value, "bbox": None, "locator": locator})
        if any(values):
            rows.append(" | ".join(value for value in values if value))
    return "\n".join(rows), cells


def _pptx_slide_data(payload: bytes, slide_index: int) -> tuple[str, list[dict[str, Any]]]:
    root = ET.fromstring(payload)
    values = []
    for paragraph in (node for node in root.iter() if _local(node.tag) == "p"):
        value = "".join("".join(text.itertext()) for text in paragraph.iter() if _local(text.tag) == "t").strip()
        if value:
            values.append(value)
    if not values:
        values = ["".join(node.itertext()).strip() for node in root.iter() if _local(node.tag) == "t" and "".join(node.itertext()).strip()]
    blocks = [
        {
            "text": value,
            "bbox": None,
            "locator": {"kind": "slide_block", "label": f"幻灯片 {slide_index} · 文本块 {block_index}", "slide": slide_index, "block": block_index},
        }
        for block_index, value in enumerate(values, 1)
    ]
    return "\n".join(values), blocks


def _column_label(index: int) -> str:
    label = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def _text_page(text: str, page: int, locator: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = unicodedata.normalize("NFKC", text or "")
    return {
        "page": page,
        "text": normalized,
        "has_text": bool(normalized.strip()),
        "ocr_required": not bool(normalized.strip()),
        "low_text_confidence": 0 < len(normalized.strip()) < 20,
        "char_count": len(normalized),
        "blocks": [],
        "locator": locator or {"kind": "page", "label": f"第 {page} 页", "index": page},
    }


def extract_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".pdf":
        return extract_pdf(path)
    if path.suffix.lower() in {".txt", ".md"}:
        return extract_text_file(path)
    if path.suffix.lower() in {".docx", ".xlsx", ".pptx"}:
        return extract_ooxml(path)
    if path.suffix.lower() in {".doc", ".xls", ".ppt"}:
        raise ExtractionError(f"{path.suffix} 为旧版 Office 格式，请先转换为 .docx、.xlsx 或 .pptx")
    raise ExtractionError(f"不支持的文件格式: {path.suffix}")
