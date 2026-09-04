import csv
import io
import sqlite3

from fastapi.testclient import TestClient

from app import config, main
from app.services import scan_service
from app.db import create_scan_job, init_db, list_recoverable_jobs, load_scan_job, record_audit_event, update_scan_job
from app.extraction import ExtractionError
from work.backup_restore import create_backup, record_backup_verification, restore_backup


def test_scan_job_persists_progress_and_recovery_state(tmp_path):
    database = tmp_path / "jobs.sqlite3"
    init_db(database)
    create_scan_job("pending", "workspace", None, "PENDING", {"tender_path": "pending.pdf"}, database)
    create_scan_job("running", "workspace", None, "RUNNING", {"tender_path": "running.pdf"}, database)
    create_scan_job("done", "workspace", None, "COMPLETED", {}, database)

    update_scan_job("running", "RUNNING", attempts=2, progress_current=2, progress_total=3, progress_message="保存结果", path=database)
    running = load_scan_job("running", database)

    assert running["progress_current"] == 2
    assert running["progress_total"] == 3
    assert running["progress_message"] == "保存结果"
    assert {job["job_id"] for job in list_recoverable_jobs(database)} == {"pending", "running"}


def test_detailed_health_reports_degraded_reasons_and_queue_counts(tmp_path, monkeypatch):
    empty_backups = tmp_path / "backups"
    empty_backups.mkdir()
    monkeypatch.setattr(config, "BACKUP_ROOT", empty_backups)
    create_scan_job("health-failed", "health", None, "FAILED", {})
    client = TestClient(main.app)

    health = client.get("/healthz?detail=true").json()

    assert health["database"] == "ok"
    assert health["job_counts"]["FAILED"] >= 1
    assert health["backup_age_hours"] is None
    assert "NO_VERIFIED_BACKUP" in health["degraded_reasons"]
    assert "FAILED_SCAN_JOBS" in health["degraded_reasons"]
    assert health["status"] == "degraded"


def test_backup_manifest_and_restore_report_inventory(tmp_path):
    source_db = tmp_path / "source.sqlite3"
    with sqlite3.connect(source_db) as database:
        database.execute("CREATE TABLE sample(value TEXT)")
        database.execute("INSERT INTO sample VALUES ('ok')")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "one.txt").write_text("one", encoding="utf-8")
    (uploads / "nested").mkdir()
    (uploads / "nested" / "two.txt").write_text("two", encoding="utf-8")

    backup = create_backup(source_db, uploads, tmp_path / "backups")
    verification = record_backup_verification(backup)
    restored = restore_backup(backup, tmp_path / "restored.sqlite3", tmp_path / "restored-uploads")

    assert verification["manifest"]["upload_file_count"] == 2
    assert verification["manifest"]["database_size_bytes"] > 0
    assert restored == {"database_integrity": "ok", "upload_file_count": 2}


def test_audit_csv_export_is_workspace_scoped():
    client = TestClient(main.app)
    owner = {"X-Workspace-ID": "audit-alpha", "X-User-ID": "owner", "X-User-Role": "OWNER"}
    record_audit_event("audit-alpha", "owner", "ALPHA_EVENT", payload={"safe": True})
    record_audit_event("audit-beta", "owner", "BETA_EVENT", payload={"safe": True})

    response = client.get("/api/audit/export.csv", headers=owner)
    rows = list(csv.DictReader(io.StringIO(response.text)))

    assert response.status_code == 200
    assert {row["event_type"] for row in rows} == {"ALPHA_EVENT"}
    assert "attachment" in response.headers["content-disposition"]


def test_failed_background_job_keeps_progress_and_recovery_reason(monkeypatch):
    client = TestClient(main.app)

    def fail_extract(_path):
        raise ExtractionError("测试解析失败")

    monkeypatch.setattr(scan_service, "extract_file", fail_extract)
    response = client.post("/api/jobs", files={"tender": ("broken.txt", "资格要求", "text/plain")})
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert job["status"] == "FAILED"
    assert job["error"] in {"TENDER_EXTRACTION_FAILED", "ExtractionError"}
    assert job["progress_total"] >= 2
    assert job["progress_message"] in {"处理失败，可重试", "招标文件解析失败"}
