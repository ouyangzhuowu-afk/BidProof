"""Run the existing four-block extractor on one PDF text layer.

Page numbers are the PDF page index (1-based). This path does not call OCR
and does not copy a line range into the page field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from app.extraction import extract_pdf
from app.ocr import DisabledOCRAdapter
from app.tender_blocks import BLOCK_ORDER, extract_tender_blocks, printed_page_facts

_FOOTER = re.compile(r"第\s*\d+\s*页\s*[/／]?\s*共\s*\d+\s*页")
_MEASURE = re.compile(r"个|年|月|日|条|项|分|元|万|页|号|名|家|次|包|人|套|台")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _footer_check(pages: list[dict]) -> dict:
    facts = printed_page_facts(pages)
    return {
        "checked_pages": len(pages),
        "pages_with_footer": facts["pages_with_footer"],
        "printed_page_offset": facts["printed_page_offset"],
        "printed_page_total": facts["printed_page_total"],
        "printed_total_consistent": facts["printed_total_consistent"],
        "printed_totals_seen": facts["printed_totals_seen"],
        "offsets_seen": facts["offsets_seen"],
        "compared_with": "printed_total",
        "mismatch_count": len(facts["mismatches"]),
        "mismatches": facts["mismatches"],
    }


def _rows(result: dict) -> list[dict]:
    rows: list[dict] = []
    for key, _label in BLOCK_ORDER:
        rows.extend(result["blocks"][key]["items"])
    rows.extend(result["uncited"])
    return rows


def _counts(result: dict) -> dict:
    by_block = {}
    with_page = 0
    without_page = 0
    for key, label in BLOCK_ORDER:
        items = result["blocks"][key]["items"]
        cited = sum(1 for item in items if item["pages"])
        by_block[key] = {"label": label, "cited": cited, "items": len(items)}
        with_page += cited
    for item in result["uncited"]:
        if item["pages"]:
            with_page += 1
        else:
            without_page += 1
    return {
        "total": with_page + without_page,
        "with_real_page": with_page,
        "without_page": without_page,
        "by_block": by_block,
    }


def _structural_checks(pages: list[dict], result: dict) -> dict[str, bool]:
    """Checks that apply to every file. They do not look up a project, a buyer, or a page."""
    rows = _rows(result)
    cited = [item for item in rows if item.get("pages")]
    labels_ok = all(
        str((item.get("locator") or {}).get("label") or "").startswith("PDF 第")
        and all(isinstance(number, int) and not isinstance(number, bool) and number >= 1 for number in item["pages"])
        for item in cited
    )
    pages_ok = all(
        isinstance(page, dict)
        and page.get("page") == index
        and (page.get("locator") or {}).get("kind") == "page"
        and not page.get("ocr_status")
        for index, page in enumerate(pages, 1)
    )
    status_ok = all(item.get("status") in {"NEEDS_REVIEW", "UNKNOWN"} for item in rows)
    return {
        "product_pass_false": result.get("product_pass") is False,
        "audit_status_pending": result.get("audit_status") == "pending_audit",
        "no_pass_status": status_ok and all(item.get("status") != "PASS" for item in rows),
        "cited_labels_use_pdf_page": labels_ok,
        "page_index_matches_order": pages_ok,
        "ocr_not_used": all(not (page.get("ocr_status") if isinstance(page, dict) else True) for page in pages),
    }


def _markdown(payload: dict) -> str:
    counts = payload["counts"]
    lines = [
        f"# 招标四块抽取 · {payload['title']} pending_audit",
        "",
        "- `audit_status`: `pending_audit`",
        "- `product_pass`: `false`",
        "- 这是公开测试材料，不是试点，不进 T-005 台账。",
        "- 行 CER ≤ 2%、关键字段 F1 ≥ 97%、TEDS ≥ 90% 三道门槛没有改。本产物不重跑这三项。",
        "- 页码是 PDF 页索引（从 1 起）。没有调用 OCR，也没有把行号写成页码。",
        f"- 来源：{payload['source_url']}",
        f"- 标题：{payload['title']}",
        f"- 项目编号：{payload['project_number']}；采购人：{payload['buyer']}",
        f"- 本地文件：`{payload['local_path']}`",
        f"- SHA-256：`{payload['sha256']}`",
        f"- PDF 页数：{payload['pdf_page_count']}",
        f"- 印制页码偏移：{_offset_text(payload['printed_page_offset'])}",
        f"- 印制总页数（页脚「共M页」）：{_total_text(payload['printed_page_total'])}",
        f"- 页脚核对：{_footer_sentence(payload['footer_check'])}",
        f"- 条款原文仍含页脚：{payload['footer_in_quotes']} 条",
        f"- 条款原文仍夹着页首页尾的裸页码：{payload['bare_page_in_quotes']} 条",
        "",
        "## 抽取数量",
        "",
        f"- 合计：{counts['total']} 条",
        f"- 带这份 PDF 的真实页码：{counts['with_real_page']} 条",
        f"- 没有页码：{counts['without_page']} 条",
        "",
        "| 块 | 条数 | 都有 PDF 页码 |",
        "|---|---:|---:|",
    ]
    for key, _label in BLOCK_ORDER:
        block = counts["by_block"][key]
        lines.append(f"| {block['label']} | {block['cited']} | {block['cited']} |")
    checks = payload["structural_checks"]
    lines.extend(
        [
            "",
            "## 结构核对",
            "",
            "- 每条条款的状态是 `NEEDS_REVIEW`（有页码）或 `UNKNOWN`（没有页码）。",
            "- `product_pass` 为 false，`audit_status` 为 pending_audit。没有 PASS。",
            "- 有页码的条款，定位都以「PDF 第」开头，页码是正整数。",
            "- 页索引与 PDF 顺序一致，没有调用 OCR。",
            f"- 核对结果：{'通过' if all(checks.values()) else '未通过'}。",
            "",
        ]
    )
    lines.extend(
        [
            "",
            "## 没有页码的条款",
            "",
        ]
    )
    if counts["without_page"] == 0:
        lines.append("没有。抽出来的条款全部带有这份 PDF 的页码，状态是 `NEEDS_REVIEW`（必须人工看），不是通过。")
    else:
        lines.append("| 块 | 状态 | 摘要 | 为什么没有页码 |")
        lines.append("|---|---|---|---|")
        for item in payload["extraction"]["uncited"]:
            summary = item["summary"].replace("|", "\\|")
            reason = str(item.get("uncited_reason") or "").replace("|", "\\|")
            lines.append(f"| {item['label']} | {item['status']} | {summary} | {reason} |")
    lines.extend(
        [
            "",
            "## 已引用条款",
            "",
            "| 块 | PDF页 | 印制页 | 状态 | 摘要 |",
            "|---|---|---|---|---|",
        ]
    )
    for key, _label in BLOCK_ORDER:
        for item in payload["extraction"]["blocks"][key]["items"]:
            summary = item["summary"].replace("|", "\\|")
            lines.append(
                f"| {item['label']} | {_pdf_pages(item['pages'])} | {_printed_text(item.get('printed_page'))} | {item['status']} | {summary} |"
            )
    lines.append("")
    return "\n".join(lines)


def _pdf_pages(pages: list[int]) -> str:
    return "、".join(f"PDF 第{number}页" for number in pages)


def _printed_text(value: int | None) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return "未知"


def _footer_sentence(check: dict) -> str:
    seen_totals = check["printed_totals_seen"] or "无"
    seen_offsets = check["offsets_seen"] or "无"
    if check["pages_with_footer"] == 0:
        return (
            "没有读到「第N页共M页」或「第N页/共M页」页脚。"
            "印制偏移和印制总页数留空，不把单独的数字当成页码。"
        )
    if check["printed_total_consistent"]:
        total_text = "印制总页数一致。"
    else:
        total_text = "印制总页数不一致，因此不取单一总页数。"
    return (
        f"读到页脚的页 {check['pages_with_footer']}。"
        f"页码偏移不一致 {check['mismatch_count']} 页。"
        f"{total_text}"
        f"见到的总页数 {seen_totals}，见到的偏移 {seen_offsets}。"
    )


def _offset_text(value: int | None) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return "未知"


def _total_text(value: int | None) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return "未知"


def _footer_in_quotes(result: dict) -> int:
    return sum(1 for item in _rows(result) if _FOOTER.search(item.get("quote") or ""))


def _bare_page_in_quotes(result: dict) -> int:
    """A PDF page index glued between CJK characters, the residue of a bare page number."""
    count = 0
    for item in _rows(result):
        quote = item.get("quote") or ""
        for number in item.get("pages") or []:
            glued = re.search(rf"(?<=[\u3400-\u9fff])\s*{int(number)}\s*(?=[\u3400-\u9fff])", quote)
            if glued is None:
                continue
            if _MEASURE.match(quote[glued.end():]):
                continue
            count += 1
            break
    return count


def run(
    pdf: Path,
    markdown_path: Path,
    json_path: Path,
    *,
    source_url: str,
    title: str,
    project_number: str,
    buyer: str,
) -> dict:
    pages = extract_pdf(pdf, ocr_adapter=DisabledOCRAdapter())
    result = extract_tender_blocks(pages, filename=pdf.name)
    checks = _structural_checks(pages, result)
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise RuntimeError(f"structural checks failed: {', '.join(failed)}")
    footer = _footer_check(pages)
    payload = {
        "audit_status": "pending_audit",
        "product_pass": False,
        "test_material_only": True,
        "source_url": source_url,
        "title": title,
        "project_number": project_number,
        "buyer": buyer,
        "local_path": pdf.as_posix(),
        "sha256": _sha256(pdf),
        "pdf_page_count": len(pages),
        "printed_page_offset": footer["printed_page_offset"],
        "printed_page_total": footer["printed_page_total"],
        "ocr": "not_used",
        "footer_check": footer,
        "footer_in_quotes": _footer_in_quotes(result),
        "bare_page_in_quotes": _bare_page_in_quotes(result),
        "counts": _counts(result),
        "structural_checks": checks,
        "extraction": result,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--project-number", required=True)
    parser.add_argument("--buyer", required=True)
    args = parser.parse_args()
    payload = run(
        args.pdf,
        args.markdown,
        args.json,
        source_url=args.source_url,
        title=args.title,
        project_number=args.project_number,
        buyer=args.buyer,
    )
    counts = payload["counts"]
    print(
        json.dumps(
            {
                "total": counts["total"],
                "with_real_page": counts["with_real_page"],
                "without_page": counts["without_page"],
                "by_block": {key: value["cited"] for key, value in counts["by_block"].items()},
                "sha256": payload["sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
