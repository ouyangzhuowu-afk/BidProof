# BidProof Enterprise Completion Design

## Goal

Complete the engineering capabilities that can be verified without real enterprise tasks, then present them as a coherent pilot product without overstating production maturity or accuracy.

## Completion Boundary

This phase completes test isolation, authenticated workspace isolation, exact source locations, measurable human-feedback contracts, durable local job recovery, backup verification, collaboration workflow, usage/privacy surfaces, and final UI integration. Real enterprise experience, payment validation, hosted high availability, and final hash review remain explicit later evidence.

## Architecture

### Isolated Runtime Context

All mutable paths are environment-configurable. Tests set a dedicated temporary data root before importing the application, so no test may read, delete, or append to the pilot SQLite database, uploads, staging jobs, or backups. Trusted identity headers are allowed only for isolated development/test mode; the public runtime uses signed session cookies.

### Source Location Contract

Every extracted block carries a typed locator and a display label:

- PDF: page plus optional bounding box.
- DOCX: paragraph or table cell; never a synthetic page number.
- XLSX: worksheet name/index plus A1 cell coordinate.
- PPTX: slide plus text block.
- TXT/MD: line range.

Reports and UI render `locator.label` verbatim. The compatibility `page` field remains an internal sequence index and must not be displayed as a page when the locator kind is not `page`.

### Accuracy Evidence

Human feedback records include `dataset_scope` (`TEST`, `PILOT`, or `ENTERPRISE`), review completeness, and stable labels. Metrics exclude `TEST` by default and expose TP/FP/FN, coverage, sample size, and `INSUFFICIENT`/`MEASURABLE`. Heuristic confidence is renamed and displayed as a rule score, not a calibrated probability. A PASS produced by keyword evidence matching remains `NEEDS_REVIEW` until a human confirms semantic sufficiency.

### Operations

Persistent job records survive restarts, with explicit progress, retry eligibility, attempts, sanitized errors, and recovery on startup. Health exposes database state, queue counts, last verified backup, backup age, and degraded reasons. Backup creation always records verification; restore remains an offline command and must pass an isolated restore drill.

### Enterprise Workflow

Runs support owner, reviewer, due date, tags, favorites, comments, audit events, and remediation actions for missing evidence. Workspace settings expose usage counts, privacy/retention policy text, and exportable audit records. Billing is represented as a disabled extension boundary until a paid plan exists; no fabricated price or invoice workflow is introduced.

### Frontend

The UI prioritizes tasks, unresolved risks, remediation ownership, evidence quality, job health, and measurable accuracy. It preserves the restrained enterprise visual system, uses exact locator labels, explains evidence boundaries at decision points, and remains usable at 1440, 768, 390, and 375 pixels.

## Acceptance

- Running pytest cannot change the pilot database file hash, row counts, users, uploads, or backups.
- Public mode rejects trusted identity headers and requires a valid session.
- DOCX/XLSX/PPTX/TXT locator tests prove that reports never mislabel non-page sources as pages.
- Accuracy metrics default to non-test labels and cannot become `MEASURABLE` without complete review coverage.
- Automatic keyword evidence never produces a final human-confirmed PASS.
- A fresh backup is verified and restored into an isolated target with SQLite integrity and upload inventory checks.
- Full API, JavaScript, workflow, and multi-viewport browser checks pass before the current build replaces port 8016.

