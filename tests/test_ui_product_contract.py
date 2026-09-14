from html.parser import HTMLParser
from pathlib import Path
import re

from fastapi.testclient import TestClient

from app import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_JS = PROJECT_ROOT / "frontend" / "src" / "app.js"
FRONTEND_SRC = PROJECT_ROOT / "frontend" / "src"
BUILT_JS = PROJECT_ROOT / "static" / "app.js"


def _read_frontend_sources() -> str:
    parts = [SOURCE_JS.read_text(encoding="utf-8")]
    for path in FRONTEND_SRC.rglob("*.js"):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


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
    sources = _read_frontend_sources()

    assert 'id="missed-locator"' in html
    assert 'id="missed-quote"' in html
    assert 'data-accuracy="RELEVANT"' in sources
    assert 'data-accuracy="NOT_RELEVANT"' in sources
    # Compliance: incomplete review population must stay visible / not look verified.
    assert "review_population_complete" in sources
    assert "formatPercent(summary.precision" in sources or "summary.precision" in sources


def test_enterprise_operations_are_exposed_as_complete_views():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    sources = _read_frontend_sources()

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
        "runs-notices-body",
        "source-files",
        "password-form",
        "sessions-list",
        "current-password",
        "new-password",
        "runs-search",
        "runs-tag",
        "runs-assignee",
        "runs-reviewer",
        "runs-sort",
        "runs-favorite",
        "runs-clear-filters-btn",
        "mfa-form",
        "mfa-code",
        "token-form",
        "token-name",
        "tokens-list",
        "run-reviewer",
    ):
        assert f'id="{element_id}"' in html, f"missing landmark id={element_id}"

    for symbol in (
        "showJobs",
        "mountJobsView",
        "reloadJobs",
        "showAdmin",
        "mountAdminView",
        "loadVersionDiff",
        "loadProjects",
        "loadCollab",
        "mountCollab",
        "configureAuth",
        "startAuth",
        "watchScanJob",
        "listNotifications",
    ):
        assert symbol in sources, f"missing frontend symbol: {symbol}"


def test_ui_does_not_reference_missing_archived_clock_icon():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-lucide="archive-clock"' not in html


def test_jobs_view_exposes_progress_and_failure_recovery_controls():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    sources = _read_frontend_sources()
    css = (PROJECT_ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert 'id="jobs-list"' in html
    assert "progress_current" in sources
    assert "data-retry-job" in sources
    assert "data-cancel-job" in sources
    assert "retryJob" in sources and "cancelJob" in sources
    assert ".job-progress-track" in css
    assert "--primary: #087f72" in css


def test_source_download_and_password_rotation_are_connected_to_api_contracts():
    sources = _read_frontend_sources()
    built = BUILT_JS.read_text(encoding="utf-8")
    assert "/api/runs/" in sources and "/files/" in sources
    assert "/api/auth/password" in sources
    assert "/api/auth/register" in sources
    assert "/api/runs/bulk/report.zip" in sources
    # Built bundle must still contain the same contract strings.
    assert "/api/auth/password" in built
    assert "/api/auth/register" in built


def test_auth_dialog_exposes_personal_register_and_enterprise_modes():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    auth_state = (FRONTEND_SRC / "features" / "auth" / "state.js").read_text(encoding="utf-8")
    assert 'data-auth-mode="setup"' in html
    assert 'data-auth-mode="login"' in html
    assert 'data-auth-mode="register"' in html
    assert 'data-auth-mode="trial"' in html
    assert 'id="register-fields"' in html
    assert 'id="auth-display-name"' in html
    assert "'register'" in auth_state
    assert "MODE_ENDPOINT" in auth_state


def test_task_management_exposes_search_filters_and_independent_reviewer():
    response = TestClient(main.app).get("/app")
    parser = LandmarkParser()
    parser.feed(response.text)
    elements = {attrs.get("id"): (tag, attrs) for tag, attrs in parser.elements if attrs.get("id")}

    assert elements["runs-search"][0] == "input"
    assert elements["runs-search"][1].get("type") == "search"
    assert elements["runs-favorite"][0] == "input"
    assert elements["runs-favorite"][1].get("type") == "checkbox"
    assert elements["runs-assignee"][0] == "select"
    assert elements["runs-reviewer"][0] == "select"
    assert elements["runs-sort"][0] == "select"
    assert elements["run-reviewer"][0] == "select"


def test_async_form_handlers_preserve_the_form_across_await_boundaries():
    sources = {
        "submitAuth": (FRONTEND_SRC / "features" / "auth" / "index.js").read_text(encoding="utf-8"),
        "createProject": (FRONTEND_SRC / "features" / "admin" / "projects.js").read_text(encoding="utf-8"),
        "createMember": (FRONTEND_SRC / "features" / "admin" / "members.js").read_text(encoding="utf-8"),
        "submitMissedFeedback": SOURCE_JS.read_text(encoding="utf-8"),
    }
    aliases = {
        "createProject": "submitCreate",
        "createMember": "submitCreate",
        "submitAuth": "async function submit",
    }

    for logical_name, script in sources.items():
        search_name = aliases.get(logical_name, logical_name)
        if search_name.startswith("async function"):
            pattern = rf"{re.escape(search_name)}\(event\) \{{(?P<body>.*?)\n\}}"
        else:
            pattern = rf"async function {search_name}\(event\) \{{(?P<body>.*?)\n\}}"
        match = re.search(pattern, script, re.DOTALL)
        assert match, f"missing async form handler for {logical_name} ({search_name})"
        body = match.group("body")
        assert "await " in body
        first_await = body.index("await ")
        assert "event.currentTarget" in body[:first_await] or "const form =" in body[:first_await]
        assert "event.currentTarget" not in body[first_await:]


def test_scan_tasks_home_keeps_aligned_workbench_landmarks():
    """Opus5 strangler home: new-scan CTAs + runs metrics/filters/accuracy (not patch-002 risk-summary)."""
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "static" / "style.css").read_text(encoding="utf-8")

    assert 'id="nav-new-scan"' in html
    assert 'id="new-scan-button"' in html
    assert 'id="top-new-scan"' in html
    assert 'id="home-view"' in html
    assert 'id="runs-metrics"' in html
    assert 'id="runs-filters"' in html
    assert 'id="runs-list"' in html
    assert 'id="runs-accuracy-body"' in html
    assert 'id="risk-summary"' not in html
    assert "/static/vendor/lucide.min.js" in html
    assert ".metric-grid" in css or ".runs-list" in css
    assert "data-theme" in html or "[data-theme" in css
