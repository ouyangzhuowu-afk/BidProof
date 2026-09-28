"""Fail-closed readiness check for T-005 pilot / ICP ledgers (no fake rows)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from work import icp_ledger, pilot_ledger

ROOT = Path(__file__).resolve().parents[1]

PILOT_TEMPLATE = ROOT / "work" / "pilot-row.template.json"
ICP_TEMPLATE = ROOT / "work" / "icp-row.template.json"
PILOT_LEDGER = ROOT / "outputs" / "pilot-ledger.csv"
ICP_LEDGER = ROOT / "outputs" / "icp-outreach.csv"
INTAKE_CHECKLIST = ROOT / "docs" / "pilot" / "t005-intake-checklist.md"


def _header_ok(path: Path, expected: list[str]) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path.relative_to(ROOT)}"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected:
            return False, f"header mismatch in {path.relative_to(ROOT)}"
        rows = list(reader)
    return True, f"{path.relative_to(ROOT)} header ok; rows={len(rows)}"


def _template_ok(path: Path, required_keys: list[str]) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing {path.relative_to(ROOT)}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON in {path.relative_to(ROOT)}: {exc}"
    if not isinstance(payload, dict):
        return False, f"{path.relative_to(ROOT)} must be a JSON object"
    missing = [key for key in required_keys if key not in payload]
    if missing:
        return False, f"{path.relative_to(ROOT)} missing keys: {', '.join(missing)}"
    return True, f"{path.relative_to(ROOT)} keys ok"


def check_readiness(project_root: Path = ROOT) -> dict[str, Any]:
    """Return engineering readiness; never writes pilot/ICP business rows."""
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    ok, detail = _template_ok(project_root / "work" / "pilot-row.template.json", pilot_ledger.REQUIRED_FIELDS)
    record("pilot_template", ok, detail)
    ok, detail = _template_ok(project_root / "work" / "icp-row.template.json", icp_ledger.REQUIRED_FIELDS)
    record("icp_template", ok, detail)
    ok, detail = _header_ok(project_root / "outputs" / "pilot-ledger.csv", pilot_ledger.REQUIRED_FIELDS)
    record("pilot_ledger", ok, detail)
    ok, detail = _header_ok(project_root / "outputs" / "icp-outreach.csv", icp_ledger.REQUIRED_FIELDS)
    record("icp_ledger", ok, detail)

    checklist = project_root / "docs" / "pilot" / "t005-intake-checklist.md"
    record(
        "intake_checklist",
        checklist.exists(),
        f"{checklist.relative_to(project_root)} {'present' if checklist.exists() else 'missing'}",
    )

    pilot_summary = pilot_ledger.summarize_file(project_root / "outputs" / "pilot-ledger.csv")
    icp_summary = icp_ledger.summarize_file(project_root / "outputs" / "icp-outreach.csv")
    ready = all(item["ok"] for item in checks)
    return {
        "ready": ready,
        "product_pass": False,
        "note": (
            "Engineering scaffolds only. Empty ledgers are expected until Joe provides "
            "real enterprise pilot / ICP inputs. Do not write demo or test rows."
        ),
        "pilot": pilot_summary,
        "icp": icp_summary,
        "checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check T-005 pilot/ICP ledger readiness without writing rows")
    parser.parse_args()
    result = check_readiness()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
