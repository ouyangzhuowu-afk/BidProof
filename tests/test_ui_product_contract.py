from html.parser import HTMLParser
from pathlib import Path
import re

from fastapi.testclient import TestClient

from app import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_JS = PROJECT_ROOT / "frontend" / "src" / "app.js"
BUILT_JS = PROJECT_ROOT / "static" / "app.js"


class LandmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_workspace_has_keyboard_and_navigation_landmarks():
    response = TestClient(main.app).get("/app")
    parser = LandmarkParser()
    parser.feed(response.text)

    assert ("a", {"class": "skip-link", "href": "#app-main"}) in parser.elements
    assert any(tag == "nav" and attrs.get("aria-label") == "主导航" for tag, attrs in parser.elements)
    assert any(tag == "main" and attrs.get("id") == "app-main" for tag, attrs in parser.elements)


def test_dynamic_feedback_is_announced_without_stealing_focus():
    response = TestClient(main.app).get("/app")
    parser = LandmarkParser()
    parser.feed(response.text)

    live_regions = [attrs for _, attrs in parser.elements if attrs.get("aria-live") == "polite"]
    assert len(live_regions) >= 2


def test_accuracy_feedback_ui_collects_complete_human_labels():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="missed-locator"' in html
    assert 'id="missed-quote"' in html
    assert 'data-accuracy="RELEVANT"' in script
    assert 'data-accuracy="NOT_RELEVANT"' in script
    assert "measurement_status" in script


def test_enterprise_operations_are_exposed_as_complete_views():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")

    for element_id in (
        "nav-jobs",
        "nav-admin",
        "jobs-view",
        "admin-view",
        "jobs-list",
        "member-form",
        "member-role",
        "members-list",
        "retention-form",
        "retention-preview",
        "create-backup",
        "backups-list",
        "version-diff",
        "duplicate-warning",
        "project-form",
        "projects-list",
        "tender-project",
        "run-project-filter",
        "remediation-form",
        "remediation-title-input",
        "remediation-requirement",
        "remediation-owner",
        "remediation-due",
        "remediations-list",
        "workspace-usage",
        "workspace-privacy",
        "notifications-list",
        "source-files",
        "password-form",
        "sessions-list",
        "current-password",
        "new-password",
        "run-search",
        "run-tag-filter",
        "run-assignee-filter",
        "run-reviewer-filter",
        "run-sort",
        "run-favorite-filter",
        "clear-run-filters",
        "toggle-filters",
        "filter-advanced",
        "filter-badge",
        "risk-summary",
        "home-lede",
        "notification-count",
        "accuracy-summary",
        "mfa-form",
        "mfa-code",
        "token-form",
        "token-name",
        "tokens-list",
        "bulk-export",
        "run-reviewer",
    ):
        assert f'id="{element_id}"' in html

    for function_name in (
        "showJobs",
        "loadJobs",
        "showAdmin",
        "loadMembers",
        "loadOperations",
        "loadVersionDiff",
        "loadProjects",
        "loadCollaboration",
        "createRemediation",
        "updateRemediation",
        "renderRemediations",
        "loadNotifications",
        "loadSessions",
        "renderRiskSummary",
        "syncFilterDisclosure",
    ):
        assert f"function {function_name}" in script or f"async function {function_name}" in script


def test_home_view_collapses_duplicate_scan_actions_and_empty_chrome():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    source = SOURCE_JS.read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="nav-new-scan"' not in html
    assert 'id="new-scan-button"' not in html
    assert 'id="top-new-scan"' in html
    assert 'id="overview-grid"' not in html
    assert 'id="risk-summary"' in html
    assert 'vendor/lucide.min.js' not in html
    assert 'id="empty-start-scan"' in source
    assert 'id="empty-sample-scan"' in source
    assert "is-first-run" in source
    assert "#home-view.is-first-run .task-filter-bar" in css
    assert ".risk-summary" in css
    assert "from './icons.js'" in source or 'from "./icons.js"' in source
    assert "#top-new-scan.button.compact-action { display: inline-flex; }" in css


def test_ui_does_not_reference_missing_archived_clock_icon():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-lucide="archive-clock"' not in html


def test_jobs_view_exposes_progress_and_failure_recovery_controls():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="jobs-list"' in html
    assert "job-progress" in script
    assert "progress_current" in script
    assert "data-retry-job" in script
    assert "data-cancel-job" in script
    assert "function cancelJob" in script
    assert ".job-progress-track" in css
    assert "--primary: #087f72" in css


def test_source_download_and_password_rotation_are_connected_to_api_contracts():
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/runs/${encodeURIComponent(store.currentRun.run_id)}/files/" in script or "/api/runs/${encodeURIComponent(currentRun.run_id)}/files/" in script
    assert "/api/auth/password" in script
    assert "/api/auth/register" in script
    assert "/api/runs/bulk/report.zip" in script


def test_auth_dialog_exposes_personal_register_and_enterprise_modes():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-auth-mode="setup"' in html
    assert 'data-auth-mode="login"' in html
    assert 'data-auth-mode="register"' in html
    assert 'data-auth-mode="trial"' in html
    assert 'id="register-fields"' in html
    assert 'id="auth-display-name"' in html
    source = SOURCE_JS.read_text(encoding="utf-8")
    assert "store.authMode === 'register'" in source or 'store.authMode === "register"' in source


def test_task_management_exposes_search_filters_and_independent_reviewer():
    response = TestClient(main.app).get("/app")
    parser = LandmarkParser()
    parser.feed(response.text)
    elements = {attrs.get("id"): (tag, attrs) for tag, attrs in parser.elements if attrs.get("id")}

    assert elements["run-search"][0] == "input"
    assert elements["run-search"][1].get("type") == "search"
    assert elements["run-favorite-filter"][0] == "input"
    assert elements["run-favorite-filter"][1].get("type") == "checkbox"
    assert elements["run-assignee-filter"][0] == "select"
    assert elements["run-reviewer-filter"][0] == "select"
    assert elements["run-sort"][0] == "select"
    assert elements["run-reviewer"][0] == "select"


def test_async_form_handlers_preserve_the_form_across_await_boundaries():
    script = SOURCE_JS.read_text(encoding="utf-8")

    for function_name in ("submitAuth", "createProject", "createMember", "submitMissedFeedback"):
        match = re.search(
            rf"async function {function_name}\(event\) \{{(?P<body>.*?)\n\}}",
            script,
            re.DOTALL,
        )
        assert match, f"missing async form handler: {function_name}"
        body = match.group("body")
        first_await = body.index("await ")

        assert "const form = event.currentTarget;" in body[:first_await]
        assert "event.currentTarget" not in body[first_await:]
