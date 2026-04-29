---
name: make-judgement
description: Review implemented changes against directions.json, produce review.md and fix-directions.json for any defects found. Replaces the old review-pr-gather + review-pr-judge pipeline. Use when the user says "/make-judgement <directions-path>", "review the implementation", "judge the changes", or after /explore-implement completes.
---

# Make Judgement

Reviews the diff produced by `/explore-implement` against the original `directions.json`. Strategic validation only — the compiler has already caught syntax and type errors during implementation. The reviewer focuses on: does the implementation correctly satisfy the directions?

Produces `review.md` (narrative review) and optionally `fix-directions.json` (fix instructions for any defects found).

## Trigger

`/make-judgement <directions-path>`

Where `<directions-path>` is the path to the `directions.json` that was used by `/explore-implement`.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `python3` for diff data gathering and validation

## Output

- `notes/pr-reviews/<plan-slug>/review.md` — narrative review
- `notes/pr-reviews/<plan-slug>/fix-directions.json` — fix instructions (if defects found)
- `notes/pr-reviews/<plan-slug>/deferred.md` — improvements deferred to future phases

## Process

### Step 1: Gather Diff Data (Script)

Run the deterministic diff data collector:

```bash
python3 scripts/gather-diff-data.py <directions-path> --output-dir notes/pr-reviews/<plan-slug>
```

This produces:
- `raw-diff.md` — the raw git diff of changes since the base commit
- `file-manifest.json` — structured file change metadata
- Analysis templates for the reviewers

### Step 2: Read Context (Orchestrator)

Read the key inputs to understand what was requested and what was delivered:

1. Read `notes/pr-reviews/<plan-slug>/raw-diff.md`
2. Read `notes/pr-reviews/<plan-slug>/file-manifest.json`
3. Read the original `<directions-path>` to understand what was asked for
4. Read `git diff` output for a high-level summary of changes

### Step 3: Diff Validation (Subagent)

Launch a **strict-code-reviewer subagent** to validate the diff against the directions:

> **Agent**: rust-development-pipeline:strict-code-reviewer (subagent, discardable context)
>
> **Task**: Validate the implementation diff against the original directions.
>
> Read:
> - `notes/pr-reviews/<plan-slug>/raw-diff.md`
> - `notes/pr-reviews/<plan-slug>/file-manifest.json`
> - The original directions.json at `{DIRECTIONS_PATH}`
>
> For each task in directions.json, check:
> 1. Were all required files created/modified/deleted as specified?
> 2. Does each change match the guidance (structs, functions, signatures)?
> 3. Are all wiring_checklist items satisfied?
> 4. Are there any changes that are NOT in the directions (scope creep)?
> 5. Are there any obvious bugs or issues in the diff?
>
> Report findings per-task:
> - ✓ Task fully implemented as directed
> - ⚠ Task implemented with issues (describe)
> - ✗ Task not implemented or mis-implemented (describe)

### Step 4: Strategic Review (Subagent)

Launch a **rust-architect subagent** for strategic review:

> **Agent**: rust-development-pipeline:rust-architect (subagent, discardable context)
>
> **Task**: Strategic review of the implementation.
>
> Read:
> - `notes/pr-reviews/<plan-slug>/raw-diff.md`
> - The original directions.json at `{DIRECTIONS_PATH}`
>
> Assess:
> 1. Does the implementation follow the architecture_notes from the directions?
> 2. Are crate boundaries respected?
> 3. Are the existing codebase patterns followed?
> 4. Are there any strategic concerns (performance, maintainability, API design)?
> 5. Is the public API surface well-designed?
>
> Report:
> - Strategic assessment (pass / issues / fail)
> - Specific concerns with recommendations
> - Items to defer to future phases (for deferred.md)

### Step 5: Synthesize Judgement (Orchestrator)

Synthesize both reviews into the final outputs:

1. **Write `review.md`**:
   ```markdown
   # Review: {Phase Title}

   **Directions**: {directions-path}
   **Reviewed**: {date}

   ## Summary

   {Overall assessment — passed, needs fixes, or rejected}

   ## Per-Task Results

   ### {TASK-ID}: {description}
   - **Status**: ✓ Passed | ⚠ Minor Issues | ✗ Failed
   - **Diff validation**: {findings from step 3}
   - **Strategic review**: {findings from step 4}

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
   python3 scripts/validate/validate-review-consistency.py notes/pr-reviews/<plan-slug>/
   ```
   If fix-directions.json was created:
   ```bash
   python3 scripts/validate/validate-fix-document.py notes/pr-reviews/<plan-slug>/fix-directions.json
   ```

### Step 6: Handoff

Report to the user:

> "Review complete. See `notes/pr-reviews/<plan-slug>/review.md`.
>
> {N} issue(s) found, {M} deferred.
>
> Next steps:
> - Fix defects: `/explore-implement notes/pr-reviews/<plan-slug>/fix-directions.json`
> - If all passed: merge the feature branch and proceed to the next phase."

## Boundaries

**Will:**
- Validate diff against directions.json per-task
- Perform both detailed (code review) and strategic (architecture) review
- Classify issues by severity
- Produce fix-directions.json for defects (follows same schema as directions.json)
- Defer non-critical improvements to future phases

**Will not:**
- Re-check compiler errors (already caught during implementation)
- Re-implement any code changes
- Run cargo check or tests (already done during implementation)
- Modify the implementation directly
