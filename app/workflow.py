"""Persistent Agent Workflow Package state checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

WORKFLOW_ROOT = PROJECT_ROOT / "workflow"
STATE_PATH = WORKFLOW_ROOT / "project-state.json"
SCHEMA_PATH = WORKFLOW_ROOT / "schemas" / "project-state.schema.json"
ALLOWED_STATUSES = {"pending", "in_progress", "completed", "blocked", "needs_verification"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "project_id",
    "goal",
    "success_criteria",
    "current_stage",
    "stage_status",
    "completed",
    "in_progress",
    "backlog",
    "dependencies",
    "decisions",
    "open_questions",
    "risks",
    "artifacts",
    "next_best_action",
    "updated_at",
}


class WorkflowStateError(ValueError):
    """Raised when the persistent workflow state cannot be trusted."""


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError as exc:
        raise WorkflowStateError(f"state file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowStateError(f"state file is invalid JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise WorkflowStateError("state root must be an object")
    return state


def validate_state(state: dict[str, Any], project_root: Path = PROJECT_ROOT) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - state.keys())
    errors.extend(f"missing top-level field: {field}" for field in missing)
    if state.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")
    if state.get("project_id") != "project-025-bid-evidence-agent":
        errors.append("project_id does not match Project-025")
    if state.get("stage_status") not in ALLOWED_STATUSES:
        errors.append("stage_status is invalid")

    task_sets = {
        name: state.get(name, [])
        for name in ("completed", "in_progress", "backlog")
    }
    task_ids: set[str] = set()
    for group, tasks in task_sets.items():
        if not isinstance(tasks, list):
            errors.append(f"{group} must be a list")
            continue
        for task in tasks:
            if not isinstance(task, dict) or not task.get("id"):
                errors.append(f"{group} contains a task without id")
                continue
            task_id = str(task["id"])
            if task_id in task_ids:
                errors.append(f"duplicate task id: {task_id}")
            task_ids.add(task_id)
            if task.get("status") not in ALLOWED_STATUSES | {"verified", "archived"}:
                errors.append(f"{task_id} has invalid status")
            dependencies = task.get("dependencies", [])
            if not isinstance(dependencies, list):
                errors.append(f"{task_id}.dependencies must be a list")
            else:
                for dependency in dependencies:
                    if dependency not in task_ids and dependency not in {
                        item.get("id") for item in state.get("dependencies", []) if isinstance(item, dict)
                    }:
                        # A dependency can be declared later in the file, so defer this check below.
                        continue

    declared_ids = task_ids | {
        item.get("id") for item in state.get("dependencies", []) if isinstance(item, dict)
    }
    for group, tasks in task_sets.items():
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            for dependency in task.get("dependencies", []):
                if dependency not in declared_ids:
                    errors.append(f"{task.get('id', '<unknown>')} has unknown dependency: {dependency}")

    next_action = state.get("next_best_action")
    if not isinstance(next_action, dict):
        errors.append("next_best_action must be an object")
    else:
        next_id = next_action.get("task_id")
        if next_id not in task_ids:
            errors.append(f"next_best_action references unknown task: {next_id}")
        else:
            task = next(task for group in task_sets.values() for task in group if task.get("id") == next_id)
            if task.get("status") in {"completed", "verified", "archived"}:
                errors.append(f"next_best_action references completed task: {next_id}")
            completed_ids = {
                item.get("id")
                for item in state.get("completed", [])
                if isinstance(item, dict) and item.get("status") in {"completed", "verified", "archived"}
            }
            for dependency in task.get("dependencies", []):
                if dependency not in completed_ids:
                    errors.append(f"next_best_action dependency is not complete: {dependency}")

    for artifact in state.get("artifacts", []):
        if not isinstance(artifact, dict) or not artifact.get("path"):
            errors.append("artifacts must contain path")
            continue
        candidate = (project_root / artifact["path"]).resolve()
        try:
            candidate.relative_to(project_root.resolve())
        except ValueError:
            errors.append(f"artifact escapes project root: {artifact['path']}")
            continue
        if artifact.get("status") == "verified" and not candidate.exists():
            errors.append(f"verified artifact does not exist: {artifact['path']}")

    return errors


def next_action(state: dict[str, Any]) -> dict[str, Any]:
    action = state["next_best_action"]
    if action["task_id"] in {task.get("id") for task in state.get("completed", [])}:
        raise WorkflowStateError("next_best_action points to a completed task")
    return action


def _run_check() -> int:
    try:
        state = load_state()
        errors = validate_state(state)
    except WorkflowStateError as exc:
        print(f"FAIL: {exc}")
        return 1
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: Project-025 workflow state is valid")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Project-025 persistent workflow state")
    parser.add_argument("command", choices=("check", "next-action"))
    args = parser.parse_args(argv)
    if args.command == "check":
        return _run_check()
    try:
        state = load_state()
        errors = validate_state(state)
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(json.dumps(next_action(state), ensure_ascii=False, indent=2))
        return 0
    except WorkflowStateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
