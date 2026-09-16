"""Build the committed S-A-05 TEDS GT JSONL from public PDFs + synthetic pages.

Canonical output: work/eval/fixtures/teds_gt.jsonl
Public tables are extracted from work/public-eval/pdfs and then frozen.
Synthetic pages are authored here and labeled origin=synthetic.

Engineering / sandbox only. Does not write pilot or ICP ledgers.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import fitz

from work.eval.teds_gt import ROOT, rows_to_table_html

DEFAULT_MANIFEST = ROOT / "work" / "public-eval" / "manifest.json"
DEFAULT_JSONL = ROOT / "work" / "eval" / "fixtures" / "teds_gt.jsonl"

PUBLIC_PICKS: list[dict[str, Any]] = [
    {
        "doc_id": "fixture-001",
        "page": 14,
        "tables": [0],
        "table_title": "采购清单",
    },
    {
        "doc_id": "fixture-001",
        "page": 32,
        "tables": [0],
        "table_title": "开标报价表",
    },
    {
        "doc_id": "fixture-002",
        "page": 33,
        "tables": [0],
        "table_title": "符合性审查表",
    },
    {
        "doc_id": "fixture-002",
        "page": 37,
        "tables": [0],
        "table_title": "货物清单",
    },
    {
        "doc_id": "fixture-003",
        "page": 29,
        "tables": [0, 1],
        "table_title": "资格审查与符合性审查",
    },
    {
        "doc_id": "fixture-003",
        "page": 35,
        "tables": [0],
        "table_title": "投标报价表",
    },
    {
        "doc_id": "pub-gx-nanning-vascular-doppler",
        "page": 3,
        "tables": [0],
        "table_title": "分标最高限价一览表",
    },
    {
        "doc_id": "pub-gx-nanning-vascular-doppler",
        "page": 16,
        "tables": [1],
        "table_title": "母婴中央监护系统配置清单",
    },
    {
        "doc_id": "pub-gx-nanning-vascular-doppler",
        "page": 17,
        "tables": [1],
        "table_title": "胎儿监护仪配置清单",
    },
    {
        "doc_id": "pub-gx-ventilator-monitors",
        "page": 15,
        "tables": [2, 3],
        "table_title": "遥测与患者监护仪配置清单",
    },
    {
        "doc_id": "pub-gx-daxin-ultrasound-anesthesia",
        "page": 51,
        "tables": [0],
        "table_title": "代理服务费费率表",
    },
    {
        "doc_id": "pub-gx-daxin-ultrasound-anesthesia",
        "page": 73,
        "tables": [0],
        "table_title": "分项报价表",
    },
]


def _clean_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\u00a0", " ").replace("\u3000", " ")
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _text_gt_from_tables(title: str, tables: list[list[list[str]]], *, synthetic: bool = False) -> str:
    lines: list[str] = []
    if synthetic:
        lines.append("【SYNTHETIC 合成样本,非真实招标】")
    if title:
        lines.append(title)
    for rows in tables:
        for row in rows:
            line = " ".join(cell for cell in row if cell)
            if line:
                lines.append(line)
    return "\n".join(lines)


def _html_from_tables(tables: list[list[list[str]]]) -> str:
    return "".join(rows_to_table_html(rows) for rows in tables if rows)


def _extract_tables(pdf_path: Path, page: int, indexes: list[int]) -> list[list[list[str]]]:
    document = fitz.open(pdf_path)
    try:
        pdf_page = document[page - 1]
        found = list(pdf_page.find_tables().tables)
        out: list[list[list[str]]] = []
        for index in indexes:
            if index < 0 or index >= len(found):
                raise ValueError(f"{pdf_path} page {page} missing table index {index}")
            rows = [[_clean_cell(cell) for cell in row] for row in found[index].extract()]
            if len(rows) < 2 or len(rows[0]) < 2:
                raise ValueError(f"{pdf_path} page {page} table {index} is too small")
            out.append(rows)
        return out
    finally:
        document.close()


def _public_record(pick: dict[str, Any], manifest_row: dict[str, Any]) -> dict[str, Any]:
    pdf_path = ROOT / str(manifest_row["path"])
    tables = _extract_tables(pdf_path, int(pick["page"]), list(pick["tables"]))
    title = str(pick["table_title"])
    return {
        "schema_version": "1.0",
        "doc_id": pick["doc_id"],
        "page": int(pick["page"]),
        "page_type": "table",
        "text_gt": _text_gt_from_tables(title, tables),
        "fields": [{"name": "table_title", "value": title}],
        "table_html": _html_from_tables(tables),
        "has_seal": False,
        "has_hw": False,
        "origin": "public",
        "source_url": manifest_row["source_url"],
        "sha256": str(manifest_row["sha256"]).lower(),
        "document_path": manifest_row["path"],
        "table_span": "single_page",
        "notes": "S-A-05 Week-1 single-page complete table. Public government tender. Not T-005.",
    }


def _synthetic_pages() -> list[dict[str, Any]]:
    bid_opening = [
        ["序号", "货物名称", "数量", "投标报价（元）", "交货期"],
        ["1", "彩色多普勒超声诊断系统", "1套", "1780000.00", "合同签订后45日内"],
        ["2", "配套探头及推车", "1套", "120000.00", "合同签订后45日内"],
        ["合计", "", "", "1900000.00", ""],
    ]
    quote = [
        ["序号", "分项名称", "规格型号", "单位", "数量", "单价（元）", "合价（元）"],
        ["1", "主机", "SYNTH-US-A", "台", "1", "1500000.00", "1500000.00"],
        ["2", "腹部探头", "SYNTH-P-ABD", "只", "1", "180000.00", "180000.00"],
        ["3", "浅表探头", "SYNTH-P-LIN", "只", "1", "120000.00", "120000.00"],
        ["4", "安装调试", "含现场培训", "项", "1", "100000.00", "100000.00"],
        ["合计", "", "", "", "", "", "1900000.00"],
    ]
    score = [
        ["序号", "评分因素", "分值", "评分标准"],
        ["1", "投标报价", "30", "满足招标文件。评标价低者得分高。"],
        ["2", "技术参数响应", "40", "带星号条款无负偏离得满分，每项负偏离扣5分。"],
        ["3", "售后服务", "15", "质保期≥3年且4小时响应得满分。"],
        ["4", "实施方案", "15", "供货、安装、验收、培训方案完整可行。"],
        ["合计", "", "100", ""],
    ]
    deviation = [
        ["序号", "招标文件条款", "投标响应", "偏离说明"],
        ["1", "整机质保不少于2年", "整机质保3年", "正偏离"],
        ["2", "交货期45日内", "合同签订后40日内交货", "正偏离"],
        ["3", "提供医疗器械注册证", "提供有效注册证", "无偏离"],
        ["4", "免费培训不少于2日", "免费培训3日", "正偏离"],
    ]
    specs = [
        ( "synthetic-teds-bid-opening", "开标一览表", bid_opening),
        ("synthetic-teds-quote-detail", "报价明细表", quote),
        ("synthetic-teds-score", "综合评分标准表", score),
        ("synthetic-teds-deviation", "技术偏离表", deviation),
    ]
    records: list[dict[str, Any]] = []
    for doc_id, title, rows in specs:
        tables = [rows]
        records.append(
            {
                "schema_version": "1.0",
                "doc_id": doc_id,
                "page": 1,
                "page_type": "table",
                "text_gt": _text_gt_from_tables(title, tables, synthetic=True),
                "fields": [{"name": "table_title", "value": title}],
                "table_html": _html_from_tables(tables),
                "has_seal": False,
                "has_hw": False,
                "origin": "synthetic",
                "table_span": "single_page",
                "notes": "Synthetic sandbox table page. Not a public tender and not enterprise/PII material.",
            }
        )
    return records


def build_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {row["document_id"]: row for row in manifest.get("documents") or []}
    records: list[dict[str, Any]] = []
    for pick in PUBLIC_PICKS:
        manifest_row = by_id.get(pick["doc_id"])
        if not manifest_row:
            raise KeyError(f"manifest missing {pick['doc_id']}")
        records.append(_public_record(pick, manifest_row))
    records.extend(_synthetic_pages())
    return records


def write_jsonl(records: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild S-A-05 TEDS GT JSONL from public PDFs + synthetic pages.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_JSONL)
    args = parser.parse_args(argv)
    if any(token in str(args.out).replace("\\", "/").lower() for token in ("pilot-ledger", "icp-outreach")):
        print(json.dumps({"ok": False, "error": "refusing ledger path"}))
        return 1
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    records = build_records(manifest)
    write_jsonl(records, args.out)
    print(
        json.dumps(
            {
                "ok": True,
                "pages": len(records),
                "public_pages": sum(1 for row in records if row["origin"] == "public"),
                "synthetic_pages": sum(1 for row in records if row["origin"] == "synthetic"),
                "path": str(args.out),
                "product_pass": False,
                "teds_status": "NOT_EVALUATED",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
