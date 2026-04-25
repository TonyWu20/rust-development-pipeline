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

## [2.1.0] — 2026-04-24

### Added

- **`plan-decomposer`: completeness envelope and module wiring rules** — Every task must leave the codebase in a compilable, reachable state. New rules require `pub mod` declarations, `pub use` re-exports, and consumer co-location (definition + adoption in the same task). Self-test checklist added.

- **`verify_impl_task.py`: workspace-level compilation gate** — After task-specific acceptance commands pass, runs `cargo check --workspace` to catch cross-crate breakages (missing re-exports, stale imports). Only runs when task checks pass. Timeout parameter made configurable on `run_command()`.

- **`enrich-phase-plan`: cross-round failure pattern extraction** — Step 1.5 now reads `fix-plan.toml` files from prior phases, extracts recurring failure categories (missing wiring, stale imports, type mismatches), and passes them as `KNOWN_FAILURE_MODES` to the decomposer as proactive checks.

- **`enrich-phase-plan`: dry-run compilation (Step 4.5)** — After decomposer approval, applies the full TOML plan to a temporary worktree, runs `cargo check --workspace`, and feeds compilation errors back to the decomposer for targeted revision (max 2 iterations) before architect final review.

### Changed

- **`skills/fix/SKILL.md`**: Added diagnose-before-retry logic (content shifted / already applied / content missing classification). Changed clippy to workspace-wide `--workspace -- -D warnings` with blocking/notes distinction based on whether files were touched this round.

- **`skills/implementation-executor/SKILL.md`**: Same diagnose-before-retry and clippy improvements as `fix`.

### Fixed

- **Module wiring gap**: Plans no longer produce unreachable code — new files must include module declarations, re-exports, and consumer wiring in the same task.

## [Unreleased]

### Added

- **Deterministic diff data collection** (`scripts/gather-diff-data.py`): Replaces the LLM subagent for gathering PR diff data. Produces authoritative `raw-diff.md` and `file-manifest.json` (trailing newlines, function signatures, imports, line counts). Both local LLMs and paid API models now share the same ground-truth factual foundation — no hallucinated file content or contradictory claims.

- **TOML plan validation** (`scripts/validate/validate-toml-plan.py`): Validates fix/implementation plans against the compilable-plan-spec. Checks `type` ∈ {replace, create, delete}, before/after field presence per type, task ID patterns, and file path existence against the diff manifest. Catches invented types like `append`.

- **Fix document validation** (`scripts/validate/validate-fix-document.py`): Validates fix document format (classification ∈ {Defect, Correctness}, severity ∈ {Blocking, Major, Minor}, sequential numbering, colon delimiter). Cross-checks file paths against the diff manifest to detect meta-issues about the review process.

- **Review consistency checking** (`scripts/validate/validate-review-consistency.py`): Cross-checks draft review factual claims (trailing newlines, file paths, verification methods) against the authoritative file-manifest.json. Catches fabricated verification claims like "verified via hex dump."

- **Validation gates in gather skills**: `review-pr-gather` runs validation scripts after Steps 4/5/6 (previously Steps 3/4/5); `enrich-plan-gather` runs validation after Step 4. Failed validation re-launches the subagent with structured errors (max 2 retries). Validation status recorded in gather-summary.md.

- **`uv` Python environment**: `pyproject.toml` and `.python-version` pin Python 3.13 via `uv`. All `python3` references replaced with `uv run` across skills and hooks for reproducible Python execution. `uv.lock` generated for dependency locking.

### Changed

- **`review-pr-gather/SKILL.md`**: Step 1 replaced from LLM subagent to script (`gather-diff-data.py`). Steps renumbered (old Step 2→3, etc.). Validation gates added after Steps 4/5/6. Step 4 (draft review) now reads `file-manifest.json` as authoritative fact source with self-consistency and classification guidance. Step 5 (fix document) gains scope rule against meta-issues. Step 6 (fix-plan.toml) references the compilable-plan-spec. Orchestrator boundaries updated to permit validation script execution.

- **`enrich-plan-gather/SKILL.md`**: TOML validation gate added after Step 4. Step 4 prompt now references `compilable-plan-spec.md` before writing TOML.

- **`hooks/hooks.json`**: Hook commands switched from `python3` to `uv run --directory ${CLAUDE_PLUGIN_ROOT} python`.

- **`compile-plan/SKILL.md`**, **`fix/SKILL.md`**, **`implementation-executor/SKILL.md`**: Inline `python3` commands replaced with `uv run python`.

- **`README.md`**: `uv` listed as required dependency.

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
