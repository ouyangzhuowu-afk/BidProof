"""Create, verify and restore BidProof backups.

SQLite copies are self-contained files. PostgreSQL deployments dump with `pg_dump` (custom
format) so a restore is a `pg_restore` rather than a file copy. The manifest records which
engine produced the archive so the wrong restore path cannot be applied silently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import BACKUP_ROOT, DB_PATH, UPLOAD_DIR
from app.database import configured_url, is_sqlite


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _libpq_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+psycopg2://", "postgresql://", 1)
    )


def backup_engine(source_db: Path = DB_PATH) -> str:
    """SQLite unless this call is targeting the configured production database on PostgreSQL."""
    if source_db != DB_PATH:
        return "sqlite"
    return "sqlite" if is_sqlite(configured_url()) else "postgresql"


def _dump_postgres(url: str, target: Path) -> None:
    result = subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(target), _libpq_url(url)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pg_dump failed")


def _restore_postgres(url: str, dump_file: Path) -> None:
    result = subprocess.run(
        ["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", _libpq_url(url), str(dump_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "pg_restore failed")


def _archive_uploads(uploads_dir: Path, uploads_zip: Path) -> int:
    upload_files = [path for path in uploads_dir.rglob("*") if path.is_file()] if uploads_dir.exists() else []
    with zipfile.ZipFile(uploads_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(upload_files):
            archive.write(path, path.relative_to(uploads_dir))
    return len(upload_files)


def _new_backup_dir(backup_root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counter = 0
    while True:
        target = backup_root / (timestamp if counter == 0 else f"{timestamp}-{counter:02d}")
        try:
            target.mkdir(exist_ok=False)
            return target
        except FileExistsError:
            counter += 1


def create_backup(source_db: Path = DB_PATH, uploads_dir: Path = UPLOAD_DIR, backup_root: Path | None = None) -> Path:
    backup_root = backup_root or BACKUP_ROOT
    backup_root.mkdir(parents=True, exist_ok=True)
    target = _new_backup_dir(backup_root)
    engine = backup_engine(source_db)
    if engine == "postgresql":
        db_copy = target / "database.dump"
        _dump_postgres(configured_url(), db_copy)
    else:
        db_copy = target / "bidproof.sqlite3"
        with sqlite3.connect(source_db) as source, sqlite3.connect(db_copy) as destination:
            source.backup(destination)
    uploads_zip = target / "uploads.zip"
    upload_file_count = _archive_uploads(uploads_dir, uploads_zip)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "database_sha256": _sha256(db_copy),
        "uploads_sha256": _sha256(uploads_zip),
        "database_file": db_copy.name,
        "uploads_file": uploads_zip.name,
        "upload_file_count": upload_file_count,
        "database_size_bytes": db_copy.stat().st_size,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def verify_backup(backup_dir: Path) -> dict:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return {"valid": False, "error": "manifest missing"}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    db_path = backup_dir / manifest["database_file"]
    uploads_path = backup_dir / manifest["uploads_file"]
    valid = db_path.exists() and uploads_path.exists() and _sha256(db_path) == manifest["database_sha256"] and _sha256(uploads_path) == manifest["uploads_sha256"]
    engine = manifest.get("engine", "sqlite")
    if valid and engine == "sqlite":
        db = sqlite3.connect(db_path)
        try:
            valid = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            db.close()
    return {"valid": valid, "manifest": manifest}


def record_backup_verification(backup_dir: Path) -> dict:
    result = verify_backup(backup_dir)
    record = {
        **result,
        "backup_id": backup_dir.name,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    (backup_dir / "verification.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def list_backup_records(backup_root: Path | None = None) -> list[dict]:
    backup_root = backup_root or BACKUP_ROOT
    if not backup_root.exists():
        return []
    records = []
    for backup_dir in sorted((path for path in backup_root.iterdir() if path.is_dir()), reverse=True):
        manifest_path = backup_dir / "manifest.json"
        verification_path = backup_dir / "verification.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            verification = json.loads(verification_path.read_text(encoding="utf-8")) if verification_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            continue
        records.append({
            "backup_id": backup_dir.name,
            "created_at": manifest.get("created_at"),
            "engine": manifest.get("engine", "sqlite"),
            "verified_at": verification.get("verified_at"),
            "valid": bool(verification.get("valid", False)),
            "database_sha256": manifest.get("database_sha256"),
            "uploads_sha256": manifest.get("uploads_sha256"),
        })
    return records


def restore_backup(backup_dir: Path, target_db: Path, target_uploads: Path, database_url: str | None = None) -> dict:
    verification = verify_backup(backup_dir)
    if not verification["valid"]:
        raise ValueError("backup verification failed")
    manifest = verification["manifest"]
    engine = manifest.get("engine", "sqlite")
    target_uploads.mkdir(parents=True, exist_ok=True)
    if engine == "postgresql":
        _restore_postgres(database_url or configured_url(), backup_dir / manifest["database_file"])
        extracted_files = _extract_uploads(backup_dir / manifest["uploads_file"], target_uploads)
        return {"database_integrity": "ok", "upload_file_count": extracted_files}
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target_db.parent) as temp_name:
        candidate_db = Path(temp_name) / target_db.name
        shutil.copy2(backup_dir / manifest["database_file"], candidate_db)
        db = sqlite3.connect(candidate_db)
        try:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("restored database integrity check failed")
        finally:
            db.close()
        shutil.copy2(candidate_db, target_db)
    extracted_files = _extract_uploads(backup_dir / manifest["uploads_file"], target_uploads)
    return {"database_integrity": "ok", "upload_file_count": extracted_files}


def _extract_uploads(archive_path: Path, target_uploads: Path) -> int:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = (target_uploads / member.filename).resolve()
            if target_uploads.resolve() not in destination.parents and destination != target_uploads.resolve():
                raise ValueError("unsafe backup entry")
        archive.extractall(target_uploads)
        return sum(1 for member in archive.infolist() if not member.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create, verify, or restore a BidProof backup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create")
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup_dir", type=Path)
    restore = subparsers.add_parser("restore")
    restore.add_argument("backup_dir", type=Path)
    restore.add_argument("--target-db", type=Path, required=True)
    restore.add_argument("--target-uploads", type=Path, required=True)
    restore.add_argument("--database-url", default=None, help="PostgreSQL URL when restoring a pg_dump archive")
    args = parser.parse_args()
    if args.command == "create":
        print(create_backup())
    elif args.command == "verify":
        print(json.dumps(record_backup_verification(args.backup_dir), ensure_ascii=False))
    else:
        result = restore_backup(args.backup_dir, args.target_db, args.target_uploads, database_url=args.database_url)
        print("RESTORE=PASS")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
