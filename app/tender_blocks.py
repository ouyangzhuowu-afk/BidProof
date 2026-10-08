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
    r"否决其?投标|否决其报价|被否决|不予受理|废标|"
    r"无效投标|投标无效|投标文件无效|其投标无效|投标被拒绝|"
    r"被认定为投标无效|认定为投标无效|"
    r"无效响应|响应无效|响应文件无效|其响应无效|"
    r"作无效报价处理|无效报价|作无效处理|按无效|视为无效|报价无效|"
    r"未(?:作出|做出|做)?实质性响应|没有(?:作出|做出|做)?实质性响应|"
    r"非实质性响应|资格审查不合格|取消投标资格|应予(以)?废标"
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
_REJECTION_LEAD = re.compile(
    r"有下列|出现下列|存在下列|下列情况之一|下列情形之一|以下情况之一|以下情形之一|属无效|应予(以)?废标"
)
_ITEM_START = re.compile(
    r"^\s*(?:"
    r"[（(]\d+[）)]|\d+[)）]|\d+[、.．]"
    r"|[（(][一二三四五六七八九十]+[）)]|[一二三四五六七八九十]+、"
    r")"
)
# 带括号、顿号、右括号的列举，以及「1.」这种清单项。单独的「26.澄清」不算子项。
_CHILD_ITEM = re.compile(
    r"^\s*(?:"
    r"[（(]\d+[）)]|[（(][一二三四五六七八九十]+[）)]"
    r"|\d+[)）、]"
    r"|[一二三四五六七八九十]+、"
    r"|\d+[.．](?!\d)"
    r")"
)
_BARE_SECTION_TITLE = re.compile(r"^\d+[.．]\s*[\u3400-\u9fff]{1,8}$")
_CHAPTER_LINE = re.compile(r"^\s*第[0-9一二三四五六七八九十]+[章节篇]")
_CLOCK = re.compile(r"\d+\s*[时点]\s*\d+\s*分|\d+\s*分钟")
_MATERIALS_LEAD = re.compile(
    r"响应文件包括|投标文件包括|报价文件包括|"
    r"响应文件由|投标文件由|报价文件由|文件组成|"
    r"包括下列(?:内容|文件|材料)|应提交下列|须提交下列|包括以下|包括但不限于"
)
_NOISE = re.compile(r"[{}]|function\s|var\s|document\.|@media|font-size|background(?:-color)?:")
# 「第N页共M页」 and 「第N页/共M页」, including spaces and a fullwidth slash.
_PAGE_FOOTER = re.compile(r"第\s*\d+\s*页\s*[/／]?\s*共\s*\d+\s*页")
_PAGE_FOOTER_NUM = re.compile(r"第\s*(\d+)\s*页\s*[/／]?\s*共\s*(\d+)\s*页")
# 「得分」单独出现只说明有分数，不说明这一句在打分。排序、通知、方法定义另判。
_SCORE_CONTEXT = re.compile(r"分值|评分标准|评分办法|满分|加分|扣分|计分|打分|不得分|不计分")
_SCORE_AMOUNT = re.compile(r"\d+\s*分(?!体|别|布|析|公司|包|钟|部|项)|扣\s*\d+")
_SCORE_ASSIGNMENT = re.compile(
    r"得\s*\d+(?:\.\d+)?\s*分|扣\s*\d+(?:\.\d+)?\s*分|加\s*\d+(?:\.\d+)?\s*分|"
    r"不得分|不计分|得分\s*[=＝]"
)
_SCORE_INTRO = re.compile(r"满分(?:为)?\s*\d+\s*分[^。]{0,16}(?:细则|标准)[^。]{0,4}如下")
_SCORING_PROCESS = re.compile(
    r"推荐[^。]{0,24}(?:成交|中标)候选|确定成交|确定中标|评审报告|"
    r"告知[^。]{0,40}得分|公告[^。]{0,24}得分|"
    r"综合评分法[^。]{0,12}是指|"
    r"由高到低|由低到高|从高到低|顺序推荐|排列推荐|"
    r"按照[^。]{0,40}得分[^。]{0,24}(?:排序|推荐|确定)"
)
_ENTERPRISE_SIZE = re.compile(r"划型|大中小微型?企业划分|中小企业划型|统计上大中小")
_DEFINITION_NOTE = re.compile(r"[「“\"][^」”\"]{1,12}[」”\"]\s*是指")
_INFORMAL_MATERIAL = re.compile(
    r"(?:非正式|非书面|口头|宣传|参考|内部|未经[^。；;]{0,20}(?:发布|通知|公布))"
    r"[^。；;]{0,16}(?:资料|材料|信息|通知)"
)
_RESPONSE_FILE = re.compile(r"响应文件|投标文件|报价文件|申请文件")
_POST_AWARD = re.compile(
    r"合同履行|履行合同|签订合同后|合同签订后|成交后|中标后|履约期间|合同期内|合同执行|"
    r"拒绝[^。]{0,24}签(?:订)?(?:政府采购)?合同|重新开展"
)
_THIS_PROCUREMENT = re.compile(r"本次|本项目|该项目|该采购|政府采购|响应磋商|投标|磋商|同一合同项下")
# 拒绝签订之后不得再参加重新采购。合同履行中的普通限制不是这一类。
_REPROCUREMENT_BAR = re.compile(
    r"不得(?!不)[^。]{0,40}参加[^。]{0,48}重新(?:开展|组织|进行)"
    r"|拒绝[^。]{0,40}签(?:订)?[^。]{0,24}合同[^。]{0,80}不得(?!不)[^。]{0,32}参加"
)
# 不同投标人由同一单位或同一人编制、办理、转出，以及同类串通列举。
_COLLUSION = re.compile(
    r"不同(?:投标人|供应商|响应人)[^。；;]{0,100}"
    r"(?:同一(?:单位|人|个人|个单位|电子设备|账户)|异常一致|规律性差异|相互混装|"
    r"硬件信息相同|联系电话一致|细节错误一致)"
    r"|同一(?:单位|个人)[^。；;]{0,16}(?:编制|办理|转出|签字)"
)
_NON_REFUND = re.compile(r"(?:不予|不再|不得)退还")
_NON_REFUND_LIST = re.compile(r"有下列|下列情形|以下情形|情形之一|情况之一|以下任何一种|任何一种情况")
_REFUND_TIMETABLE = re.compile(r"个工作日内|及时退还|予以退还")
# 售价、报名和领取文件的时间地点不是资格条件。
_PROCUREMENT_ACCESS = re.compile(
    r"售价|工本费|报名时间|报名截止|登记时间|文件发售|"
    r"获取(?:招标|采购|磋商|响应)?文件(?:的)?(?:时间|地点|方式)|"
    r"购买(?:招标|采购|磋商)?文件"
)
_PROCUREMENT_HEADING = re.compile(
    r"^(?:[一二三四五六七八九十\d]+[、.．])?获取(?:招标|采购|磋商|响应)?文件$"
)
_BARE_NUMBERING = re.compile(
    r"(?:第)?\d+(?:\.\d+)*[、.．)）]?"
    r"|[（(]\d+[）)]"
    r"|[（(][一二三四五六七八九十]+[）)]"
    r"|[一二三四五六七八九十]+[、.．]"
)
_COMPLAINT = re.compile(r"质疑函|质疑事项|质疑人|提出质疑")
# 谁不能参加，是资格限制，不是已经递交的文件被否决。
_PARTICIPATION_LIMIT = re.compile(r"不得(?!不)(?:(?![。！？]).){0,48}(?:参加|组成联合体)")
# 响应文件本身被拒绝接收。单独的「拒收货物/服务」不算。
# 拒收必须是采购人作出的接收决定。密封风险里列举的「拒收、误放、遗漏」不是否决。
_DOCUMENT_REJECTION = re.compile(r"无效文件|不予接收")
_DOCUMENT_REFUSAL = re.compile(
    r"(?:将|予以|有权|可以|应当|应予|决定)拒收"
    r"(?:(?![。！？]).){0,24}(?:响应文件|投标文件|报价文件|申请文件)"
    r"|(?:响应文件|投标文件|报价文件|申请文件)"
    r"(?:(?![。！？]).){0,40}(?:将|予以|有权|可以|应当|应予|决定)拒收"
)
_NEGATED_DOCUMENT = re.compile(r"不视为无效文件|不属于无效文件|不作为无效文件|不得拒收|不予拒收|应当接收|应予接收")
# 条款自己已经给出投标结论时，提到质疑也不算质疑程序。
_BID_RULE_BESIDE_COMPLAINT = re.compile(
    r"被否决|报价无效|无效报价|按无效|应予(以)?废标|无效响应|响应无效|响应文件无效|"
    r"投标文件无效|作无效报价处理|非实质性响应|无效文件|不予接收|"
    r"无效投标|投标无效|投标被拒绝|认定为投标无效|否决其?投标|否决其报价|"
    r"资格审查不合格|取消投标资格|"
    r"未(?:作出|做出|做)?实质性响应|没有(?:作出|做出|做)?实质性响应|"
    r"不得(?!不)(?:(?![。！？]).){0,48}(?:参加|组成联合体)"
)
_INLINE_MARK = re.compile(
    r"[（(]\d{1,2}[）)]|[（(][一二三四五六七八九十]+[）)]|"
    r"(?<!\d)\d{1,2}[)）]|(?<!\d)\d{1,2}[、．]|(?<!\d)\d{1,2}\.(?!\d)"
)
_FRONT_HEADER_LINE = re.compile(r"^(?:序号|条款号|内容|说明|栏目|编列内容|内|容|说|明)$")
_FRONT_PREFIX = re.compile(
    r"^(?:(?:供应商|投标人|磋商)须知)+(?:前附表)(?:序号|条款号|内容|说明|栏目)*"
    r"|^(?:序号内容|序号说明|条款号内容|内容说明)"
)
_TOC_LINE = re.compile(r"[\.．·…]{4,}\s*\d+\s*$")
_EMAIL = re.compile(r"@|邮箱|电子邮箱|电子邮件")
_QUOTE_SOFT_CAP = 400
_QUOTE_HARD_CAP = 1200
_HEADER_LABELS = (
    "序号",
    "项目",
    "分值",
    "比例",
    "描述",
    "是否客观",
    "评审因素",
    "评分标准",
    "内容",
    "说明",
    "适用对象",
    "栏目",
)
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
        "printed_page_offset": None,
        "printed_page_total": None,
        "blocks": {
            key: {"label": label, "items": []}
            for key, label in BLOCK_ORDER
        },
        "uncited": [],
    }


