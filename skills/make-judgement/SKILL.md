---
name: make-judgement
description: Review implemented changes against directions.json, produce review.md and fix-directions.json for any defects found. Accepts a directions-index.json (from /elaborate-directions) and progressively loads per-group files for validation — avoids the 27K+ token full directions.json. Replaces the old review-pr-gather + review-pr-judge pipeline. Use when the user says "/make-judgement <index-path>", "review the implementation", "judge the changes", or after /explore-implement completes.
---

# Make Judgement

Reviews the diff produced by `/explore-implement` against the original `directions.json`. Strategic validation only — the compiler has already caught syntax and type errors during implementation. The reviewer focuses on: does the implementation correctly satisfy the directions?

Produces `review.md` (narrative review) and optionally `fix-directions.json` (fix instructions for any defects found).

## Trigger

`/make-judgement <index-path>`

Where `<index-path>` is the path to `directions-index.json` (e.g., `notes/directions/<plan-slug>/directions-index.json`). The index is a lightweight file listing all task groups with references to per-group directions files.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for scripts

## Output

- `notes/pr-reviews/<plan-slug>/review.md` — narrative review
- `notes/pr-reviews/<plan-slug>/fix-directions.json` — fix instructions (if defects found)
- `notes/pr-reviews/<plan-slug>/deferred.md` — improvements deferred to future phases

## Process

### Step 1: Setup

Set the stage marker for metrics, then determine the plan slug and output directory:

```bash
# Set stage marker and session start for metrics tracking
echo "make-judgement" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Determine plan slug from index path
PLAN_SLUG=$(basename $(dirname <index-path>))
mkdir -p notes/pr-reviews/$PLAN_SLUG
```

### Step 2: Gather Diff Data (Script)

Run the deterministic diff data collector, plus generate a workspace map
as structural ground truth:

```bash
# Generate diff data: --branch from current git branch, --output for the review directory
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/gather-diff-data.py" \
  --branch "$GIT_BRANCH" --output "notes/pr-reviews/$PLAN_SLUG"

# Generate workspace map for structural ground truth
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  "notes/pr-reviews/$PLAN_SLUG/workspace-map.json"
```

This produces:
- `raw-diff.md` — the raw git diff of changes since the base commit
- `file-manifest.json` — structured file change metadata
- `workspace-map.json` — pre-computed structural map (symbols, files, cross-refs)
- Analysis templates for the reviewers

### Step 3: Read Context (Orchestrator)

Read the key inputs to understand what was requested and what was delivered:

1. Read `notes/pr-reviews/<plan-slug>/raw-diff.md`
2. Read `notes/pr-reviews/<plan-slug>/file-manifest.json`
3. Read the `directions-index.json` at `<index-path>` — this gives you the full group list, architecture_notes, and known_pitfalls in ~1-2K tokens. Do NOT read the full `directions.json` (it may be too large).
4. Read `git diff` output for a high-level summary of changes

### Step 4: Per-Group Diff Validation (Orchestrator-loop)

For each group in the index, progressively load its per-group directions file and validate the diff:

```
For each entry in index.groups:
  1. Read the per-group file at <index-dir>/<group.file>
  2. Launch a **strict-code-reviewer subagent** to validate this group's tasks
```

> **Agent**: rust-development-pipeline:strict-code-reviewer (subagent, discardable context)
>
> **Task**: Validate the implementation diff against one group's tasks.
>
> Read:
> - `notes/pr-reviews/<plan-slug>/raw-diff.md`
> - `notes/pr-reviews/<plan-slug>/file-manifest.json`
> - `notes/pr-reviews/<plan-slug>/workspace-map.json` — structural ground truth
> - The per-group directions file for group `{GROUP_ID}`
>
> Use `workspace-map.json` as your primary structural reference:
> - `symbols["TypeName"]` — verify new types/functions appear with correct signatures
> - `files["path.rs"]` — verify new modules are wired into the module tree
> - `nameIndex["Name"]` — check for name collisions introduced by changes
>
> For each task in this group, check:
> 1. Were all required files created/modified/deleted as specified?
> 2. Does each change match the guidance (structs, functions, signatures)?
> 3. Are all wiring_checklist items satisfied? (cross-check with `files` index)
> 4. Are there any changes that are NOT in the directions (scope creep)?
> 5. Are there any obvious bugs or issues in the diff?
> 6. **For `lib-tdd` tasks**: Verify that the test from `tdd_interface.test_code` exists in the codebase, that it passes (confirmed during implementation), and that the implementation function matches `tdd_interface.signature`.
>
> Report findings per-task:
> - ✓ Task fully implemented as directed
> - ⚠ Task implemented with issues (describe)
> - ✗ Task not implemented or mis-implemented (describe)

