"""Four-block tender clauses on top of the existing page extraction.

Blocks: 资格要求, 评分要求, 要交的材料, 废标项.
This does not replace ``extract_requirements`` or the evidence matcher.
A clause is kept only when the sentence, the table header, or an open list
says so. A bare hit on 否决投标 / 不予受理 / 废标 is not enough.
Clauses without an original page number are listed under ``uncited`` and
cannot be PASS.
"""

from __future__ import annotations

import re
from typing import Any

BLOCK_ORDER: tuple[tuple[str, str], ...] = (
    ("qualification", "资格要求"),
    ("scoring", "评分要求"),
    ("materials", "要交的材料"),
    ("rejection", "废标项"),
)
BLOCK_LABELS = dict(BLOCK_ORDER)
_PAGE_KINDS = {"page", "page_region", "ocr_line"}
_CLOSED = ("。", "！", "？", "；", ";", "：", ":")
_HEADER_CELLS = {
    "序号",
    "审查项目",
    "审查标准",
    "审查内容",
    "评审项目",
    "评审标准",
    "评审因素",
    "评审内容",
    "分值",
    "评分标准",
    "证明材料",
    "证明文件",
    "提交材料",
    "是否废标",
    "是否否决",
    "是否无效",
    "处理",
    "资格条件",
    "条款",
    "情形",
}
_REJECTION_OUTCOME = re.compile(
    r"否决其?投标|不予受理|废标|无效投标|投标无效|无效响应|响应无效|作无效处理|"
    r"按无效|视为无效|资格审查不合格|取消投标资格|不得参加本次|应予(以)?废标"
)
_NEGATED_REJECTION = re.compile(
    r"不作为[^。]{0,30}(否决|废标|无效)"
    r"|不属于[^。]{0,20}(废标|无效|否决)"
    r"|不构成[^。]{0,20}(废标|无效|否决)"
    r"|不因此[^。]{0,16}(废标|否决|无效)"
    r"|不得仅因[^。]{0,30}(否决|废标|无效)"
    r"|不(予)?否决(其)?投标"
    r"|不予废标"
    r"|不视为无效"
)
_REJECTION_LEAD = re.compile(r"有下列|出现下列|存在下列|下列情况之一|下列情形之一|属无效|应予(以)?废标")
_ITEM_START = re.compile(
    r"^\s*(?:[（(]\d+[）)]|\d+[、.．]|[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+、)"
)
_CHILD_ITEM = re.compile(r"^\s*[（(]")
_CHAPTER_LINE = re.compile(r"^\s*第[0-9一二三四五六七八九十]+[章节篇]")
_CLOCK = re.compile(r"\d+\s*时\s*\d+\s*分|\d+\s*分钟")
_MATERIALS_LEAD = re.compile(r"响应文件包括|投标文件包括|包括下列(?:内容|文件|材料)|应提交下列|须提交下列")
_NOISE = re.compile(r"[{}]|function\s|var\s|document\.|@media|font-size|background(?:-color)?:")
_SECTION_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rejection", ("废标", "无效响应", "无效投标", "否决投标", "投标无效", "响应无效")),
    ("scoring", ("评分标准", "评分办法", "评审办法", "综合评分", "评审因素")),
    ("materials", ("响应文件组成", "投标文件组成", "应提交的材料", "资格证明材料", "要交的材料")),
    ("qualification", ("资格条件", "资格要求", "供应商资格", "投标人资格", "申请人的资格", "资格审查")),
)


def empty_tender_blocks() -> dict[str, Any]:
    return {
        "audit_status": "pending_audit",
        "product_pass": False,
        "blocks": {
            key: {"label": label, "items": []}
            for key, label in BLOCK_ORDER
        },
        "uncited": [],
    }


