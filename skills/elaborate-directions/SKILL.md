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
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for scripts

## Output

- `notes/directions/<phase-slug>/directions.json` — the final directions artifact
- Intermediate artifacts in `notes/directions/<phase-slug>/`:
  - `deferred-and-patterns.md`
  - `workspace-map.json` — pre-computed codebase structural map
  - `codebase-state.md`
  - `draft-elaboration.md`
  - `draft-directions.json`
  - `task-checklist.md`

## Process

### Step 1: Setup

Set the stage marker for metrics, then determine the phase slug and create the output directory:

```bash
# Set stage marker and session start for metrics tracking
echo "elaborate-directions" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Determine phase slug and create output directory
PHASE_SLUG=$(basename $(dirname <plan-path>))
mkdir -p notes/directions/$PHASE_SLUG
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

### Step 2.5: Generate Workspace Map

Generate a pre-computed structural map of the codebase. This replaces
mechanical file discovery (fd/rg), letting the Explore subagent focus on
qualitative analysis.

Run the wrapper script from the project root (the target project, not
the pipeline plugin directory):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  "notes/directions/$PHASE_SLUG/workspace-map.json" \
  --validate
```

On success, `notes/directions/<phase-slug>/workspace-map.json` is created
with the full structural map (symbols, files, nameIndex, crossReferences,
and any validation warnings).

### Step 3: Explore Codebase (Subagent)

Launch an **Explore subagent** to analyze the codebase, starting from the
workspace map (rather than fd/rg):

> **Agent**: Explore (subagent, discardable context)
>
> **Task**: Explore the codebase for plan elaboration at `{PLAN_PATH}`.
>
> Read these inputs:
> - The plan file
> - `notes/directions/<phase-slug>/workspace-map.json` — pre-computed structural map
>
> Use the workspace map for O(1) structural lookups:
> - `symbols["TypeName"]` — type info, fields, generics, impls
> - `files["path.rs"]` — module wiring, crate ownership, submodules
> - `nameIndex["Name"]` — disambiguation across crates
> - `crossReferences.types["Type"]` — who imports/exports this type
>
> Then for each area the plan touches:
> 1. Focus on qualitative analysis the map can't provide: code patterns,
>    anti-patterns, test coverage gaps, architectural observations
> 2. Read specific files for detail where the map entry isn't sufficient
> 3. Document any compilation issues or LSP diagnostics
>
> Output to `notes/directions/<phase-slug>/codebase-state.md`:
> - Current file tree for affected areas
> - Key type/function signatures (use the map as starting point)
> - Module dependency graph (which crates depend on which)
> - Existing test structure
> - Observations and patterns that the workspace map cannot capture

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

First resolve `<plugin-ref-dir>` — the absolute path to the plugin's references:
```bash
echo "${CLAUDE_PLUGIN_ROOT}/skills/elaborate-directions/references"
```

Then launch the **plan-decomposer agent** to break the design into tasks.
Use the resolved `<plugin-ref-dir>` from above in the file list:

> **Agent**: rust-development-pipeline:plan-decomposer (subagent, discardable context)
>
> **Task**: Decompose the elaborated plan into structured directions.json tasks.
>
> Read these inputs:
> - The plan file
> - `notes/directions/<phase-slug>/draft-elaboration.md`
> - `notes/directions/<phase-slug>/codebase-state.md`
> - `<plugin-ref-dir>/directions-spec.md` (the spec)
> - `<plugin-ref-dir>/tdd-pattern.md` (the ch12-04 TDD reference)
>
> Output to `notes/directions/<phase-slug>/draft-directions.json`:
> - Follow the directions-spec.md schema exactly
> - Each task must have clear `changes[].guidance` (descriptive, not exact before/after)
> - Each task must have `wiring_checklist` entries where applicable
> - Each task must have runnable `acceptance` commands
> - Group tasks by shared files/concerns in `task_groups`
> - Include `architecture_notes` and `known_pitfalls` at the top level
> - Do NOT include exact before/after blocks — use descriptive guidance
> - For library code tasks, use `kind: "lib-tdd"` with a `tdd_interface` that embeds the test as specification. The test code must assert concrete, falsifiable behavior. Follow the TDD pattern documented in `tdd-pattern.md`.
> - For non-library code tasks (CLI, config, I/O adapters), use `kind: "direct"` (or omit `kind`).

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
> - For each `lib-tdd` task: is the `tdd_interface.test_code` a meaningful specification (not trivial)? Does it assert concrete, falsifiable behavior? Does `signature` match the function called in `test_code`?

### Step 7: Orchestrator Refinement

Read all intermediate artifacts and produce the final `directions.json`:

1. Read `notes/directions/<phase-slug>/draft-directions.json`
2. Read `notes/directions/<phase-slug>/task-checklist.md`
3. Address any clarity issues flagged by the reviewer:
   - Refine guidance text where ambiguous
   - Add missing files_in_scope
   - Fix acceptance commands
   - Correct wiring_checklist items
4. **If any task uses `kind: "lib-tdd"`**: ensure `architecture_notes` includes:
   > Library code in this phase follows ch12-04 TDD: tests claim interfaces first via `tdd_interface`, then implementations evolve to meet them. See the tdd-pattern.md reference (resolved path available as `<plugin-ref-dir>/tdd-pattern.md`).
5. Validate the final directions.json:
   ```bash
   uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/validate/validate-directions.py" notes/directions/<phase-slug>/directions.json
   ```
5. Save the final version as `notes/directions/<phase-slug>/directions.json`
6. Split into per-group files for explore-implement:
   ```bash
   uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/split-directions.py" notes/directions/<phase-slug>/directions.json
   ```
   Each task group becomes a separate `notes/directions/<phase-slug>/directions-<slug>-<group-id>.json`. The per-group files are small enough for the model to read fully. Invoke `/explore-implement` with a single group file. Also emits `notes/directions/<phase-slug>/directions-index.json` — a lightweight index with group list, architecture_notes, and known_pitfalls (1-2K tokens). Use the index for `/make-judgement`.

### Step 8: Handoff

Stage the directions artifacts for tracking:

```bash
git add notes/directions/<phase-slug>/
```

Run the session metrics eval to report performance:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" elaborate-directions
```

Report to the user:

> "Directions elaborated to `notes/directions/<phase-slug>/directions.json`.
>
> {eval output}
>
> Next step: `/explore-implement notes/directions/<phase-slug>/directions-<slug>-<group-id>.json` (one per task group)
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
