# Database Assessment

- Branch: `assessment/ocr-backend-db`
- Refreshed: `2026-09-16`
- Engines: SQLite (test/dev) · PostgreSQL 16 (compose/production)
- Source of truth: `app/models.py` + `migrations/versions/`

## Summary

Schema is coherent for multi-tenant scan SaaS MVP. **No greenfield rewrite.** Evolve JSON payload size and optional FTS only with volume evidence.

## Schema strengths

- Single metadata definition for SQLite + PG (`IsoTimestamp`, `json_column` JSONB variant).
- Workspace isolation FKs with `ON DELETE CASCADE` where appropriate.
- `runs` denormalized counters for list queries.
- `idempotency_keys`, `rate_limit_hits`, `accuracy_feedback` support product gates.
- Alembic history covers baseline, identity/audit, FK ACL, timestamptz, run list counts.

## P0

| ID | Issue | Action |
|---|---|---|
| D-P0-1 | None blocking correctness | — |

## P1

| ID | Issue | Proposal | Status |
|---|---|---|---|
| D-P1-1 | `runs.*_json` unbounded with OCR text | Cap page text; optional `run_pages` child table | **Deferred** — needs volume evidence + migration approval |
| D-P1-2 | No GIN on JSONB filter paths | Add after measuring queries | Open |
| D-P1-3 | Job claim workspace filter | **Reviewed**: `claim_next_scan_job` is global oldest-PENDING + PG `SKIP LOCKED` / SQLite conditional UPDATE. Correct for shared worker pool; list APIs already workspace-scoped. **No change.** |
| D-P1-4 | Retention / cold storage | Lifecycle → compressed files | Open |

## P2

| ID | Issue | Proposal |
|---|---|---|
| D-P2-1 | No FTS on quotes | PG `tsvector` only if product needs search |
| D-P2-2 | No vector embeddings | Out of scope |
| D-P2-3 | Monthly partitions | Defer until audit/runs volume demands |
| D-P2-4 | SQLite in prod | Compose already forces Postgres |

## claim_next verification

```text
SELECT … FROM scan_jobs
 WHERE status='PENDING' AND cancel_requested=0
 ORDER BY created_at, job_id LIMIT 1
 [FOR UPDATE SKIP LOCKED on PostgreSQL]
UPDATE … SET status='RUNNING' WHERE job_id=? AND status='PENDING'
```

Tests: `tests/test_queue_observability.py::test_claim_next_takes_the_oldest_pending_job_once` — PASS.

## Migration policy (before any D-P1-1)

1. Alembic upgrade + downgrade.
2. Backup under `work/backups/`.
3. Expand-contract if moving page text out of JSON.
4. No production applies without explicit approval.

## Verdict

**Keep schema; selective evolution.** Highest-value future change is extracting OCR page payloads from monolithic `runs` JSON **after** volume evidence — not now. Backend/DB do **not** need rewrite to unlock OCR precision work.
