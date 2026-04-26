#!/usr/bin/env python3
"""Audit a committed fix-plan.toml against current workspace state.

For each ``before`` block in the fix-plan, search the target file with
``rg -F``. If the full before block is found in the current source, the fix
was NOT applied. If not found, the fix was applied.

Run this after Step 1 (data collection) and before Step 2 (per-file analysis).
Results feed into the draft review as context for unapplied tasks.

Usage:
    uv run scripts/validate/validate-fix-plan-application.py \\
        --fix-plan notes/pr-reviews/{branch}/fix-plan.toml \\
        --workspace .

Exit codes:
  0  — all tasks applied (or no fix-plan found)
  1  — unapplied tasks found (errors printed to stdout as JSON)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


# ── Config ───────────────────────────────────────────────────────────────────

# Short name patterns the fix-plan uses for task IDs
TASK_ID_RE = re.compile(r"^(TASK|Issue|Fix|FIX)-\d+$", re.IGNORECASE)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _find_before_blocks(data: dict) -> list[dict]:
    """Extract (task_id, before, file) triples from a parsed TOML plan."""
    blocks: list[dict] = []
    tasks = data.get("tasks", {})
    for task_id, task_data in tasks.items():
        changes = task_data.get("changes", [])
        for ci, change in enumerate(changes):
            before = change.get("before")
            fpath = change.get("file")
            if before is not None and fpath is not None:
                blocks.append({
                    "task_id": str(task_id),
                    "change_index": ci,
                    "file": str(fpath),
                    "before": str(before),
                })
    return blocks


def _search_in_file(before_text: str, file_path: Path) -> bool:
    """Run rg -F to check if the full before_text exists in the file.

    Returns True if the text is found (fix NOT applied). Returns False if
    not found (fix applied or file missing).
    """
    if not file_path.exists():
        return False  # file deleted — fix may have been applied

    try:
        result = subprocess.run(
            ["rg", "-F", "--", before_text, str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        # rg exits 0 when match found, 1 when no match
        return result.returncode == 0
    except FileNotFoundError:
        # rg not available — fall back to Python string search
        try:
            content = file_path.read_text()
            return before_text in content
        except (OSError, UnicodeDecodeError):
            return False  # binary or unreadable
    except subprocess.TimeoutExpired:
        print(f"Warning: rg timed out on {file_path}", file=sys.stderr)
        return False


# ── Main ─────────────────────────────────────────────────────────────────────


def audit(fix_plan_path: Path, workspace_root: Path) -> list[dict]:
    """Audit a fix-plan against the workspace.

    Returns a list of unapplied task entries (empty list = all applied).
    """
    unapplied: list[dict] = []

    if not fix_plan_path.exists():
        return unapplied  # no prior fix-plan — nothing to audit

    try:
        data = tomllib.loads(fix_plan_path.read_text())
    except Exception as e:
        return [{
            "type": "parse_error",
            "detail": f"Failed to parse fix-plan: {e}",
        }]

    blocks = _find_before_blocks(data)
    if not blocks:
        return unapplied  # no before blocks — nothing to audit

    for block in blocks:
        target_file = (workspace_root / block["file"]).resolve()
        found = _search_in_file(block["before"], target_file)

        if found:
            unapplied.append({
                "task_id": block["task_id"],
                "change_index": block["change_index"],
                "file": block["file"],
                "before_preview": block["before"][:80],
                "status": "unapplied",
                "detail": f"Before block for {block['task_id']} change #{block['change_index']} "
                          f"still present in {block['file']} — fix was not applied.",
            })

    return unapplied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit committed fix-plan against workspace state"
    )
    parser.add_argument(
        "--fix-plan", required=True,
        help="Path to the committed fix-plan.toml (e.g. notes/pr-reviews/{branch}/fix-plan.toml)",
    )
    parser.add_argument(
        "--workspace", default=".",
        help="Workspace root directory (default: current directory)",
    )
    args = parser.parse_args()

    fix_plan_path = Path(args.fix_plan).resolve()
    workspace_root = Path(args.workspace).resolve()

    if not fix_plan_path.exists():
        result = {
            "valid": True,
            "audited": False,
            "note": "No fix-plan.toml found — nothing to audit",
            "unapplied": [],
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    unapplied = audit(fix_plan_path, workspace_root)
    result = {
        "valid": len(unapplied) == 0,
        "audited": True,
        "fix_plan": str(fix_plan_path),
        "unapplied_count": len(unapplied),
        "unapplied": unapplied,
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
