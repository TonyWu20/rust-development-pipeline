---
name: enrich-plan-gather
description: Session 1 of the split plan enrichment pipeline. Run this in a local model session to explore the codebase, elaborate the plan, and produce a draft TOML task breakdown. Output is saved to notes/plan-enrichment/{plan-slug}/ for user review before the judge session. Triggered by /enrich-plan-gather [plan-file].
version: 0.2.0
---

# Enrich Phase Plan — Gather (Local Model Session)

Orchestrates a sequence of focused subagents to explore the codebase, elaborate the plan, and produce a draft TOML implementation plan. Each subagent handles one concern in isolation — the orchestrator only coordinates and never accumulates file contents in its own context.

Output is saved to `notes/plan-enrichment/{plan-slug}/` for user review before the judge session.

## Trigger

`/enrich-plan-gather [plan-file]`

If no plan file is given, ask the user for the path.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Orchestrator Role

You are the orchestrator. Your context must stay clean. You do **not** read source files, plan contents, or output files yourself. You launch subagents, receive their short result summaries, and pass those summaries forward to the next subagent or to the final gather-summary.

## Process

### Step 0: Resolve plan slug and prepare output directory

Read the plan file header only (first 10 lines) to extract the title and phase number.

Derive the plan slug from the filename: e.g., `plans/phase-6.md` → `phase-6`.

Set:
```
PLAN_FILE={plan-file}
PLAN_SLUG={slug}
OUT=notes/plan-enrichment/{slug}
```

Create the output directory:
```bash
mkdir -p notes/plan-enrichment/{slug}
```

### Step 1: Load deferred improvements and failure patterns

Spawn a general-purpose subagent with this exact prompt (simple fd search — no specialist needed):

```
Your job: find and summarize deferred improvements and known failure patterns from prior phases.

OUTPUT_DIR: {OUT}

## Task A — Deferred improvements

Run: fd deferred.md notes/pr-reviews/

If any files are found: read each one. Extract items as a bulleted list.
If none found: write "None found."

## Task B — Known failure modes from prior fix plans

Run: fd fix-plan.toml notes/pr-reviews/ | head -3

If any files are found: read each one. Identify recurring issue categories among these patterns:
- Missing pub mod declarations
- Missing pub use re-exports
- Incomplete consumer updates
- Stale imports after refactoring
- Cross-module integration failures
- Other patterns you see repeated

If none found: write "None found."

## Output

Write {OUT}/deferred-and-patterns.md:

  ## Deferred Improvements
  [bulleted list, or "None found"]

  ## Known Failure Modes
  [bulleted list of recurring categories, or "None found"]

When done, respond with EXACTLY:
RESULT: deferred-and-patterns.md saved. Deferred items: N. Failure modes identified: M.
```

Record the result.

### Step 2: Explore codebase state

Spawn a `rust-development-pipeline:strict-code-reviewer` subagent with this exact prompt:

```
Your job: read the plan file, identify all source files it mentions, and record the current state of those files.

PLAN_FILE: {PLAN_FILE}
OUTPUT_DIR: {OUT}

## Task A — Read the plan

Read {PLAN_FILE} in full.

## Task B — Identify files mentioned in the plan

Extract every source file path, module name, type name, or function name mentioned in the plan.
For each, locate the relevant source file (use fd or Glob if needed).
Focus ONLY on files mentioned in the plan — do not explore the whole codebase.

## Task C — Record current state per file

For each relevant source file found:
1. Read the file
2. Record:
   - File path
   - Public types (structs, enums, traits) and their fields/variants
   - Public function signatures (name, parameters, return type)
   - Module structure (pub mod, pub use declarations)
   - Relationship to the plan: what the plan says to do here vs what currently exists

## Output

Write {OUT}/codebase-state.md. Format per file:

  ## File: path/to/file.rs

  ### Public API
  - pub struct Foo { field: Type }
  - pub fn bar(x: Type) -> Result<Out, Err>
  - (etc.)

  ### Module wiring
  - pub mod declarations present: [list or "none"]
  - pub use re-exports present: [list or "none"]

  ### Plan relationship
  - Plan says: [what the plan intends for this file]
  - Current state: [brief description of what exists]
  - Gap: [what needs to be added or changed]

When done, respond with EXACTLY:
RESULT: codebase-state.md saved. Files documented: N. Files mentioned in plan but not found: [list or "none"].
```

Record the result.

### Step 3: Draft elaboration

Spawn a `rust-development-pipeline:rust-architect` subagent with this exact prompt:

```
Your job: read the plan and codebase state, then produce a concrete elaboration of underspecified details.

FILES TO READ (read these now, do not read anything else):
  {PLAN_FILE}
  {OUT}/codebase-state.md
  {OUT}/deferred-and-patterns.md

## Rules

- Base all proposals on existing patterns found in codebase-state.md. Do not invent new patterns.
- Do not decompose into tasks yet — produce a narrative elaboration only.
- Flag anything uncertain explicitly.

## For each underspecified item in the plan, write:

  ## Item: [plan item description]

  **Proposed type signature:**
  pub fn foo(x: ExistingType) -> Result<NewType, ExistingError>

  **Module placement:** path/to/module.rs

  **Error handling strategy:** [e.g., "add variant X to existing ErrorKind enum"]

  **Ownership/lifetime notes:** [concern if any, or "None"]

  **Trait coherence notes:** [concern if any, or "None"]

Also add a section for deferred items:

  ## Deferred Items Assessment
  [For each item in deferred-and-patterns.md: is it directly relevant now? Should it be absorbed?]
  - [item]: [Absorb — reason] OR [Skip — not applicable yet]

## Output

Write {OUT}/draft-elaboration.md

When done, respond with EXACTLY:
RESULT: draft-elaboration.md saved. Items elaborated: N. Deferred items absorbed: M. Confidence notes: [brief — or "None"].
```

