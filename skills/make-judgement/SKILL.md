---
name: make-judgement
description: Review implemented changes against TASKS.md, produce review.md and fix-tasks.md for any defects found. Accepts a TASKS.md path and progressively loads group sections for validation. Use when the user says "/make-judgement <tasks-path>", "review the implementation", "judge the changes", or after /explore-implement completes for complex multi-group changes.
---

# Make Judgement

Reviews the diff produced by `/explore-implement` against the original `TASKS.md`. Includes runtime outcome verification — actually running the code against declared fixtures to compare output against success criteria. The compiler and auto-review have already caught syntax, wiring, and scope errors during implementation. The judge additionally verifies: does the code produce the right output for real data?

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

```

### Step 3: Read Context

Read the key inputs:

1. Read `TASKS.md` at `<tasks-path>` — this gives you the full group list, architecture_notes, and known_pitfalls.
2. Run `git diff main...HEAD` for the cumulative diff.

### Step 4: Runtime Outcome Verification

Run acceptance commands against declared fixtures to verify outcomes match criteria:

```bash
cd "${CLAUDE_PROJECT_DIR}"

# Run complete test suite — catches regressions
cargo test --workspace 2>&1 | tail -40

# If TASKS.md has success criteria with fixture references, run those specific tests
# with output captured for review
cargo test -p <crate> 2>&1 | tail -40
```

For each task group with `lib-tdd` tasks and success criteria:
1. Check if the criteria reference specific fixture files.
2. Verify those fixture files exist at the declared paths.
3. Run the relevant test(s) and capture stdout/stderr.
4. Compare the test output to the expected criteria values from TASKS.md.
5. If tests fail: note in review. If tests pass but use vacuous assertions
   (is_finite, circular round-trip): flag as PLACEBO regardless.

### Step 5: Per-Group Diff Validation

**IMPORTANT**: Never launch subagents in background mode (`run_in_background`). Permission requests from background subagents are invisible in the Claude Code interface — they can only be approved via the Discord hook, which has a 2-minute timeout. Always launch subagents in foreground.

Extract group sections from TASKS.md by finding `## Task Group:` headers. For each group, extract the section boundary (from its header to the next `## Task Group:` or end of file).

For each group section, launch a **strict-code-reviewer subagent**:

> **Agent**: rust-development-pipeline:strict-code-reviewer (subagent, discardable context)
>
> **Task**: Validate the implementation diff against one group's tasks.
>
> Read:
> - The cumulative diff (`git diff main...HEAD` — run this)
> - The task group section (markdown) for group `{GROUP_ID}` from TASKS.md
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

### Step 6: Strategic Review

Launch a **rust-architect subagent** for strategic review:

> **Agent**: rust-development-pipeline:rust-architect (subagent, discardable context)
>
> **Task**: Strategic review of the implementation.
>
> Read:
> - `git diff main...HEAD` (run this)
> - TASKS.md at `{TASKS_PATH}` (architecture_notes and known_pitfalls are sufficient)
>
> Assess:
> 1. Does the implementation follow the architecture_notes from TASKS.md?
> 2. Are crate boundaries respected?
> 3. Are the existing codebase patterns followed?
> 4. Are there strategic concerns (performance, maintainability, API design)?
> 5. **For `lib-tdd` tasks**: Does the implementation satisfy expected_behavior? Is the test adequate?
>
> Report: Strategic assessment (pass / issues / fail), specific concerns, items to defer.

### Step 7: Synthesize Judgement

Synthesize all reviews into the final outputs:

1. **Write `review.md`**:
   ```markdown
   # Review: {Phase Title}

   **Tasks**: {tasks-path}
   **Reviewed**: {date}

   ## Summary

   {Overall assessment — passed, needs fixes, or rejected}
   {Outcome verification: N criteria met, M failed, P adjusted}

   ## Per-Task Results

   ### {TASK-ID}: {description}
   - **Status**: ✓ Passed | ⚠ Minor Issues | ✗ Failed
   - **Runtime outcome verification**: {findings from step 4: did it work against real fixtures?}
   - **Diff validation**: {findings from step 5}
   - **Strategic review**: {findings from step 6}

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

### Step 8: Handoff

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
- Modify the implementation directly
- Use JSON schemas, index files, or wrapper scripts

**Will (new behaviors):**
- Verify outcomes by running acceptance commands against declared fixtures
- Flag placebo test patterns (is_finite, circular round-trip, unbounded thresholds)
- Compare test output against success criteria values from TASKS.md
