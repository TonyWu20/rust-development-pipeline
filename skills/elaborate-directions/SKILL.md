---
name: elaborate-directions
description: Elaborate a reviewed phase plan into structured directions.json with task decomposition, codebase exploration, wiring checklists, and architectural guidance. Replaces the old enrich-phase-plan + enrich-plan-gather + enrich-plan-judge pipeline. Use when the user says "/elaborate-directions <plan-path>", "elaborate the plan", "break down the phase", or after /plan-review has completed.
---

# Elaborate Directions

Transforms a reviewed phase plan (from `/plan-review`) into `directions.json` — the input for `/explore-implement`. Uses subagents for each elaboration step, keeping process context discardable. Only the final refinement runs in the orchestrator.

## Trigger

`/elaborate-directions <plan-path>`

Where `<plan-path>` is the path to a reviewed `PHASE_PLAN.md` (the output of `/plan-review`).

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `python3` for validation scripts

## Output

- `notes/directions/<phase-slug>/directions.json` — the final directions artifact
- Intermediate artifacts in `notes/directions/<phase-slug>/`:
  - `deferred-and-patterns.md`
  - `codebase-state.md`
  - `draft-elaboration.md`
  - `draft-directions.json`
  - `task-checklist.md`

## Process

### Step 1: Setup

Determine the phase slug from the plan filename (e.g., `plans/phase-3.1/PHASE_PLAN.md` → `phase-3.1`). Create the output directory:

```bash
mkdir -p notes/directions/<phase-slug>
```

### Step 2: Load Context (Subagent)

Launch a **general-purpose subagent** to gather deferred improvements and known failure patterns:

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Load context for plan elaboration.
>
> 1. Read the plan file at `{PLAN_PATH}`.
> 2. Read all `deferred.md` files from prior review rounds:
>    ```bash
>    fd deferred.md notes/pr-reviews/
>    ```
> 3. Read the fix report at `fix-reports/issue-9-enrich-plan-judge-detection-gaps.md` (if it exists) for known failure modes.
> 4. Read `feature-requests/reduce_recurring_problems.md` (if it exists).
> 5. Synthesize into `notes/directions/<phase-slug>/deferred-and-patterns.md`:
>    - Key architectural patterns from the plan
>    - Known failure modes to avoid
>    - Deferred improvements that should be incorporated

### Step 3: Explore Codebase (Subagent)

Launch an **Explore subagent** to map the relevant parts of the codebase:

> **Agent**: Explore (subagent, discardable context)
>
> **Task**: Explore the codebase for plan elaboration at `{PLAN_PATH}`.
>
> Read the plan file first. Then for each area the plan touches:
> 1. Use `fd` and `rg` to find relevant files and their structure
> 2. Read the key files to understand current state
> 3. Document module structure, public API surface, and existing patterns
>
> Output to `notes/directions/<phase-slug>/codebase-state.md`:
> - Current file tree for affected areas
> - Key type/function signatures
> - Module dependency graph (which crates depend on which)
> - Existing test structure
> - Any LSP diagnostics or compilation issues in the current codebase

### Step 4: Design Elaboration (Subagent)

Launch the **rust-architect agent** to make design decisions:

> **Agent**: rust-development-pipeline:rust-architect (subagent, discardable context)
>
> **Task**: Elaborate the architectural design for the plan at `{PLAN_PATH}`.
>
> Read these inputs:
> - The plan file
> - `notes/directions/<phase-slug>/deferred-and-patterns.md`
> - `notes/directions/<phase-slug>/codebase-state.md`
>
> Output to `notes/directions/<phase-slug>/draft-elaboration.md`:
> - Design decisions for each goal in the plan
> - Crate boundary decisions (what goes where)
> - Pattern requirements (which existing patterns to follow)
> - Type signatures for key new types
> - Known pitfalls and constraints
> - Suggested task grouping rationale

### Step 5: Task Decomposition (Subagent)

Launch the **plan-decomposer agent** to break the design into tasks:

> **Agent**: rust-development-pipeline:plan-decomposer (subagent, discardable context)
>
> **Task**: Decompose the elaborated plan into structured directions.json tasks.
>
> Read these inputs:
> - The plan file
> - `notes/directions/<phase-slug>/draft-elaboration.md`
> - `notes/directions/<phase-slug>/codebase-state.md`
> - `skills/elaborate-directions/references/directions-spec.md` (the spec)
>
> Output to `notes/directions/<phase-slug>/draft-directions.json`:
> - Follow the directions-spec.md schema exactly
> - Each task must have clear `changes[].guidance` (descriptive, not exact before/after)
> - Each task must have `wiring_checklist` entries where applicable
> - Each task must have runnable `acceptance` commands
> - Group tasks by shared files/concerns in `task_groups`
> - Include `architecture_notes` and `known_pitfalls` at the top level
> - Do NOT include exact before/after blocks — use descriptive guidance

### Step 6: Clarity Review (Subagent)

Launch the **impl-plan-reviewer agent** to assess the directions for clarity:

> **Agent**: rust-development-pipeline:impl-plan-reviewer (subagent, discardable context)
>
> **Task**: Review the draft directions.json for clarity and completeness.
>
> Read:
> - `notes/directions/<phase-slug>/draft-directions.json`
> - `notes/directions/<phase-slug>/codebase-state.md`
>
> Output to `notes/directions/<phase-slug>/task-checklist.md`:
> - For each task: is the guidance clear enough to implement without ambiguity?
> - For each task: are the files_in_scope correct and complete?
> - For each task: are the acceptance commands sufficient to validate?
> - For each task: are wiring_checklist items correct?
> - Overall assessment: is this ready for implementation, or what needs refinement?
> - Flag any tasks where guidance is ambiguous, underspecified, or contradictory

### Step 7: Orchestrator Refinement

Read all intermediate artifacts and produce the final `directions.json`:

1. Read `notes/directions/<phase-slug>/draft-directions.json`
2. Read `notes/directions/<phase-slug>/task-checklist.md`
3. Address any clarity issues flagged by the reviewer:
   - Refine guidance text where ambiguous
   - Add missing files_in_scope
   - Fix acceptance commands
   - Correct wiring_checklist items
4. Validate the final directions.json:
   ```bash
   python3 scripts/validate/validate-directions.py notes/directions/<phase-slug>/directions.json
   ```
5. Save the final version as `notes/directions/<phase-slug>/directions.json`

### Step 8: Handoff

Report to the user:

> "Directions elaborated to `notes/directions/<phase-slug>/directions.json`.
>
> Next step: `/explore-implement notes/directions/<phase-slug>/directions.json`
>
> Summary: {N} tasks in {M} groups covering {areas}."

## Boundaries

**Will:**
- Decompose phase plans into structured, implementable directions
- Use descriptive guidance (not exact before/after blocks) that won't go stale
- Include wiring checklists that the implementer can verify after each task
- Validate the output against the directions-spec

**Will not:**
- Write exact before/after replacement blocks (that's the old TOML approach)
- Implement any code changes
- Review architectural decisions (that was already done by /plan-review)
- Execute acceptance commands
