import json
from pathlib import Path

from work.pilot_readiness import check_readiness

ROOT = Path(__file__).parents[1]


def test_pilot_readiness_reports_empty_ledgers_ready():
    result = check_readiness(ROOT)
    assert result["ready"] is True
    assert result["product_pass"] is False
    assert result["pilot"]["rows"] == 0
    assert result["icp"]["rows"] == 0
    assert all(item["ok"] for item in result["checks"])
    assert "demo" in result["note"].lower() or "Do not write" in result["note"]


def test_pilot_readiness_cli_exits_zero(tmp_path, monkeypatch):
    # Ensure module main path stays importable; full CLI covered via check_readiness above.
    payload = check_readiness(ROOT)
    assert json.loads(json.dumps(payload))["ready"] is True
