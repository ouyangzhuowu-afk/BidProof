import copy

from app.workflow import load_state, next_action, validate_state


def _find(state, task_id):
    for group in ("completed", "in_progress", "backlog"):
        for task in state[group]:
            if task.get("id") == task_id:
                return group, task
    raise AssertionError(task_id)


def test_persistent_workflow_state_is_valid():
    state = load_state()
    assert validate_state(state) == []
    assert next_action(state)["task_id"] == "T-005"
    group, t005 = _find(state, "T-005")
    assert group == "backlog"
    assert t005["status"] == "blocked"
    assert "blocked_reason" in t005
    assert "unblocked" not in t005.get("validation", "").lower()
    ready_group, ready = _find(state, "C-T005-READY-2026-09-28")
    assert ready_group == "backlog"
    assert ready["status"] == "pending_audit"
    assert "scaffold-only" in ready.get("note", "")
    blocked_by = next_action(state).get("blocked_by") or []
    assert any("real enterprise" in item.lower() or "Joe" in item for item in blocked_by)
    assert all(task.get("id") != "T-005" for task in state["completed"])
    assert all(task.get("id") != "C-T005-READY-2026-09-28" for task in state["completed"])
    decision = next(item for item in state["decisions"] if item.get("id") == "D-T005-UNBLOCK-2026-09-28")
    assert decision["decided_by"] == "Edith (orchestration)"
    assert decision["scope"] == "scaffold-only"
    assert "修 #13" in decision["evidence"]
    assert "2026-09-29" in decision["evidence"]


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
