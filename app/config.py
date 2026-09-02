import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_configured_root = os.environ.get("BIDPROOF_DATA_ROOT")
DATA_DIR = Path(_configured_root).expanduser().resolve() if _configured_root else (PROJECT_ROOT / "work" / "data")
UPLOAD_DIR = DATA_DIR / "uploads" if _configured_root else (PROJECT_ROOT / "work" / "uploads")
DB_PATH = DATA_DIR / "bid_agent.sqlite3"
JOB_STAGING_DIR = DATA_DIR / "job-staging" if _configured_root else (PROJECT_ROOT / "work" / "job-staging")
BACKUP_ROOT = DATA_DIR / "backups" if _configured_root else (PROJECT_ROOT / "work" / "backups")
ENVIRONMENT = os.environ.get("BIDPROOF_ENV", "development").strip().lower()
_TRUSTED_HEADERS_REQUESTED = os.environ.get("BIDPROOF_ALLOW_TRUSTED_HEADERS", "0").strip().lower() in {"1", "true", "yes"}
# Self-asserted identity headers let any caller claim any workspace and role, so they are a
# test-harness affordance only and are ignored everywhere except BIDPROOF_ENV=test.
ALLOW_TRUSTED_HEADERS = _TRUSTED_HEADERS_REQUESTED and ENVIRONMENT == "test"
TRUSTED_HEADERS_IGNORED = _TRUSTED_HEADERS_REQUESTED and not ALLOW_TRUSTED_HEADERS
BOOTSTRAP_TOKEN = os.environ.get("BIDPROOF_BOOTSTRAP_TOKEN", "").strip()
# When set, unauthenticated users may self-join the primary workspace as REVIEWER.
TRIAL_JOIN_CODE = os.environ.get("BIDPROOF_TRIAL_JOIN_CODE", "").strip()

for directory in (DATA_DIR, UPLOAD_DIR, JOB_STAGING_DIR, BACKUP_ROOT):
    directory.mkdir(parents=True, exist_ok=True)
