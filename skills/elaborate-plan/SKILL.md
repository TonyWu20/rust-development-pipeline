---
name: elaborate-plan
description: Elaborate a phase plan into DECISIONS.md + TASKS.md using a grill-me interview followed by task decomposition. Replaces the old /plan-review + /elaborate-directions pipeline. Use when the user says "/elaborate-plan <plan-path>", "elaborate the plan", "break down the phase", or after /next-phase-plan completes.
---

# Elaborate Plan

> **DEPRECATED**: Replaced by `/drive-outcomes`. This skill continues to work for
> existing phases but will be removed after the migration period. New phases should
> use `/drive-outcomes`.

Transforms a phase plan (from `/next-phase-plan`) into two markdown documents: `DECISIONS.md` (architectural decisions from the grill-me interview) and `TASKS.md` (task breakdown with serial/parallel dependency mapping). Uses two subagents, down from the old seven.

## Trigger

`/elaborate-plan <plan-path>`

Where `<plan-path>` is the path to a `PHASE_PLAN.md` (the output of `/next-phase-plan`).

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `bash ${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh` to generate workspace maps

## Output

- `notes/plans/<phase-slug>/DECISIONS.md` — architectural decisions, patterns, conventions, pitfalls
- `notes/plans/<phase-slug>/TASKS.md` — task breakdown in markdown format (consumed by `/explore-implement`)

## Process

### Step 1: Setup

```bash
# Set stage marker and session start for metrics tracking
echo "elaborate-plan" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Determine phase slug from plan path
PHASE_SLUG=$(basename $(dirname <plan-path>))
mkdir -p notes/plans/$PHASE_SLUG
```

### Step 2: Load Context

Read the plan, deferred items from prior phases, and failure patterns:

```bash
# Read the plan
cat <plan-path>

# Read deferred improvements from prior phases
fd deferred.md notes/pr-reviews/ | while read f; do echo "=== $f ==="; cat "$f"; done

# Read failure patterns (if they exist)
cat notes/failure-patterns.md 2>/dev/null || echo "No failure patterns catalog yet"

# Read project documentation
cat CONTEXT.md 2>/dev/null || echo "NO_CONTEXT_MD"
cat CONTEXT-MAP.md 2>/dev/null || echo "NO_CONTEXT_MAP"
fd -e md . docs/adr/ 2>/dev/null | sort | while read f; do
  echo "=== $f ===" && cat "$f" && echo ""
done
```

