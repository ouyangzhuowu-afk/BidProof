"""Private-delivery artefacts: preflight, helm chart, offline pack, license gate."""

from pathlib import Path
import json
import subprocess
import sys

from app.license import valid_key


ROOT = Path(__file__).resolve().parents[1]


def test_preflight_passes_without_a_live_database():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "preflight.py"), "--skip-database"],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 0
    assert all(item["ok"] for item in payload["checks"])
    assert {item["name"] for item in payload["checks"]} >= {"python", "data_root", "worker", "license"}


def test_helm_chart_and_offline_pack_script_exist():
    chart = ROOT / "deploy" / "helm" / "bidproof"
    assert (chart / "Chart.yaml").is_file()
    assert (chart / "values.yaml").is_file()
    templates = {path.name for path in (chart / "templates").glob("*.yaml")} | {path.name for path in (chart / "templates").glob("*.tpl")}
    assert "deployment.yaml" in templates
    assert "service.yaml" in templates
    assert (ROOT / "scripts" / "pack-offline.sh").is_file()
    assert (ROOT / "docs" / "upgrade.md").is_file()
    assert (ROOT / "docs" / "xinchuang-matrix.md").is_file()
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "python -m app.worker" in compose
    assert "BIDPROOF_JOB_RUNNER: worker" in compose


def test_license_prefix_is_the_only_accepted_shape():
    assert valid_key("bp-lic-customer-estate")
    assert not valid_key("customer-estate")
    assert not valid_key("bp-lic-short")
