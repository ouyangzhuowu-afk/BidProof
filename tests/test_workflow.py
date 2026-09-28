import copy

from app.workflow import load_state, next_action, validate_state


def test_persistent_workflow_state_is_valid():
    state = load_state()
    assert validate_state(state) == []
    assert next_action(state)["task_id"] == "T-005"
    t005 = next(task for task in state["in_progress"] if task.get("id") == "T-005")
    assert t005["status"] == "in_progress"
    assert "blocked_reason" not in t005
    blocked_by = next_action(state).get("blocked_by") or []
    assert any("real enterprise" in item.lower() or "Joe" in item for item in blocked_by)
    assert all(task.get("id") != "T-005" for task in state["completed"])
    assert any(d.get("id") == "D-T005-UNBLOCK-2026-09-28" for d in state["decisions"])


def test_state_rejects_completed_next_action():
    state = load_state()
    broken = copy.deepcopy(state)
    broken["next_best_action"]["task_id"] = "C-001"
    assert any("completed task" in error for error in validate_state(broken))


def test_state_rejects_artifact_path_escape():
    state = load_state()
    broken = copy.deepcopy(state)
    broken["artifacts"].append({"path": "../outside.txt", "kind": "bad", "status": "verified"})
    assert any("escapes project root" in error for error in validate_state(broken))
