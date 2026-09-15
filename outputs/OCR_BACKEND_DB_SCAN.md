# OCR / Backend / Database Scan

- Branch: `assessment/ocr-backend-db`
- Generated: 2026-09-15
- Backup: `outputs/assessment-backup/` (env.example, migrations, models, ocr, extraction)

## 0. Inventory (filled from repo)

| Item | Value |
|---|---|
| Repo | `C:/BidProof` |
| Frontend | Opus5 refactor on `main` lineage; current worktree also has `cursor/fix-auth-and-fullscreen-layout` WIP — **UI not modified in this assessment** |
| Backend | `app/` (FastAPI) |
| DB | SQLite (dev/test) + **PostgreSQL 16** (compose). Schema: SQLAlchemy `app/models.py` + Alembic `migrations/` |
| OCR | **Qwen-VL-OCR** (DashScope OpenAI-compatible). Default `BID_OCR_PROVIDER=disabled`. Code: `app/ocr.py`, batch: `work/ocr_batch.py` |
| Parse | PyMuPDF text/blocks + OOXML zip parse: `app/extraction.py` |
| Samples | Public electronic: `work/public-eval/pdfs/` (3). Scanned OCR cache: `work/ocr/akss-water-it/` (PII) |
| Labeled set | Minimal `work/eval/key_fields.json` + `work/ground-truth/fixture-00*.md` (5 quotes each, needs 2nd review). **No 50–100 doc CER/TEDS set** |
| API | FastAPI routes under `app/api/`; no separate OpenAPI export file (Swagger at runtime `/docs`) |
| Env sample | `.env.example` |
| Deploy | Docker Compose (`Dockerfile`, `docker-compose.yml`: api + worker + postgres) |
| Queue | **DB-backed** `scan_jobs` + `app/worker.py` (SKIP LOCKED on PG). Not Celery/Redis/Kafka |
| Object storage | **Local filesystem** volumes (`BIDPROOF_DATA_ROOT`) |
| Compliance | Cloud OCR egress to Aliyun DashScope when enabled. On-prem docs warn offline ≠ no egress until local OCR exists. `BIDPROOF_DATA_REGION` default `singapore` |

## 1. Document pipeline

```
upload (app/uploads.py, file_safety)
  → stage job (scan_jobs.payload_json)
  → worker / inline (app/queue.py, app/services/scan_service.py)
  → extract_pdf / extract_ooxml (app/extraction.py)
       ├─ text layer via PyMuPDF
       ├─ if empty/low-text AND OCR enabled → render PNG 1.5x → OCRAdapter
       └─ fail-closed: OCRUnavailable → ocr_status=FAILED, no auto PASS
  → extract_requirements (app/rules.py regex keywords)
  → match_evidence (keyword presence)
  → persist runs.*_json (app/db.py / repositories)
  → review / accuracy_feedback / audit_events
```

### Gaps vs 招投标难点

| Capability | Status |
|---|---|
| Electronic PDF text | Strong (PyMuPDF) |
| Scanned PDF OCR | Opt-in cloud only |
| Tables / TEDS | **Missing** (OCR collapses to one page block) |
| Seals / handwriting | **Missing** |
| Multi-column / TOC dense pages | **Weak** (VL model HTML+truncate) |
| Key-field IE schema | **Missing** (regex categories only) |
| Cross-page linking | Locator per page/block only |
| Business validators (大小写金额等) | **Missing** |

## 2. Backend scan

| Area | Finding |
|---|---|
| API | Modular routers: auth, jobs, runs, projects, members, reports, admin, health |
| AuthZ | Workspace-scoped roles, MFA, OIDC/LDAP optional, API tokens |
| Jobs | PENDING→claim→process; retry endpoint; stale requeue; cancel flag |
| Idempotency | `Idempotency-Key` middleware + `idempotency_keys` table |
| Rate limit | DB-backed `rate_limit_hits` |
| Observability | structlog JSON, optional metrics/OTEL flags (off by default) |
| Multi-tenant | `workspace_id` on core tables |
| Storage | Local disk uploads + sha256 duplicate hints on runs |
| Security | CSRF, security headers, fail-closed trusted headers outside test |

## 3. Database scan

19 tables (workspaces, users, runs, scan_jobs, audit_events, …).  
`runs` stores large JSON documents (`requirements_json`, `state_json`, …) — JSONB on PG.  
Indexes cover workspace listing, job claim, audit, idempotency.  
**No** FTS, **no** vector store, **no** table partitions yet (TIMESTAMPTZ prepared for future).  
Retention via `workspaces.retention_days` + archive fields.

## 4. Privacy / desensitization

- **ALERT:** `work/ocr/akss-water-it/*.json` matches phone / 身份证 phrases. Isolated with `work/ocr/_PRIVATE_PII_WARNING/`.
- **P0 fix applied:** `.gitignore` now excludes `work/ocr/` and `work/previews/`.
- Public-eval PDFs are published government tenders (OK for engineering regression).

## 5. P0 code fixes already applied (low risk)

1. Ignore OCR runtime artifacts in git.
2. `sanitize_ocr_text` strips HTML/Markdown fences from Qwen output.
3. Prompt forbids HTML/Markdown.
4. Low confidence (0.35) + `low_text_confidence` when markup/truncation suspected.
5. Benchmark harness: `work/eval/ocr_benchmark.py`.

## 6. Artifacts

- `outputs/OCR_EVAL_DATASET.md`
- `outputs/OCR_TECH_ASSESSMENT.md`
- `outputs/ocr-benchmark/raw-results.json`
- `outputs/BACKEND_ASSESSMENT.md`
- `outputs/DATABASE_ASSESSMENT.md`
- `outputs/REFACTOR_PLAN.md`
