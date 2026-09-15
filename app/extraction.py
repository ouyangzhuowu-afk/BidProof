from pathlib import Path
from typing import Any
import logging
import os
import unicodedata
import re
import zipfile
import xml.etree.ElementTree as ET

from .ocr import (
    OCRAdapter,
    OCRResult,
    OCRUnavailable,
    get_cloud_ocr_adapter,
    get_local_ocr_adapter,
    get_ocr_adapter,
)
from .ocr_privacy import (
    REDACTION_VERSION,
    classify_page_text,
    egress_allowed_for_cloud,
    egress_mode,
    merge_ocr_texts,
    redact_png_bytes,
    should_escalate_to_cloud,
)


logger = logging.getLogger("bidproof.extraction")


class ExtractionError(RuntimeError):
    pass


def _ocr_tiles_enabled() -> bool:
    return os.getenv("BID_OCR_TILE_ENABLED", "1").strip().lower() in {"1", "true", "yes"}


def _tile_count() -> int:
    try:
        return max(2, min(int(os.getenv("BID_OCR_TILE_STRIPS", "3")), 6))
    except ValueError:
        return 3


def _needs_page_tiling(result: OCRResult, page_height: float) -> bool:
    if not _ocr_tiles_enabled():
        return False
    if result.confidence is not None and result.confidence < 0.5:
        return True
    # Local engines with line boxes already covered the page — skip strip OCR.
    if result.lines and result.confidence is not None and result.confidence >= 0.5:
        return False
    return page_height >= 700 and len(result.text.strip()) < 500


def _blocks_from_ocr_result(
    result: OCRResult,
    *,
    page_number: int,
    page_rect: list[float],
    scale: float = 1.5,
) -> list[dict[str, Any]]:
    """Prefer per-line OCR boxes so quote matching can localize after OCR."""
    if not result.lines:
        return [
            {
                "text": result.text,
                "bbox": page_rect,
                "locator": {
                    "kind": "page",
                    "label": f"第 {page_number} 页",
                    "page": page_number,
                    "index": page_number,
                    "bbox": page_rect,
                },
            }
        ]
    blocks: list[dict[str, Any]] = []
    for line_index, line in enumerate(result.lines, 1):
        bbox = None
        if line.bbox is not None:
            x0, y0, x1, y1 = line.bbox
            # OCR boxes are in rendered image pixels; convert back to PDF points.
            bbox = [x0 / scale, y0 / scale, x1 / scale, y1 / scale]
        blocks.append(
            {
                "text": line.text,
                "bbox": bbox,
                "locator": {
                    "kind": "ocr_line",
                    "label": f"第 {page_number} 页 · OCR行 {line_index}",
                    "page": page_number,
                    "line": line_index,
                    "bbox": bbox,
                },
            }
        )
    return blocks


def ocr_page_image(page: Any, adapter: OCRAdapter, page_number: int, scale: float = 1.5) -> OCRResult:
    """OCR a PDF page; optionally stitch vertical strips when the full-page pass looks truncated."""
    import fitz

    matrix = fitz.Matrix(scale, scale)
    full = adapter.extract(page.get_pixmap(matrix=matrix, alpha=False).tobytes("png"), page_number)
    if not _needs_page_tiling(full, float(page.rect.height)):
        return full

    strips = _tile_count()
    rect = page.rect
    overlap = rect.height * 0.04
    band = rect.height / strips
    parts: list[str] = []
    confidences: list[float] = []
    line_acc = list(full.lines)
    for index in range(strips):
        y0 = max(rect.y0, rect.y0 + index * band - (overlap if index else 0))
        y1 = min(rect.y1, rect.y0 + (index + 1) * band + (overlap if index < strips - 1 else 0))
        clip = fitz.Rect(rect.x0, y0, rect.x1, y1)
        try:
            tile = adapter.extract(page.get_pixmap(matrix=matrix, clip=clip, alpha=False).tobytes("png"), page_number)
        except OCRUnavailable:
            continue
        if tile.text.strip():
            parts.append(tile.text.strip())
        if tile.confidence is not None:
            confidences.append(tile.confidence)
        line_acc.extend(tile.lines)
    if not parts:
        return full
    stitched = "\n".join(parts)
    if len(stitched) <= len(full.text):
        return full
    confidence = sum(confidences) / len(confidences) if confidences else full.confidence
    provider = full.provider if "+tiles" in full.provider else f"{full.provider}+tiles"
    return OCRResult(text=stitched, confidence=confidence, provider=provider, lines=tuple(line_acc))


