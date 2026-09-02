from datetime import datetime, timezone

from app.db import accuracy_metrics, add_accuracy_feedback, init_db, save_run
from app.rules import extract_requirements, match_evidence


def _save_metric_run(path, workspace_id: str, run_id: str, requirement_count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    requirements = [
        {
            "requirement_id": f"REQ-{index:04d}",
            "category": "QUALIFICATION",
            "title": f"资格要求 {index}",
            "status": "NEEDS_REVIEW",
            "source": {"page": 1, "locator": {"kind": "page", "label": "第 1 页"}, "quote": "资格要求"},
            "evidence": [],
        }
        for index in range(1, requirement_count + 1)
    ]
    save_run({
        "run_id": run_id,
        "workspace_id": workspace_id,
        "owner_id": "reviewer",
        "created_at": now,
        "updated_at": now,
        "status": "AUDIT",
        "tender_filename": "fixture.pdf",
        "tender_path": "fixture.pdf",
        "evidence_files": [],
        "state": {},
        "requirements": requirements,
        "review": {"items": []},
    }, path)


def _feedback(requirement_id: str, scope: str, review_complete: bool = False) -> dict:
    return {
        "category": "QUALIFICATION",
        "predicted": "DETECTED",
        "actual": "RELEVANT",
        "requirement_id": requirement_id,
        "locator_label": None,
        "quote": None,
        "note": "",
        "dataset_scope": scope,
        "review_complete": review_complete,
    }


def test_accuracy_metrics_exclude_test_feedback_by_default(tmp_path):
    database = tmp_path / "metrics.sqlite3"
    init_db(database)
    _save_metric_run(database, "workspace", "run-1", 2)
    add_accuracy_feedback("workspace", "run-1", "reviewer", _feedback("REQ-0001", "TEST"), database)
    add_accuracy_feedback("workspace", "run-1", "reviewer", _feedback("REQ-0002", "PILOT"), database)

    categories = accuracy_metrics("workspace", path=database)
    qualification = next(item for item in categories if item["category"] == "QUALIFICATION")

    assert qualification["tp"] == 1
    assert qualification["sample_size"] == 1
    assert qualification["included_scopes"] == ["PILOT", "ENTERPRISE"]


def test_complete_review_is_required_before_metrics_are_measurable(tmp_path):
    database = tmp_path / "complete.sqlite3"
    init_db(database)
    _save_metric_run(database, "workspace", "run-complete", 20)
    for index in range(1, 21):
        add_accuracy_feedback(
            "workspace",
            "run-complete",
            "reviewer",
            _feedback(f"REQ-{index:04d}", "PILOT", review_complete=False),
            database,
        )

    before = accuracy_metrics("workspace", path=database)[0]
    assert before["coverage"] == 1.0
    assert before["sample_size"] == 20
    assert before["review_population_complete"] is False
    assert before["measurement_status"] == "INSUFFICIENT"

    for index in range(1, 21):
        add_accuracy_feedback(
            "workspace",
            "run-complete",
            "reviewer",
            _feedback(f"REQ-{index:04d}", "PILOT", review_complete=True),
            database,
        )
    after = accuracy_metrics("workspace", path=database)[0]
    assert after["review_population_complete"] is True
    assert after["measurement_status"] == "MEASURABLE"


def test_keyword_evidence_match_is_only_a_review_suggestion():
    requirements = extract_requirements([{"page": 2, "text": "资格要求：提供营业执照。"}])
    matched = match_evidence(requirements, [{"page": 1, "text": "本公司营业执照有效。"}], "company.txt")

    assert matched[0]["status"] == "NEEDS_REVIEW"
    assert matched[0]["suggested_status"] == "PASS"
    assert matched[0]["match_review_status"] == "PENDING"
    assert matched[0]["confidence"] is None
    assert matched[0]["rule_score_kind"] == "HEURISTIC_MATCH_COUNT"
    assert matched[0]["confidence_kind"] == "UN_CALIBRATED_HEURISTIC"


def test_false_positive_rate_uses_negative_population_denominator(tmp_path):
    database = tmp_path / "fpr.sqlite3"
    init_db(database)
    _save_metric_run(database, "workspace", "run-fpr", 10)
    add_accuracy_feedback("workspace", "run-fpr", "reviewer", {**_feedback("REQ-0001", "PILOT"), "actual": "RELEVANT"}, database)
    add_accuracy_feedback("workspace", "run-fpr", "reviewer", {**_feedback("REQ-0002", "PILOT"), "actual": "NOT_RELEVANT"}, database)
    for index in range(3, 11):
        add_accuracy_feedback("workspace", "run-fpr", "reviewer", {**_feedback(f"REQ-{index:04d}", "PILOT"), "predicted": "MISSED", "actual": "NOT_RELEVANT", "locator_label": f"第 {index} 页"}, database)

    metric = next(item for item in accuracy_metrics("workspace", path=database) if item["category"] == "QUALIFICATION")
    assert metric["false_positive_rate"] == round(1 / 9, 4)


def test_accuracy_coverage_denominator_excludes_runs_outside_selected_scopes(tmp_path):
    database = tmp_path / "metrics-scope.sqlite3"
    init_db(database)
    _save_metric_run(database, "workspace", "pilot-run", 2)
    _save_metric_run(database, "workspace", "test-run", 2)
    add_accuracy_feedback("workspace", "pilot-run", "reviewer", {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": "REQ-0001", "dataset_scope": "PILOT", "review_complete": True}, database)
    add_accuracy_feedback("workspace", "pilot-run", "reviewer", {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": "REQ-0002", "dataset_scope": "PILOT", "review_complete": True}, database)
    add_accuracy_feedback("workspace", "test-run", "reviewer", {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": "REQ-0001", "dataset_scope": "TEST", "review_complete": True}, database)

    metric = next(item for item in accuracy_metrics("workspace", path=database) if item["category"] == "QUALIFICATION")

    assert metric["detected_total"] == 2
    assert metric["coverage"] == 1


def test_accuracy_population_is_incomplete_when_any_feedback_row_is_unreviewed(tmp_path):
    database = tmp_path / "metrics-complete.sqlite3"
    init_db(database)
    _save_metric_run(database, "workspace", "pilot-run", 2)
    add_accuracy_feedback("workspace", "pilot-run", "reviewer", {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "RELEVANT", "requirement_id": "REQ-0001", "dataset_scope": "PILOT", "review_complete": True}, database)
    add_accuracy_feedback("workspace", "pilot-run", "reviewer", {"category": "QUALIFICATION", "predicted": "DETECTED", "actual": "NOT_RELEVANT", "requirement_id": "REQ-0002", "dataset_scope": "PILOT", "review_complete": False}, database)

    metric = next(item for item in accuracy_metrics("workspace", path=database) if item["category"] == "QUALIFICATION")

    assert metric["review_population_complete"] is False
