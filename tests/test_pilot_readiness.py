import csv
import json
import subprocess
import sys
from pathlib import Path

from work.icp_ledger import REQUIRED_FIELDS as ICP_FIELDS
from work.pilot_ledger import REQUIRED_FIELDS as PILOT_FIELDS
from work.pilot_readiness import check_readiness

ROOT = Path(__file__).parents[1]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _scaffold(tmp_path: Path, *, pilot_rows: int, icp_rows: int) -> Path:
    root = tmp_path / "fixture-project"
    (root / "work").mkdir(parents=True)
    (root / "docs" / "pilot").mkdir(parents=True)
    for name in ("pilot-row.template.json", "icp-row.template.json"):
        (root / "work" / name).write_text(
            (ROOT / "work" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (root / "docs" / "pilot" / "t005-intake-checklist.md").write_text(
        "fixture intake checklist\n",
        encoding="utf-8",
    )
    _write_csv(
        root / "outputs" / "pilot-ledger.csv",
        PILOT_FIELDS,
        [{field: f"pilot-{index}" for field in PILOT_FIELDS} for index in range(pilot_rows)],
    )
    _write_csv(
        root / "outputs" / "icp-outreach.csv",
        ICP_FIELDS,
        [{field: f"icp-{index}" for field in ICP_FIELDS} for index in range(icp_rows)],
    )
    return root


def test_pilot_readiness_counts_fixture_ledgers_not_the_repo_files(tmp_path):
    root = _scaffold(tmp_path, pilot_rows=1, icp_rows=2)
    result = check_readiness(root)
    assert result["ready"] is True
    assert result["product_pass"] is False
    assert result["pilot"]["rows"] == 1
    assert result["icp"]["rows"] == 2
    assert all(item["ok"] for item in result["checks"])
    assert "NEEDS_REVIEW" in result["note"]
    assert "accuracy acceptance" in result["note"]
    assert "scaffold-only" in result["note"]


def test_pilot_readiness_cli_exits_zero():
    completed = subprocess.run(
        [sys.executable, "-m", "work.pilot_readiness", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ready"] is True
    assert payload["product_pass"] is False
    assert "NEEDS_REVIEW" in payload["note"]
    assert "checks" in payload
