#!/usr/bin/env python3
"""
Checkpoint and resume utility for the explore-implement pipeline.

Manages worktree-based checkpoint state so interrupted sessions can resume
without losing progress.  The core insight is that the worktree IS the
checkpoint — this utility just records metadata about what was completed.

Usage:
  checkpoint-resume.py init <directions-path> <worktree-path>
      Create initial checkpoint for a directions.json.

  checkpoint-resume.py complete <group-id> <worktree-path>
      Mark a task group as completed.

  checkpoint-resume.py failed <group-id> <worktree-path> [reason]
      Mark a task group as failed.

  checkpoint-resume.py status <worktree-path>
      Show current checkpoint status.

  checkpoint-resume.py remaining <directions-path> <worktree-path>
      List task groups not yet completed.

  checkpoint-resume.py clear <worktree-path>
      Remove checkpoint for a completed session.
"""

import json
import sys
from pathlib import Path


def _checkpoint_path(worktree_path: str) -> Path:
    return Path(worktree_path) / ".exploration_checkpoint.json"


def _load_directions(directions_path: str) -> dict:
    path = Path(directions_path)
    if not path.exists():
        print(f"ERROR: directions.json not found: {directions_path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def cmd_init(directions_path: str, worktree_path: str) -> None:
    directions = _load_directions(directions_path)
    groups = directions.get("task_groups", [])

    checkpoint = {
        "directions_path": str(Path(directions_path).resolve()),
        "worktree_path": str(Path(worktree_path).resolve()),
        "groups": {
            g["group_id"]: {
                "status": "pending",
                "tasks": g["tasks"],
                "reason": g.get("reason", ""),
            }
            for g in groups
        },
    }

    cp_path = _checkpoint_path(worktree_path)
    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(f"Checkpoint initialized at {cp_path}")
    print(f"Total groups: {len(groups)}")


def cmd_complete(group_id: str, worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("ERROR: No checkpoint found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    checkpoint = json.loads(cp_path.read_text())
    if group_id not in checkpoint["groups"]:
        print(f"ERROR: Unknown group '{group_id}'", file=sys.stderr)
        sys.exit(1)

    checkpoint["groups"][group_id]["status"] = "completed"
    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(f"Group '{group_id}' marked as completed")


def cmd_failed(group_id: str, worktree_path: str, reason: str = "") -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        print("ERROR: No checkpoint found. Run 'init' first.", file=sys.stderr)
        sys.exit(1)

    checkpoint = json.loads(cp_path.read_text())
    if group_id not in checkpoint["groups"]:
        print(f"ERROR: Unknown group '{group_id}'", file=sys.stderr)
        sys.exit(1)

    checkpoint["groups"][group_id]["status"] = "failed"
    if reason:
        checkpoint["groups"][group_id]["reason"] = reason
    cp_path.write_text(json.dumps(checkpoint, indent=2) + "\n")
    print(f"Group '{group_id}' marked as failed")


def cmd_status(worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        # No checkpoint — nothing started yet
        print("No checkpoint found. Nothing initialized yet.")
        return

    checkpoint = json.loads(cp_path.read_text())
    directions_path = checkpoint.get("directions_path", "unknown")
    print(f"Directions: {directions_path}")
    print(f"Worktree:   {checkpoint['worktree_path']}")
    print()

    groups = checkpoint["groups"]
    completed = [gid for gid, g in groups.items() if g["status"] == "completed"]
    failed = [gid for gid, g in groups.items() if g["status"] == "failed"]
    pending = [gid for gid, g in groups.items() if g["status"] == "pending"]

    print(f"Groups: {len(groups)} total")
    print(f"  Completed: {len(completed)}")
    print(f"  Failed:    {len(failed)}")
    print(f"  Pending:   {len(pending)}")
    print()

    if completed:
        print("Completed groups: " + ", ".join(completed))
    if failed:
        print("Failed groups: " + ", ".join(failed))
    if pending:
        print("Pending groups: " + ", ".join(pending))


def cmd_remaining(directions_path: str, worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if not cp_path.exists():
        # No checkpoint — all groups are remaining
        directions = _load_directions(directions_path)
        for g in directions.get("task_groups", []):
            print(g["group_id"])
        return

    checkpoint = json.loads(cp_path.read_text())
    remaining = [
        gid for gid, g in checkpoint["groups"].items()
        if g["status"] not in ("completed",)
    ]
    for gid in remaining:
        print(gid)


def cmd_clear(worktree_path: str) -> None:
    cp_path = _checkpoint_path(worktree_path)
    if cp_path.exists():
        cp_path.unlink()
        print(f"Checkpoint cleared for {worktree_path}")
    else:
        print("No checkpoint to clear")


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        if len(sys.argv) < 4:
            print("Usage: checkpoint-resume.py init <directions-path> <worktree-path>",
                  file=sys.stderr)
            sys.exit(1)
        cmd_init(sys.argv[2], sys.argv[3])
    elif command == "complete":
        cmd_complete(sys.argv[2], sys.argv[3])
    elif command == "failed":
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_failed(sys.argv[2], sys.argv[3], reason)
    elif command == "status":
        cmd_status(sys.argv[2])
    elif command == "remaining":
        cmd_remaining(sys.argv[2], sys.argv[3])
    elif command == "clear":
        cmd_clear(sys.argv[2])
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
