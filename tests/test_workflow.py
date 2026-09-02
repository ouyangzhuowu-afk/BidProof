import copy

from app.workflow import load_state, next_action, validate_state


def test_persistent_workflow_state_is_valid():
    state = load_state()
    assert validate_state(state) == []
    assert next_action(state)["task_id"] == "T-005"


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