def extract_tender_blocks(pages: list[dict[str, Any]], filename: str | None = None) -> dict[str, Any]:
    """Group tender clauses into four blocks. Never emits PASS."""
    printed = printed_page_facts(pages)
    events = _drop_loose_fragments(_events(pages, _running_headers(pages)))
    clauses = _close_cross_page(events)
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key, _label in BLOCK_ORDER}
    uncited: list[dict[str, Any]] = []
    section: str | None = None
    list_mode: str | None = None
    carried: set[str] = set()
    stem: int | None = None
    for clause in clauses:
        if clause["kind"] == "heading":
            found = _section_of(clause["text"])
            section = found
            list_mode = None
            if found in {"qualification", "rejection", "materials"}:
                carried = {found}
            else:
                carried = set()
                stem = None
            continue
        text = clause["text"]
        if not _keep(text) or _bare_numbering(text):
            continue
        if clause["kind"] == "item" and _ends_open_list(text, stem):
            list_mode = None
            carried = set()
            stem = None
        lead = _lead_kind(text)
        if lead == "rejection" or _non_refund_list(text):
            list_mode = "rejection"
        elif lead == "suppress":
            list_mode = "suppress"
        elif _materials_lead(text):
            list_mode = "materials"
        scoped_mode = list_mode if clause["kind"] == "item" else None
        blocks = _classify(clause, section, scoped_mode)
        inherits = clause["kind"] == "item" and bool(carried) and not _ends_open_list(text, stem)
        if inherits:
            blocks |= _inherited_blocks(text, carried)
        if _no_action_fragment(text) and not inherits and not _opens_item_list(text):
            blocks = set()
        if (
            clause["kind"] == "paragraph"
            and lead is None
            and not _opens_item_list(text)
            and not _materials_lead(text)
            and not _non_refund_list(text)
        ):
            list_mode = None
        if _carries(text, blocks):
            carried = set(blocks)
            found_stem = _lead_stem(text)
            if found_stem is not None:
                stem = found_stem
        elif _list_aside(text):
            pass
        elif clause["kind"] != "item" and not _bundle_label(text):
            carried = set()
            stem = None
        if not blocks:
            continue
        for block in BLOCK_LABELS:
            if block not in blocks:
                continue
            item = _item(block, clause, filename, printed["by_page"])
            if item["pages"]:
                grouped[block].append(item)
            else:
                uncited.append(item)
    result = empty_tender_blocks()
    result["printed_page_offset"] = printed["printed_page_offset"]
    result["printed_page_total"] = printed["printed_page_total"]
    for key, _label in BLOCK_ORDER:
        result["blocks"][key]["items"] = _dedupe(grouped[key])
    result["blocks"]["materials"]["items"] = _drop_material_echoes(
        result["blocks"]["materials"]["items"],
        result["blocks"]["rejection"]["items"],
    )
    result["uncited"] = _dedupe(uncited)
    _assign_ids(result)
    return sanitize_tender_blocks(result)