def _maybe_escalate_cloud(
    page: Any,
    page_number: int,
    local: OCRResult,
    scale: float = 1.5,
) -> tuple[OCRResult, dict[str, Any]]:
    """T1: escalate only after image redaction; never send original pixels."""
    meta: dict[str, Any] = {
        "ocr_egress": "none",
        "ocr_egress_mode": egress_mode(),
        "ocr_redaction_version": REDACTION_VERSION,
        "ocr_escalation_reason": "",
        "ocr_page_types": [],
    }
    risk = classify_page_text(local.text)
    meta["ocr_page_types"] = list(risk.page_types)
    escalate, reason = should_escalate_to_cloud(
        local_text=local.text,
        local_confidence=local.confidence,
        risk=risk,
        page_height_pt=float(page.rect.height),
    )
    meta["ocr_escalation_reason"] = reason
    if not escalate:
        if reason.startswith("blocked:"):
            meta["ocr_egress"] = "blocked_sensitive_page"
        return local, meta

    cloud = get_cloud_ocr_adapter()
    if not cloud.enabled:
        meta["ocr_egress"] = "cloud_unavailable"
        return local, meta

    import fitz

    matrix = fitz.Matrix(scale, scale)
    original_png = page.get_pixmap(matrix=matrix, alpha=False).tobytes("png")
    redacted = redact_png_bytes(original_png, local.lines)
    meta["ocr_redaction_sha256"] = redacted.content_sha256
    meta["ocr_redaction_masked_lines"] = redacted.masked_line_count
    if not redacted.clean:
        meta["ocr_egress"] = "blocked_residual_pii"
        meta["ocr_redaction_residuals"] = redacted.residual_findings
        logger.info(
            "ocr_escalation_blocked_residual",
            extra={"page": page_number, "residuals": redacted.residual_findings},
        )
        return local, meta

    try:
        cloud_result = cloud.extract(redacted.image_bytes, page_number)
    except OCRUnavailable:
        meta["ocr_egress"] = "cloud_failed"
        return local, meta

    merged = merge_ocr_texts(local.text, cloud_result.text)
    used_cloud = len(cloud_result.text.strip()) > len(local.text.strip())
    if used_cloud:
        meta["ocr_egress"] = "redacted_cloud" if egress_mode() == "redacted_only" else "vpc"
        provider = f"{local.provider}+redacted:{cloud_result.provider}"
        confidence = cloud_result.confidence if cloud_result.confidence is not None else local.confidence
        return (
            OCRResult(text=merged, confidence=confidence, provider=provider, lines=local.lines),
            meta,
        )
    meta["ocr_egress"] = "redacted_cloud_unused"
    return local, meta


def extract_pdf(path: Path, ocr_adapter: OCRAdapter | None = None) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise ExtractionError("PyMuPDF is required to extract PDF text") from exc

    pages: list[dict[str, Any]] = []
    if ocr_adapter is not None:
        adapter = ocr_adapter
    elif egress_allowed_for_cloud():
        adapter = get_local_ocr_adapter()
        if not adapter.enabled:
            adapter = get_ocr_adapter()
    else:
        adapter = get_ocr_adapter()
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
                    result = ocr_page_image(page, adapter, index + 1)
                    if egress_allowed_for_cloud():
                        result, egress_meta = _maybe_escalate_cloud(page, index + 1, result)
                        page_data.update(egress_meta)
                    else:
                        page_data["ocr_egress"] = "none"
                        page_data["ocr_egress_mode"] = egress_mode()
                    page_data["text"] = result.text
                    page_data["has_text"] = True
                    page_data["ocr_status"] = "EXTRACTED"
                    page_data["ocr_provider"] = result.provider
                    page_data["ocr_confidence"] = result.confidence
                    page_data["char_count"] = len(result.text)
                    page_data["blocks"] = _blocks_from_ocr_result(result, page_number=index + 1, page_rect=list(page.rect))
                    if result.confidence is not None and result.confidence < 0.5:
                        page_data["low_text_confidence"] = True
                    try:
                        from . import observability

                        observability.record_ocr_page(
                            provider=result.provider,
                            egress=str(page_data.get("ocr_egress") or "none"),
                        )
                    except Exception:  # noqa: BLE001 — metrics must never break extraction
                        pass
                except OCRUnavailable:
                    page_data["ocr_status"] = "FAILED"
                    page_data["ocr_error"] = "OCR_UNAVAILABLE"
                    page_data["low_text_confidence"] = True
                    page_data["ocr_egress"] = "none"
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
