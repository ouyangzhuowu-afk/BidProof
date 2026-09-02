import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import BACKUP_ROOT, DB_PATH, UPLOAD_DIR


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(source_db: Path = DB_PATH, uploads_dir: Path = UPLOAD_DIR, backup_root: Path | None = None) -> Path:
    backup_root = backup_root or BACKUP_ROOT
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root.mkdir(parents=True, exist_ok=True)
    counter = 0
    while True:
        target = backup_root / (timestamp if counter == 0 else f"{timestamp}-{counter:02d}")
        try:
            target.mkdir(exist_ok=False)
            break
        except FileExistsError:
            counter += 1
    db_copy = target / "bidproof.sqlite3"
    with sqlite3.connect(source_db) as source, sqlite3.connect(db_copy) as destination:
        source.backup(destination)
    uploads_zip = target / "uploads.zip"
    with zipfile.ZipFile(uploads_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if uploads_dir.exists():
            for path in sorted(uploads_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(uploads_dir))
    upload_files = [path for path in uploads_dir.rglob("*") if path.is_file()] if uploads_dir.exists() else []
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_sha256": _sha256(db_copy),
        "uploads_sha256": _sha256(uploads_zip),
        "database_file": db_copy.name,
        "uploads_file": uploads_zip.name,
        "upload_file_count": len(upload_files),
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
    if valid:
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
            "verified_at": verification.get("verified_at"),
            "valid": bool(verification.get("valid", False)),
            "database_sha256": manifest.get("database_sha256"),
            "uploads_sha256": manifest.get("uploads_sha256"),
        })
    return records


def restore_backup(backup_dir: Path, target_db: Path, target_uploads: Path) -> dict:
    verification = verify_backup(backup_dir)
    if not verification["valid"]:
        raise ValueError("backup verification failed")
    manifest = verification["manifest"]
    target_db.parent.mkdir(parents=True, exist_ok=True)
    target_uploads.mkdir(parents=True, exist_ok=True)
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
    extracted_files = 0
    with zipfile.ZipFile(backup_dir / manifest["uploads_file"]) as archive:
        for member in archive.infolist():
            destination = (target_uploads / member.filename).resolve()
            if target_uploads.resolve() not in destination.parents and destination != target_uploads.resolve():
                raise ValueError("unsafe backup entry")
        archive.extractall(target_uploads)
        extracted_files = sum(1 for member in archive.infolist() if not member.is_dir())
    return {"database_integrity": "ok", "upload_file_count": extracted_files}


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
    args = parser.parse_args()
    if args.command == "create":
        print(create_backup())
    elif args.command == "verify":
        print(json.dumps(record_backup_verification(args.backup_dir), ensure_ascii=False))
    else:
        restore_backup(args.backup_dir, args.target_db, args.target_uploads)
        print("RESTORE=PASS")


if __name__ == "__main__":
    main()