def sanitize_tender_blocks(payload: dict[str, Any]) -> dict[str, Any]:
    """Force pending_audit, product_pass false, and no PASS without a real page."""
    result = empty_tender_blocks()
    if isinstance(payload, dict):
        result["printed_page_offset"] = _optional_int(payload.get("printed_page_offset"))
        result["printed_page_total"] = _optional_int(payload.get("printed_page_total"))
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


def _events(pages: list[dict[str, Any]], banners: set[str] | None = None) -> list[dict[str, Any]]:
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
        page_number = pages_on[0] if len(pages_on) == 1 else None
        for kind, piece in _split_prose(text, banners or set(), page_number):
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
        "text": _clean_clause(text),
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
    if _REJECTION_LEAD.search(nxt) or _is_section_heading(nxt):
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
    # 质疑函怎么写不是废标。保证金不予退还的情形本身是废标。
    leave_out = _complaint_procedure(text)
    collusion = _collusion(text)
    not_a_rejection = _definition_note(text) or _invalidates_unofficial_material(text)
    if list_mode == "suppress" or leave_out or not_a_rejection:
        pass
    elif collusion or (list_mode == "rejection" and not _negated(text)) or _is_rejection(text):
        blocks.add("rejection")
    inherited = None if list_mode in {"rejection", "suppress"} else section
    if _is_scoring(text, inherited):
        blocks.add("scoring")
    if not leave_out and not collusion and _keeps_materials(text, inherited, list_mode):
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
        # A table cell is 废标项 only when its header says so. Cell text alone is not.
        blocks.discard("rejection")
    if _collusion(text):
        blocks.add("rejection")
        blocks.discard("materials")
    if explicit_keep:
        blocks.discard("rejection")
    if "scoring" in blocks and (
        not _has_clause_subject(text) or _scoring_process(text) or _header_echo(text) or _enterprise_size_only(text)
    ):
        blocks.discard("scoring")
    return blocks


def _is_rejection(text: str) -> bool:
    if _definition_note(text) or _invalidates_unofficial_material(text):
        return False
    if _document_rejected(text) or _collusion(text) or _non_refund_situation(text) or _reprocurement_bar(text):
        return True
    if _cross_reference_only(text):
        return False
    parts = re.split(r"[，,；;]", text)
    for part in parts:
        if _REJECTION_OUTCOME.search(part) and not _negated(part):
            return True
    return False