def extract_tender_blocks(pages: list[dict[str, Any]], filename: str | None = None) -> dict[str, Any]:
    """Group tender clauses into four blocks. Never emits PASS."""
    events = _events(pages)
    clauses = _close_cross_page(events)
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key, _label in BLOCK_ORDER}
    uncited: list[dict[str, Any]] = []
    section: str | None = None
    list_mode: str | None = None
    for clause in clauses:
        if clause["kind"] == "heading":
            found = _section_of(clause["text"])
            section = found
            list_mode = None
            continue
        text = clause["text"]
        if not _keep(text):
            continue
        if clause["kind"] == "item" and not _CHILD_ITEM.match(text) and _lead_kind(text) is None and not _materials_lead(text):
            list_mode = None
        lead = _lead_kind(text)
        if lead == "rejection":
            list_mode = "rejection"
        elif lead == "suppress":
            list_mode = "suppress"
        elif _materials_lead(text):
            list_mode = "materials"
        active_mode = list_mode
        blocks = _classify(clause, section, active_mode)
        if clause["kind"] == "paragraph" and lead is None:
            list_mode = None
        elif lead is None and clause["kind"] == "item":
            list_mode = active_mode
        else:
            list_mode = active_mode
        if not blocks:
            continue
        for block in BLOCK_LABELS:
            if block not in blocks:
                continue
            item = _item(block, clause, filename)
            if item["pages"]:
                grouped[block].append(item)
            else:
                uncited.append(item)
    result = empty_tender_blocks()
    for key, _label in BLOCK_ORDER:
        result["blocks"][key]["items"] = _dedupe(grouped[key])
    result["uncited"] = _dedupe(uncited)
    _assign_ids(result)
    return sanitize_tender_blocks(result)


def sanitize_tender_blocks(payload: dict[str, Any]) -> dict[str, Any]:
    """Force pending_audit, product_pass false, and no PASS without a real page."""
    result = empty_tender_blocks()
    seen_uncited: set[tuple[str, str]] = set()
    source_blocks = payload.get("blocks") if isinstance(payload, dict) else None
    if not isinstance(source_blocks, dict):
        source_blocks = {}
    for key, label in BLOCK_ORDER:
        raw_items = source_blocks.get(key, {})
        items = raw_items.get("items") if isinstance(raw_items, dict) else raw_items
        if not isinstance(items, list):
            items = []
        kept: list[dict[str, Any]] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            item = _force_status(raw, label, key)
            if item["pages"]:
                kept.append(item)
            else:
                marker = (item["block"], item["quote"])
                if marker not in seen_uncited:
                    seen_uncited.add(marker)
                    result["uncited"].append(item)
        result["blocks"][key]["items"] = kept
    extra = payload.get("uncited") if isinstance(payload, dict) else None
    if isinstance(extra, list):
        for raw in extra:
            if not isinstance(raw, dict):
                continue
            block = raw.get("block") if raw.get("block") in BLOCK_LABELS else "qualification"
            item = _force_status(raw, BLOCK_LABELS[block], block)
            item["pages"] = []
            item["page"] = None
            marker = (item["block"], item["quote"])
            if marker not in seen_uncited:
                seen_uncited.add(marker)
                result["uncited"].append(item)
    _assign_ids(result)
    return result


