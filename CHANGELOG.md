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

## [3.1.0] — 2026-04-29

### Added

- **PostToolUse/PostToolUseFailure metrics hook** (`hooks/metrics_hook.py`): Records per-tool-call proxy metrics (input/output sizes) and real token counts (from transcript `usage` data) to `notes/metrics/{date}.jsonl` and per-stage breakdowns. Uses incremental transcript scanning via a state file (`.claude/.metrics_state.json`) for efficiency. Enables data-driven optimization of token costs.

- **`eval-session-metrics.py`** (`scripts/eval-session-metrics.py`): Reads collected metrics for the current session (filtered by `.claude/.session_start` timestamp) and outputs a formatted performance summary — input/output tokens, cache read/create, tool call distribution, model usage breakdown, and estimated API cost.

- **Auto performance eval in skill handoffs**: Each skill now writes stage marker + session start timestamp at startup, and runs `eval-session-metrics.py` at completion. The formatted summary is included in the handoff message, giving immediate cost/performance feedback after every pipeline stage.

### Fixed

- **`hooks/hooks.json`**: Fixed `uv run` "Failed to spawn" error in metrics hook by adding missing `python` interpreter before the script path. Both `PostToolUse` and `PostToolUseFailure` hook commands now match the pattern used by other hooks (`uv run --directory ... python script.py`). Previously the `.py` file was passed directly to `uv run`, which failed to spawn the process.
- **`hooks/hooks.json` + `hooks/metrics_hook.py`**: Fixed metrics hook spawn failure — script path used `${CLAUDE_PROJECT_DIR}` (user's project) instead of `${CLAUDE_PLUGIN_ROOT}` (plugin directory), causing "Failed to spawn" when the plugin was used from another project. Also relocated all metrics output (`notes/metrics/`, state file) from the project dir into `{plugin_root}/notes/metrics/{project_slug}/`, preventing untracked file noise in the user's project git tree.

### Changed

- **`hooks/hooks.json`**: Registered `PostToolUse` and `PostToolUseFailure` hooks (matcher `.*`, async) pointing to `metrics_hook.py`.
- **`skills/elaborate-directions/SKILL.md`**: Step 1 writes stage marker + session start; Step 8 runs metrics eval and includes output in report.
- **`skills/explore-implement/SKILL.md`**: Step 1 writes stage marker + session start; new Step 7 runs metrics eval and reports results.
- **`skills/make-judgement/SKILL.md`**: Step 1 writes stage marker + session start (renumbered from old Step 1); Step 7 (was 6) runs metrics eval and includes output in report.

## [3.0.0] — 2026-04-29

### Added

- **`/elaborate-directions` skill** (`skills/elaborate-directions/SKILL.md`): Replaces the old enrich-phase-plan + enrich-plan-gather + enrich-plan-judge pipeline. Uses 5 subagent steps (context loading, codebase exploration, design elaboration, task decomposition, clarity review) followed by orchestrator refinement. Produces `directions.json` with descriptive guidance + wiring checklists instead of TOML before/after blocks. Input: a reviewed PHASE_PLAN.md. Output: `notes/directions/<phase-slug>/directions.json`.

- **`explore-implement` skill** (`skills/explore-implement/SKILL.md`): Replaces implementation-executor + fix. Implements code changes in git worktrees with real `cargo check` feedback — the edit→check→fix loop catches incorrect API usage, missing imports, type errors, and clippy violations immediately. Supports three tiers of parallelism: Tier 1 (sequential main agent), Tier 2 (subagent parallelism for independent groups), Tier 3 (multi-session via tmux). Accepts both `directions.json` and `fix-directions.json` with an identical loop.

- **`/make-judgement` skill** (`skills/make-judgement/SKILL.md`): Replaces review-pr-gather + review-pr-judge. Validates implementation diff against directions.json using two subagents (strict-code-reviewer for diff validation, rust-architect for strategic review). Produces `review.md`, `fix-directions.json`, and `deferred.md`. Strategic validation only — compiler already caught syntax/type errors.

- **`/file-issue` skill** (`skills/file-issue/SKILL.md`): Lets pipeline users file bug reports to `TonyWu20/rust-development-pipeline` with auto-gathered context. Lowers friction for reporting pipeline defects during daily use.

- **`directions-spec.md`** (`skills/elaborate-directions/references/directions-spec.md`): Full schema specification for the `directions.json` format. Defines task groups, descriptive guidance, wiring checklists, and acceptance commands — replaces the old compilable-plan-spec.md.

- **`validate-directions.py`** (`scripts/validate/validate-directions.py`): Validates `directions.json` against the spec. Checks meta fields, task group structure, change actions (create/modify/delete), wiring checklist format, and circular dependency detection for both groups and tasks.

- **`worktree-utils.sh`** (`scripts/worktree-utils.sh`): Git worktree management utility. Supports create, remove, list, status, merge, and discover operations. Used by `/explore-implement` for worktree lifecycle management.

- **`checkpoint-resume.py`** (`scripts/checkpoint-resume.py`): Worktree-based checkpoint manager for interrupted sessions. Supports init, complete, failed, status, remaining, and clear operations. The worktree IS the checkpoint — this utility records metadata about what was completed.

- **Worktree-aware hook** (`hooks/verify_impl_task.py`): Extended with `worktree_path` support in sidecar data. When present, acceptance commands and git operations run in the worktree instead of the main project directory. Also writes to `.exploration_checkpoint.json` for session resume.

- **Three-tier exploration model**: The `/explore-implement` stage supports three levels of parallelism: Tier 1 (sequential main agent, default), Tier 2 (subagent parallelism for 2-4 independent groups), Tier 3 (multi-session via tmux for 4+ groups). The worktree IS the checkpoint — interrupted sessions resume by reading worktree state.

### Removed

- **Deprecated skills** (7): compile-plan/, enrich-phase-plan/, enrich-plan-gather/, enrich-plan-judge/, fix/, review-pr/, review-pr-gather/, review-pr-judge/. The old TOML before/after block approach is fully replaced by descriptive guidance + compiler feedback.

- **Deprecated scripts** (3): `scripts/task-sidecar.sh` (tied to compiled manifest model), `scripts/validate/validate-toml-plan.py` (TOML eliminated), `scripts/validate/validate-fix-plan-application.py` (fix-plan.toml eliminated).

- **Deprecated hooks** (1): `hooks/post_compiled_script.py` (no more compiled scripts).

- **Deprecated agents** (1): `agents/fix-plan-reader.md` (fix-plan.toml eliminated).

### Pipeline

The full development pipeline is now:

```
/next-phase-plan          → discuss goals with user → PHASE_PLAN.md
/plan-review              → validate plan, decide on deferred items
/elaborate-directions     → decompose into directions.json with task groups
/explore-implement        → implement in worktree with cargo check feedback
/make-judgement           → validate diff against directions, produce fixes if needed
```

The edit→check→fix loop in `/explore-implement` eliminates the "mental dance" — LLM agents no longer deduce code impact from static analysis alone. Every change is validated by the Rust compiler.

- **Deterministic diff data collection** (`scripts/gather-diff-data.py`): Replaces the LLM subagent for gathering PR diff data. Produces authoritative `raw-diff.md` and `file-manifest.json` (trailing newlines, function signatures, imports, line counts). Both local LLMs and paid API models now share the same ground-truth factual foundation — no hallucinated file content or contradictory claims.

- **TOML plan validation** (`scripts/validate/validate-toml-plan.py`): Validates fix/implementation plans against the compilable-plan-spec. Checks `type` ∈ {replace, create, delete}, before/after field presence per type, task ID patterns, and file path existence against the diff manifest. Catches invented types like `append`.

- **Fix document validation** (`scripts/validate/validate-fix-document.py`): Validates fix document format (classification ∈ {Defect, Correctness}, severity ∈ {Blocking, Major, Minor}, sequential numbering, colon delimiter). Cross-checks file paths against the diff manifest to detect meta-issues about the review process.

- **Review consistency checking** (`scripts/validate/validate-review-consistency.py`): Cross-checks draft review factual claims (trailing newlines, file paths, verification methods) against the authoritative file-manifest.json. Catches fabricated verification claims like "verified via hex dump."

- **Pre-populated per-file analysis template** (`scripts/gather-diff-data.py --template`): Generates `per-file-analysis-template.md` with manifest facts (trailing newlines, line counts, functions, imports) pre-rendered as immutable tables per file. The LLM subagent fills in only judgment fields — structurally prevented from fabricating factual claims about manifest data.

- **Fix-plan application audit** (`scripts/validate/validate-fix-plan-application.py`): Audits committed `fix-plan.toml` tasks against current workspace state. Runs `rg -F` for each `before` block against its target file. Detects fixes that were planned but never applied, re-injecting them as current issues in the draft review.

- **Externalized cross-reference with isolated validator**: Step 4a of `review-pr-gather` now writes `cross-reference.md` documenting how each planned issue was validated against per-file-analysis, manifest, and context before inclusion. Step 4b is a separate subagent that reads source documents fresh and validates the cross-reference reasoning — agent isolation catches hallucinations that the writing agent missed.

- **Cross-subagent consistency evals** (`skills/review-pr-gather/evals/evals.json`): Three new evals covering cross-subagent-consistency (Eval 4), fix-plan-audit (Eval 5), and context-awareness (Eval 6).

- **Validation gates in gather skills**: `review-pr-gather` runs validation scripts after Steps 4/5/6 (previously Steps 3/4/5); `enrich-plan-gather` runs validation after Step 4. Failed validation re-launches the subagent with structured errors (max 2 retries). Validation status recorded in gather-summary.md.

- **`uv` Python environment**: `pyproject.toml` and `.python-version` pin Python 3.13 via `uv`. All `python3` references replaced with `uv run` across skills and hooks for reproducible Python execution. `uv.lock` generated for dependency locking.

### Changed

- **`review-pr-gather/SKILL.md`**: v0.3.0 → v0.4.0. Step 1 generates `per-file-analysis-template.md` via `--template` flag. Step 1.5 adds fix-plan application audit. Step 2 reads pre-populated template instead of `file-manifest.json`. Step 4 split into 4a (draft review + cross-reference.md) and 4b (isolated cross-reference validator). Orchestrator boundaries updated for two-layer validation (LLM subagent gates + Python script gates). Gather-summary template includes fix-plan audit and cross-reference validation sections.

- **`enrich-plan-gather/SKILL.md`**: TOML validation gate added after Step 4. Step 4 prompt now references `compilable-plan-spec.md` before writing TOML.

- **`hooks/hooks.json`**: Hook commands switched from `python3` to `uv run --directory ${CLAUDE_PLUGIN_ROOT} python`.

- **`compile-plan/SKILL.md`**, **`fix/SKILL.md`**, **`implementation-executor/SKILL.md`**: Inline `python3` commands replaced with `uv run python`.

- **`README.md`**: `uv` listed as required dependency.

### Fixed

- **Parallel-safe sidecar filenames**: `task-sidecar.sh` now writes per-task sidecar files (`current_task_{TASK_ID}.json`) instead of a single shared `current_task.json`. Concurrent subagents no longer overwrite each other's metadata.
- **Unstaged sidecar deletion**: `verify_impl_task.py` now deletes the sidecar file _before_ `git add -A`, so it is never committed and leaves no unstaged deletion in the working tree after each task.
- **Checkpoint staleness**: Sidecar now includes `all_task_ids` (the full task list from the manifest). The hook prunes any task IDs not in the current plan from the checkpoint's `completed`/`failed`/`blocked` lists, preventing stale entries from previous rounds from polluting resume logic.
- **Compiled script cleanup**: `/implementation-executor` and `/fix` now delete the `compiled/` directory on full completion. Previously these build artifacts were left on disk after execution finished.
- **Multi-change create/delete tasks no longer silently drop files**: `generate_create_py()` and `generate_delete_py()` in `compile_plan.py` now iterate over all `[[changes]]` entries instead of processing only the first. Fixes issues #4 Bug 2 and #7.
- **Trailing newline preserved in created files**: `strip_toml_newlines()` in `compile_plan.py` no longer strips the trailing `\n` from `after` blocks — POSIX-compliant trailing newlines are now preserved. Fixes issue #4 Bug 1. Updated `compilable-plan-spec.md` to correct the documented behavior.
- **Validator no longer skips acceptance checks when `type` is missing**: `validate-toml-plan.py` now infers `task_type` from changes and falls through to full validation instead of `continue`-ing past acceptance checks. Fixes issue #5.
- **`type` field now required in gather skill**: `enrich-plan-gather` Step 4 prompt explicitly requires `type` on every `[tasks.TASK-N]`, aligning with the toml-validity eval criterion. Fixes issue #5.
- **Judge skill cleanup step**: `enrich-plan-judge` now renames `draft-plan.toml` → `plan.approved.toml` and removes `compiled/` artifacts after completion. Fixes issue #6.
- **Plugin root resolution picks most recent install**: All 5 SKILL.md files now select the entry with the most recent `lastUpdated` timestamp instead of the first entry in the `installed_plugins.json` array. Fixes issue #8.

### Changed

- **`hooks/verify_impl_task.py`**: Replaced hardcoded `SIDECAR_PATH` constant with `SIDECAR_DIR` and a `resolve_sidecar()` function that finds the correct sidecar via task-ID extraction from `last_assistant_message`, glob fallback, and legacy filename fallback.
- **`scripts/task-sidecar.sh`**: Default output path uses `current_task_${task_id}.json`; sidecar JSON now includes an `all_task_ids` field.
- **`skills/implementation-executor/SKILL.md`**: Agent call template now sets `name: "{TASK_ID}"`; parallel launch of independent tasks (those with no declared dependencies) is now supported and documented. Clean-up step now removes the `compiled/` directory on full completion.
- **`skills/fix/SKILL.md`**: Same updates as `implementation-executor/SKILL.md` for `{ISSUE_ID}`. Clean-up step now removes the `compiled/` directory on full completion.

### Added

- **`.gitignore`**: Ignores `.claude/hooks/current_task*.json` to prevent sidecar files from ever being tracked by git.

### Changed

- **`scripts/gather-diff-data.py`**: Filters out `**/compiled/**`, `.claude/hooks/current_task_*.json`, and `execution_reports/.checkpoint_*.json` from the diff file list. These are internal build artifacts that don't need code review — previously they inflated the review pipeline's file count and wasted reviewer effort.
