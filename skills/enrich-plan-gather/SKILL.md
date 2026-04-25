---
name: enrich-plan-gather
description: Session 1 of the split plan enrichment pipeline. Run this in a local model session to explore the codebase, elaborate the plan, and produce a draft TOML task breakdown. Output is saved to notes/plan-enrichment/{plan-slug}/ for user review before the judge session. Triggered by /enrich-plan-gather [plan-file].
version: 0.1.0
---

# Enrich Phase Plan — Gather (Local Model Session)

Reads the phase plan, explores the codebase state, elaborates underspecified details, and produces a draft TOML implementation plan. Designed to run in a Claude Code session pointed at a local llama-server backend (free compute). All output is saved to files for the user to review before the judge session.

## Trigger

`/enrich-plan-gather [plan-file]`

If no plan file is given, ask the user for the path.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Process

### Step 1: Read the plan file

Read the plan file provided by the user. Record:
- Plan slug: derive from filename (e.g., `plans/phase-6.md` → slug `phase-6`)
- Plan title and phase number
- Key goals and deliverables

All output files go under: `notes/plan-enrichment/{plan-slug}/`

### Step 2: Load deferred improvements and failure patterns

**Deferred improvements:**
```bash
fd deferred.md notes/pr-reviews/
```
If found, read each file. Summarize as bullet points.

**Known failure modes from prior fix plans:**
```bash
fd fix-plan.toml notes/pr-reviews/ | head -3
```
If found, read each file. Extract recurring issue categories:
- Missing `pub mod` declarations
- Missing `pub use` re-exports
- Incomplete consumer updates
- Stale imports after refactoring
- Cross-module integration failures

Save to: `notes/plan-enrichment/{plan-slug}/deferred-and-patterns.md`

Format:
```
## Deferred Improvements
[list of items from deferred.md files, or "None found"]

## Known Failure Modes
[list of recurring categories, or "None found"]
```

### Step 3: Explore codebase state

For each module, file, type, or function **mentioned in the plan**, read the relevant source:

1. Read the file using the Read tool
2. Record:
   - File path
   - Public types and their fields/variants
   - Public function signatures (name, parameters, return type)
   - Trait implementations
   - Module structure (`pub mod`, `pub use`)
   - Current state vs what the plan says to create/modify

**Focus only on files mentioned in the plan.** Do not explore the entire codebase.

Save to: `notes/plan-enrichment/{plan-slug}/codebase-state.md`

Format per file:
```
## File: path/to/file.rs

### Current types/traits/functions
- `pub struct Foo { ... }`
- `pub fn bar(x: Type) -> Result<Out, Err>`
- ...

### Relationship to plan
- Plan says: [what the plan wants to do here]
- Current state: [what currently exists]
- Gap: [what needs to be added/changed]
```

### Step 4: Draft elaboration

For each underspecified item in the plan, propose concrete implementation details.

**Record proposals — do not invent architecture. Base proposals on existing patterns in the codebase.**

For each underspecified item:
```
## Item: [plan item description]

**Proposed type signature:**
pub fn foo(x: ExistingType) -> Result<NewType, ExistingError>

**Module placement:** path/to/module.rs

**Error handling strategy:** [e.g., use existing ErrorKind enum, add variant X]

**Ownership/lifetime notes:** [any concerns, or "None"]

**Trait coherence notes:** [any concerns, or "None"]
```

Also note deferred improvements that are **directly relevant** to this plan and could be absorbed:
```
## Deferred Items to Consider
- [item name]: [why it's relevant now — or "skip, not yet applicable"]
```

Save to: `notes/plan-enrichment/{plan-slug}/draft-elaboration.md`

### Step 5: Draft TOML plan

Break the elaboration into minimum-viable, SRP-aligned tasks following the compilable-plan-spec.

**Before writing each `before` block:**
1. Read the actual source file
2. Copy the exact text verbatim — no paraphrasing, no `...`
3. Self-check: `rg -F "{first 20 chars}" path/to/file.rs`
4. If grep fails: the before block is wrong — re-read and fix

**Module wiring checklist (check per new file):**
- [ ] New `.rs` file → task includes `pub mod <name>;` in parent `lib.rs` or `mod.rs`
- [ ] New public types → task includes `pub use <type>;` at crate root or prelude
- [ ] Consumer updates (if plan mentions "update Y to use X") → in same task as definition

**Known failure mode prevention (check per task):**
- [ ] Does this task avoid missing `pub mod`?
- [ ] Does this task avoid missing `pub use`?
- [ ] Does this task include all consumer-side changes?
- [ ] Does this task avoid stale imports?

TOML structure:
```toml
[meta]
title = "Phase X.Y: <Phase Name>"
source_branch = "<branch>"
created = "<YYYY-MM-DD>"

[dependencies]
# TASK-N = ["TASK-M"]  — omit if all independent

[tasks.TASK-N]
description = "Short description"
type = "replace"  # "replace" | "create" | "delete"
acceptance = [
    "cargo check -p crate_name",
    "cargo test -p crate_name",
]

[[tasks.TASK-N.changes]]
file = "relative/path/from/root"
before = '''
exact content copied verbatim — no paraphrasing, no ellipsis
'''
after = '''
exact replacement content
'''
```

Save to: `notes/plan-enrichment/{plan-slug}/draft-plan.toml`

### Step 6: Per-task self-check

For each task in the TOML plan, produce a checklist entry:

```
## TASK-N: [description]

- [ ] Before block matches source file (grep confirmed: [Yes/No/Unverified])
- [ ] Has acceptance commands: [Yes/No]
- [ ] Module wiring complete: [Yes/No/Not applicable]
- [ ] Would cargo check pass after this task alone: [Probably/Uncertain/No]
- [ ] Depends on: [TASK-X / None]

Notes: [anything uncertain or worth the judge session's attention]
```

Save to: `notes/plan-enrichment/{plan-slug}/task-checklist.md`

### Step 7: Summary for user review

```
## Gather Summary: {plan-slug}

**Tasks created:** N
**Dependency chain:** [brief description, e.g. "TASK-1 → TASK-2,3 (parallel) → TASK-4"]
**Deferred items absorbed:** [N items / None]

**Gather completeness:**
- [ ] deferred-and-patterns.md — [created / missing]
- [ ] codebase-state.md — [created / missing]
- [ ] draft-elaboration.md — [created / missing]
- [ ] draft-plan.toml — [created / missing]
- [ ] task-checklist.md — [created / missing]

**Before-block verification:**
- [N/M] before blocks confirmed to match source files
- Unverified: [list task IDs with unverified before blocks]

**Confidence notes:**
[Things I am uncertain about — flag these for the judge session]
- e.g., "I'm not sure if TaskSuccessors needs a re-export at the crate root"
- e.g., "The error handling strategy for Task 3 is based on inference — confirm"

**Questions for user:**
[Specific questions about design decisions or scope boundaries]
```

Save to: `notes/plan-enrichment/{plan-slug}/gather-summary.md`

---

## Boundaries

**Will:**
- Base proposals on existing codebase patterns — not invention
- Verify before blocks by rg-grepping
- Save every output file even if partial (partial is better than nothing)
- Flag confidence notes for any uncertain decision

**Will not:**
- Make final architectural decisions
- Use `...` or placeholder text in before/after blocks
- Skip the module wiring checklist
- Explore files not mentioned in the plan
