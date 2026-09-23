"""Independent job lifecycle checks, isolated from demo and enterprise runtime data."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app import config, db, job_leases, main, uow
from app.repositories import jobs
from app.services import scan_service


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv('BIDPROOF_DATABASE_URL', f'sqlite+pysqlite:///{tmp_path / "jobs.sqlite3"}')
    monkeypatch.setenv('DATABASE_URL', '')
    for name, dirname in [('DATA_DIR', 'data'), ('UPLOAD_DIR', 'uploads'), ('JOB_STAGING_DIR', 'staging')]:
        path = tmp_path / dirname
        path.mkdir()
        monkeypatch.setattr(config, name, path)
    monkeypatch.setattr(config, 'JOB_RUNNER', 'worker')
    db.init_db()


PRINCIPAL = {'workspace_id': 'jobs-workspace', 'user_id': 'jobs-owner', 'role': 'OWNER'}


def source():
    return UploadFile(filename='source.txt', file=BytesIO('投标人须提供有效营业执照。'.encode()))


def stage(**overrides):
    arguments = {'principal': PRINCIPAL, 'tender': source(), 'evidence': None, 'company_name': '示例',
                 'evidence_metadata': None, 'project_id': None}
    arguments.update(overrides)
    return asyncio.run(scan_service.stage_job(**arguments))


def expire(job_id):
    with db.connect() as connection:
        connection.execute(db.scan_jobs.update().where(db.scan_jobs.c.job_id == job_id)
                           .values(updated_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()))


def test_claim_is_exclusive_and_new_lease_fences_the_old_attempt():
    job_id = stage()
    first = job_leases.claim(job_id)
    assert first is not None and first['attempts'] == 1
    assert job_leases.claim(job_id) is None
    expire(job_id)
    assert jobs.requeue_stale(60) == 1
    second = job_leases.claim(job_id)
    assert second['lease_token'] != first['lease_token'] and second['attempts'] == 2
    assert not job_leases.update(job_id, first['lease_token'], status='FAILED')
    with pytest.raises(job_leases.LeaseLost), uow.transaction():
        job_leases.fence_publication(job_id, first['lease_token'])
    assert job_leases.update(job_id, second['lease_token'])


def test_live_heartbeat_prevents_stale_recovery():
    job_id = stage()
    claim = job_leases.claim(job_id)
    expire(job_id)
    assert job_leases.update(job_id, claim['lease_token'])
    assert jobs.requeue_stale(60) == 0
    assert jobs.load(job_id)['status'] == 'RUNNING'


def test_cancel_during_extraction_does_not_publish_a_run(monkeypatch):
    job_id = stage()
    original = scan_service.extract_file
    def cancel_while_extracting(path):
        jobs.cancel(job_id)
        return original(path)
    monkeypatch.setattr(scan_service, 'extract_file', cancel_while_extracting)
    asyncio.run(scan_service.process_job(job_id))
    finished = jobs.load(job_id)
    assert finished['status'] == 'CANCELLED' and finished['run_id'] is None
    assert not db.list_runs(workspace_id=PRINCIPAL['workspace_id'])
    assert not list(config.UPLOAD_DIR.iterdir())
    assert not list(config.JOB_STAGING_DIR.iterdir())


def test_reclaimed_old_worker_result_cannot_publish_or_delete_new_staging(monkeypatch):
    job_id = stage()
    original = scan_service.extract_file
    replacement = {}
    def reclaim_while_extracting(path):
        expire(job_id)
        assert jobs.requeue_stale(60) == 1
        replacement.update(job_leases.claim(job_id))
        return original(path)
    monkeypatch.setattr(scan_service, 'extract_file', reclaim_while_extracting)
    asyncio.run(scan_service.process_job(job_id))
    current = jobs.load(job_id)
    assert current['status'] == 'RUNNING' and current['lease_token'] == replacement['lease_token']
    assert current['run_id'] is None
    assert not list(config.UPLOAD_DIR.iterdir())
    assert (config.JOB_STAGING_DIR / job_id).exists()
    monkeypatch.setattr(scan_service, 'extract_file', original)
    asyncio.run(scan_service.process_job(job_id, replacement['lease_token']))
    assert jobs.load(job_id)['status'] == 'COMPLETED'
    assert len(db.list_runs(workspace_id=PRINCIPAL['workspace_id'])) == 1


def test_normal_queued_rescan_keeps_parent_project_and_version():
    first = stage()
    asyncio.run(scan_service.process_job(first))
    parent = db.load_run(jobs.load(first)['run_id'])
    second = stage(parent_run_id=parent['run_id'])
    asyncio.run(scan_service.process_job(second))
    child = db.load_run(jobs.load(second)['run_id'])
    assert child['parent_run_id'] == parent['run_id']
    assert child['version_number'] == parent['version_number'] + 1
    assert child['project_id'] == parent['project_id']


def test_queued_rescan_cannot_use_another_tenants_parent():
    first = stage()
    asyncio.run(scan_service.process_job(first))
    parent_id = jobs.load(first)['run_id']
    other = {**PRINCIPAL, 'workspace_id': 'another-workspace'}
    with pytest.raises(HTTPException) as error:
        stage(parent_run_id=parent_id, principal=other)
    assert error.value.status_code == 404
    assert not list(config.JOB_STAGING_DIR.iterdir())


def test_upload_cannot_write_into_a_restricted_project():
    project = db.create_project(PRINCIPAL['workspace_id'], 'Restricted', 'RESTRICTED')
    db.replace_project_members(project['project_id'], [{'user_id': 'different-user', 'role': 'REVIEWER'}])
    reviewer = {**PRINCIPAL, 'role': 'REVIEWER'}
    with pytest.raises(HTTPException) as error:
        stage(project_id=project['project_id'], principal=reviewer)
    assert error.value.status_code == 404
    assert not list(config.JOB_STAGING_DIR.iterdir())


def test_retry_does_not_overwrite_a_concurrently_claimed_job(monkeypatch):
    job_id = stage()
    original = jobs.require_scoped
    def claim_after_read(*args):
        stale = original(*args)
        assert job_leases.claim(job_id) is not None
        return stale
    monkeypatch.setattr(jobs, 'require_scoped', claim_after_read)
    result = TestClient(main.app).post(f'/api/jobs/{job_id}/retry', headers={
        'X-Workspace-ID': PRINCIPAL['workspace_id'], 'X-User-ID': PRINCIPAL['user_id'], 'X-User-Role': 'OWNER'})
    assert result.status_code == 409
    assert jobs.load(job_id)['status'] == 'RUNNING'


def test_job_read_response_never_discloses_internal_lease():
    job_id = stage()
    assert job_leases.claim(job_id)
    headers = {'X-Workspace-ID': PRINCIPAL['workspace_id'], 'X-User-ID': PRINCIPAL['user_id'], 'X-User-Role': 'OWNER'}
    client = TestClient(main.app)
    response = client.get(f'/api/jobs/{job_id}', headers=headers)
    assert response.status_code == 200
    assert 'payload' not in response.json()
    assert 'lease_token' not in response.json()
    assert all('lease_token' not in job for job in client.get('/api/jobs', headers=headers).json()['jobs'])


def test_supervisor_runs_real_child_and_publishes_once(tmp_path, monkeypatch):
    from app import job_runner
    monkeypatch.setenv('BIDPROOF_DATA_ROOT', str(tmp_path))
    monkeypatch.setenv('BIDPROOF_ENV', 'test')
    monkeypatch.setattr(job_runner, 'JOB_TIMEOUT_SECONDS', 30)
    job_id = stage()
    claim = job_leases.claim(job_id)
    asyncio.run(job_runner.supervise(claim))
    current = jobs.load(job_id)
    assert current['status'] == 'COMPLETED'
    assert current['run_id'] == job_leases.attempt_run_id(job_id, claim['lease_token'])
    assert len(db.list_runs(workspace_id=PRINCIPAL['workspace_id'])) == 1
    assert not (config.JOB_STAGING_DIR / job_id).exists()


def test_supervisor_timeout_terminates_child_and_preserves_retry_inputs(monkeypatch):
    from app import job_runner
    class HangingChild:
        returncode = None
        terminated = False
        def terminate(self):
            self.terminated = True
            self.returncode = -15
        def kill(self):
            self.returncode = -9
        async def wait(self):
            while self.returncode is None:
                await asyncio.sleep(0.01)
            return self.returncode
    child = HangingChild()
    async def spawn(*args, **kwargs):
        return child
    monkeypatch.setattr(job_runner.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(job_runner, 'JOB_TIMEOUT_SECONDS', 0)
    job_id = stage()
    claim = job_leases.claim(job_id)
    asyncio.run(job_runner.supervise(claim))
    assert child.terminated
    current = jobs.load(job_id)
    assert current['status'] == 'FAILED' and current['error'] == 'SCAN_TIMEOUT'
    assert (config.JOB_STAGING_DIR / job_id).exists()
    assert not current['run_id']


def test_supervisor_spawn_failure_is_retryable_without_poisoning_worker(monkeypatch):
    from app import job_runner
    async def spawn(*args, **kwargs):
        raise OSError('No process slots')
    monkeypatch.setattr(job_runner.asyncio, 'create_subprocess_exec', spawn)
    job_id = stage()
    claim = job_leases.claim(job_id)
    asyncio.run(job_runner.supervise(claim))
    current = jobs.load(job_id)
    assert current['status'] == 'FAILED' and current['error'] == 'WORKER_START_FAILED'
    assert (config.JOB_STAGING_DIR / job_id).exists()


def test_two_separate_worker_processes_cannot_claim_the_same_job(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('BIDPROOF_DATA_ROOT', str(tmp_path))
    job_id = stage()
    script = ('import json,sys; from app import job_leases; '
              'job=job_leases.claim(sys.argv[1]); '
              'print(json.dumps({"claimed":bool(job)}))')
    def worker():
        result = subprocess.run([sys.executable, '-c', script, job_id], cwd=config.PROJECT_ROOT,
                                env=os.environ.copy(), check=True, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)['claimed']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert results.count(True) == 1
    assert jobs.load(job_id)['attempts'] == 1


def test_queue_intake_does_not_enter_native_pdf_parser(monkeypatch):
    import pymupdf

    def forbidden_parser(*_args, **_kwargs):
        raise AssertionError("Native parser must only run in the scan execution process")
    monkeypatch.setattr(pymupdf, "open", forbidden_parser)
    uploaded = UploadFile(filename="synthetic.pdf", file=BytesIO(b"%PDF-1.7\nsynthetic parser boundary check"))
    job_id = stage(tender=uploaded)
    assert jobs.load(job_id)["status"] == "PENDING"


def test_pdf_page_budget_is_enforced_in_execution_and_not_published(monkeypatch):
    import pymupdf

    from app import uploads

    with pymupdf.open() as document:
        document.new_page()
        document.new_page()
        pdf = document.tobytes()
    monkeypatch.setattr(uploads, "MAX_PDF_PAGES", 1)
    job_id = stage(tender=UploadFile(filename="two-pages.pdf", file=BytesIO(pdf)))
    asyncio.run(scan_service.process_job(job_id))
    assert jobs.load(job_id)["status"] == "FAILED"
    assert jobs.load(job_id)["run_id"] is None
    assert not db.list_runs(workspace_id=PRINCIPAL["workspace_id"])
