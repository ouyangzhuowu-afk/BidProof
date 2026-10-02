"""Side-by-side local vs cloud OCR compare on the frozen public-expand cohort.

Same pages, fields, table subset, and scorer as the expanded public set.
Real HTTP sends only when egress policy (approval + key + allow-list) allows.
Without a cloud API key (or other gate): status APPROVED_NOT_RUN or
BLOCKED_NOT_RUN, zero sends.

Does not claim OCR gate pass, product pass, or T-005 unblock.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.egress_policy import evaluate_cloud_egress, policy_snapshot
from work.eval.cohort_manifest import (
    COHORT_ID,
    DEFAULT_MANIFEST_PATH,
    EXPECTED_CER_DENOM,
    EXPECTED_PAGE_COUNT,
    SCORER_VERSION,
    load_cohort_manifest,
    verify_cohort_manifest,
)
from work.eval.page_annotation import load_annotations
from work.eval.public_expand import (
    CER_GT_PATH,
    CER_HYP_PATH,
    KF_GT_PATH,
    KF_HYP_PATH,
    TEDS_GT_PATH,
    TEDS_HYP_PATH,
    prepare_expanded_cer,
    score_bundle,
)
from work.eval.rapidocr_line_cer import load_hypotheses

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "ocr-benchmark" / "cloud-compare"
LOCAL_DIR = OUT_DIR / "local"
CLOUD_DIR = OUT_DIR / "cloud"
REPORT_JSON = OUT_DIR / "provider-compare-report.json"
REPORT_MD = OUT_DIR / "provider-compare-report.md"

# Documented approval id for Joe's 2026-10-02 written T1/T2 compare purpose.
# Must be set in the environment as BIDPROOF_OCR_EGRESS_APPROVAL to actually send.
DOCUMENTED_APPROVAL_ID = "T1-JOE-CLOUD-COMPARE-2026-10-02"

REQUIRED_ENV_FOR_SEND = [
    "BIDPROOF_OCR_EGRESS_ALLOWED",
    "BIDPROOF_OCR_EGRESS_MODE",
    "BIDPROOF_OCR_EGRESS_APPROVAL",
    "QWEN_OCR_API_KEY",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_run_status(*, policy_allowed: bool, api_key_present: bool, approval_present: bool) -> str:
    """Return RUN | APPROVED_NOT_RUN | BLOCKED_NOT_RUN."""
    if policy_allowed and api_key_present:
        return "RUN"
    # Joe approved the purpose in writing (decision recorded). Missing keys/switch
    # means we do not send — APPROVED_NOT_RUN rather than inventing sends.
    if approval_present or os.getenv("BIDPROOF_OCR_COMPARE_PURPOSE_APPROVED", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return "APPROVED_NOT_RUN"
    # Decision is recorded in workflow; default for this leaf is approved purpose.
    # Still BLOCKED when egress master switch was never contemplated / policy hard-deny.
    decision = evaluate_cloud_egress()
    if decision.reason in {"egress_disabled", "egress_mode_never", "no_auth_approval", "no_auth_api_key"}:
        # Purpose approval is recorded in-repo; treat missing runtime config as APPROVED_NOT_RUN.
        return "APPROVED_NOT_RUN"
    return "BLOCKED_NOT_RUN"


def page_failure_record(
    *,
    doc_id: str,
    page: int,
    provider: str,
    reason: str,
    kept_in_denominator: bool = True,
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "page": page,
        "provider": provider,
        "failure_reason": reason,
        "kept_in_denominator": kept_in_denominator,
    }


def score_local_baseline() -> dict[str, Any]:
    """Score committed RapidOCR hypotheses against frozen GT (no egress)."""
    scored = score_bundle(
        load_annotations(CER_GT_PATH),
        load_hypotheses(CER_HYP_PATH),
        load_annotations(TEDS_GT_PATH),
        [
            json.loads(line)
            for line in TEDS_HYP_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ],
        load_annotations(KF_GT_PATH),
        [
            json.loads(line)
            for line in KF_HYP_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ],
        prepare_cer=prepare_expanded_cer,
    )
    return {
        "provider": "rapidocr_onnxruntime",
        "source": "committed_hypotheses",
        "egress_sends": 0,
        **scored,
    }


def attempt_cloud_predict(
    *,
    cohort: dict[str, Any],
    send_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run cloud OCR only when policy allows; otherwise zero sends.

    ``send_fn`` is injectable for tests. Real default refuses unless policy
    permits and a key exists; this module never invents HTTP without that gate.
    """
    endpoint = os.getenv(
        "QWEN_OCR_ENDPOINT",
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    decision = evaluate_cloud_egress(endpoint=endpoint)
    snapshot = policy_snapshot()
    status = classify_run_status(
        policy_allowed=decision.allowed,
        api_key_present=bool(snapshot.get("api_key_present")),
        approval_present=bool(snapshot.get("approval_present")),
    )

    result: dict[str, Any] = {
        "provider": "qwen-vl-ocr",
        "status": status,
        "egress_sends": 0,
        "egress_decision": {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "mode": decision.mode,
            "approval_id": decision.approval_id,
            "endpoint_host": decision.endpoint_host,
        },
        "policy": snapshot,
        "page_failures": [],
        "hypotheses": [],
        "scored": None,
        "note": "",
    }

    if status != "RUN" or not decision.allowed:
        # Keep every frozen page in the denominator with an explicit skip reason.
        skip_reason = decision.reason if not decision.allowed else "compare_not_run"
        for page in cohort.get("pages") or []:
            result["page_failures"].append(
                page_failure_record(
                    doc_id=str(page.get("doc_id")),
                    page=int(page.get("page") or 0),
                    provider="qwen-vl-ocr",
                    reason=f"not_sent:{skip_reason}",
                )
            )
        result["note"] = (
            f"{status}: zero cloud HTTP sends. "
            "Set BIDPROOF_OCR_EGRESS_ALLOWED=1, BIDPROOF_OCR_EGRESS_MODE=redacted_only|vpc_private, "
            f"BIDPROOF_OCR_EGRESS_APPROVAL={DOCUMENTED_APPROVAL_ID} (or another T1-/T2- token), "
            "and QWEN_OCR_API_KEY before a live compare."
        )
        return result

    if send_fn is None:
        # Live path reserved: do not silently call cloud from CI without an explicit
        # --live flag wiring. Treat missing send_fn as approved-but-not-wired.
        for page in cohort.get("pages") or []:
            result["page_failures"].append(
                page_failure_record(
                    doc_id=str(page.get("doc_id")),
                    page=int(page.get("page") or 0),
                    provider="qwen-vl-ocr",
                    reason="not_sent:live_sender_not_wired",
                )
            )
        result["status"] = "APPROVED_NOT_RUN"
        result["egress_sends"] = 0
        result["note"] = (
            "Policy would allow send, but this runner requires an explicit live sender "
            "bound by the operator. Zero sends in this invocation."
        )
        return result

    sends = 0
    for page in cohort.get("pages") or []:
        doc_id = str(page.get("doc_id"))
        page_no = int(page.get("page") or 0)
        try:
            hyp = send_fn(doc_id=doc_id, page=page_no, pdf_sha256=page.get("pdf_sha256"))
            sends += 1
            if not hyp or not str(hyp.get("text_hyp") or "").strip():
                result["page_failures"].append(
                    page_failure_record(
                        doc_id=doc_id,
                        page=page_no,
                        provider="qwen-vl-ocr",
                        reason="cloud_empty_text",
                    )
                )
                result["hypotheses"].append(
                    {
                        "doc_id": doc_id,
                        "page": page_no,
                        "text_hyp": "",
                        "lines_hyp": [],
                        "failure_reason": "cloud_empty_text",
                        "hypothesis_source": "qwen-vl-ocr",
                    }
                )
            else:
                result["hypotheses"].append(
                    {
                        "doc_id": doc_id,
                        "page": page_no,
                        "text_hyp": hyp.get("text_hyp"),
                        "lines_hyp": hyp.get("lines_hyp") or [],
                        "hypothesis_source": "qwen-vl-ocr",
                    }
                )
        except Exception as exc:  # noqa: BLE001 — keep page in denom with reason
            result["page_failures"].append(
                page_failure_record(
                    doc_id=doc_id,
                    page=page_no,
                    provider="qwen-vl-ocr",
                    reason=f"cloud_error:{type(exc).__name__}",
                )
            )
            result["hypotheses"].append(
                {
                    "doc_id": doc_id,
                    "page": page_no,
                    "text_hyp": "",
                    "lines_hyp": [],
                    "failure_reason": f"cloud_error:{type(exc).__name__}",
                    "hypothesis_source": "qwen-vl-ocr",
                }
            )
    result["egress_sends"] = sends
    return result


def build_compare_report(
    *,
    cohort: dict[str, Any] | None = None,
    send_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cohort = cohort or load_cohort_manifest()
    integrity = verify_cohort_manifest(cohort)
    local = score_local_baseline()
    cloud = attempt_cloud_predict(cohort=cohort, send_fn=send_fn)

    report = {
        "leaf_id": "S-A-OCR-CLOUD-COMPARE",
        "generated_at": _utcnow(),
        "cohort_id": cohort.get("cohort_id", COHORT_ID),
        "mainline_baseline": cohort.get("mainline_baseline"),
        "scorer_version": SCORER_VERSION,
        "page_count": cohort.get("page_count", EXPECTED_PAGE_COUNT),
        "cer_denominator_chars": cohort.get("cer_denominator_chars", EXPECTED_CER_DENOM),
        "integrity": integrity,
        "run_status": cloud["status"],
        "egress_sends_total": int(cloud.get("egress_sends") or 0),
        "product_pass": False,
        "business_pass": False,
        "t005": "unchanged",
        "claim_scope": "engineering_compare_only",
        "teds_note": cohort.get("teds_note"),
        "documented_approval_id": DOCUMENTED_APPROVAL_ID,
        "required_env_for_send": REQUIRED_ENV_FOR_SEND
        + [
            "BIDPROOF_OCR_EGRESS_APPROVAL_EXPIRES_AT (optional)",
            "BIDPROOF_OCR_EGRESS_DOC_SHA256 (optional pin)",
            "BIDPROOF_OCR_EGRESS_ALLOWED_HOSTS (optional; defaults to DashScope/VPC OCR hosts)",
            "QWEN_OCR_ENDPOINT (optional)",
        ],
        "local": {
            "provider": local["provider"],
            "egress_sends": 0,
            "line_cer": local["line_cer"],
            "line_cer_gate": local["line_cer_gate"],
            "key_field_f1": local["key_field_f1"],
            "key_field_f1_gate": local["key_field_f1_gate"],
            "teds": local["teds"],
            "teds_gate": local["teds_gate"],
            "line_cer_pages": local["line_cer_pages"],
            "teds_pages_scored": local["teds_pages_scored"],
        },
        "cloud": {
            "provider": cloud["provider"],
            "status": cloud["status"],
            "egress_sends": cloud["egress_sends"],
            "egress_decision": cloud["egress_decision"],
            "policy": cloud["policy"],
            "page_failures": cloud["page_failures"],
            "note": cloud["note"],
            "scored": cloud.get("scored"),
        },
        "side_by_side": {
            "same_pages": True,
            "same_fields": True,
            "same_table_subset": True,
            "same_scorer": SCORER_VERSION,
            "pages_dropped_from_denominator": 0,
        },
        "gate_claim": "NOT_CLAIMED",
        "note": (
            "Cloud compare infrastructure + frozen cohort. "
            "Does not claim OCR GATE_PASS, product PASS, or T-005 unblock. "
            "Mainline baseline scores remain the published RapidOCR expanded set."
        ),
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    local = report["local"]
    cloud = report["cloud"]

    def pct(value: float | None) -> str:
        if value is None:
            return "n/a"
        return f"{value * 100:.2f}%"

    lines = [
        "# OCR provider compare (frozen public-expand cohort)",
        "",
        "Engineering compare only. Not a product PASS, not T-005, not business acceptance.",
        "TEDS uses PDF table ruling-line assist for cell placement; that is documented and is not a pure E2E OCR table score.",
        "",
        f"- Run status: **{report['run_status']}**",
        f"- Cohort: `{report['cohort_id']}` · pages **{report['page_count']}** · CER denom **{report['cer_denominator_chars']}**",
        f"- Scorer: `{report['scorer_version']}` · mainline baseline `{report['mainline_baseline']}`",
        f"- Cloud HTTP sends: **{report['egress_sends_total']}**",
        f"- Documented approval id (set as env to send): `{report['documented_approval_id']}`",
        "",
        "## Side-by-side",
        "",
        "| Provider | CER | CER gate | F1 | F1 gate | TEDS | TEDS gate | sends |",
        "|---|---:|---|---:|---|---:|---|---:|",
        (
            f"| Local RapidOCR (committed) | {pct(local.get('line_cer'))} | {local.get('line_cer_gate')} | "
            f"{pct(local.get('key_field_f1'))} | {local.get('key_field_f1_gate')} | "
            f"{pct(local.get('teds'))} | {local.get('teds_gate')} | 0 |"
        ),
        (
            f"| Cloud Qwen-VL-OCR | "
            f"{'n/a' if cloud.get('scored') is None else pct((cloud.get('scored') or {}).get('line_cer'))} | "
            f"{'NOT_RUN' if cloud.get('scored') is None else (cloud.get('scored') or {}).get('line_cer_gate')} | "
            f"{'n/a' if cloud.get('scored') is None else pct((cloud.get('scored') or {}).get('key_field_f1'))} | "
            f"{'NOT_RUN' if cloud.get('scored') is None else (cloud.get('scored') or {}).get('key_field_f1_gate')} | "
            f"{'n/a' if cloud.get('scored') is None else pct((cloud.get('scored') or {}).get('teds'))} | "
            f"{'NOT_RUN' if cloud.get('scored') is None else (cloud.get('scored') or {}).get('teds_gate')} | "
            f"{cloud.get('egress_sends', 0)} |"
        ),
        "",
        f"Gate claim: **{report['gate_claim']}**. `product_pass=false`.",
        "",
        "## Env vars Joe must set (Render / local) for a live send",
        "",
    ]
    for item in report["required_env_for_send"]:
        lines.append(f"- `{item}`")
    lines += [
        "",
        "## Cloud skip / page failures",
        "",
        cloud.get("note") or "(none)",
        "",
        f"Page-level failure rows: **{len(cloud.get('page_failures') or [])}** "
        "(pages remain in the CER denominator).",
        "",
        f"Generated at `{report['generated_at']}`.",
        "",
    ]
    return "\n".join(lines)


def write_reports(report: dict[str, Any]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    CLOUD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")
    (LOCAL_DIR / "baseline.json").write_text(
        json.dumps(report["local"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (CLOUD_DIR / "result.json").write_text(
        json.dumps(report["cloud"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local vs cloud OCR compare on frozen cohort.")
    parser.add_argument("--run", action="store_true", help="Run compare (cloud only if policy+key allow).")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to frozen cohort manifest.",
    )
    args = parser.parse_args(argv)
    if not args.run:
        parser.print_help()
        return 1
    cohort = load_cohort_manifest(args.manifest)
    report = build_compare_report(cohort=cohort, send_fn=None)
    write_reports(report)
    print(
        json.dumps(
            {
                "run_status": report["run_status"],
                "egress_sends_total": report["egress_sends_total"],
                "page_count": report["page_count"],
                "cer_denominator_chars": report["cer_denominator_chars"],
                "local_line_cer": report["local"]["line_cer"],
                "product_pass": False,
                "gate_claim": report["gate_claim"],
                "report_json": str(REPORT_JSON),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
