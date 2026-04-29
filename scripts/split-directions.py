#!/usr/bin/env python3
"""
Split a full directions.json into per-group files.

Usage: split-directions.py <directions-path> [--output-dir <dir>]

Output: <output-dir>/directions-<slug>-<group-id>.json
Defaults output-dir to the directory containing <directions-path>.
"""

import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: split-directions.py <directions-path> [--output-dir <dir>]",
              file=sys.stderr)
        sys.exit(1)

    directions_path = Path(sys.argv[1])
    if not directions_path.exists():
        print(f"ERROR: {directions_path} not found", file=sys.stderr)
        sys.exit(1)

    output_dir = directions_path.parent.resolve()
    if "--output-dir" in sys.argv:
        idx = sys.argv.index("--output-dir")
        if idx + 1 < len(sys.argv):
            output_dir = Path(sys.argv[idx + 1])
    output_dir.mkdir(parents=True, exist_ok=True)

    directions = json.loads(directions_path.read_text())
    meta = directions.get("meta", {})
    slug = meta.get("source_branch", meta.get("title", "plan"))
    architecture_notes = directions.get("architecture_notes", [])
    known_pitfalls = directions.get("known_pitfalls", [])
    all_tasks = {t["id"]: t for t in directions.get("tasks", [])}
    task_groups = directions.get("task_groups", [])

    if not task_groups:
        print("No task_groups found in directions.json", file=sys.stderr)
        sys.exit(1)

    index_groups = []

    for group in task_groups:
        group_id = group["group_id"]
        task_ids = group.get("tasks", [])
        group_tasks = []
        for tid in task_ids:
            if tid in all_tasks:
                group_tasks.append(all_tasks[tid])
            else:
                print(f"  WARNING: task '{tid}' referenced by group '{group_id}' not found",
                      file=sys.stderr)

        group_file = {
            "meta": meta,
            "architecture_notes": architecture_notes,
            "known_pitfalls": known_pitfalls,
            "task_groups": [group],
            "tasks": group_tasks,
        }

        out_name = f"directions-{slug}-{group_id}.json"
        out_path = output_dir / out_name
        out_path.write_text(json.dumps(group_file, indent=2) + "\n")
        print(f"Created {out_path} ({len(group_tasks)} tasks)")

        # Build index entry for this group
        index_groups.append({
            "group_id": group_id,
            "task_ids": task_ids,
            "description": group.get("reason", group_id),
            "file": out_name,
        })

    # Write the index file
    index = {
        "meta": meta,
        "architecture_notes": architecture_notes,
        "known_pitfalls": known_pitfalls,
        "groups": index_groups,
    }
    index_path = output_dir / "directions-index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n")
    print(f"Created {index_path} ({len(index_groups)} groups)")


if __name__ == "__main__":
    main()
