"""Projections from stored runs to API and report shapes.

Kept separate from the routes so the response contract is readable in one place and cannot
drift between the run, summary and report views.
"""

from __future__ import annotations

import html
from typing import Any

from .schemas import ReviewRequest


def locator_label(item: dict) -> str:
    return str(item.get("locator", {}).get("label") or "定位缺失")


def page_index(pages: list[dict]) -> list[dict]:
    return [
        {
            "page": page.get("page"),
            "locator": page.get("locator", {"kind": "page", "label": f"第 {page.get('page', '?')} 页", "index": page.get("page")}),
            "char_count": page.get("char_count", len(page.get("text", ""))),
            "ocr_required": bool(page.get("ocr_required", False)),
            "low_text_confidence": bool(page.get("low_text_confidence", False)),
            "ocr_status": page.get("ocr_status", "NOT_REQUIRED"),
            "ocr_provider": page.get("ocr_provider"),
            "ocr_confidence": page.get("ocr_confidence"),
            "block_count": len(page.get("blocks", [])),
        }
        for page in pages
    ]


def scan_quality(tender_pages: list[dict], evidence_pages: list[dict]) -> dict:
    pages = [*tender_pages, *evidence_pages]
    return {
        "total_pages": len(pages),
        "text_pages": sum(bool(page.get("has_text")) for page in pages),
        "ocr_required_pages": sum(bool(page.get("ocr_required")) for page in pages),
        "ocr_failed_pages": sum(page.get("ocr_status") == "FAILED" for page in pages),
        "low_text_confidence_pages": sum(bool(page.get("low_text_confidence")) for page in pages),
        "interpretation": "规则初筛结果，必须结合原文定位和人工复核；OCR 抽取成功不等于语义判断准确。",
    }


def quality_for_run(run: dict) -> dict:
    quality = run.get("state", {}).get("scan_quality", {})
    if quality.get("total_pages") is not None:
        return quality
    total_pages = sum(int(document.get("pages") or 0) for document in run.get("source_documents", []))
    return {
        "total_pages": total_pages,
        "text_pages": total_pages,
        "ocr_required_pages": 0,
        "ocr_failed_pages": 0,
        "low_text_confidence_pages": 0,
        "interpretation": "历史任务未保存逐定位单元的文本质量元数据；结果仍需结合原文定位和人工复核。",
    }


