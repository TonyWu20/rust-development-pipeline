#!/usr/bin/env python3
"""
Validate a directions.json file against the directions-spec.

Reads a directions.json file from disk, validates its structure and semantics
against the specification, and exits with:
  0 — valid
  1 — invalid

Usage:
  python validate-directions.py <path-to-directions.json>

Outputs validation errors to stderr.
"""

import json
import sys
from collections import deque
from pathlib import Path


ERRORS: list[str] = []


def error(msg: str) -> None:
    ERRORS.append(msg)
    print(f"ERROR: {msg}", file=sys.stderr)


def validate_meta(data: dict) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        error("'meta' must be a dict")
        return
    if not isinstance(meta.get("title"), str) or not meta["title"].strip():
        error("meta.title is required and must be a non-empty string")
    if not isinstance(meta.get("source_branch"), str) or not meta["source_branch"].strip():
        error("meta.source_branch is required and must be a non-empty string")


def validate_architecture_notes(data: dict) -> None:
    notes = data.get("architecture_notes")
    if notes is not None:
        if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
            error("architecture_notes must be a list of strings or omitted")


def validate_known_pitfalls(data: dict) -> None:
    pitfalls = data.get("known_pitfalls")
    if pitfalls is not None:
        if not isinstance(pitfalls, list) or not all(isinstance(p, str) for p in pitfalls):
            error("known_pitfalls must be a list of strings or omitted")


def validate_task_groups(data: dict) -> list[dict]:
    groups = data.get("task_groups", [])
    if not isinstance(groups, list):
        error("task_groups must be a list")
        return []

    seen_ids: set[str] = set()
    all_task_ids = {t["id"] for t in data.get("tasks", []) if isinstance(t, dict)}

    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            error(f"task_groups[{i}] must be a dict")
            continue

        gid = group.get("group_id")
        if not isinstance(gid, str) or not gid.strip():
            error(f"task_groups[{i}].group_id is required and must be a non-empty string")
            continue

        if gid in seen_ids:
            error(f"Duplicate group_id: '{gid}'")
        seen_ids.add(gid)

        if not isinstance(group.get("reason"), str) or not group["reason"].strip():
            error(f"task_groups[{i}] ('{gid}'): 'reason' is required and must be a non-empty string")

        tasks = group.get("tasks", [])
        if not isinstance(tasks, list):
            error(f"task_groups[{i}] ('{gid}'): 'tasks' must be a list")
        else:
            for j, tid in enumerate(tasks):
                if tid not in all_task_ids:
                    error(
                        f"task_groups[{i}] ('{gid}'): tasks[{j}]='{tid}' "
                        f"references unknown task"
                    )

        deps = group.get("depends_on_groups", [])
        if not isinstance(deps, list):
            error(f"task_groups[{i}] ('{gid}'): 'depends_on_groups' must be a list")

    return groups


def detect_circular_group_deps(
    groups: list[dict], group_map: dict[str, dict]
) -> None:
    """Detect circular dependencies between task groups."""
    for group in groups:
        gid = group["group_id"]
        visited = {gid}
        queue = deque(group.get("depends_on_groups", []))
        while queue:
            dep = queue.popleft()
            if dep in visited:
                error(
                    f"Circular group dependency detected involving '{gid}' "
                    f"and '{dep}'"
                )
                return
            visited.add(dep)
            dep_group = group_map.get(dep)
            if dep_group:
                queue.extend(dep_group.get("depends_on_groups", []))