def _negated(text: str) -> bool:
    return _NEGATED_REJECTION.search(text) is not None


def _collusion(text: str) -> bool:
    return _COLLUSION.search(text) is not None


def _reprocurement_bar(text: str) -> bool:
    """Refusing to sign, then being barred from the restarted procurement, is a rejection."""
    return _REPROCUREMENT_BAR.search(text) is not None


def _non_refund_situation(text: str) -> bool:
    """A bond that is kept is a rejection. A timetable that only mentions the exception is not."""
    if _NON_REFUND.search(text) is None or not re.search(r"保证金|保函", text):
        return False
    if _REFUND_TIMETABLE.search(text) and re.search(r"除外|但因", text):
        return False
    return not (_refund_procedure(text) and _NON_REFUND_LIST.search(text) is None)


def _non_refund_list(text: str) -> bool:
    return _non_refund_situation(text) and _NON_REFUND_LIST.search(text) is not None


def _complaint_procedure(text: str) -> bool:
    """质疑函怎么写、谁可以提、如何答复。顺带提到质疑的投标结论仍保留。"""
    if not _COMPLAINT.search(text):
        return False
    return _BID_RULE_BESIDE_COMPLAINT.search(text) is None


def _participation_limit(text: str) -> bool:
    """Eligibility to take part in this procurement. Contract and post-award bans are not."""
    match = _PARTICIPATION_LIMIT.search(text)
    if match is None or _POST_AWARD.search(text):
        return False
    after = text[match.end():match.end() + 24]
    if re.match(r"其他", after):
        return False
    window = text[max(0, match.start() - 16):match.end() + 24]
    return _THIS_PROCUREMENT.search(window) is not None


def _document_rejected(text: str) -> bool:
    """响应/投标文件被判定无效或被拒绝接收。"""
    if _NEGATED_DOCUMENT.search(text):
        return False
    if _DOCUMENT_REJECTION.search(text):
        return True
    return _DOCUMENT_REFUSAL.search(text) is not None


def _refund_procedure(text: str) -> bool:
    """保证金何时退、怎么退。这不是要放进响应文件的材料。"""
    if not re.search(r"保证金|保函", text) or not re.search(r"退还|退回", text):
        return False
    without_forfeit = re.sub(r"不予退还|不退还|不得退还", "", text)
    if not re.search(r"退还|退回", without_forfeit):
        return False
    return re.search(r"(?:须|应|应当|必须)(?:提交|提供|递交).{0,12}退(?:还|款)申请", text) is None


def _strip_footer(text: str) -> str:
    return _PAGE_FOOTER.sub("", text).strip()


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
    if _enterprise_size_only(text) or _scoring_process(text) or _header_echo(text):
        return False
    if not _has_clause_subject(text):
        return False
    clockless = _CLOCK.sub("", text)
    if _SCORE_ASSIGNMENT.search(clockless) or _SCORE_CONTEXT.search(clockless) or _SCORE_AMOUNT.search(clockless):
        return True
    return section == "scoring" and re.search(r"评审因素|评分标准|评分办法", text) is not None


def _scoring_process(text: str) -> bool:
    """Ranking, award, notification, and a bare 'the rules follow' line are not criteria."""
    if _SCORE_INTRO.search(text):
        return True
    if _SCORE_ASSIGNMENT.search(text):
        return False
    return _SCORING_PROCESS.search(text) is not None


def _enterprise_size_only(text: str) -> bool:
    """企业划型标准 explains firm size. It is not a score unless it also assigns points."""
    if _ENTERPRISE_SIZE.search(text) is None:
        return False
    return _SCORE_ASSIGNMENT.search(text) is None


def _header_echo(text: str) -> bool:
    """A row that only repeats column titles is not a criterion."""
    if _SCORE_ASSIGNMENT.search(text) or _SCORE_AMOUNT.search(text) or re.search(r"[。！？]", text):
        return False
    compact = _compact(re.sub(r"<br\s*/?>|Col\d+：", "", text, flags=re.IGNORECASE))
    for label in _HEADER_LABELS:
        compact = compact.replace(label, "")
    return len(re.findall(r"[\u3400-\u9fff]", compact)) < 4


def _has_clause_subject(text: str) -> bool:
    """A score fragment such as 「得3分」 has no subject and is not its own clause."""
    stripped = _CLOCK.sub("", text)
    stripped = _SCORE_CONTEXT.sub("", stripped)
    stripped = _SCORE_AMOUNT.sub("", stripped)
    return len(re.findall(r"[\u3400-\u9fff]", stripped)) >= 2


def _definition_note(text: str) -> bool:
    return _DEFINITION_NOTE.search(text) is not None


def _invalidates_unofficial_material(text: str) -> bool:
    """Invalidating an unofficial notice or material does not reject the response file."""
    if not re.search(r"作无效处理|按无效处理|视为无效", text):
        return False
    if _RESPONSE_FILE.search(text):
        return False
    if _INFORMAL_MATERIAL.search(text):
        return True
    return re.search(r"作无效处理", text) is not None and re.search(
        r"未经[^。；;]{0,40}(?:发布|通知|公布)", text
    ) is not None