def public_summary(run: dict) -> dict:
    requirements = run.get("requirements", [])
    unresolved = [item for item in requirements if item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"}]
    blockers = [
        item for item in requirements
        if item.get("category") in {"FATAL", "QUALIFICATION"}
        and item.get("status") in {"FAIL", "UNKNOWN", "NEEDS_REVIEW"}
    ]
    return {
        "run_id": run["run_id"],
        "workspace_id": run.get("workspace_id", "local"),
        "owner_id": run.get("owner_id", "local-owner"),
        "parent_run_id": run.get("parent_run_id"),
        "version_number": run.get("version_number", 1),
        "job_id": run.get("job_id"),
        "assignee_id": run.get("assignee_id"),
        "reviewer_id": run.get("reviewer_id"),
        "tags": run.get("tags", []),
        "favorite": bool(run.get("favorite", False)),
        "status": run["status"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "tender_filename": run["tender_filename"],
        "requirement_count": len(requirements),
        "unresolved_count": len(unresolved),
        "blocker_count": len(blockers),
        "fatal_risk_count": sum(1 for item in requirements if item.get("category") == "FATAL"),
        "decision": run.get("decision", {}),
        "archived_at": run.get("archived_at"),
        "scan_quality": quality_for_run(run),
    }


def public_run(run: dict) -> dict:
    return {
        **public_summary(run),
        "workspace_id": run.get("workspace_id", "local"),
        "owner_id": run.get("owner_id", "local-owner"),
        "parent_run_id": run.get("parent_run_id"),
        "version_number": run.get("version_number", 1),
        "job_id": run.get("job_id"),
        "assignee_id": run.get("assignee_id"),
        "reviewer_id": run.get("reviewer_id"),
        "tags": run.get("tags", []),
        "favorite": bool(run.get("favorite", False)),
        "project_id": run.get("project_id"),
        "tender_sha256": run.get("tender_sha256"),
        "duplicate_run_ids": run.get("duplicate_run_ids", []),
        "tender_filename": run["tender_filename"],
        "evidence_files": [
            {key: item[key] for key in ("asset_id", "filename", "file_type", "sha256", "category", "valid_until", "pages") if key in item}
            for item in run.get("evidence_assets", [])
        ],
        "source_documents": run.get("source_documents", []),
        "evidence_assets": run.get("evidence_assets", []),
        "requirements": run["requirements"],
        "review": run["review"],
        "decision": run.get("decision", {}),
        "archived_at": run.get("archived_at"),
        "scan_quality": quality_for_run(run),
        "research_state": run["state"],
    }


def requirement_signature(item: dict) -> tuple[str, str]:
    return (str(item.get("category", "")), " ".join(str(item.get("title", "")).split()).casefold())


def resolve_review_status(payload: ReviewRequest, old_status: str) -> str:
    if payload.decision in {"PASS", "FAIL", "UNKNOWN", "NEEDS_REVIEW"}:
        return payload.decision
    if payload.decision == "CONFIRM":
        return payload.new_status or (old_status if old_status in {"PASS", "FAIL"} else "NEEDS_REVIEW")
    if payload.decision == "REJECT":
        return "NEEDS_REVIEW"
    return "UNKNOWN"


def has_complete_citation(requirement: dict) -> bool:
    """A PASS needs a citation on both sides: the requirement text and the enterprise evidence."""
    source = requirement.get("source", {})
    source_complete = bool(source.get("locator", {}).get("label") and source.get("quote"))
    return source_complete and any(item.get("locator", {}).get("label") and item.get("quote") for item in requirement.get("evidence", []))


def evidence_gap(item: dict) -> str:
    if item.get("status") == "PASS" and item.get("evidence"):
        return "已定位企业证据，仍需人工确认原件有效性"
    if item.get("category") in {"QUALIFICATION", "CREDENTIAL", "BOND", "SIGNATURE"}:
        return "未定位到可核验的企业证据"
    return "该项主要依赖招标原文，需人工确认适用条件"


def risk_impact(item: dict) -> str:
    if item.get("category") == "FATAL":
        return "可能导致废标或资格失效"
    if item.get("category") == "QUALIFICATION":
        return "可能导致资格审查不通过"
    if item.get("category") == "DEADLINE":
        return "错过节点可能导致文件不被接收"
    return "可能影响合规性、评分或材料完整性"


def next_action(item: dict) -> str:
    if item.get("status") in {"UNKNOWN", "NEEDS_REVIEW"}:
        return "补充证据并由人工复核"
    if item.get("status") == "FAIL":
        return "核对原文并制定风险处置方案"
    return "保留原文定位并确认原件有效"


REPORT_COLUMNS = [
    "requirement_id",
    "category",
    "label",
    "status",
    "severity",
    "title",
    "tender_locator",
    "evidence_locators",
    "evidence_gap",
    "risk_impact",
    "next_action",
]


def report_row(item: dict) -> dict[str, Any]:
    return {
        "requirement_id": item.get("requirement_id", ""),
        "category": item.get("category", ""),
        "label": item.get("label", ""),
        "status": item.get("status", ""),
        "severity": item.get("severity", ""),
        "title": item.get("title", ""),
        "tender_locator": locator_label(item.get("source", {})),
        "evidence_locators": "; ".join(f'{entry.get("filename", "")} {locator_label(entry)}' for entry in item.get("evidence", [])),
        "evidence_gap": evidence_gap(item),
        "risk_impact": risk_impact(item),
        "next_action": next_action(item),
    }


def report_html(run: dict) -> str:
    rows = []
    for item in run.get("requirements", []):
        source = item.get("source", {})
        evidence = item.get("evidence", [])
        evidence_locators = "; ".join(f'{entry.get("filename", "")} · {locator_label(entry)}' for entry in evidence) or "未定位"
        rows.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
                item.get("requirement_id", ""), item.get("category", ""), item.get("status", ""), item.get("title", ""),
                locator_label(source), evidence_locators, evidence_gap(item), risk_impact(item), next_action(item),
            ))
            + "</tr>"
        )
    quality = quality_for_run(run)
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>招标证据链报告 - {html.escape(run['tender_filename'])}</title>
<style>body{{font:14px/1.6 Arial,'Microsoft YaHei',sans-serif;color:#1f2937;margin:32px}}h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:17px;margin:28px 0 8px}}.meta{{color:#667085;margin-bottom:20px}}.notice{{border:1px solid #fecdca;background:#fff6f5;padding:12px 14px;margin:16px 0}}.quality{{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}}.quality div{{border:1px solid #e4e7ec;padding:10px}}.quality b{{display:block;font-size:20px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #d0d5dd;padding:8px;vertical-align:top;text-align:left}}th{{background:#f2f4f7}}@media print{{body{{margin:12mm}}.notice{{break-inside:avoid}}}}</style>
<h1>招标证据链报告</h1><div class='meta'>文件：{html.escape(run['tender_filename'])} · 任务：{html.escape(run['run_id'][:12])} · 更新：{html.escape(run['updated_at'])}</div>
<div class='notice'><b>解读边界：</b>本报告是规则初筛和证据索引，不是自动投标结论。没有完整原文定位或存在 OCR 风险的项目必须人工复核。</div>
<h2>扫描质量</h2><div class='quality'><div><b>{quality.get('total_pages', 0)}</b>定位单元</div><div><b>{quality.get('text_pages', 0)}</b>有文本单元</div><div><b>{quality.get('ocr_required_pages', 0)}</b>需 OCR 单元</div><div><b>{quality.get('ocr_failed_pages', 0)}</b>OCR 失败单元</div><div><b>{quality.get('low_text_confidence_pages', 0)}</b>低文本质量单元</div></div>
<h2>逐项核验</h2><table><thead><tr><th>ID</th><th>类别</th><th>状态</th><th>要求与原文摘要</th><th>招标定位</th><th>企业证据定位</th><th>证据缺口</th><th>风险影响</th><th>建议动作</th></tr></thead><tbody>{''.join(rows)}</tbody></table></html>"""
