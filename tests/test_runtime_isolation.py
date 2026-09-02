import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _config_from_subprocess(data_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["BIDPROOF_DATA_ROOT"] = str(data_root)
    command = (
        "import json; from app.config import DATA_DIR, DB_PATH, UPLOAD_DIR, "
        "JOB_STAGING_DIR, BACKUP_ROOT; "
        "print(json.dumps({"
        "'data': str(DATA_DIR), 'db': str(DB_PATH), 'uploads': str(UPLOAD_DIR), "
        "'jobs': str(JOB_STAGING_DIR), 'backups': str(BACKUP_ROOT)}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_runtime_paths_follow_configured_data_root(tmp_path):
    configured = tmp_path / "isolated-runtime"
    paths = _config_from_subprocess(configured)

    assert Path(paths["data"]) == configured
    assert Path(paths["db"]) == configured / "bid_agent.sqlite3"
    assert Path(paths["uploads"]) == configured / "uploads"
    assert Path(paths["jobs"]) == configured / "job-staging"
    assert Path(paths["backups"]) == configured / "backups"


def test_default_runtime_keeps_legacy_pilot_asset_layout(tmp_path):
    environment = os.environ.copy()
    environment.pop("BIDPROOF_DATA_ROOT", None)
    command = (
        "import json; from app.config import PROJECT_ROOT, DATA_DIR, DB_PATH, UPLOAD_DIR, "
        "JOB_STAGING_DIR, BACKUP_ROOT; "
        "print(json.dumps({"
        "'data': str(DATA_DIR), 'db': str(DB_PATH), 'uploads': str(UPLOAD_DIR), "
        "'jobs': str(JOB_STAGING_DIR), 'backups': str(BACKUP_ROOT)}))"
    )
    result = subprocess.run([sys.executable, "-c", command], cwd=ROOT, env=environment, check=True, capture_output=True, text=True)
    paths = json.loads(result.stdout)

    assert Path(paths["data"]) == ROOT / "work" / "data"
    assert Path(paths["db"]) == ROOT / "work" / "data" / "bid_agent.sqlite3"
    assert Path(paths["uploads"]) == ROOT / "work" / "uploads"
    assert Path(paths["jobs"]) == ROOT / "work" / "job-staging"
    assert Path(paths["backups"]) == ROOT / "work" / "backups"


def test_runtime_directories_are_created_under_configured_root(tmp_path):
    configured = tmp_path / "created-runtime"
    paths = _config_from_subprocess(configured)

    assert all(Path(value).parent == configured or Path(value) == configured for value in paths.values())
    assert configured.is_dir()
    assert (configured / "uploads").is_dir()
    assert (configured / "job-staging").is_dir()
    assert (configured / "backups").is_dir()


def test_public_mode_rejects_self_asserted_identity_headers(tmp_path):
    environment = os.environ.copy()
    environment["BIDPROOF_DATA_ROOT"] = str(tmp_path / "public-runtime")
    environment["BIDPROOF_ENV"] = "production"
    environment["BIDPROOF_ALLOW_TRUSTED_HEADERS"] = "0"
    command = (
        "from fastapi.testclient import TestClient; from app.main import app; "
        "client=TestClient(app); "
        "response=client.get('/api/runs', headers={'X-Workspace-ID':'forged','X-User-Role':'OWNER'}); "
        "status=client.get('/api/auth/status').json(); "
        "print(response.status_code, status['setup_required'])"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "401 True"
