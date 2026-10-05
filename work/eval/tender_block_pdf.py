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
from app.tender_blocks import BLOCK_ORDER, extract_tender_blocks

SOURCE_URL = "https://www.gl.gov.cn/xjwz/zwgkml/zdlyxxgk/zfcg/zhbgg/zbgg_swj/202609/P020260920414795183978.pdf"
TITLE = "竞争性磋商文件（服务类）— 2026年八闽美食嘉年华暨鼓楼区海鲜美食消费季活动"
PROJECT_NUMBER = "2026-FZSC339"
BUYER = "福州市鼓楼区商务局"
DEFAULT_PDF = Path("work/public-eval/tender-blocks/pub-gl-fzsc339-cuoshang-202609.pdf")
DEFAULT_MARKDOWN = Path("outputs/tender-blocks/pub-gl-fzsc339-pending-audit.md")
DEFAULT_JSON = Path("outputs/tender-blocks/pub-gl-fzsc339-pending-audit.json")
_FOOTER = re.compile(r"第\s*(\d+)\s*页\s*共\s*(\d+)\s*页")
_KNOWN = (
    ("资格要求", "第二十二条第一款", 2),
    ("废标项", "资格审查和实质性响应审查不合格", 24),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _footer_check(pages: list[dict]) -> dict:
    mismatches = []
    for page in pages:
        number = page["page"]
        found = _FOOTER.findall(page.get("text") or "")
        printed = found[-1] if found else None
        if printed != (str(number), str(len(pages))):
            mismatches.append({"pdf_page": number, "printed": printed})
    return {"checked_pages": len(pages), "mismatches": mismatches}


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


def _known_hits(result: dict) -> list[dict]:
    hits = []
    rows = _rows(result)
    for label, needle, expected_page in _KNOWN:
        matched = [
            {
                "block": item["label"],
                "pages": item["pages"],
                "status": item["status"],
                "summary": item["summary"],
            }
            for item in rows
            if needle in item["quote"]
        ]
        hits.append(
            {
                "label": label,
                "needle": needle,
                "expected_pdf_page": expected_page,
                "matches": matched,
            }
        )
    return hits


def _markdown(payload: dict) -> str:
    counts = payload["counts"]
    lines = [
        "# 招标四块抽取 · 鼓楼区竞争性磋商 PDF pending_audit",
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
        f"- 页脚核对：{payload['footer_check']['checked_pages']} 页，与「第 N 页 共 {payload['pdf_page_count']} 页」不一致的页数：{len(payload['footer_check']['mismatches'])}",
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
    lines.extend(["", "## 已知条款", ""])
    for hit in payload["known_hits"]:
        if hit["matches"]:
            pages = ", ".join(str(item["pages"]) for item in hit["matches"])
            lines.append(
                f"- 第 {hit['expected_pdf_page']} 页「{hit['needle']}」抽到 {len(hit['matches'])} 条，页码 {pages}。"
            )
        else:
            lines.append(f"- 第 {hit['expected_pdf_page']} 页「{hit['needle']}」没有抽到。")
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
    lines.extend(["", "## 已引用条款", "", "| 块 | 页码 | 状态 | 摘要 |", "|---|---|---|---|"])
    for key, _label in BLOCK_ORDER:
        for item in payload["extraction"]["blocks"][key]["items"]:
            summary = item["summary"].replace("|", "\\|")
            pages = "、".join(str(number) for number in item["pages"])
            lines.append(f"| {item['label']} | {pages} | {item['status']} | {summary} |")
    lines.append("")
    return "\n".join(lines)


def run(pdf: Path, markdown_path: Path, json_path: Path) -> dict:
    pages = extract_pdf(pdf, ocr_adapter=DisabledOCRAdapter())
    for index, page in enumerate(pages, 1):
        if page.get("page") != index or page.get("locator", {}).get("kind") != "page":
            raise RuntimeError(f"page {index} is not the PDF page index")
        if page.get("ocr_status"):
            raise RuntimeError(f"page {index} used OCR")
    result = extract_tender_blocks(pages, filename=pdf.name)
    if result.get("product_pass") is not False or result.get("audit_status") != "pending_audit":
        raise RuntimeError("extraction did not stay pending_audit with product_pass false")
    payload = {
        "audit_status": "pending_audit",
        "product_pass": False,
        "test_material_only": True,
        "source_url": SOURCE_URL,
        "title": TITLE,
        "project_number": PROJECT_NUMBER,
        "buyer": BUYER,
        "local_path": pdf.as_posix(),
        "sha256": _sha256(pdf),
        "pdf_page_count": len(pages),
        "ocr": "not_used",
        "footer_check": _footer_check(pages),
        "counts": _counts(result),
        "known_hits": _known_hits(result),
        "extraction": result,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    payload = run(args.pdf, args.markdown, args.json)
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