### Step 3: Generate Workspace Map

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  "notes/plans/$PHASE_SLUG/workspace-map.json"
```

### Step 4: Grill + Decompose (Two Subagents)

#### Step 4a — Grill (subagent 1): Design-level interview

Launch a grill-me style subagent that interviews the user about design decisions:

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Grill the user on the design decisions in this plan, with documentation-driven validation.
>
> Context:
> - PHASE_PLAN.md at `{PLAN_PATH}`
> - Workspace map at `notes/plans/{SLUG}/workspace-map.json` (use `jq` for lookups)
> - Deferred improvements from prior phases: {summary from step 2}
> - Failure patterns catalog: {summary from step 2}
> - Domain glossary (CONTEXT.md): {contents or "none"}
> - Existing ADRs (docs/adr/): {list of filenames and one-line summaries}
>
> **Reference files** (read when needed):
> - Context format: `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/context-format.md`
> - ADR format: `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/adr-format.md`
>
> Walk each branch of the design decision tree by interviewing the user:
> 1. For each goal in the plan, question the architectural approach. Explore the codebase (workspace map + LSP) to ground your questions.
> 2. For each design decision, identify alternatives and get explicit user confirmation.
> 3. Surface edge cases, potential pitfalls, and overlooked dependencies.
> 4. For deferred items from prior phases: should each be absorbed or deferred again?
>
> **Terminology validation** — challenge against the glossary:
> - If the plan or user uses a term that conflicts with CONTEXT.md, call it out immediately: "Your glossary defines 'cancellation' as X, but your plan implies Y — which is it?"
> - When the user uses vague or overloaded terms during the design discussion, propose a precise canonical term and confirm it.
> - Cross-reference claims about how the system works against actual code (use `jq` on the workspace map, then read files). If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"
> - When a term is resolved, update CONTEXT.md inline using the format at `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/context-format.md`. Capture as they happen — don't batch.
> - Create CONTEXT.md lazily (only when the first term is resolved). If the repo has a CONTEXT-MAP.md, infer which context the current discussion relates to.
>
> **ADR creation** — offer sparingly:
> - Only offer to create an ADR when ALL THREE are true:
>   1. **Hard to reverse** — the cost of changing your mind later is meaningful
>   2. **Surprising without context** — a future reader will wonder "why did they do it this way?"
>   3. **The result of a real trade-off** — there were genuine alternatives and you picked one for specific reasons
> - If any criterion is missing, skip the ADR. Record the decision in DECISIONS.md instead.
> - When an ADR is warranted: scan `docs/adr/` for the highest number, increment by one, create `docs/adr/{NNNN}-{slug}.md` using the format at `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/adr-format.md`.
> - Create the `docs/adr/` directory lazily — only when the first ADR is needed.
>
> **Discuss concrete scenarios** — when domain relationships or architectural decisions are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about boundaries.
>
> After each question, provide your recommended answer. Explore the codebase when a question requires code-level evidence.
>
> Continue until all branches are resolved and the user confirms shared understanding.
>
> Output: {will be captured by the orchestrator}

Note: this is an interactive interview. The orchestrator presents the subagent's questions to the user and relays answers back. After the interview completes, produce `notes/plans/{SLUG}/DECISIONS.md` with:

- **Architectural decisions** — crate boundaries, patterns, type choices. For decisions that became ADRs, reference the ADR number (e.g., "ADR-0003: event-sourced write model").
- **Domain terms validated** — terms from CONTEXT.md that were challenged and confirmed, and new terms that were added during this session. Reference them in bold as they appear in the glossary.
- **Coding conventions** to follow
- **Known pitfalls** and anti-patterns to avoid
- **Deferred item disposition** (absorbed or re-deferred)
- **ADR index** — list of ADRs created during this session (number, title, one-line summary)

#### Step 4b — Decompose (subagent 2): Task breakdown

After the interview, launch a decomposer subagent:

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Decompose the reviewed plan into implementable tasks in markdown format.
>
> Context:
> - PHASE_PLAN.md at `{PLAN_PATH}`
> - DECISIONS.md at `notes/plans/{SLUG}/DECISIONS.md`
> - Workspace map at `notes/plans/{SLUG}/workspace-map.json` (use `jq` for lookups)
> - TASKS.md format spec at `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/tasks-spec.md`
> - ODD pattern reference at `{CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md`
> - Domain glossary (CONTEXT.md): {contents or "none"}
> - Existing ADRs (docs/adr/): {list of filenames and one-line summaries}
>
> Produce a markdown task breakdown following the tasks-spec.md format:
>
> 1. **Group tasks by shared files/concern** — tasks in the same group share a worktree
> 2. **Map serial vs parallel dependencies** — use `**Depends on groups:**` and `**Depends on:**`
> 3. **Apply ODD where appropriate** — library code gets `**Kind:** lib-tdd` with embedded success criteria and test code
> 4. **Link goals** — each task gets `**Goal:** G{N}` for traceability
> 5. **Describe changes naturally** — `**create**` / `**modify**` / `**delete**` as bullet start
> 6. **Provide concrete acceptance** — falsifiable commands, examples where possible
>
> Read the failure-patterns catalog at `notes/failure-patterns.md` (if it exists) and ensure no known recurring mistakes are repeated in this breakdown.
>
> Reference the tasks-spec.md for the exact markdown format. Keep guidance descriptive, not exact before/after blocks.
>
> Output: `notes/plans/{SLUG}/TASKS.md`

### Step 5: Orchestrator Refinement

Read both outputs and verify:

1. **Coverage**: Every plan goal has at least one task
2. **Acyclicity**: No circular dependencies between tasks or groups
3. **Traceability**: Every task links to a plan goal via `**Goal:** G{N}`
4. **Completeness**: Acceptance criteria are concrete and falsifiable
5. **Consistency**: Success criteria are concrete and falsifiable with cited sources
6. **Documentation consistency**: Domain terms in DECISIONS.md match CONTEXT.md. ADR references are valid (files exist, numbers are sequential). No ADR was created unnecessarily (verify the three criteria).

No JSON validation, no scripts — just a read-through sanity check. If something is wrong, fix it directly in the markdown.

### Step 6: Handoff

Stage the artifacts and report:

```bash
git add notes/plans/$PHASE_SLUG/
```

Run the session metrics eval:

```bash
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR}" uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" elaborate-plan
```

Report to the user:

> "Elaboration complete for {Phase Name}.
>
> - `notes/plans/{SLUG}/DECISIONS.md` — architectural decisions and conventions (with ADR index inside)
> - `notes/plans/{SLUG}/TASKS.md` — {N} tasks in {M} groups
> {If ADRs created: "- `docs/adr/{NNNN}-{slug}.md` — {N} new Architecture Decision Records"}
> {If CONTEXT.md updated: "- `CONTEXT.md` — domain glossary updated with refined terms"}
>
> Next steps:
> 1. `/explore-implement notes/plans/{SLUG}/TASKS.md` — implement a group
>    (for multi-group plans, the orchestrator tells the user which group to start with)
> 2. For simple single-group plans, that's the whole implementation.
> 3. For complex multi-group plans, use `/make-judgement notes/plans/{SLUG}/TASKS.md` for cross-group validation."

## Boundaries

**Will:**
- Interview the user about design decisions using grill-me questioning
- Challenge terminology against the project's domain glossary and update CONTEXT.md inline
- Create ADRs when design decisions are hard to reverse, surprising, and the result of a real trade-off
- Cross-reference design claims against code during the grill interview
- Decompose into markdown tasks with serial/parallel dependency mapping
- Follow the ODD pattern (odd-pattern.md) for library code: success criteria anchored to ground truth before implementation
- Produce natural markdown output (no JSON)

**Will not:**
- Write any implementation code
- Use JSON schemas or validation scripts
- Run cargo check or cargo test (that's `/explore-implement`'s job)
- Rigidly enforce SRP at task level (the compiler handles that)
