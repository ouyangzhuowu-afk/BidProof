"""Seed an isolated local UI acceptance workspace with generated example PDFs.
Never used for pilot/ICP evidence. Requires BIDPROOF_DATA_ROOT outside production data.
"""
import os
if not os.environ.get('BIDPROOF_DATA_ROOT'):
    raise SystemExit('Set an isolated BIDPROOF_DATA_ROOT before seeding.')
if os.environ.get('BIDPROOF_DATABASE_URL') or os.environ.get('DATABASE_URL'):
    raise SystemExit('Clear BIDPROOF_DATABASE_URL and DATABASE_URL for the isolated demo.')
if os.environ.get('BIDPROOF_ENV', 'development').lower() == 'production':
    raise SystemExit('Use BIDPROOF_ENV=development for the isolated demo.')
import json
from pathlib import Path
import pymupdf as fitz
from fastapi.testclient import TestClient
from app import main

client = TestClient(main.app)
credentials = {'username': 'ui-review', 'password': 'LocalReview2026!'}
status = client.get('/api/auth/status').json()
if status['setup_required']:
    result = client.post('/api/auth/bootstrap', json={**credentials, 'workspace_name':'BidProof 界面验收 · 示例空间'})
else:
    result = client.post('/api/auth/login', json=credentials)
assert result.status_code == 200, result.text
client.headers['X-CSRF-Token'] = client.cookies.get('bidproof_csrf')
projects = client.get('/api/projects').json()['projects']
if not projects:
    project = client.post('/api/projects', json={'name':'政务协同平台建设项目 · 示例','code':'UI-DEMO'}).json()
else:
    project = projects[0]

def pdf(pages, title):
    doc = fitz.open()
    for n,(heading,body) in enumerate(pages,1):
        page=doc.new_page(width=595,height=842)
        page.insert_text((56,56), 'BidProof / UI REVIEW SAMPLE', fontsize=10, color=(.2,.4,.38))
        page.insert_textbox(fitz.Rect(56,110,540,170),heading,fontname='china-s',fontsize=20)
        page.insert_textbox(fitz.Rect(56,205,540,650),body,fontname='china-s',fontsize=13,lineheight=1.8)
        page.insert_textbox(fitz.Rect(56,748,540,805),f'界面验收示例 · 非真实采购材料\n{title} / 第 {n} 页',fontname='china-s',fontsize=10,color=(.4,.45,.45))
    data=doc.tobytes();doc.close();return data

tender_pages=[
 ('第一章 资格要求','投标人资格要求：须具有独立承担民事责任的能力，并提供有效的营业执照。\n\n本项目为政务协同平台软件实施与运维服务，实施范围包含平台部署、数据迁移和一年运维支持。'),
 ('第二章 投标文件签署','投标文件应由法定代表人签字并加盖公章，未按要求签字或盖章的，否决投标。\n\n委托代理人签署的，应同时提交法定代表人授权委托书，载明授权范围和有效期限。'),
 ('第三章 履约保证','投标保证金应在投标截止时间前到账，未按规定提交投标保证金的，否决投标。\n\n请提交保证金转账凭证，并确认收款账户、金额与采购文件一致。'),
 ('第四章 人员与服务','项目经理须提供软件实施服务相关业绩证明及在职证明。\n\n项目实施周期为合同签订后九十日，服务地点为采购人指定地点。'),
 ('第五章 商务条款','评分项：提供近三年类似软件实施项目业绩合同，根据有效合同数量计分。\n\n投标截止时间为2026年10月30日09时30分。投标人应核对招标公告中的最终安排。'),
]
evidence_pages=[
 ('企业营业执照','本公司具有独立承担民事责任的能力，提供有效营业执照。\n\n公司名称：示例软件服务有限公司。经营范围：软件实施、技术服务。\n\n此文档仅为页面验收生成，不代表真实企业资质。'),
 ('签字与盖章说明','投标文件已由法定代表人签字并加盖公章。法定代表人授权委托书已提供。\n\n请人工核实原件签署位置与授权有效期限。本页为界面验收示例。'),
 ('项目业绩证明','项目经理在职证明已提供，具备软件实施服务相关业绩证明。\n\n类似软件实施项目业绩合同：示例平台建设合同。\n\n本材料用于界面验收。'),
]
files=[('tender',('政务协同平台建设项目_示例招标.pdf',pdf(tender_pages,'示例招标文件'),'application/pdf')),('evidence',('企业资质包_示例.pdf',pdf(evidence_pages,'示例企业证据'),'application/pdf'))]
r=client.post('/api/runs',data={'company_name':'示例软件服务有限公司','project_id':project['project_id']},files=files)
assert r.status_code==200,r.text
run=r.json()
Path(os.environ['BIDPROOF_DATA_ROOT'],'ui-run.json').write_text(json.dumps({'run_id':run['run_id'],'requirements':len(run['requirements'])},ensure_ascii=False))
print(json.dumps({'run_id':run['run_id'],'requirements':len(run['requirements']),'categories':[x['category'] for x in run['requirements']]},ensure_ascii=False))
