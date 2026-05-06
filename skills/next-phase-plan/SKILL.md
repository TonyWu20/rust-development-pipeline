---
name: next-phase-plan
description: Interactive skill for discussing and designing the next phase of a Rust project. Facilitates a conversation with the user about goals, scope, and high-level design, producing a markdown plan document as output. Uses grill-me + first-principle thinking to question priorities and foundations before committing to a plan. Use when the user says "/next-phase-plan", "plan the next phase", "what should the next phase do", "let's figure out the next steps", or wants to decide what the next phase should accomplish before breaking it into tasks. This is the FIRST step in the planning pipeline — its output feeds into /elaborate-plan.
---

# Next Phase Plan

Facilitates a structured discussion to define the next phase of work. Uses **first-principle thinking** to question the foundations of what's being proposed — and **grill-me interviewing** to walk the decision tree for scope and priorities — before committing to a plan. Produces a high-level plan document in markdown, consumed by `/elaborate-plan` for task decomposition.

## Trigger

`/next-phase-plan`

No arguments. This skill is conversational — it gathers context and discusses with the user.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Process

### Step 1: Gather Context

Automatically collect background before engaging the user:

1. **Project memory**:

   ```bash
   MEMORY_DIR="$HOME/.claude/projects/$(pwd | sd '/' '-')/memory"
   ```

   Read `$MEMORY_DIR/MEMORY.md` and every linked memory file.

2. **Recent git history** (last 10 commits on `main`):

   ```bash
   git log --oneline -10 main
   ```

3. **Existing plan files** (if any):

   ```bash
   fd -e md -e toml . plans/
   ```

   Read the most recent plan file to understand what was last planned.

4. **Deferred improvements** from prior review rounds:

   ```bash
   fd deferred.md notes/pr-reviews/
   ```

   Read all `deferred.md` files found — these are improvements the reviewer identified but the plan didn't commission, and they are candidates for this phase.

5. **Execution reports** (if any):

   ```bash
   fd -e md . execution_reports/
   ```

   Skim the most recent report to understand what was completed and what failed.

### Step 2: Grill Goals with First-Principle Thinking

Before accepting any goals, question the foundations of what's being proposed. Invoke a grill-me + first-principle subagent:

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Question the next phase goals using first-principle thinking and grill-me interviewing.
>
> Context:
> - Project memory: {MEMORY_CONTENTS}
> - Recent git history: {GIT_LOG}
> - Last plan: {LAST_PLAN_CONTENTS or "No prior plan"}
> - Deferred improvements: {DEFERRED_CONTENTS or "None"}
> - Execution report: {LAST_REPORT_SUMMARY or "None"}
>
> **First-principle thinking** — question the foundations:
> - "WHY do we need this? What's the actual problem we're solving?"
> - "Is this even the right approach? What alternatives exist that don't require code changes?"
> - "What assumptions is this plan resting on? Verify each against the codebase."
> - "Are we solving a real problem or a perceived one? What evidence exists?"
> - "What would happen if we did nothing?"
>
> **Grill-me** — question scope and priorities:
> - "What's the highest-priority problem right now? Is this it?"
> - "What deferred items should influence this decision?"
> - "What downstream effects will these choices have?"
> - Walk the decision tree for scope boundaries.
>
> After the user responds to your questions, propose candidate goals. For each goal:
> - State what it achieves and why it's the right next step
> - Estimate small, medium, or large effort
> - Note dependencies on prior work or other goals
>
> Also flag any deferred improvements now appropriate to incorporate.

Present the proposal to the user.

```
You are helping define the next phase of a Rust project.

<project_memory>
{{MEMORY_CONTENTS}}
</project_memory>

<recent_git_history>
{{GIT_LOG}}
</recent_git_history>

<last_plan>
{{LAST_PLAN_CONTENTS — or "No prior plan found"}}
</last_plan>

<deferred_improvements>
{{DEFERRED_CONTENTS — or "None"}}
</deferred_improvements>

<execution_report>
{{LAST_REPORT_SUMMARY — or "No prior execution report"}}
</execution_report>

Propose candidate goals for the NEXT phase. For each goal:
- State what it achieves and why it's the right next step
- Estimate whether it is a small, medium, or large effort
- Note any dependencies on prior work or on other goals in this list

Also flag any deferred improvements that are now appropriate to incorporate.

Keep the list focused — 3 to 7 goals is ideal. Do not decompose into tasks.
```

Present the architect's proposal to the user.

### Step 3: Iterate with the User

Discuss the proposed goals with the user. Typical questions to work through:

- Which goals are in scope for this phase vs. a later phase?
- Are there goals missing from the proposal?
- Are any deferred improvements now ready to absorb?
- What are the hard constraints (API stability, performance, deadline)?
- What should explicitly be **out of scope** for this phase?

Use the `rust-development-pipeline:rust-architect` agent for follow-up analysis as needed (e.g., if the user wants to explore a specific design direction).

There is no fixed number of rounds — continue until the user is satisfied with the scope.

### Step 4: Write the Plan Document

Once the scope is agreed, produce a structured markdown plan document and save it to the path the user specifies (default: `plans/phase-{N}/PHASE_PLAN.md`):

```markdown
# Phase {N}: {Phase Name}

**Date:** {YYYY-MM-DD}
**Status:** Draft

## Goals

{Numbered list of agreed goals, each with a one-paragraph description of what it achieves and why now.}

## Scope Boundaries

**In scope:**
{Bulleted list of what this phase covers}

**Out of scope:**
{Bulleted list of what is explicitly deferred — prevents scope creep during implementation}

## Design Notes

{Key architectural decisions, constraints, and cautions raised during the discussion. This section is the input to the /plan-review gate.}

## Deferred Items Absorbed

{List any deferred improvements from prior phases that this plan incorporates, with a note on where/how they fit. If none, write "None."}

## Open Questions

{Unresolved questions that /plan-review or /elaborate-directions may need to address. If none, write "None."}
```

Commit the plan document:

```bash
git add plans/phase-{N}/PHASE_PLAN.md
git commit -m "plan(phase-{N}): initial phase plan — {Phase Name}"
```

### Step 5: Handoff

Tell the user:

> "Phase {N} plan saved to `plans/phase-{N}/PHASE_PLAN.md`.
>
> Next steps:
> 1. `/elaborate-plan plans/phase-{N}/PHASE_PLAN.md` — grills the design decisions, decomposes into TASKS.md with serial/parallel task groups.
> 2. `/explore-implement notes/plans/<phase-slug>/TASKS.md` — implements a task group in a git worktree with real compiler feedback + auto-review before commit.
> 3. For complex multi-group changes: `/make-judgement notes/plans/<phase-slug>/TASKS.md` — cross-group validation and fix instructions."

## Boundaries

**Will:**
- Question goals using first-principle thinking and grill-me interviewing before goals are set
- Discuss scope, goals, and design decisions with the user before any plan is written
- Surface deferred improvements as explicit candidates
- Produce a structured plan document with clear scope boundaries

**Will not:**
- Decompose into tasks (that is `/elaborate-plan`'s job)
- Review the plan for architectural soundness (built into `/elaborate-plan`'s grill step)
- Make implementation decisions without user input
