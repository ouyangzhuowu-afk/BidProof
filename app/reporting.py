from datetime import datetime, timezone
from typing import Any


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 44
CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2
FONT_NAME = "china-s"


def build_pdf_report(run: dict[str, Any]) -> bytes:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF report runtime is unavailable") from exc

    document = fitz.open()
    page = _new_page(document, "BidProof 投标证据链报告")
    y = 82
    requirements = run.get("requirements", [])
    unresolved = sum(item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"} for item in requirements)
    blockers = sum(item.get("category") in {"FATAL", "QUALIFICATION"} and item.get("status") != "PASS" for item in requirements)
    decision = run.get("decision", {}).get("decision") or "未记录"
    summary_lines = [
        f"招标文件：{run.get('tender_filename', '')}",
        f"任务编号：{run.get('run_id', '')}",
        f"版本：v{run.get('version_number', 1)}    要求项：{len(requirements)}    高风险：{blockers}    待复核：{unresolved}",
        f"人工决定：{decision}",
        "结论边界：本报告是规则初筛与证据索引，必须由授权人员复核；规则分值不是校准概率。",
    ]
    for line in summary_lines:
        y = _write_wrapped(page, line, y, 10.5, 14)
    y += 8

    for index, item in enumerate(requirements, 1):
        source = item.get("source", {})
        evidence = item.get("evidence", [])
        evidence_text = "；".join(
            f"{entry.get('filename', '')} {_locator_label(entry)}：{_clean(entry.get('quote', ''))}"
            for entry in evidence
        ) or "未定位到企业证据"
        lines = [
            f"{item.get('requirement_id', f'REQ-{index:04d}')}  [{item.get('category', '')}]  {item.get('status', '')} / {item.get('severity', '')}",
            f"要求：{_clean(item.get('title', ''))}",
            f"招标定位：{_locator_label(source)}；原文：{_clean(source.get('quote', ''))}",
            f"企业证据：{evidence_text}",
            f"证据缺口：{_evidence_gap(item)}；风险影响：{_risk_impact(item)}；建议动作：{_next_action(item)}",
        ]
        wrapped = [chunk for line in lines for chunk in _wrap(line, 62)]
        block_height = 18 + len(wrapped) * 12
        if y + block_height > PAGE_HEIGHT - 48:
            page = _new_page(document, "要求项明细（续）")
            y = 76
        page.draw_rect((MARGIN, y - 4, PAGE_WIDTH - MARGIN, y + block_height - 4), color=(0.82, 0.85, 0.88), width=0.6)
        for line_index, line in enumerate(wrapped):
            page.insert_text((MARGIN + 8, y + line_index * 12), line, fontsize=8.5 if line_index else 9.5, fontname=FONT_NAME, color=(0.12, 0.15, 0.18))
        y += block_height + 7

    generated_at = datetime.now(timezone.utc).isoformat()
    for page_index, report_page in enumerate(document, 1):
        report_page.insert_text((MARGIN, PAGE_HEIGHT - 24), f"生成时间 {generated_at}    第 {page_index}/{document.page_count} 页", fontsize=7.5, fontname=FONT_NAME, color=(0.35, 0.38, 0.42))
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def _new_page(document, title: str):
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_text((MARGIN, 44), title, fontsize=16, fontname=FONT_NAME, color=(0.05, 0.10, 0.16))
    page.draw_line((MARGIN, 56), (PAGE_WIDTH - MARGIN, 56), color=(0.25, 0.52, 0.55), width=1.2)
    return page


def _write_wrapped(page, text: str, y: float, fontsize: float, line_height: float) -> float:
    for line in _wrap(text, 68):
        page.insert_text((MARGIN, y), line, fontsize=fontsize, fontname=FONT_NAME, color=(0.12, 0.15, 0.18))
        y += line_height
    return y


def _wrap(value: str, limit: int) -> list[str]:
    cleaned = _clean(value)
    return [cleaned[index:index + limit] for index in range(0, len(cleaned), limit)] or [""]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _locator_label(item: dict[str, Any]) -> str:
    return str(item.get("locator", {}).get("label") or "定位缺失")


def _evidence_gap(item: dict[str, Any]) -> str:
    if item.get("status") == "PASS" and item.get("evidence"):
        return "已定位证据，仍需核验原件与有效期"
    if item.get("category") in {"QUALIFICATION", "CREDENTIAL", "BOND", "SIGNATURE"}:
        return "未定位到可核验的企业证据"
    return "需人工确认适用条件"


def _risk_impact(item: dict[str, Any]) -> str:
    return {
        "FATAL": "可能导致废标或资格失效",
        "QUALIFICATION": "可能导致资格审查不通过",
        "DEADLINE": "错过节点可能导致文件不被接收",
    }.get(item.get("category"), "可能影响合规性、评分或材料完整性")


def _next_action(item: dict[str, Any]) -> str:
    if item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"}:
        return "补充证据并由人工复核"
    if item.get("status") == "FAIL":
        return "核对原文并制定风险处置方案"
    return "保留定位引用并确认原件有效"
