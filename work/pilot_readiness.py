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


def _label(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _header_ok(path: Path, expected: list[str], project_root: Path) -> tuple[bool, str]:
    label = _label(path, project_root)
    if not path.exists():
        return False, f"missing {label}"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != expected:
            return False, f"header mismatch in {label}"
        rows = list(reader)
    return True, f"{label} header ok; rows={len(rows)}"


def _template_ok(path: Path, required_keys: list[str], project_root: Path) -> tuple[bool, str]:
    label = _label(path, project_root)
    if not path.exists():
        return False, f"missing {label}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON in {label}: {exc}"
    if not isinstance(payload, dict):
        return False, f"{label} must be a JSON object"
    missing = [key for key in required_keys if key not in payload]
    if missing:
        return False, f"{label} missing keys: {', '.join(missing)}"
    return True, f"{label} keys ok"


def check_readiness(project_root: Path = ROOT) -> dict[str, Any]:
    """Return engineering readiness; never writes pilot/ICP business rows."""
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    ok, detail = _template_ok(
        project_root / "work" / "pilot-row.template.json",
        pilot_ledger.REQUIRED_FIELDS,
        project_root,
    )
    record("pilot_template", ok, detail)
    ok, detail = _template_ok(
        project_root / "work" / "icp-row.template.json",
        icp_ledger.REQUIRED_FIELDS,
        project_root,
    )
    record("icp_template", ok, detail)
    ok, detail = _header_ok(
        project_root / "outputs" / "pilot-ledger.csv",
        pilot_ledger.REQUIRED_FIELDS,
        project_root,
    )
    record("pilot_ledger", ok, detail)
    ok, detail = _header_ok(
        project_root / "outputs" / "icp-outreach.csv",
        icp_ledger.REQUIRED_FIELDS,
        project_root,
    )
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
            "scaffold-only. Engineering scaffolds only; this is not a business unblock. "
            "Pilot scan results are always NEEDS_REVIEW and cannot count as accuracy acceptance. "
            "Do not write demo or test rows."
        ),
        "pilot": pilot_summary,
        "icp": icp_summary,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check T-005 pilot/ICP ledger readiness without writing rows")
    parser.add_argument("--json", action="store_true", help="Print the readiness report as JSON")
    parser.parse_args(argv)
    result = check_readiness()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
