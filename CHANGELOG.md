# Changelog

## [Unreleased]

### Fixed

- **Parallel-safe sidecar filenames**: `task-sidecar.sh` now writes per-task sidecar files (`current_task_{TASK_ID}.json`) instead of a single shared `current_task.json`. Concurrent subagents no longer overwrite each other's metadata.
- **Unstaged sidecar deletion**: `verify_impl_task.py` now deletes the sidecar file *before* `git add -A`, so it is never committed and leaves no unstaged deletion in the working tree after each task.
- **Checkpoint staleness**: Sidecar now includes `all_task_ids` (the full task list from the manifest). The hook prunes any task IDs not in the current plan from the checkpoint's `completed`/`failed`/`blocked` lists, preventing stale entries from previous rounds from polluting resume logic.

### Changed

- **`hooks/verify_impl_task.py`**: Replaced hardcoded `SIDECAR_PATH` constant with `SIDECAR_DIR` and a `resolve_sidecar()` function that finds the correct sidecar via task-ID extraction from `last_assistant_message`, glob fallback, and legacy filename fallback.
- **`scripts/task-sidecar.sh`**: Default output path uses `current_task_${task_id}.json`; sidecar JSON now includes an `all_task_ids` field.
- **`skills/implementation-executor/SKILL.md`**: Agent call template now sets `name: "{TASK_ID}"`; parallel launch of independent tasks (those with no declared dependencies) is now supported and documented.
- **`skills/fix/SKILL.md`**: Same updates as `implementation-executor/SKILL.md` for `{ISSUE_ID}`.

### Added

- **`.gitignore`**: Ignores `.claude/hooks/current_task*.json` to prevent sidecar files from ever being tracked by git.