_SUBMISSION_DUTY = re.compile(
    r"(?:须|应|应当|必须|需)(?:提供|提交|递交)|复印件|加盖公章|资格证明文件|资格证明材料"
)
_BOND_TEMPLATE = re.compile(r"本保函|本担保书")
_BOND_BODY = re.compile(r"见索即付|不可撤销|担保人|开立人|担保范围")


def _bond_template(text: str) -> bool:
    """The body of a guarantee letter is not a document the bidder must enclose."""
    if re.search(r"(?:须|应|应当|必须|需)(?:提交|提供|递交|缴纳)[^。]{0,16}(?:保函|保证金|担保)", text):
        return False
    if _BOND_TEMPLATE.search(text):
        return True
    return bool(re.search(r"保函|担保书|担保函", text) and _BOND_BODY.search(text))


def _keeps_materials(text: str, section: str | None, list_mode: str | None) -> bool:
    """Refund timing is not a document to enclose. A real submission duty still is."""
    if _bond_template(text):
        return False
    if _refund_procedure(text) and _SUBMISSION_DUTY.search(text) is None:
        return False
    return (list_mode == "materials" and _is_child_item(text)) or _is_materials(text, section)


def _is_materials(text: str, section: str | None) -> bool:
    if _bond_template(text):
        return False
    if re.search(r"未提供不(计分|得分)", text) and not re.search(r"(?:须|应|应当|必须|需)(?:提供|提交)", text):
        return False
    if re.search(r"未(?:按要求)?(?:提供|提交)|应提供而未提供", text) and not re.search(
        r"(?:须|应|应当|必须)(?:提供|提交)[^。]{0,12}(?:复印件|证书|执照|材料|文件)",
        text,
    ):
        return False
    if re.search(r"(?:须|应|应当|必须|需)(?:提供|提交|递交)|证明材料|复印件|加盖公章|资格证明文件", text):
        return True
    return bool(
        section == "materials"
        and _ITEM_START.match(text)
        and re.search(r"函|委托书|偏离表|报价表|证明|执照|证书|材料|身份证明", text)
    )


def _materials_lead(text: str) -> bool:
    return _MATERIALS_LEAD.search(text) is not None


def _procurement_access(text: str) -> bool:
    """Sale price, registration time, and where to collect the tender are not eligibility."""
    if _PROCUREMENT_ACCESS.search(text):
        return True
    return _PROCUREMENT_HEADING.fullmatch(_compact(text)) is not None


