from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initial_research_state(run_id: str) -> dict[str, Any]:
    return {
        "runtime_contract_version": "1.0",
        "run_id": run_id,
        "status": "FRAME",
        "run_stage": "INTAKE",
        "research_brief": {
            "topic": "投标资格与废标风险扫描",
            "decision_to_support": "判断企业是否值得继续投入本次投标准备",
            "scope": "IT 服务、软件实施类公开采购文件",
            "constraints": ["结果必须可定位到原文页码", "不能替代人工投标决策"],
        },
        "research_map": [
            {"branch": "资格条件", "status": "PENDING"},
            {"branch": "废标/否决条款", "status": "PENDING"},
            {"branch": "评分项与关键日期", "status": "PENDING"},
            {"branch": "企业证据匹配", "status": "PENDING"},
        ],
        "assumption_log": [],
        "source_registry": [],
        "source_documents": [],
        "evidence_assets": [],
        "evidence_matrix": [],
        "review_events": [],
        "decision_record": {},
        "contradiction_log": [],
        "working_findings": [],
        "open_questions": [],
        "decision_matrix": [],
        "action_plan": [],
        "research_backlog": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def advance_state(state: dict[str, Any], status: str) -> dict[str, Any]:
    state["status"] = status
    state["run_stage"] = {
        "FRAME": "INTAKE",
        "AUDIT": "SCAN",
        "SYNTHESIZE": "DECISION",
    }.get(status, state.get("run_stage", "REVIEW"))
    state["updated_at"] = utc_now()
    return state
