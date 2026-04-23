# Changelog

## [2.0.0] — 2026-04-22

### Breaking Changes

- **`/next-phase-plan` is now an interactive planning skill.** It no longer produces a TOML task breakdown. It facilitates a conversation with the user about the next phase's goals and scope, writing a high-level `PHASE_PLAN.md`. Users who previously ran `/next-phase-plan <plan-file>` to produce executor-ready TOML should now use `/enrich-phase-plan <plan-file>` for that step.

### Added

- **`/plan-review` skill** (`skills/plan-review/SKILL.md`): Pre-implementation architectural gate. Reads the phase plan and any `deferred.md` files from prior review rounds, then asks the `rust-architect` agent to assess design soundness, decide on each deferred item (Absorb / Defer / Close), and recommend plan amendments. Output saved to `notes/plan-reviews/{plan-slug}/decisions.md`.

- **`/enrich-phase-plan` skill** (`skills/enrich-phase-plan/SKILL.md`): The former `next-phase-plan` pipeline (architect elaborate → decomposer breakdown → impl-plan-reviewer loop → architect final review), now with an added Step 1.5 that loads `deferred.md` files as soft context for the architect before elaboration.

- **Scope classification in `/review-pr`**: Every issue the `rust-architect` agent raises is now classified as `[Defect]`, `[Correctness]`, or `[Improvement]`. Only `[Defect]` and `[Correctness]` items enter the fix plan. `[Improvement]` items are written to `notes/pr-reviews/{branch}/deferred.md` for deliberate consideration in a future plan.

- **Phase plan loading in `/review-pr` Step 1**: The skill now loads the phase plan before the snapshot short-circuit, giving the `rust-architect` agent an authoritative scope spec. Plan resolution tries branch-name pattern matching against `plans/`, falls back to a single-plan heuristic, and disables scope gating gracefully if no plan is found.

- **`deferred.md` output from `/review-pr`**: Step 7 now writes `notes/pr-reviews/{branch}/deferred.md` when `[Improvement]` items are found. On re-reviews, new items are appended under a dated heading rather than overwriting, so the full improvement history accumulates for the next `/plan-review` to consume.

### Changed

- **`/review-pr` Step 2**: Phase plan content and classification instruction added to the `rust-architect` handoff prompt.
- **`/review-pr` Step 3**: Axis A now defines the three-class classification rule for all issues across all four axes.
- **`/review-pr` Step 5**: Verification now also checks that no `[Improvement]`-classified issue appears in the Fix Document.
- **`/review-pr` Step 6**: PR Review output template gains a `**Deferred Improvements:**` field. Fix Document template gains a `**Classification:**` field (informational; not parsed by `compile_plan.py`). New Deferred Improvements template added.
- **`/next-phase-plan` skill** (`skills/next-phase-plan/SKILL.md`): Fully replaced with an interactive goal-discussion skill. Gathers project memory, git history, existing plans, deferred improvements, and execution reports; proposes phase goals via `rust-architect`; iterates with the user; saves a structured `PHASE_PLAN.md`.

### Pipeline

The full development pipeline is now:

```
/next-phase-plan          → discuss goals with user → PHASE_PLAN.md
/plan-review              → validate plan, decide on deferred items
/enrich-phase-plan        → elaborate into executor-ready TOML
/compile-plan             → generate compiled/*.sh scripts
/implementation-executor  → execute all tasks
/review-pr                → rate PR, generate fix-plan.toml + deferred.md
/fix                      → apply fixes deterministically
```

## [Unreleased]

### Fixed

- **Parallel-safe sidecar filenames**: `task-sidecar.sh` now writes per-task sidecar files (`current_task_{TASK_ID}.json`) instead of a single shared `current_task.json`. Concurrent subagents no longer overwrite each other's metadata.
- **Unstaged sidecar deletion**: `verify_impl_task.py` now deletes the sidecar file _before_ `git add -A`, so it is never committed and leaves no unstaged deletion in the working tree after each task.
- **Checkpoint staleness**: Sidecar now includes `all_task_ids` (the full task list from the manifest). The hook prunes any task IDs not in the current plan from the checkpoint's `completed`/`failed`/`blocked` lists, preventing stale entries from previous rounds from polluting resume logic.
- **Compiled script cleanup**: `/implementation-executor` and `/fix` now delete the `compiled/` directory on full completion. Previously these build artifacts were left on disk after execution finished.

### Changed

- **`hooks/verify_impl_task.py`**: Replaced hardcoded `SIDECAR_PATH` constant with `SIDECAR_DIR` and a `resolve_sidecar()` function that finds the correct sidecar via task-ID extraction from `last_assistant_message`, glob fallback, and legacy filename fallback.
- **`scripts/task-sidecar.sh`**: Default output path uses `current_task_${task_id}.json`; sidecar JSON now includes an `all_task_ids` field.
- **`skills/implementation-executor/SKILL.md`**: Agent call template now sets `name: "{TASK_ID}"`; parallel launch of independent tasks (those with no declared dependencies) is now supported and documented. Clean-up step now removes the `compiled/` directory on full completion.
- **`skills/fix/SKILL.md`**: Same updates as `implementation-executor/SKILL.md` for `{ISSUE_ID}`. Clean-up step now removes the `compiled/` directory on full completion.

### Added

- **`.gitignore`**: Ignores `.claude/hooks/current_task*.json` to prevent sidecar files from ever being tracked by git.