Record the result.

### Step 4: Draft TOML plan

Spawn a `rust-development-pipeline:plan-decomposer` subagent with this exact prompt:

```
Your job: read the elaboration and produce a TOML implementation plan with exact before/after blocks.

FILES TO READ (read these now):
  {OUT}/draft-elaboration.md
  {OUT}/codebase-state.md

For before/after blocks, you will also need to read actual source files.
Use Read tool or: git show HEAD:path/to/file.rs

## Critical rules for before blocks

The "before" field MUST be an exact verbatim substring of the target file.
- Copy text character-for-character. No paraphrasing. No "...".
- Include enough surrounding lines to uniquely identify the location.
- After writing each before block, self-check: rg -F "first 20 chars of before" path/to/file.rs
  If grep fails: the before is wrong. Re-read the file and fix it.

## Module wiring rules (check each new file)

For every task that creates a new .rs file:
- The task MUST include a [[changes]] entry adding pub mod <name>; to the parent lib.rs or mod.rs
- If the new file defines public types for use in other crates: the task MUST include a [[changes]] entry adding pub use <type>; at the crate root
- If the plan says "update Y to use X": consumer-side changes go in the SAME task as the definition

## TOML format

  [meta]
  title = "Phase X.Y: <Phase Name>"
  source_branch = "<current branch>"
  created = "<YYYY-MM-DD>"

  [dependencies]
  # TASK-N = ["TASK-M"]  — omit section if all tasks are independent

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
  exact verbatim content from source file
  '''
  after = '''
  exact replacement content
  '''

For multiple changes in one task (multiple files or multiple locations), use multiple [[tasks.TASK-N.changes]] entries, each with its own file field.

## Output

Write {OUT}/draft-plan.toml

When done, respond with EXACTLY:
RESULT: draft-plan.toml saved. Tasks: N. Before-block verification: M/N confirmed. Unverified: [list TASK IDs or "none"].
```

Record the result.

### Step 5: Per-task self-check

Spawn a `rust-development-pipeline:impl-plan-reviewer` subagent with this exact prompt:

```
Your job: read the draft TOML plan and verify each task against the module wiring checklist.

FILES TO READ (read these now):
  {OUT}/draft-plan.toml
  {OUT}/codebase-state.md

For before-block verification, you may also read source files as needed.

## For each task, write a checklist entry:

  ## TASK-N: [description]

  Module wiring check (if this task creates a new .rs file):
  - pub mod in parent: [Yes / No / Not applicable]
  - pub use re-export: [Yes / No / Not applicable]
  - Consumer updates co-located: [Yes / No / Not applicable]

  Known failure mode check:
  - Missing pub mod risk: [Low / Medium / High — reason]
  - Missing pub use risk: [Low / Medium / High — reason]
  - Stale import risk: [Low / Medium / High — reason]

  Before-block check:
  - Grep confirmed: [Yes / No / Unverified]
  - Acceptance commands present: [Yes / No]

  Depends on: [TASK-X, TASK-Y / None]

  Notes: [anything uncertain or flagged for the judge session]

## Output

Write {OUT}/task-checklist.md

When done, respond with EXACTLY:
RESULT: task-checklist.md saved. Tasks checked: N. Wiring issues flagged: M. Before-block unverified: K.
```

Record the result.

### Step 6: Write gather summary

Using only the RESULT strings collected from Steps 1–5 (do not read any files), write `notes/plan-enrichment/{slug}/gather-summary.md`:

```
## Gather Summary: {PLAN_SLUG}

**Tasks created:** [from Step 4 result]
**Dependency chain:** [from Step 4 — or "not extracted, see draft-plan.toml"]
**Deferred items absorbed:** [from Step 3 result]

**Gather completeness:**
- [x/o] deferred-and-patterns.md — [saved / missing]
- [x/o] codebase-state.md — [saved / missing] — Files documented: N
- [x/o] draft-elaboration.md — [saved / missing]
- [x/o] draft-plan.toml — [saved / missing]
- [x/o] task-checklist.md — [saved / missing]

**Before-block verification:** [M/N confirmed from Step 4]
**Unverified tasks:** [list from Step 4, or "none"]
**Wiring issues flagged:** [from Step 5]

**Confidence notes:**
[Summarize confidence notes from Step 3 result — or "None flagged"]

**Questions for user:**
[Any questions raised — or "None"]
```

---

## Boundaries

**Orchestrator will:**
- Stay out of file contents — only read the first 10 lines of the plan file in Step 0
- Launch one subagent per step, sequentially (each depends on prior outputs)
- Write gather-summary.md itself from collected RESULT strings only

**Orchestrator will not:**
- Read the full plan file, codebase-state.md, draft-elaboration.md, or draft-plan.toml itself
- Accumulate source file contents in its own context
- Skip a step if a prior step failed — proceed with a note in the summary

**Subagents will:**
- Read only the files explicitly listed in their prompt
- Write exactly one output file per subagent
- End their response with a RESULT: line in the exact format specified