def _is_qualification(text: str, section: str | None) -> bool:
    if _procurement_access(text) or _reprocurement_bar(text):
        return False
    if _participation_limit(text):
        return True
    if re.search(
        r"(?:供应商|投标人|申请人).{0,12}资格(?:条件|要求)|资格(?:条件|要求|证明)\s*[:：]|"
        r"特定资格|基本资格|资格证明材料|政府采购法》第二十二条|须具备|应具备|应当符合",
        text,
    ):
        return True
    return bool(
        section == "qualification"
        and re.search(r"应当符合|必须具备|必须是|须具备|须具有|须满足|具备|具有", text)
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
    if not compact or _NOISE.search(text):
        return False
    if len(compact) < 4 and not re.search(r"无效|否决|拒绝|废标", text):
        return False
    if _TOC_LINE.search(text) and _REJECTION_OUTCOME.search(text) is None:
        return False
    return not _contact_only(text)


def _contact_only(text: str) -> bool:
    """A contact channel is not a clause unless the same sentence scores or rejects."""
    if _EMAIL.search(text) is None:
        return False
    if re.search(r"无效|否决|废标|满分|不得分", text):
        return False
    return re.search(r"(?:须|应|应当|必须)(?:提供|提交|递交)", text) is None


def _opens_item_list(text: str) -> bool:
    if re.search(r"下列|以下|如下|包括以下|包括下列|包括但不限于|情形之一|情况之一|文件由|文件组成", text):
        return True
    return text.rstrip().endswith(("：", ":"))


def _is_child_item(text: str) -> bool:
    if _BARE_SECTION_TITLE.match(text.strip()):
        return False
    return _CHILD_ITEM.match(text) is not None


def _lead_stem(text: str) -> int | None:
    """The major number of a list lead such as 「3.」。 A decimal child 「3.1」 has no stem of its own."""
    if re.match(r"^\s*\d+[.．]\d", text):
        return None
    match = re.match(r"^\s*(\d+)[.．、]", text)
    if match is None:
        return None
    return int(match.group(1))


def _continues_stem(text: str, stem: int | None) -> bool:
    match = re.match(r"^\s*(\d+)[.．]\d", text)
    return bool(match and stem is not None and int(match.group(1)) == stem)


def _ends_open_list(text: str, stem: int | None = None) -> bool:
    """A new numbered section ends the list. A decimal child of the open stem does not."""
    if _continues_stem(text, stem):
        return False
    if _is_child_item(text) or not _ITEM_START.match(text):
        return False
    return not (
        re.match(r"^\s*\d+\.\d+", text)
        and not re.search(r"[，。！？；;]", text)
        and len(_compact(text)) <= 24
    )


def _bare_numbering(text: str) -> bool:
    return _BARE_NUMBERING.fullmatch(_compact(text)) is not None


def _no_action_fragment(text: str) -> bool:
    """A label with no predicate is not its own item. Invalidity words keep the sentence."""
    if re.search(r"无效|否决|拒绝|废标", text):
        return False
    if re.search(r"[。！？]", text):
        return False
    if re.search(r"须|应当|必须|不得|提供|提交|递交|具备|具有|参加|缴纳|退还", text):
        return False
    if re.search(r"函|委托书|偏离表|报价表|执照|证书|证明", text):
        return False
    return re.search(r"[，,；;]", text) is None


def _drop_loose_fragments(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A bare number or a prose label is not glued onto the next sentence."""
    kept: list[dict[str, Any]] = []
    for event in events:
        text = event["text"]
        loose = (
            event["kind"] != "item"
            and _no_action_fragment(text)
            and not _opens_item_list(text)
            and not _materials_lead(text)
            and not _non_refund_list(text)
        )
        if event["kind"] != "heading" and (_bare_numbering(text) or loose):
            continue
        kept.append(event)
    return kept


def _list_aside(text: str) -> bool:
    """A note or a quoted definition between numbered children does not close the list."""
    return bool(re.match(r"^\s*注\s*[:：]?", text) or _definition_note(text))


def _carries(text: str, blocks: set[str]) -> bool:
    if not blocks:
        return False
    if _opens_item_list(text):
        return True
    if not (blocks & {"qualification", "rejection"}):
        return False
    return re.search(r"[，,。！？；;]", text) is None


def _bundle_label(text: str) -> bool:
    compact = _compact(text)
    if re.search(r"[，。！？；;]", text) or len(compact) > 24:
        return False
    return bool(re.match(r"^\d+(?:\.\d+)+", text) and re.search(r"(?:文件|部分|内容|材料)$", compact))


def _inherited_blocks(text: str, carried: set[str]) -> set[str]:
    extra = set(carried)
    if _bond_template(text) or _collusion(text):
        extra.discard("materials")
    if _negated(text) or _definition_note(text):
        extra.discard("rejection")
    if _procurement_access(text):
        extra.discard("qualification")
    if _collusion(text) or (_REJECTION_OUTCOME.search(text) and not _negated(text)):
        extra.add("rejection")
    if _refund_procedure(text):
        extra.discard("materials")
        extra.discard("rejection")
    return extra


def _item(
    block: str,
    clause: dict[str, Any],
    filename: str | None,
    printed_by_page: dict[int, int],
) -> dict[str, Any]:
    pages = [number for number in clause["pages"] if isinstance(number, int) and number >= 1]
    locator = _locator(clause, pages)
    status = "NEEDS_REVIEW" if pages or locator else "UNKNOWN"
    reason = None if pages else _uncited_reason(locator)
    detection = "table" if clause["kind"] == "table_row" else "clause"
    if len(pages) > 1 or clause.get("cross_page"):
        detection = "cross_page"
    quote = _bounded_quote(clause["text"])
    printed_pages = [_printed_on(number, printed_by_page) for number in pages]
    return {
        "clause_id": "",
        "block": block,
        "label": BLOCK_LABELS[block],
        "summary": quote[:80],
        "quote": quote,
        "pages": pages,
        "page": pages[0] if pages else None,
        "printed_page": printed_pages[0] if printed_pages else None,
        "printed_pages": printed_pages,
        "status": status,
        "locator": locator,
        "detection": detection,
        "filename": filename or "",
        "uncited_reason": reason,
        "audit_status": "pending_audit",
    }


def _printed_on(number: int, printed_by_page: dict[int, int]) -> int | None:
    value = printed_by_page.get(number)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
    return None


def _pdf_page_label(pages: list[int]) -> str:
    if len(pages) == 1:
        return f"PDF 第{pages[0]}页"
    return f"PDF 第{pages[0]}-{pages[-1]}页"


def _locator(clause: dict[str, Any], pages: list[int]) -> dict[str, Any] | None:
    locator = dict(clause["locator"]) if clause.get("locator") else None
    if not pages:
        return locator
    if locator is None:
        locator = {"kind": "page", "index": pages[0]}
    locator["label"] = _pdf_page_label(pages)
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


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _printed_fields(raw: dict[str, Any], pages: list[int]) -> tuple[int | None, list[int | None]]:
    printed_page = _optional_int(raw.get("printed_page"))
    if printed_page is not None and printed_page < 1:
        printed_page = None
    printed_pages: list[int | None] = []
    raw_pages = raw.get("printed_pages")
    if isinstance(raw_pages, list):
        for value in raw_pages:
            number = _optional_int(value)
            printed_pages.append(number if number is not None and number >= 1 else None)
    if pages and not printed_pages:
        printed_pages = [None for _number in pages]
    if printed_page is None and printed_pages:
        printed_page = printed_pages[0]
    return printed_page, printed_pages


def printed_page_facts(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Read 「第N页/共M页」 from each page. Unknown stays null. Never invent a number."""
    by_page: dict[int, int] = {}
    observations: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        number = page.get("page")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            continue
        matches = _PAGE_FOOTER_NUM.findall(str(page.get("text") or ""))
        if not matches:
            continue
        pairs = {(int(printed), int(total)) for printed, total in matches}
        if len(pairs) != 1:
            observations.append({"pdf_page": number, "printed_page": None, "printed_total": None, "conflict": True})
            continue
        printed, total = next(iter(pairs))
        by_page[number] = printed
        observations.append({"pdf_page": number, "printed_page": printed, "printed_total": total, "conflict": False})
    totals = {item["printed_total"] for item in observations if isinstance(item["printed_total"], int)}
    offsets = {
        item["pdf_page"] - item["printed_page"]
        for item in observations
        if isinstance(item["printed_page"], int)
    }
    printed_total = next(iter(totals)) if len(totals) == 1 else None
    offset = next(iter(offsets)) if len(offsets) == 1 else None
    mismatches = []
    for item in observations:
        if item["conflict"] or not isinstance(item["printed_page"], int):
            mismatches.append(item)
            continue
        if offset is None or item["pdf_page"] - item["printed_page"] != offset:
            mismatches.append(item)
    return {
        "printed_page_offset": offset,
        "printed_page_total": printed_total,
        "printed_total_consistent": printed_total is not None,
        "pages_with_footer": sum(1 for item in observations if item["printed_page"] is not None),
        "printed_totals_seen": sorted(totals),
        "offsets_seen": sorted(offsets),
        "by_page": by_page,
        "mismatches": mismatches,
    }


def _force_status(raw: dict[str, Any], label: str, block: str) -> dict[str, Any]:
    pages = [number for number in raw.get("pages") or [] if isinstance(number, int) and not isinstance(number, bool) and number >= 1]
    locator = raw.get("locator") if isinstance(raw.get("locator"), dict) else None
    if pages:
        locator = dict(locator) if locator else {"kind": "page", "index": pages[0]}
        locator["label"] = _pdf_page_label(pages)
        locator["pages"] = pages
    printed_page, printed_pages = _printed_fields(raw, pages)
    item = {
        "clause_id": str(raw.get("clause_id") or ""),
        "block": block,
        "label": label,
        "summary": str(raw.get("summary") or raw.get("quote") or "")[:80],
        "quote": _bounded_quote(str(raw.get("quote") or raw.get("summary") or "")),
        "pages": pages,
        "page": pages[0] if pages else None,
        "printed_page": printed_page,
        "printed_pages": printed_pages,
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


def _bounded_quote(text: str) -> str:
    """Keep a short quote, but do not cut off an invalidity consequence that sits past it."""
    if len(text) <= _QUOTE_SOFT_CAP:
        return text
    last = None
    for match in _REJECTION_OUTCOME.finditer(text):
        last = match
    if last is None or last.end() <= _QUOTE_SOFT_CAP:
        return text[:_QUOTE_SOFT_CAP]
    end = last.end()
    period = re.search(r"[。！？]", text[end:end + 80])
    if period:
        end += period.end()
    return text[: min(end, _QUOTE_HARD_CAP)]


def _passage(text: str) -> str:
    cleaned = re.sub(r"<br\s*/?>", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"Col\d+：", "", cleaned)
    return _compact(cleaned)


def _drop_material_echoes(
    materials: list[dict[str, Any]],
    rejection: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """On one page, a sentence that states invalidity is kept as 废标项 only."""
    rejection_pages: dict[str, set[int]] = {}
    for item in rejection:
        if not _is_rejection(item["quote"]):
            continue
        rejection_pages.setdefault(_compact(item["quote"]), set()).update(item["pages"])
    kept: list[dict[str, Any]] = []
    for item in materials:
        pages = set(item["pages"])
        overlap = rejection_pages.get(_compact(item["quote"]), set())
        if pages and pages <= overlap:
            continue
        kept.append(item)
    return kept


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, tuple[int, ...], str]] = set()
    kept: list[dict[str, Any]] = []
    for item in items:
        key = (item["block"], tuple(item["pages"]), _compact(item["quote"]))
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    table_passages = [
        (item["pages"], _passage(item["quote"]))
        for item in kept
        if item.get("detection") == "table" and len(_passage(item["quote"])) >= 20
    ]
    if not table_passages:
        return kept
    filtered: list[dict[str, Any]] = []
    for item in kept:
        passage = _passage(item["quote"])
        if item.get("detection") != "table" and len(passage) >= 20 and any(
            set(item["pages"]) & set(pages) and (passage in table or table in passage)
            for pages, table in table_passages
        ):
            continue
        filtered.append(item)
    return filtered


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


def _cjk(char: str) -> bool:
    return "\u3400" <= char <= "\u9fff"


def _sentence_end(line: str) -> bool:
    return line.endswith(("。", "！", "？"))


def _join_wrapped(parts: list[str]) -> str:
    """Join lines of one sentence. A CJK line break is not a word space."""
    text = parts[0]
    for part in parts[1:]:
        if text and part and _cjk(text[-1]) and _cjk(part[0]):
            text += part
        else:
            text += f" {part}"
    return text


def _is_section_heading(line: str) -> bool:
    if _ITEM_START.match(line):
        return False
    if _CHAPTER_LINE.match(line):
        return True
    if len(line) > 40 or "，" in line or "," in line or "。" in line:
        return False
    # A lead that introduces the following items is a sentence, not a section title.
    if line.rstrip().endswith(("：", ":")) or re.search(r"下列|如下", line):
        return False
    return _section_of(line) is not None


def _running_headers(pages: list[dict[str, Any]]) -> set[str]:
    """The first line of a page, when that same line opens several pages, is a running header."""
    counts: dict[str, int] = {}
    for page in pages:
        if not isinstance(page, dict):
            continue
        first = ""
        for raw in str(page.get("text") or "").splitlines():
            line = _strip_footer(raw.strip())
            if not line:
                continue
            first = line
            break
        if not first or re.search(r"[，。！？；;、：:]", first):
            continue
        if len(_compact(first)) < 8 or _is_section_heading(first) or _ITEM_START.match(first):
            continue
        counts[first] = counts.get(first, 0) + 1
    return {line for line, count in counts.items() if count >= 3}


def _score_only_line(line: str) -> bool:
    """「得5分」 or 「0-15分」 has no subject."""
    compact = _compact(line).strip("；;。")
    return re.fullmatch(r"(?:得|扣|加)?\d+分|满分\d+分|\d+[-~～至到]\d+分", compact) is not None


def _score_fragment(line: str) -> bool:
    """A tail such as 「0.5分,扣完为止」 or a bare label 「商务部分5分」 belongs to the previous sentence."""
    compact = _compact(line).strip("；;。")
    if re.match(r"^\d+(?:\.\d+)?分", compact):
        return True
    return re.fullmatch(r"[\u3400-\u9fff]{2,12}\d+(?:\.\d+)?分", compact) is not None


def _clean_clause(text: str) -> str:
    text = _strip_footer(text)
    text = re.sub(r"^\d+\.\d{2,}(?!\d)\s+", "", text)
    text = _FRONT_PREFIX.sub("", text)
    return " ".join(text.split()).strip()


def _page_edge_skips(lines: list[str], page_number: int | None) -> set[int]:
    """Drop a bare page index at the page edge, and a front-table header repeated under it."""
    content: list[int] = []
    for index, raw in enumerate(lines):
        line = _strip_footer(raw.strip())
        if line and not _NOISE.search(raw):
            content.append(index)
    skip: set[int] = set()
    if not content:
        return skip
    edges = {content[0], content[-1]}
    if page_number is not None:
        for index in edges:
            line = _strip_footer(lines[index].strip())
            if re.fullmatch(r"\d{1,3}", line) and int(line) == page_number:
                skip.add(index)
    header_run: list[int] = []
    for index in content[:8]:
        if index in skip:
            continue
        line = _strip_footer(lines[index].strip())
        if page_number is not None and re.fullmatch(r"\d{1,3}", line) and int(line) == page_number:
            continue
        if _FRONT_HEADER_LINE.fullmatch(line):
            header_run.append(index)
            continue
        break
    names = {_strip_footer(lines[index].strip()) for index in header_run}
    if names & {"序号", "内容", "说明", "条款号", "栏目", "编列内容"}:
        skip.update(header_run)
    return skip


def _explode_items(text: str) -> list[tuple[str, str]]:
    """Numbered sub-items written on one line each become their own clause."""
    marks = [match for match in _INLINE_MARK.finditer(text) if match.start() > 0]
    if not marks:
        kind = "item" if _ITEM_START.match(text) else "paragraph"
        return [(kind, text)]
    pieces: list[tuple[str, str]] = []
    lead = text[: marks[0].start()].strip()
    if lead:
        pieces.append(("paragraph" if not _ITEM_START.match(lead) else "item", lead))
    bounds = [*marks, None]
    for index, mark in enumerate(marks):
        end = bounds[index + 1].start() if bounds[index + 1] is not None else len(text)
        chunk = text[mark.start():end].strip()
        if chunk:
            pieces.append(("item", chunk))
    return pieces


def _split_prose(
    text: str,
    banners: set[str] | None = None,
    page_number: int | None = None,
) -> list[tuple[str, str]]:
    banners = banners or set()
    raw_lines = text.splitlines()
    skip = _page_edge_skips(raw_lines, page_number)
    pieces: list[tuple[str, str]] = []
    buffer_kind = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer_kind, buffer
        if buffer:
            joined = _join_wrapped(buffer)
            if buffer_kind == "heading":
                pieces.append((buffer_kind, joined))
            else:
                pieces.extend(_explode_items(joined))
        buffer_kind = ""
        buffer = []

    def absorb(line: str) -> None:
        if buffer:
            buffer.append(line)
            if _sentence_end(line) or (line.endswith(_CLOSED) and buffer_kind == "item"):
                flush()
            return
        if pieces and _score_fragment(line):
            kind, previous = pieces[-1]
            pieces[-1] = (kind, _join_wrapped([previous, line]))
            return
        pieces.append(("paragraph", line))

    for index, raw in enumerate(raw_lines):
        if index in skip:
            continue
        line = raw.strip()
        if not line or _NOISE.search(line):
            flush()
            continue
        line = _strip_footer(line)
        if not line or line in banners:
            continue
        if _score_fragment(line) or _score_only_line(line):
            # A fragment joins the sentence before it. A bare score on the next page stays separate
            # so the cross-page joiner can attach it.
            if buffer:
                buffer.append(line)
                flush()
            else:
                absorb(line)
            continue
        if re.match(r"^注\s*[:：]", line) and buffer:
            flush()
        if _is_section_heading(line):
            flush()
            pieces.append(("heading", line))
            continue
        kind = "item" if _ITEM_START.match(line) else "paragraph"
        if buffer and (kind == "item" or _sentence_end(buffer[-1])):
            flush()
        if not buffer:
            buffer_kind = kind
        buffer.append(line)
        if (line.endswith(_CLOSED) and kind == "item") or _sentence_end(line):
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
