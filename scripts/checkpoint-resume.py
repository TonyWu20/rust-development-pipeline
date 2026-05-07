#!/usr/bin/env python3
"""
Checkpoint and resume utility for the explore-implement pipeline.

Manages worktree-based checkpoint state so interrupted sessions can resume
without losing progress.  The core insight is that the worktree IS the
checkpoint — this utility just records metadata about what was completed.

Usage:
  checkpoint-resume.py init <tasks-path> <worktree-path>
      Create initial checkpoint from a TASKS.md file.

  checkpoint-resume.py complete <group-id> <worktree-path> [task-id]
      Mark a task group as completed (or mark a single task, auto-promote).

  checkpoint-resume.py failed <group-id> <worktree-path> [reason]
      Mark a task group as failed.

  checkpoint-resume.py status <worktree-path>
      Show current checkpoint status.

  checkpoint-resume.py remaining <tasks-path> <worktree-path>
      List task groups not yet completed.

  checkpoint-resume.py clear <worktree-path>
      Remove checkpoint for a completed session.

  checkpoint-resume.py source-branch <worktree-path>
      Read the source branch recorded in the checkpoint.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional


def _checkpoint_path(worktree_path: str) -> Path:
    return Path(worktree_path) / ".exploration_checkpoint.json"


def _parse_tasks_md(tasks_path: str) -> dict:
    """Parse TASKS.md and return {group_id: {"tasks": [task_id, ...], "reason": "..."}}."""
    path = Path(tasks_path)
    if not path.exists():
        print(f"ERROR: TASKS.md not found: {tasks_path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text()
    groups = {}

    # Match each ## Task Group: section
    group_pattern = re.compile(
        r"^## Task Group:\s*(\S+)[^\n]*(?:\n|$)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )

    for match in group_pattern.finditer(text):
        group_id = match.group(1)
        body = match.group(2)

        # Extract reason
        reason_match = re.search(r"\*\*Reason:\*\*\s*(.*)", body)
        reason = reason_match.group(1).strip() if reason_match else ""

        # Extract task IDs from ### TASK-{N}: headers
        tasks = re.findall(r"^###\s+(TASK-\S+):", body, re.MULTILINE)

        groups[group_id] = {
            "tasks": tasks,
            "reason": reason,
        }

    if not groups:
        print(f"ERROR: No '## Task Group:' sections found in {tasks_path}",
              file=sys.stderr)
        sys.exit(1)

    return groups


def _read_tasks_path_from_checkpoint(checkpoint: dict) -> str:
    tasks_path = checkpoint.get("tasks_path")
    if not tasks_path:
        print("ERROR: Checkpoint has no 'tasks_path' key. Was it created by an old version?",
              file=sys.stderr)
        sys.exit(1)
    if not Path(tasks_path).exists():
        print(f"ERROR: TASKS.md not found at '{tasks_path}' (recorded in checkpoint). "
              f"Has it been moved?", file=sys.stderr)
        sys.exit(1)
    return tasks_path


def cmd_init(tasks_path: str, worktree_path: str, source_branch: Optional[str] = None) -> None:
    # Validate TASKS.md exists and has groups (populates groups map we don't need yet)
    _parse_tasks_md(tasks_path)

    checkpoint = {
        "tasks_path": str(Path(tasks_path).resolve()),
        "worktree_path": str(Path(worktree_path).resolve()),
        "source_branch": source_branch,
        "groups": {},
    }

    cp_path = _checkpoint_path(worktree_path)
    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(f"Checkpoint initialized at {cp_path}")


def cmd_complete(group_id: str, worktree_path: str, task_id: Optional[str] = None) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("ERROR: No checkpoint found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    checkpoint = json.loads(cp_path.read_text())
    tasks_path = _read_tasks_path_from_checkpoint(checkpoint)

    # Parse TASKS.md for authoritative task list
    groups = _parse_tasks_md(tasks_path)
    if group_id not in groups:
        print(f"ERROR: Unknown group '{group_id}' — not found in TASKS.md", file=sys.stderr)
        sys.exit(1)

    group = groups[group_id]
    all_tasks = group["tasks"]

    # Ensure group entry exists in checkpoint (lazy init)
    if group_id not in checkpoint["groups"]:
        checkpoint["groups"][group_id] = {
            "status": "pending",
            "completed_tasks": [],
            "failed_reason": "",
        }

    cp_group = checkpoint["groups"][group_id]

    if task_id is not None:
        # Per-task tracking mode
        if task_id not in all_tasks:
            print(f"ERROR: Task '{task_id}' is not in group '{group_id}' (TASKS.md has: "
                  f"{', '.join(all_tasks)})", file=sys.stderr)
            sys.exit(1)

        if task_id in cp_group["completed_tasks"]:
            print(f"Task '{task_id}' was already completed in group '{group_id}'")
        else:
            cp_group["completed_tasks"].append(task_id)
            print(f"Task '{task_id}' marked as completed in group '{group_id}'")

        # Auto-promote: if all tasks are done, mark group as completed
        if set(cp_group["completed_tasks"]) == set(all_tasks):
            cp_group["status"] = "completed"
            print(f"All {len(all_tasks)} tasks complete — group '{group_id}'"
                  f" automatically marked as completed")
        else:
            pending = set(all_tasks) - set(cp_group["completed_tasks"])
            if pending:
                print(f"  Remaining tasks in '{group_id}': "
                      f"{', '.join(sorted(pending))}")
    else:
        # Legacy mode: no task_id — mark entire group complete at once
        cp_group["status"] = "completed"
        cp_group["completed_tasks"] = list(all_tasks)
        print(f"Group '{group_id}' marked as completed ({len(all_tasks)} tasks)")

    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")


def cmd_failed(group_id: str, worktree_path: str, reason: str = "") -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("ERROR: No checkpoint found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    checkpoint = json.loads(cp_path.read_text())
    tasks_path = _read_tasks_path_from_checkpoint(checkpoint)

    # Validate group exists in TASKS.md
    groups = _parse_tasks_md(tasks_path)
    if group_id not in groups:
        print(f"ERROR: Unknown group '{group_id}' — not found in TASKS.md", file=sys.stderr)
        sys.exit(1)

    # Ensure group entry exists (lazy init)
    if group_id not in checkpoint["groups"]:
        checkpoint["groups"][group_id] = {
            "status": "pending",
            "completed_tasks": [],
            "failed_reason": "",
        }

    checkpoint["groups"][group_id]["status"] = "failed"
    if reason:
        checkpoint["groups"][group_id]["failed_reason"] = reason
    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(f"Group '{group_id}' marked as failed")


def cmd_status(worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("No checkpoint found. Nothing initialized yet.")
        return

    checkpoint = json.loads(cp_path.read_text())
    tasks_path = _read_tasks_path_from_checkpoint(checkpoint)
    all_groups = _parse_tasks_md(tasks_path)

    cp_groups = checkpoint.get("groups", {})
    completed = []
    failed = []
    pending = []

    print(f"Tasks file: {tasks_path}")
    print(f"Worktree:   {checkpoint['worktree_path']}")
    print()

    # Merge TASKS.md groups with checkpoint progress
    for gid, g in all_groups.items():
        cp_entry = cp_groups.get(gid, {"status": "pending", "completed_tasks": []})
        status = cp_entry["status"]
        done = len(cp_entry.get("completed_tasks", []))
        total = len(g["tasks"])

        if status == "completed" or (done == total and total > 0):
            marker = "[DONE]"
            completed.append(gid)
        elif status == "failed":
            marker = "[FAIL]"
            failed.append(gid)
        elif done > 0:
            marker = f"[{done}/{total}]"
            pending.append(gid)
        else:
            marker = f"[0/{total}]"
            pending.append(gid)

        print(f"  {marker} {gid}")
        if status == "failed" and cp_entry.get("failed_reason"):
            print(f"      Reason: {cp_entry['failed_reason']}")
        if done > 0:
            print(f"      Done: {', '.join(cp_entry['completed_tasks'])}")
        pending_tasks = set(g["tasks"]) - set(cp_entry.get("completed_tasks", []))
        if pending_tasks and status != "failed":
            print(f"      Remaining: {', '.join(sorted(pending_tasks))}")

    print()
    print(f"Groups: {len(all_groups)} total")
    if completed:
        print(f"  Completed: {len(completed)}")
    if failed:
        print(f"  Failed:    {len(failed)} ({', '.join(failed)})")
    if pending:
        print(f"  Pending:   {len(pending)}")


def cmd_remaining(tasks_path: str, worktree_path: str) -> None:
    all_groups = _parse_tasks_md(tasks_path)

    cp_path = _checkpoint_path(worktree_path)
    if cp_path.exists():
        checkpoint = json.loads(cp_path.read_text())
        cp_groups = checkpoint.get("groups", {})
    else:
        cp_groups = {}

    for gid, g in all_groups.items():
        cp_entry = cp_groups.get(gid, {"status": "pending", "completed_tasks": []})
        if cp_entry["status"] == "completed":
            continue

        done = set(cp_entry.get("completed_tasks", []))
        pending_tasks = set(g["tasks"]) - done

        if cp_entry["status"] == "failed":
            reason = cp_entry.get("failed_reason", "")
            reason_str = f" — failed: {reason}" if reason else " — failed"
            print(f"{gid} (failed{pending_tasks and f', pending: {sorted(pending_tasks)}' or ''}){reason_str}")
        elif pending_tasks:
            print(f"{gid} (pending: {', '.join(sorted(pending_tasks))})")
        else:
            # All tasks done but status not updated (edge case)
            print(gid)


def cmd_clear(worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if cp_path.exists():
        cp_path.unlink()
        print(f"Checkpoint cleared for {worktree_path}")
    else:
        print("No checkpoint to clear")


def cmd_source_branch(worktree_path: str) -> None:
    """Read the source branch recorded in the checkpoint."""
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("ERROR: No checkpoint found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    checkpoint = json.loads(cp_path.read_text())
    source_branch = checkpoint.get("source_branch")
    if not source_branch:
        print("ERROR: No source branch recorded in checkpoint.", file=sys.stderr)
        sys.exit(1)
    print(source_branch)


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        # Filter --source-branch and its value out of positional args for
        # order-independent parsing.
        source_branch = None
        positional = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--source-branch" and i + 1 < len(sys.argv):
                source_branch = sys.argv[i + 1]
                i += 2
            else:
                positional.append(sys.argv[i])
                i += 1
        if len(positional) < 2:
            print("Usage: checkpoint-resume.py init <tasks-path> <worktree-path> [--source-branch <name>]",
                  file=sys.stderr)
            sys.exit(1)
        cmd_init(positional[0], positional[1], source_branch)
    elif command == "complete":
        if len(sys.argv) < 4:
            print("Usage: checkpoint-resume.py complete <group-id> <worktree-path> [task-id]",
                  file=sys.stderr)
            sys.exit(1)
        task_id = sys.argv[4] if len(sys.argv) > 4 else None
        cmd_complete(sys.argv[2], sys.argv[3], task_id)
    elif command == "failed":
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_failed(sys.argv[2], sys.argv[3], reason)
    elif command == "status":
        cmd_status(sys.argv[2])
    elif command == "remaining":
        cmd_remaining(sys.argv[2], sys.argv[3])
    elif command == "clear":
        cmd_clear(sys.argv[2])
    elif command == "source-branch":
        if len(sys.argv) < 3:
            print("Usage: checkpoint-resume.py source-branch <worktree-path>",
                  file=sys.stderr)
            sys.exit(1)
        cmd_source_branch(sys.argv[2])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