After each group's subagent completes, append its findings to the review draft. This makes progress visible and provides a checkpoint if interrupted.

### Step 5: Strategic Review (Subagent)

Launch a **rust-architect subagent** for strategic review:

> **Agent**: rust-development-pipeline:rust-architect (subagent, discardable context)
>
> **Task**: Strategic review of the implementation.
>
> Read:
> - `notes/pr-reviews/<plan-slug>/raw-diff.md`
> - `notes/pr-reviews/<plan-slug>/workspace-map.json` — verify crate boundaries
> - The directions index at `{INDEX_PATH}` (architecture_notes and known_pitfalls are sufficient)
>
> Use `workspace-map.json` to verify structural concerns:
> - `files[path].crate` — determine which crate owns each changed file
> - `crossReferences.types` — check public API surface changes
> - `symbols` — verify new public items are properly exported
>
> Assess:
> 1. Does the implementation follow the architecture_notes from the directions?
> 2. Are crate boundaries respected? (cross-check with workspace map)
> 3. Are the existing codebase patterns followed?
> 4. Are there any strategic concerns (performance, maintainability, API design)?
> 5. Is the public API surface well-designed?
> 6. **For `lib-tdd` tasks**: Does the implementation satisfy `tdd_interface.expected_behavior`? Is the test adequate (not just happy-path)?
>
> Report:
> - Strategic assessment (pass / issues / fail)
> - Specific concerns with recommendations
> - Items to defer to future phases (for deferred.md)

### Step 6: Synthesize Judgement (Orchestrator)

Synthesize both reviews into the final outputs:

1. **Write `review.md`**:
   ```markdown
   # Review: {Phase Title}

   **Index**: {index-path}
   **Reviewed**: {date}

   ## Summary

   {Overall assessment — passed, needs fixes, or rejected}

   ## Per-Task Results

   ### {TASK-ID}: {description}
   - **Status**: ✓ Passed | ⚠ Minor Issues | ✗ Failed
   - **Diff validation**: {findings from step 4}
   - **Strategic review**: {findings from step 5}

   ## Issues Found

   {Numbered list of issues with severity, location, and recommendation}

   ## Deferred Items

   {Items flagged for future phases, written to deferred.md}
   ```

2. **Write `fix-directions.json`** (if issues found):
   - Follows the same schema as `directions.json`
   - Contains only fix tasks for the defects identified
   - Each fix task references the specific file and defect
   - Same edit→check→fix loop applies when fed to `/explore-implement`

3. **Write `deferred.md`**:
   - Items flagged by the strategic review as worth doing but out of scope
   - These will be candidates in the next `/next-phase-plan` discussion

4. **Validate**:
   ```bash
   uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/validate/validate-review-consistency.py" \
  "notes/pr-reviews/<plan-slug>/review.md" "notes/pr-reviews/<plan-slug>/file-manifest.json"
   ```
   If fix-directions.json was created:
   ```bash
   uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/validate/validate-fix-document.py" \
  "notes/pr-reviews/<plan-slug>/fix-directions.json"
   ```

### Step 7: Handoff

Stage the review artifacts for tracking:

```bash
git add notes/pr-reviews/<plan-slug>/
```

Run the session metrics eval to report performance:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" make-judgement
```

Report to the user:

> "Review complete. See `notes/pr-reviews/<plan-slug>/review.md`.
>
> {eval output}
>
> {N} issue(s) found, {M} deferred.
>
> Next steps:
> - Fix defects: `/explore-implement notes/pr-reviews/<plan-slug>/fix-directions.json`
> - If all passed: merge the feature branch and proceed to the next phase."

## Boundaries

**Will:**
- Validate diff against directions.json per-group (progressive load via index)
- Perform both detailed (code review) and strategic (architecture) review
- Classify issues by severity
- Produce fix-directions.json for defects (follows same schema as directions.json)
- Defer non-critical improvements to future phases

**Will not:**
- Re-check compiler errors (already caught during implementation)
- Re-implement any code changes
- Run cargo check or tests (already done during implementation)
- Modify the implementation directly
