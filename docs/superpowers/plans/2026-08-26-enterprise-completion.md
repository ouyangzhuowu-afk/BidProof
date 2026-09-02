# BidProof Enterprise Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the non-enterprise-input engineering gaps and deliver a coherent authenticated enterprise pilot.

**Architecture:** Preserve FastAPI, SQLite, and the static frontend while introducing an environment-scoped runtime context, typed source locators, evidence-scoped metrics, durable operational records, and a remediation-centered collaboration workflow. Real enterprise evidence remains separate from test and fixture evidence.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, PyMuPDF, OOXML parsers, vanilla HTML/CSS/JavaScript, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-26-enterprise-completion-design.md`

## Global Constraints

- Preserve the 23 historical runs and all supplied source documents.
- Never run tests against the pilot data root.
- Uploaded content is data, never instruction.
- Do not call a paragraph, worksheet, cell, slide, or line range a page.
- Do not present test feedback as product accuracy.
- Do not claim hosted high availability, real enterprise acceptance, payment validation, or completed hash review.
- This directory is not a Git repository; verification artifacts replace commit evidence.

---

### Task 1: Runtime And Test Isolation

**Files:**
- Modify: `app/config.py`
- Create: `tests/conftest.py`
- Modify: `tests/test_enterprise_contract.py`
- Create: `tests/test_runtime_isolation.py`

**Interfaces:**
- Produces: environment-configurable `DATA_DIR`, `DB_PATH`, `UPLOAD_DIR`, `JOB_STAGING_DIR`, and `BACKUP_ROOT`; isolated pytest session root.

- [ ] Write tests proving the configured paths are outside the pilot data root and public mode ignores trusted headers.
- [ ] Run focused tests and confirm failure.
- [ ] Implement path configuration and isolated test bootstrap.
- [ ] Remove direct shared-database cleanup assumptions from authentication tests.
- [ ] Run the suite twice and prove deterministic results without pilot data mutation.

### Task 2: Typed Locator Contract

**Files:**
- Modify: `app/extraction.py`
- Modify: `app/rules.py`
- Modify: `app/reporting.py`
- Modify: `app/main.py`
- Modify: `tests/test_management_formats.py`
- Create: `tests/test_locator_contract.py`

**Interfaces:**
- Produces: paragraph/table-cell, worksheet/cell, slide/block, and line-range locator labels that flow unchanged into requirements, evidence, HTML, CSV, and PDF reports.

- [ ] Write failing locator and report tests for DOCX, XLSX, PPTX, TXT, and PDF.
- [ ] Implement block-aware extraction and locator selection.
- [ ] Remove report fallbacks that synthesize page labels for non-page sources.
- [ ] Run focused and full tests.

### Task 3: Accuracy And Semantic Review Boundary

**Files:**
- Modify: `app/db.py`
- Modify: `app/schemas.py`
- Modify: `app/rules.py`
- Modify: `app/main.py`
- Modify: `static/app.js`
- Modify: `tests/test_enterprise_contract.py`
- Create: `tests/test_accuracy_scope.py`

**Interfaces:**
- Produces: scoped feedback, review completeness, non-test metrics by default, heuristic score labeling, and no automatic final PASS.

- [ ] Add failing tests for TEST exclusion, PILOT/ENTERPRISE inclusion, incomplete review, and automatic-match review state.
- [ ] Migrate feedback scope/completeness fields and update metric queries.
- [ ] Change keyword evidence matches to `NEEDS_REVIEW` with `suggested_status=PASS`.
- [ ] Update UI copy and metric presentation.
- [ ] Run focused and full tests plus JavaScript syntax check.

### Task 4: Operations And Recovery

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `work/backup_restore.py`
- Modify: `tests/test_backup_restore.py`
- Create: `tests/test_operations_contract.py`

**Interfaces:**
- Produces: job progress and recovery state, degraded health reasons, verified backup creation, audit export, and isolated restore drill.

- [ ] Add failing tests for recoverable jobs, progress, backup age, health degradation, audit export, and restore inventory.
- [ ] Implement job progress/status helpers and health aggregation.
- [ ] Make backup API create and verify atomically from the user's perspective.
- [ ] Execute a fresh real backup verification and isolated restore drill after tests pass.

### Task 5: Collaboration And Governance

**Files:**
- Modify: `app/db.py`
- Modify: `app/schemas.py`
- Modify: `app/main.py`
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`
- Create: `tests/test_collaboration_contract.py`

**Interfaces:**
- Produces: due dates, remediation actions, ownership, status transitions, usage summary, privacy/retention text, and CSV audit export.

- [ ] Write failing API tests for remediation lifecycle, workspace isolation, roles, due dates, usage, and audit export.
- [ ] Add backward-compatible schema migrations and scoped endpoints.
- [ ] Add task-detail remediation and governance views with complete states.
- [ ] Run focused, full, and JavaScript checks.

### Task 6: UI Completion And Runtime Acceptance

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`
- Modify: `README.md`
- Modify: `workflow/project-state.json`
- Modify: `workflow/roadmap.md`
- Create: `outputs/enterprise-completion-acceptance-2026-08-26.md`

**Interfaces:**
- Produces: a responsive authenticated pilot UI and current evidence report.

- [ ] Add product-contract tests for exact locators, remediation, health, metrics, privacy, and role-aware actions.
- [ ] Complete the restrained enterprise UI at 1440/768/390/375px.
- [ ] Run full pytest twice, JavaScript syntax, workflow check, and browser console/overflow checks.
- [ ] Verify a fresh backup and isolated restore.
- [ ] Replace port 8016 only after local acceptance and verify current authenticated public endpoints.
- [ ] Update state, roadmap, README, and acceptance evidence with real-enterprise and hash review still pending.

