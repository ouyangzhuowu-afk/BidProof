import os
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_configured_root = os.environ.get("BIDPROOF_DATA_ROOT")
DATA_DIR = Path(_configured_root).expanduser().resolve() if _configured_root else (PROJECT_ROOT / "work" / "data")
UPLOAD_DIR = DATA_DIR / "uploads" if _configured_root else (PROJECT_ROOT / "work" / "uploads")
DB_PATH = DATA_DIR / "bid_agent.sqlite3"
JOB_STAGING_DIR = DATA_DIR / "job-staging" if _configured_root else (PROJECT_ROOT / "work" / "job-staging")
BACKUP_ROOT = DATA_DIR / "backups" if _configured_root else (PROJECT_ROOT / "work" / "backups")
AUDIT_WORM_ROOT = DATA_DIR / "audit-worm"
ENVIRONMENT = os.environ.get("BIDPROOF_ENV", "development").strip().lower()
_TRUSTED_HEADERS_REQUESTED = os.environ.get("BIDPROOF_ALLOW_TRUSTED_HEADERS", "0").strip().lower() in {"1", "true", "yes"}
# Self-asserted identity headers let any caller claim any workspace and role, so they are a
# test-harness affordance only and are ignored everywhere except BIDPROOF_ENV=test.
ALLOW_TRUSTED_HEADERS = _TRUSTED_HEADERS_REQUESTED and ENVIRONMENT == "test"
TRUSTED_HEADERS_IGNORED = _TRUSTED_HEADERS_REQUESTED and not ALLOW_TRUSTED_HEADERS
BOOTSTRAP_TOKEN = os.environ.get("BIDPROOF_BOOTSTRAP_TOKEN", "").strip()
# When set, unauthenticated users may self-join the primary workspace as REVIEWER.
TRIAL_JOIN_CODE = os.environ.get("BIDPROOF_TRIAL_JOIN_CODE", "").strip()


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes"}


# Personal signup creates an isolated workspace owned by the new account. Enterprise-only
# installs that only want invite / bootstrap / SSO can turn it off.
PERSONAL_SIGNUP = _flag("BIDPROOF_PERSONAL_SIGNUP", "1")


# Tests and local development run jobs in-process so a POST /api/jobs is finished when the
# request returns. Production compose runs `python -m app.worker` against the same database.
JOB_RUNNER = os.environ.get(
    "BIDPROOF_JOB_RUNNER",
    "inline" if ENVIRONMENT != "production" else "worker",
).strip().lower()
JOB_STALE_SECONDS = int(os.environ.get("BIDPROOF_JOB_STALE_SECONDS", "900"))
JOB_POLL_SECONDS = float(os.environ.get("BIDPROOF_JOB_POLL_SECONDS", "1"))
JSON_LOGS = _flag("BIDPROOF_JSON_LOGS", "1" if ENVIRONMENT == "production" else "0")
METRICS_ENABLED = _flag("BIDPROOF_METRICS")
OTEL_ENABLED = _flag("BIDPROOF_OTEL")
LICENSE_KEY = os.environ.get("BIDPROOF_LICENSE_KEY", "").strip()
LICENSE_REQUIRED = _flag("BIDPROOF_LICENSE_REQUIRED")
DATA_REGION = os.environ.get("BIDPROOF_DATA_REGION", "deployment-defined").strip() or "deployment-defined"
PUBLIC_ORIGIN = os.environ.get("BIDPROOF_PUBLIC_ORIGIN", "").strip().rstrip("/")
ALLOWED_HOSTS = tuple(host.strip().lower() for host in os.environ.get("BIDPROOF_ALLOWED_HOSTS", "").split(",") if host.strip())
FEDERATED_WORKSPACE_ID = os.environ.get("BIDPROOF_FEDERATED_WORKSPACE_ID", "").strip()


def validate_runtime_security() -> None:
    """Fail startup before accepting traffic when a production boundary is ambiguous."""
    if ENVIRONMENT not in {"development", "test", "production"}:
        raise RuntimeError("BIDPROOF_ENV must be development, test or production")
    if JOB_RUNNER not in {"inline", "worker"}:
        raise RuntimeError("BIDPROOF_JOB_RUNNER must be inline or worker")
    if JOB_STALE_SECONDS < 60 or not 0.1 <= JOB_POLL_SECONDS <= 60:
        raise RuntimeError("Job lease/poll settings are outside supported bounds")
    if ENVIRONMENT != "production":
        return
    origin = urlsplit(PUBLIC_ORIGIN)
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.path or origin.query or origin.fragment):
        raise RuntimeError("Production requires BIDPROOF_PUBLIC_ORIGIN as an HTTPS origin")
    if not ALLOWED_HOSTS or any("*" in host or "/" in host for host in ALLOWED_HOSTS):
        raise RuntimeError("Production requires explicit BIDPROOF_ALLOWED_HOSTS without wildcards")
    if origin.hostname not in ALLOWED_HOSTS:
        raise RuntimeError("BIDPROOF_PUBLIC_ORIGIN hostname must be in BIDPROOF_ALLOWED_HOSTS")
    if _TRUSTED_HEADERS_REQUESTED:
        raise RuntimeError("Test identity headers must not be configured in production")
    if TRIAL_JOIN_CODE:
        raise RuntimeError("Shared trial join codes are disabled in production")
    if BOOTSTRAP_TOKEN and len(BOOTSTRAP_TOKEN) < 32:
        raise RuntimeError("BIDPROOF_BOOTSTRAP_TOKEN must contain at least 32 characters")
    if JOB_RUNNER != "worker":
        raise RuntimeError("Production requires an independent worker")
    if not os.environ.get("BIDPROOF_DATA_ROOT", "").strip():
        raise RuntimeError("Production requires explicit persistent BIDPROOF_DATA_ROOT")
    from . import directory, oidc

    oidc_settings = oidc.settings_from_env()
    ldap_settings = directory.settings_from_env()
    if oidc_settings.issuer or oidc_settings.client_id:
        oidc.validate_settings(oidc_settings)
    if ldap_settings.server_uri or ldap_settings.user_dn_template:
        directory.validate_settings(ldap_settings)
    if (oidc_settings.enabled or ldap_settings.enabled) and not FEDERATED_WORKSPACE_ID:
        raise RuntimeError("Federated login requires BIDPROOF_FEDERATED_WORKSPACE_ID")

for directory in (DATA_DIR, UPLOAD_DIR, JOB_STAGING_DIR, BACKUP_ROOT, AUDIT_WORM_ROOT):
    directory.mkdir(parents=True, exist_ok=True)
