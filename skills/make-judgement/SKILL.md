---
name: make-judgement
description: Review implemented changes against TASKS.md, produce review.md and fix-tasks.md for any defects found. Accepts a TASKS.md path and progressively loads group sections for validation. Use when the user says "/make-judgement <tasks-path>", "review the implementation", "judge the changes", or after /explore-implement completes for complex multi-group changes.
---

# Make Judgement

Reviews the diff produced by `/explore-implement` against the original `TASKS.md`. Strategic validation only — the compiler and auto-review have already caught syntax, wiring, and scope errors during implementation. The reviewer focuses on: does the implementation correctly satisfy the planned tasks?

Produces `review.md` (narrative review) and optionally `fix-tasks.md` (fix instructions in markdown for any defects found).

## Trigger

`/make-judgement <tasks-path>`

Where `<tasks-path>` is the path to `TASKS.md` (e.g., `notes/plans/<plan-slug>/TASKS.md`).

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Output

- `notes/pr-reviews/<plan-slug>/review.md` — narrative review
- `notes/pr-reviews/<plan-slug>/fix-tasks.md` — fix instructions (if defects found; same markdown format as TASKS.md)
- `notes/pr-reviews/<plan-slug>/deferred.md` — improvements deferred to future phases

## Process

### Step 1: Setup

```bash
# Set stage marker and session start for metrics tracking
echo "make-judgement" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Determine plan slug from tasks path
PLAN_SLUG=$(basename $(dirname <tasks-path>))
mkdir -p notes/pr-reviews/$PLAN_SLUG
```

### Step 2: Gather Diff Data

Agents use git directly — no wrapper script needed:

```bash
# Cumulative diff against main (sees net change, ignores commit noise)
git diff main...HEAD

# Stat summary
git diff --stat main...HEAD

# Generate workspace map for structural ground truth
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  "notes/pr-reviews/$PLAN_SLUG/workspace-map.json"
```

### Step 3: Read Context

Read the key inputs:

1. Read `TASKS.md` at `<tasks-path>` — this gives you the full group list, architecture_notes, and known_pitfalls.
2. Run `git diff main...HEAD` for the cumulative diff.
3. Read the workspace map at `notes/pr-reviews/$PLAN_SLUG/workspace-map.json` via `jq`.

### Step 4: Per-Group Diff Validation

**IMPORTANT**: Never launch subagents in background mode (`run_in_background`). Permission requests from background subagents are invisible in the Claude Code interface — they can only be approved via the Discord hook, which has a 2-minute timeout. Always launch subagents in foreground.

Extract group sections from TASKS.md by finding `## Task Group:` headers. For each group, extract the section boundary (from its header to the next `## Task Group:` or end of file).

For each group section, launch a **strict-code-reviewer subagent**:

> **Agent**: rust-development-pipeline:strict-code-reviewer (subagent, discardable context)
>
> **Task**: Validate the implementation diff against one group's tasks.
>
> Read:
> - The cumulative diff (`git diff main...HEAD` — run this)
> - `notes/pr-reviews/<plan-slug>/workspace-map.json` — structural ground truth
> - The task group section (markdown) for group `{GROUP_ID}` from TASKS.md
>
> Use `workspace-map.json` as your primary structural reference:
> - `symbols["TypeName"]` — verify new types/functions appear with correct signatures
> - `files["path.rs"]` — verify new modules are wired into the module tree
> - `nameIndex["Name"]` — check for name collisions
>
> For each task in this group, check:
> 1. Were all required files created/modified/deleted as specified?
> 2. Does each change match the guidance (structs, functions, signatures)?
> 3. Are there any changes that are NOT in the tasks (scope creep)?
> 4. Are there any obvious bugs or issues in the diff?
> 5. **For `lib-tdd` tasks**: Verify the test exists in the codebase, the implementation matches the signature, and the expected behavior is satisfied.
>
> Report per-task:
> - ✓ Task fully implemented as directed
> - ⚠ Task implemented with issues (describe)
> - ✗ Task not implemented or mis-implemented (describe)

After each group's subagent completes, append findings to the review draft.

### Step 5: Strategic Review

Launch a **rust-architect subagent** for strategic review:

> **Agent**: rust-development-pipeline:rust-architect (subagent, discardable context)
>
> **Task**: Strategic review of the implementation.
>
> Read:
> - `git diff main...HEAD` (run this)
> - `notes/pr-reviews/<plan-slug>/workspace-map.json` — verify crate boundaries
> - TASKS.md at `{TASKS_PATH}` (architecture_notes and known_pitfalls are sufficient)
>
> Use `workspace-map.json` to verify structural concerns:
> - `files[path].crate` — determine which crate owns each changed file
> - `crossReferences.types` — check public API surface changes
> - `symbols` — verify new public items are properly exported
>
> Assess:
> 1. Does the implementation follow the architecture_notes from TASKS.md?
> 2. Are crate boundaries respected?
> 3. Are the existing codebase patterns followed?
> 4. Are there strategic concerns (performance, maintainability, API design)?
> 5. **For `lib-tdd` tasks**: Does the implementation satisfy expected_behavior? Is the test adequate?
>
> Report: Strategic assessment (pass / issues / fail), specific concerns, items to defer.

### Step 6: Synthesize Judgement

Synthesize both reviews into the final outputs:

1. **Write `review.md`**:
   ```markdown
   # Review: {Phase Title}

   **Tasks**: {tasks-path}
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

2. **Write `fix-tasks.md`** (if issues found):
   - Follows the same markdown format as TASKS.md
   - Contains only fix tasks for the defects identified
   - Each fix task references the specific file and defect
   - Consumed by `/explore-implement <fix-tasks-path>`

3. **Write `deferred.md`**:
   - Items flagged by strategic review as worth doing but out of scope
   - Candidates for the next `/next-phase-plan` discussion

### Step 7: Handoff

Stage the review artifacts:

```bash
git add notes/pr-reviews/<plan-slug>/
```

Run the session metrics eval:

```bash
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR}" uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" make-judgement
```

Report to the user:

> "Review complete. See `notes/pr-reviews/<plan-slug>/review.md`.
>
> {eval output}
>
> {N} issue(s) found, {M} deferred.
>
> Next steps:
> - Fix defects: `/explore-implement notes/pr-reviews/<plan-slug>/fix-tasks.md`
> - If all passed: merge the feature branch and proceed to the next phase."

## Boundaries

**Will:**
- Validate diff against TASKS.md per-group (progressive load via markdown headers)
- Perform both detailed (code review) and strategic (architecture) review
- Classify issues by severity
- Produce fix-tasks.md for defects (same markdown format as TASKS.md)
- Defer non-critical improvements to future phases

**Will not:**
- Re-check compiler errors (already caught during implementation)
- Re-implement any code changes
- Run cargo check or tests (already done during implementation)
- Modify the implementation directly
- Use JSON schemas, index files, or wrapper scripts
