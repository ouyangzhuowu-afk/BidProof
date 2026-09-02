import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_configured_root = os.environ.get("BIDPROOF_DATA_ROOT")
DATA_DIR = Path(_configured_root).expanduser().resolve() if _configured_root else (PROJECT_ROOT / "work" / "data")
UPLOAD_DIR = DATA_DIR / "uploads" if _configured_root else (PROJECT_ROOT / "work" / "uploads")
DB_PATH = DATA_DIR / "bid_agent.sqlite3"
JOB_STAGING_DIR = DATA_DIR / "job-staging" if _configured_root else (PROJECT_ROOT / "work" / "job-staging")
BACKUP_ROOT = DATA_DIR / "backups" if _configured_root else (PROJECT_ROOT / "work" / "backups")
ALLOW_TRUSTED_HEADERS = os.environ.get("BIDPROOF_ALLOW_TRUSTED_HEADERS", "0").strip().lower() in {"1", "true", "yes"}
ENVIRONMENT = os.environ.get("BIDPROOF_ENV", "development").strip().lower()
BOOTSTRAP_TOKEN = os.environ.get("BIDPROOF_BOOTSTRAP_TOKEN", "").strip()

for directory in (DATA_DIR, UPLOAD_DIR, JOB_STAGING_DIR, BACKUP_ROOT):
    directory.mkdir(parents=True, exist_ok=True)
