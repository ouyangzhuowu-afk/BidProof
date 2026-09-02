import sqlite3

from fastapi.testclient import TestClient

from app import config, main
from work.backup_restore import create_backup, record_backup_verification, restore_backup, verify_backup


def test_backup_can_be_verified_and_restored(tmp_path):
    source_db = tmp_path / "source.sqlite3"
    with sqlite3.connect(source_db) as db:
        db.execute("CREATE TABLE sample(value TEXT)")
        db.execute("INSERT INTO sample(value) VALUES ('ok')")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "evidence.txt").write_text("proof", encoding="utf-8")

    backup = create_backup(source_db, uploads, tmp_path / "backups")
    verification = verify_backup(backup)
    assert verification["valid"] is True

    restored_db = tmp_path / "restored.sqlite3"
    restored_uploads = tmp_path / "restored-uploads"
    restore_backup(backup, restored_db, restored_uploads)
    with sqlite3.connect(restored_db) as db:
        assert db.execute("SELECT value FROM sample").fetchone()[0] == "ok"
    assert (restored_uploads / "evidence.txt").read_text(encoding="utf-8") == "proof"


def test_consecutive_backups_get_unique_directories(tmp_path):
    source_db = tmp_path / "source.sqlite3"
    with sqlite3.connect(source_db) as db:
        db.execute("CREATE TABLE sample(value TEXT)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    root = tmp_path / "backups"

    first = create_backup(source_db, uploads, root)
    second = create_backup(source_db, uploads, root)

    assert first != second
    assert verify_backup(first)["valid"] is True
    assert verify_backup(second)["valid"] is True


def test_backup_listing_and_health_use_verified_evidence(tmp_path, monkeypatch):
    source_db = tmp_path / "source.sqlite3"
    with sqlite3.connect(source_db) as db:
        db.execute("CREATE TABLE sample(value TEXT)")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    backup_root = tmp_path / "backups"
    backup = create_backup(source_db, uploads, backup_root)
    verification = record_backup_verification(backup)
    assert verification["valid"] is True

    monkeypatch.setattr(config, "BACKUP_ROOT", backup_root)
    client = TestClient(main.app)
    owner = {"X-Workspace-ID": "backup-workspace", "X-User-ID": "backup-owner", "X-User-Role": "OWNER"}
    viewer = {"X-Workspace-ID": "backup-workspace", "X-User-ID": "backup-viewer", "X-User-Role": "VIEWER"}

    listed = client.get("/api/backups", headers=owner)
    assert listed.status_code == 200
    assert listed.json()["backups"][0]["valid"] is True
    assert client.post("/api/backups", headers=viewer).status_code == 403
    health = client.get("/healthz?detail=true", headers=owner).json()
    assert health["backup_status"] == "verified"
    assert health["last_verified_backup_at"]
    assert isinstance(health["failed_jobs"], int)


def test_postgres_backup_writes_a_dump_manifest(tmp_path, monkeypatch):
    from work import backup_restore as module

    monkeypatch.setattr(module, "backup_engine", lambda source_db=None: "postgresql")
    monkeypatch.setattr(module, "configured_url", lambda: "postgresql+psycopg://bidproof:x@localhost/bidproof")

    def fake_dump(_url, target):
        target.write_bytes(b"PGDUMP")

    monkeypatch.setattr(module, "_dump_postgres", fake_dump)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "a.txt").write_text("a", encoding="utf-8")
    backup = module.create_backup(tmp_path / "ignored.sqlite3", uploads, tmp_path / "backups")
    manifest = (backup / "manifest.json").read_text(encoding="utf-8")

    assert '"engine": "postgresql"' in manifest
    assert (backup / "database.dump").read_bytes() == b"PGDUMP"
    assert module.verify_backup(backup)["valid"] is True
