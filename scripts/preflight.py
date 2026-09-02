#!/usr/bin/env python3
"""Fail-closed checks that a private deployment must pass before serving traffic."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


MINIMUM_PYTHON = (3, 11)
MINIMUM_FREE_BYTES = 512 * 1024 * 1024


def _ok(name: str, detail: str) -> dict:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "ok": False, "detail": detail}


def check_python() -> dict:
    version = sys.version_info
    if version[:2] < MINIMUM_PYTHON:
        return _fail("python", f"need Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+, found {version.major}.{version.minor}")
    return _ok("python", f"{version.major}.{version.minor}.{version.micro}")


def check_data_root() -> dict:
    from app import config

    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = config.DATA_DIR / ".preflight-write"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return _fail("data_root", str(exc))
    usage = shutil.disk_usage(config.DATA_DIR)
    if usage.free < MINIMUM_FREE_BYTES:
        return _fail("disk", f"only {usage.free} bytes free under {config.DATA_DIR}")
    return _ok("data_root", str(config.DATA_DIR))


def check_database() -> dict:
    from app import db, dbctl
    from app.database import configured_url

    url = configured_url()
    if not db.ping():
        return _fail("database", "ping failed")
    try:
        current = dbctl.current_revision(url)
        head = dbctl.head_revision()
    except Exception as exc:  # noqa: BLE001 — preflight must name the failure, not crash
        return _fail("migrations", str(exc))
    if current is None:
        return _fail("migrations", "database has no alembic_version row; run python -m app.dbctl upgrade")
    if current != head:
        return _fail("migrations", f"current={current} head={head}; run python -m app.dbctl upgrade")
    return _ok("database", f"reachable, revision {current}")


def check_license() -> dict:
    from app import config
    from app.license import valid_key

    if not config.LICENSE_REQUIRED:
        return _ok("license", "not required")
    if valid_key(config.LICENSE_KEY):
        return _ok("license", "present")
    return _fail("license", "BIDPROOF_LICENSE_REQUIRED=1 but BIDPROOF_LICENSE_KEY is missing or malformed")


def check_worker_entry() -> dict:
    worker = Path(__file__).resolve().parents[1] / "app" / "worker.py"
    if not worker.is_file():
        return _fail("worker", "app/worker.py missing")
    return _ok("worker", "python -m app.worker")


def run_checks(include_database: bool) -> list[dict]:
    results = [check_python(), check_data_root(), check_worker_entry(), check_license()]
    if include_database:
        results.append(check_database())
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BidProof private-deployment preflight")
    parser.add_argument("--skip-database", action="store_true", help="Skip the live database and Alembic check")
    args = parser.parse_args(argv)
    results = run_checks(include_database=not args.skip_database)
    print(json.dumps({"checks": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
