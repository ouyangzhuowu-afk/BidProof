"""Synthetic starter PDFs must remain readable and use the actual review pipeline."""
import fitz
import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.services.starter_service import document


@pytest.mark.parametrize('scenario,expected', [('software', '软件项目管理'), ('operations', '业绩合同')])
def test_starter_pair_is_chinese_readable_and_extracts_source_pages(tmp_path, monkeypatch, scenario, expected):
    monkeypatch.setenv('BIDPROOF_DATABASE_URL', f'sqlite+pysqlite:///{tmp_path / "starter.sqlite3"}')
    monkeypatch.setenv('DATABASE_URL', '')
    db.init_db()
    client = TestClient(main.app)
    tender = client.get('/api/sample-tender', params={'scenario': scenario})
    evidence = client.get('/api/sample-tender', params={'scenario': scenario, 'kind': 'evidence'})
    assert tender.status_code == evidence.status_code == 200
    assert 'no-store' in tender.headers['cache-control']
    with fitz.open(stream=tender.content, filetype='pdf') as pdf:
        text = pdf[0].get_text()
        assert '合成示例' in text and '投标无效' in text and expected in text
    with fitz.open(stream=evidence.content, filetype='pdf') as pdf:
        assert '营业执照' in pdf[0].get_text() and '不具有证明效力' in pdf[0].get_text()
    result = client.post('/api/runs', data={'company_name': '合成示例企业'}, files=[
        ('tender', ('【合成示例】招标.pdf', tender.content, 'application/pdf')),
        ('evidence', ('【合成示例】材料.pdf', evidence.content, 'application/pdf')),
    ])
    assert result.status_code == 200, result.text
    run = result.json()
    assert run['requirements'], 'The real extractor must create reviewable requirements'
    assert run['source_documents'] and run['evidence_assets']
    assert all(r['source']['page'] == 1 for r in run['requirements'])
    assert any('营业执照' in r['source']['quote'] for r in run['requirements'])
    assert client.delete(f'/api/runs/{run["run_id"]}').status_code == 200


def test_starter_rejects_unknown_scenario_and_document_kind():
    client = TestClient(main.app)
    assert client.get('/api/sample-tender?scenario=../../private').status_code == 422
    assert client.get('/api/sample-tender?kind=unknown').status_code == 422
    assert document('software', 'tender').startswith(b'%PDF')
