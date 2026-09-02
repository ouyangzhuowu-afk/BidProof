# BidProof Enterprise Hardening Design

## Goal

Turn the current local pilot into a coherent enterprise trial product without claiming production maturity or measured business accuracy before evidence exists.

## Product Boundaries

- Every API that reads or changes tenant data must require an authenticated principal once the first user is bootstrapped and must scope records by `workspace_id`.
- `OWNER` and `ADMIN` manage members and destructive lifecycle actions. `REVIEWER` manages scans, metadata, comments, feedback, reviews, and decisions. `VIEWER` is read-only.
- Uploaded documents remain untrusted data. File acceptance includes size, signature, archive-safety, macro, executable, and active-content checks.
- PDF locations are pages; DOCX locations are paragraphs; XLSX locations are sheets and cells; PPTX locations are slides; TXT/MD locations are full text. The UI and reports must preserve these labels.
- Accuracy is reported only from explicit human labels. Detected items support relevant and irrelevant labels; missed items support relevant labels. Metrics expose TP/FP/FN, coverage, and a `MEASURABLE`/`INSUFFICIENT` boundary. Detection output carries an uncalibrated keyword-match count and never exposes it as a probability.
- Public deployment remains a pilot while it depends on a personal computer, SQLite, and a tunnel. Health checks, backups, and recovery evidence do not imply high availability.

## Enterprise Workflows

### Workspace And Members

The first bootstrap creates a workspace owner. Owners and admins can list members, create a member with an initial password, change roles, and deactivate accounts. The UI uses member selectors for assignees rather than free-form IDs. Audit events record member changes without passwords.

### Scans And Versions

Uploads enter a persistent job queue. Users can list recent jobs, see progress/status/error, and retry failed jobs. Rescans create versions and expose a human-readable added/removed/changed comparison. Duplicate tender files are detected by SHA-256 inside the same workspace and shown as a warning, not silently rejected.

### Review And Accuracy

Reviewers can confirm a detected requirement as relevant, mark it irrelevant, or submit a missed requirement with category, source locator, quote, and note. Repeated labels for the same requirement are updated rather than double counted. Metrics show category-level sample counts and whether recall is measurable; missing-item feedback without a stable review population cannot be presented as production recall.

### Retention And Recovery

Runs can be archived, restored, or permanently deleted by authorized roles. Workspaces expose a retention setting and a dry-run purge preview. Backup creation and verification are available to owners/admins; restore stays an offline operator command because it replaces live state. Health detail reports database state, last verified backup, failed jobs, and backup age.

### Reports

HTML, CSV, and PDF reports contain the same decision-critical fields: scope and caveat, scan quality, counts, final decision, every requirement, exact locator label, source quote, evidence quote, evidence gap, risk impact, next action, reviewer history, and generation time. PDF is paginated and uses a Chinese-capable font when available; failure to load a suitable font is explicit.

## Frontend Information Architecture

- Primary navigation: tasks, scan jobs, members/settings.
- Home: searchable/filterable task table, bulk actions, accuracy evidence status, and service/backup status.
- Detail: risks first, version comparison, assignment/tags, complete evidence matrix, review feedback, comments, and audit timeline.
- Admin: members, retention, backups, and service health.
- All interactions have visible labels, keyboard focus, loading/error/empty states, 44px minimum touch targets, no horizontal overflow at 375/390px, and reduced-motion support.

## Acceptance Evidence

- Cross-workspace read and mutation attempts return 404; unauthorized roles return 403; unauthenticated access returns 401 after bootstrap.
- Member lifecycle and role changes are covered by API tests.
- Accuracy tests cover TP, FP, FN, deduplication, insufficient samples, and per-category output.
- Job listing/retry, duplicate warning, retention preview, backup verification, and PDF pagination are covered by tests.
- Browser acceptance covers login, tasks, jobs, members/admin, feedback, report download, version diff, and 1440/768/390/375px layouts.
- Public endpoints are rechecked only after the local suite and browser acceptance pass.