def validate_tasks(data: dict) -> list[dict]:
    tasks = data.get("tasks", [])
    if not isinstance(tasks, list):
        error("tasks must be a list")
        return []

    seen_ids: set[str] = set()

    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            error(f"tasks[{i}] must be a dict")
            continue

        tid = task.get("id")
        if not isinstance(tid, str) or not tid.strip():
            error(f"tasks[{i}].id is required and must be a non-empty string")
            continue

        if tid in seen_ids:
            error(f"Duplicate task id: '{tid}'")
        seen_ids.add(tid)

        if not isinstance(task.get("description"), str) or not task["description"].strip():
            error(f"Task '{tid}': 'description' is required and must be a non-empty string")

        files_in_scope = task.get("files_in_scope", [])
        if not isinstance(files_in_scope, list):
            error(f"Task '{tid}': 'files_in_scope' must be a list")
        elif not files_in_scope:
            error(f"Task '{tid}': 'files_in_scope' must not be empty")

        changes = task.get("changes", [])
        if not isinstance(changes, list) or not changes:
            error(f"Task '{tid}': 'changes' must be a non-empty list")
        else:
            seen_paths: set[str] = set()
            for j, change in enumerate(changes):
                if not isinstance(change, dict):
                    error(f"Task '{tid}': changes[{j}] must be a dict")
                    continue
                path = change.get("path")
                if not isinstance(path, str) or not path.strip():
                    error(f"Task '{tid}': changes[{j}].path is required")
                    continue
                if path in seen_paths:
                    error(f"Task '{tid}': duplicate changes path '{path}'")
                seen_paths.add(path)

                action = change.get("action")
                if action not in ("create", "modify", "delete"):
                    error(
                        f"Task '{tid}': changes[{j}].action must be one of: "
                        f"create, modify, delete (got '{action}')"
                    )

                guidance = change.get("guidance")
                if action in ("create", "modify") and (
                    not isinstance(guidance, str) or not guidance.strip()
                ):
                    error(
                        f"Task '{tid}': changes[{j}].guidance is required "
                        f"for action '{action}'"
                    )

        wiring = task.get("wiring_checklist", [])
        if wiring is not None:
            if not isinstance(wiring, list):
                error(f"Task '{tid}': 'wiring_checklist' must be a list")
            else:
                for j, w in enumerate(wiring):
                    if not isinstance(w, dict):
                        error(f"Task '{tid}': wiring_checklist[{j}] must be a dict")
                        continue
                    if w.get("kind") not in ("pub_mod", "pub_use", "fn_call", "type_annotation"):
                        error(
                            f"Task '{tid}': wiring_checklist[{j}].kind must be "
                            f"pub_mod|pub_use|fn_call|type_annotation"
                        )
                    if not isinstance(w.get("file"), str) or not w["file"].strip():
                        error(
                            f"Task '{tid}': wiring_checklist[{j}].file is required"
                        )
                    if not isinstance(w.get("detail"), str) or not w["detail"].strip():
                        error(
                            f"Task '{tid}': wiring_checklist[{j}].detail is required"
                        )

        acceptance = task.get("acceptance", [])
        if not isinstance(acceptance, list) or not acceptance:
            error(f"Task '{tid}': 'acceptance' must be a non-empty list of command strings")
        else:
            for j, cmd in enumerate(acceptance):
                if not isinstance(cmd, str) or not cmd.strip():
                    error(f"Task '{tid}': acceptance[{j}] must be a non-empty string")

    return tasks


def detect_circular_task_deps(tasks: list[dict]) -> None:
    """Detect circular dependencies between tasks."""
    task_map = {t["id"]: t for t in tasks if isinstance(t, dict) and "id" in t}

    for task in tasks:
        tid = task["id"]
        visited = {tid}
        queue = deque(task.get("depends_on", []))
        while queue:
            dep = queue.popleft()
            if dep in visited:
                error(f"Circular task dependency detected involving '{tid}' and '{dep}'")
                return
            visited.add(dep)
            dep_task = task_map.get(dep)
            if dep_task:
                queue.extend(dep_task.get("depends_on", []))


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path-to-directions.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        error(f"File not found: {path}")
        sys.exit(1)

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        error(f"Invalid JSON: {e}")
        sys.exit(1)

    if not isinstance(data, dict):
        error("Root element must be a JSON object")
        sys.exit(1)

    validate_meta(data)
    validate_architecture_notes(data)
    validate_known_pitfalls(data)
    groups = validate_task_groups(data)
    tasks = validate_tasks(data)

    if groups:
        group_map = {g["group_id"]: g for g in groups if "group_id" in g}
        detect_circular_group_deps(groups, group_map)

    if tasks:
        detect_circular_task_deps(tasks)

    if ERRORS:
        print(f"\nValidation FAILED — {len(ERRORS)} error(s)", file=sys.stderr)
        sys.exit(1)
    else:
        print("Validation PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