def _events(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    index = 0
    while index < len(pages):
        office, consumed = _office_table(pages, index)
        if office:
            events.extend(office)
            index = consumed
            continue
        page = pages[index] if isinstance(pages[index], dict) else {}
        pages_on = _original_pages(page)
        locator = page.get("locator") if isinstance(page.get("locator"), dict) else None
        structured = _structured_rows(page)
        if structured:
            for headers, cells in structured:
                events.append(_event("table_row", _row_text(headers, cells), pages_on, locator, headers, cells))
        text = str(page.get("text") or "")
        if not structured:
            text = _consume_flat_tables(text, pages_on, locator, events)
        for kind, piece in _split_prose(text):
            events.append(_event(kind, piece, pages_on, locator, None, None))
        index += 1
    return events


def _event(
    kind: str,
    text: str,
    pages_on: list[int],
    locator: dict[str, Any] | None,
    headers: list[str] | None,
    cells: list[str] | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": " ".join(text.split()),
        "pages": list(pages_on),
        "locator": dict(locator) if locator else None,
        "headers": headers,
        "cells": cells,
        "cross_page": False,
    }


def _close_cross_page(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for event in events:
        if event["kind"] == "heading":
            if pending:
                closed.append(pending)
                pending = None
            closed.append(event)
            continue
        if pending and _can_continue(pending, event):
            pending["text"] = f"{pending['text']}{event['text']}"
            for number in event["pages"]:
                if number not in pending["pages"]:
                    pending["pages"].append(number)
            pending["cross_page"] = len(pending["pages"]) > 1 or pending.get("cross_page")
            if _closed_text(pending["text"]):
                closed.append(pending)
                pending = None
            continue
        if pending:
            closed.append(pending)
            pending = None
        if event["kind"] == "table_row" or _closed_text(event["text"]):
            closed.append(event)
        else:
            pending = event
    if pending:
        closed.append(pending)
    return closed


def _can_continue(pending: dict[str, Any], event: dict[str, Any]) -> bool:
    if pending["kind"] == "table_row" or event["kind"] in {"table_row", "heading", "item"}:
        return False
    if pending["text"].rstrip().endswith(("：", ":")):
        return False
    if _closed_text(pending["text"]):
        return False
    nxt = event["text"]
    if _REJECTION_LEAD.search(nxt) or _section_of(nxt):
        return False
    if "，" not in pending["text"] and len(_compact(pending["text"])) <= 24 and len(_compact(nxt)) > 8:
        return False
    left = pending["pages"]
    right = event["pages"]
    return not (left and right and right[0] != left[-1] + 1 and right[0] != left[-1])


def _closed_text(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith(_CLOSED)


def _classify(clause: dict[str, Any], section: str | None, list_mode: str | None) -> set[str]:
    if clause["kind"] == "table_row":
        return _classify_row(clause.get("headers") or [], clause.get("cells") or [], clause["text"])
    text = clause["text"]
    blocks: set[str] = set()
    if list_mode == "suppress":
        pass
    elif (list_mode == "rejection" and not _negated(text)) or _is_rejection(text):
        blocks.add("rejection")
    inherited = None if list_mode in {"rejection", "suppress"} else section
    if _is_scoring(text, inherited):
        blocks.add("scoring")
    if (list_mode == "materials" and _CHILD_ITEM.match(text)) or _is_materials(text, inherited):
        blocks.add("materials")
    if _is_qualification(text, inherited):
        blocks.add("qualification")
    if "scoring" in blocks and "rejection" in blocks and _negated(text):
        blocks.discard("rejection")
    return blocks


def _classify_row(headers: list[str], cells: list[str], text: str) -> set[str]:
    blocks: set[str] = set()
    explicit_keep = False
    pairs = list(zip(headers, cells))
    for header, cell in pairs:
        name = _compact(header)
        value = _compact(cell)
        if not value or value in {"序号"}:
            continue
        if any(token in name for token in ("是否废标", "是否否决", "是否无效")):
            if value in {"否", "不", "无", "不是"} or value.startswith("不") or _negated(cell):
                explicit_keep = True
                continue
            if value in {"是", "废标", "无效", "否决"} or value.startswith("是") or _is_rejection(cell):
                blocks.add("rejection")
            continue
        if any(token in name for token in ("废标情形", "无效情形", "否决情形", "处理")):
            if value in {"否", "无", "不"} or _negated(cell):
                continue
            if _is_rejection(cell) or any(token in name for token in ("废标", "无效", "否决")):
                blocks.add("rejection")
        if any(token in name for token in ("分值", "评分", "评审标准", "评审因素", "评审项目")) and (
            _is_scoring(cell, "scoring") or "分值" in name
        ):
            blocks.add("scoring")
        if any(token in name for token in ("证明材料", "证明文件", "提交材料", "审查标准")) and re.search(
            r"提供|提交|复印件|原件|盖章", cell
        ):
            blocks.add("materials")
        if any(token in name for token in ("资格", "审查项目")) and _is_qualification(cell, "qualification"):
            blocks.add("qualification")
    if not blocks and not explicit_keep:
        blocks = _classify({"kind": "paragraph", "text": text}, None, None)
    if explicit_keep:
        blocks.discard("rejection")
    return blocks


def _is_rejection(text: str) -> bool:
    if _cross_reference_only(text):
        return False
    parts = re.split(r"[，,；;]", text)
    for part in parts:
        if _REJECTION_OUTCOME.search(part) and not _negated(part):
            return True
    return False


def _negated(text: str) -> bool:
    return _NEGATED_REJECTION.search(text) is not None


def _cross_reference_only(text: str) -> bool:
    if not re.search(r"详见|参见|见第|见本章", text):
        return False
    return re.search(r"否则|有下列|应当|必须|未按|不具备", text) is None


def _lead_kind(text: str) -> str | None:
    if not _REJECTION_LEAD.search(text) and "不作为" not in text and "不因此" not in text:
        return None
    if _negated(text) and not _is_rejection(text):
        return "suppress"
    if _is_rejection(text) or (_REJECTION_LEAD.search(text) and re.search(r"废标|无效|否决", text) and not _negated(text)):
        return "rejection"
    if _negated(text):
        return "suppress"
    return None


def _is_scoring(text: str, section: str | None) -> bool:
    if re.search(r"不作为评分|不计入评分|不予记分", text):
        return False
    clockless = _CLOCK.sub("", text)
    if re.search(r"\d+\s*分(?!体|别|布|析|公司)|扣\s*\d+|计分|满分|打分|不得分", clockless):
        return True
    return section == "scoring" and re.search(r"评审因素|评分标准|得分", text) is not None and len(text) <= 80


def _is_materials(text: str, section: str | None) -> bool:
    if re.search(r"未提供不(计分|得分)", text) and not re.search(r"须提供|应提供|应提交|须提交", text):
        return False
    if re.search(r"须提供|应提供|应提交|须提交|证明材料|复印件|加盖公章|资格证明文件", text):
        return True
    return bool(
        section == "materials"
        and _ITEM_START.match(text)
        and len(text) <= 32
        and re.search(r"函|委托书|偏离表|报价表|证明|执照|证书|材料|身份证明", text)
    )


def _materials_lead(text: str) -> bool:
    return _MATERIALS_LEAD.search(text) is not None


def _is_qualification(text: str, section: str | None) -> bool:
    if re.search(r"(?:供应商|投标人|申请人).{0,12}资格(?:条件|要求)|资格(?:条件|要求)\s*[:：]|特定资格|基本资格|政府采购法》第二十二条|须具备|应具备|应当符合", text):
        return True
    return bool(
        section == "qualification"
        and re.search(r"应当符合|必须具备|必须是|须具备|须具有|须满足|具备|具有|不得参加", text)
    )


def _section_of(text: str) -> str | None:
    if len(text) > 40:
        return None
    compact = _compact(text)
    for name, keys in _SECTION_KEYS:
        if any(key in compact for key in keys):
            return name
    return None


def _keep(text: str) -> bool:
    compact = _compact(text)
    return not (len(compact) < 4 or _NOISE.search(text))


def _item(block: str, clause: dict[str, Any], filename: str | None) -> dict[str, Any]:
    pages = [number for number in clause["pages"] if isinstance(number, int) and number >= 1]
    locator = _locator(clause, pages)
    status = "NEEDS_REVIEW" if pages or locator else "UNKNOWN"
    reason = None if pages else _uncited_reason(locator)
    detection = "table" if clause["kind"] == "table_row" else "clause"
    if len(pages) > 1 or clause.get("cross_page"):
        detection = "cross_page"
    quote = clause["text"][:400]
    return {
        "clause_id": "",
        "block": block,
        "label": BLOCK_LABELS[block],
        "summary": quote[:80],
        "quote": quote,
        "pages": pages,
        "page": pages[0] if pages else None,
        "status": status,
        "locator": locator,
        "detection": detection,
        "filename": filename or "",
        "uncited_reason": reason,
        "audit_status": "pending_audit",
    }


def _locator(clause: dict[str, Any], pages: list[int]) -> dict[str, Any] | None:
    locator = dict(clause["locator"]) if clause.get("locator") else None
    if not pages:
        return locator
    label = f"第 {pages[0]} 页" if len(pages) == 1 else f"第 {pages[0]}-{pages[-1]} 页"
    if locator is None:
        locator = {"kind": "page", "index": pages[0]}
    locator["label"] = label
    locator["pages"] = pages
    return locator


def _uncited_reason(locator: dict[str, Any] | None) -> str:
    if not locator:
        return "这条条款没有可用的原文页码。"
    kind = str(locator.get("kind") or "missing")
    label = str(locator.get("label") or "无定位")
    if kind not in _PAGE_KINDS:
        return f"来源定位是{kind}（{label}），文件没有给出原文页码，不能把段落号或行号当成页码。"
    return "这条条款没有可用的原文页码。"


def _force_status(raw: dict[str, Any], label: str, block: str) -> dict[str, Any]:
    pages = [number for number in raw.get("pages") or [] if isinstance(number, int) and not isinstance(number, bool) and number >= 1]
    locator = raw.get("locator") if isinstance(raw.get("locator"), dict) else None
    item = {
        "clause_id": str(raw.get("clause_id") or ""),
        "block": block,
        "label": label,
        "summary": str(raw.get("summary") or raw.get("quote") or "")[:80],
        "quote": str(raw.get("quote") or raw.get("summary") or "")[:400],
        "pages": pages,
        "page": pages[0] if pages else None,
        "status": "NEEDS_REVIEW" if pages or locator else "UNKNOWN",
        "locator": locator,
        "detection": raw.get("detection") or "clause",
        "filename": str(raw.get("filename") or ""),
        "uncited_reason": None if pages else (raw.get("uncited_reason") or _uncited_reason(locator)),
        "audit_status": "pending_audit",
    }
    if item["status"] == "PASS":
        item["status"] = "NEEDS_REVIEW" if pages else "UNKNOWN"
    return item


def _assign_ids(result: dict[str, Any]) -> None:
    counter = 1
    for key, _label in BLOCK_ORDER:
        for item in result["blocks"][key]["items"]:
            item["clause_id"] = f"TB-{counter:04d}"
            item["status"] = "NEEDS_REVIEW"
            item["audit_status"] = "pending_audit"
            counter += 1
    for item in result["uncited"]:
        item["clause_id"] = f"TB-{counter:04d}"
        if item["status"] not in {"UNKNOWN", "NEEDS_REVIEW"}:
            item["status"] = "UNKNOWN" if not item.get("locator") else "NEEDS_REVIEW"
        item["pages"] = []
        item["page"] = None
        item["audit_status"] = "pending_audit"
        counter += 1
    result["audit_status"] = "pending_audit"
    result["product_pass"] = False


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, tuple[int, ...], str]] = set()
    kept: list[dict[str, Any]] = []
    for item in items:
        key = (item["block"], tuple(item["pages"]), _compact(item["quote"]))
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return kept


def _original_pages(page: dict[str, Any]) -> list[int]:
    locator = page.get("locator") if isinstance(page.get("locator"), dict) else {}
    kind = locator.get("kind")
    if kind not in (None, *_PAGE_KINDS):
        return []
    number = page.get("page", locator.get("page"))
    if isinstance(number, int) and not isinstance(number, bool) and number >= 1:
        return [number]
    return []


def _office_table(pages: list[dict[str, Any]], start: int) -> tuple[list[dict[str, Any]], int]:
    first = pages[start] if isinstance(pages[start], dict) else {}
    locator = first.get("locator") if isinstance(first.get("locator"), dict) else {}
    if locator.get("kind") != "table_cell":
        return [], start
    table_id = locator.get("table")
    rows: dict[int, list[tuple[int, str, dict[str, Any]]]] = {}
    index = start
    while index < len(pages):
        page = pages[index] if isinstance(pages[index], dict) else {}
        cell = page.get("locator") if isinstance(page.get("locator"), dict) else {}
        if cell.get("kind") != "table_cell" or cell.get("table") != table_id:
            break
        row_index = int(cell.get("row") or 0)
        column_index = int(cell.get("column") or 0)
        rows.setdefault(row_index, []).append((column_index, str(page.get("text") or ""), cell))
        index += 1
    if index == start:
        return [], start
    ordered = [rows[key] for key in sorted(rows)]
    header_cells = [text for _col, text, _loc in sorted(ordered[0], key=lambda item: item[0])]
    events: list[dict[str, Any]] = []
    data_rows = ordered[1:] if len(ordered) > 1 else ordered
    for row in data_rows:
        sorted_row = sorted(row, key=lambda item: item[0])
        cells = [text for _col, text, _loc in sorted_row]
        sample = sorted_row[0][2]
        events.append(_event("table_row", _row_text(header_cells, cells), [], sample, header_cells, cells))
    return events, index


def _structured_rows(page: dict[str, Any]) -> list[tuple[list[str], list[str]]]:
    rows: list[tuple[list[str], list[str]]] = []
    for table in page.get("tables") or []:
        grid = _grid(table)
        if len(grid) < 2:
            continue
        headers = grid[0]
        for cells in grid[1:]:
            if any(_compact(cell) for cell in cells):
                rows.append((headers, cells))
    markdown = str(page.get("markdown") or "")
    if not rows and markdown:
        for grid in _markdown_tables(markdown):
            headers = grid[0]
            for cells in grid[1:]:
                rows.append((headers, cells))
    return rows


def _grid(table: Any) -> list[list[str]]:
    if isinstance(table, dict):
        header = table.get("header") or table.get("headers") or table.get("columns")
        body = table.get("rows") or table.get("data") or table.get("cells")
        grid: list[list[str]] = []
        if isinstance(header, list) and header and not isinstance(header[0], (list, tuple)):
            grid.append([_cell_text(cell) for cell in header])
        if isinstance(body, list):
            for row in body:
                if isinstance(row, (list, tuple)):
                    grid.append([_cell_text(cell) for cell in row])
                elif isinstance(row, dict):
                    grid.append([_cell_text(value) for value in row.values()])
        return grid
    if isinstance(table, (list, tuple)) and table and isinstance(table[0], (list, tuple)):
        return [[_cell_text(cell) for cell in row] for row in table]
    return []


def _markdown_tables(text: str) -> list[list[list[str]]]:
    tables: list[list[list[str]]] = []
    buffer: list[str] = []
    for line in text.splitlines():
        if line.count("|") >= 2:
            buffer.append(line)
            continue
        if len(buffer) >= 2:
            parsed = _parse_markdown(buffer)
            if parsed:
                tables.append(parsed)
        buffer = []
    if len(buffer) >= 2:
        parsed = _parse_markdown(buffer)
        if parsed:
            tables.append(parsed)
    return tables


def _parse_markdown(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if re.match(r"^\s*\|?\s*:?-{3,}", line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append(cells)
    return rows if len(rows) >= 2 else []


def _consume_flat_tables(
    text: str,
    pages_on: list[int],
    locator: dict[str, Any] | None,
    events: list[dict[str, Any]],
) -> str:
    lines = text.splitlines()
    skip = set()
    index = 0
    while index < len(lines):
        headers, _row_end = _flat_table_at(lines, index)
        if not headers:
            index += 1
            continue
        width = len(headers)
        cursor = index + width
        body: list[list[str]] = []
        while cursor + width <= len(lines):
            cells = [lines[cursor + offset].strip() for offset in range(width)]
            if not cells[0] or not re.fullmatch(r"\d{1,3}", _compact(cells[0])):
                break
            if any(_section_of(cell) for cell in cells):
                break
            if _compact(headers[-1]) == "分值" and not re.fullmatch(r"\d{1,3}(?:\.\d+)?", _compact(cells[-1] if cells else "")):
                break
            body.append(cells)
            cursor += width
        if body:
            for cells in body:
                events.append(_event("table_row", _row_text(headers, cells), pages_on, locator, headers, cells))
            skip.update(range(index, cursor))
            index = cursor
            continue
        index += 1
    if not skip:
        return text
    return "\n".join(line for number, line in enumerate(lines) if number not in skip)


def _flat_table_at(lines: list[str], start: int) -> tuple[list[str], int]:
    headers: list[str] = []
    index = start
    while index < len(lines) and len(headers) < 6:
        compact = _compact(lines[index])
        if compact not in _HEADER_CELLS:
            break
        headers.append(lines[index].strip())
        index += 1
    if len(headers) < 2 or "序号" not in {_compact(header) for header in headers}:
        return [], start
    return headers, index


def _split_prose(text: str) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    buffer_kind = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer_kind, buffer
        if buffer:
            pieces.append((buffer_kind, " ".join(buffer)))
        buffer_kind = ""
        buffer = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line or _NOISE.search(line):
            flush()
            continue
        if _CHAPTER_LINE.match(line) or (len(line) <= 40 and "，" not in line and "。" not in line and _section_of(line)):
            flush()
            pieces.append(("heading", line))
            continue
        kind = "item" if _ITEM_START.match(line) else "paragraph"
        if buffer and kind == "item":
            flush()
        if not buffer:
            buffer_kind = kind
        buffer.append(line)
        if line.endswith(_CLOSED) and kind == "item":
            flush()
    flush()
    return pieces


def _row_text(headers: list[str], cells: list[str]) -> str:
    parts = []
    for header, cell in zip(headers, cells):
        value = " ".join(cell.split())
        if not value:
            continue
        name = " ".join(header.split())
        parts.append(f"{name}：{value}" if name else value)
    if len(cells) > len(headers):
        parts.extend(" ".join(cell.split()) for cell in cells[len(headers):] if cell.strip())
    return " ".join(parts)


def _cell_text(cell: Any) -> str:
    if isinstance(cell, str):
        return cell.strip()
    if isinstance(cell, dict):
        return str(cell.get("text") or cell.get("value") or "").strip()
    return str(cell or "").strip()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
