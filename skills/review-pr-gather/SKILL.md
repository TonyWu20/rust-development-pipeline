---
name: review-pr-gather
description: Session 1 of the split PR review pipeline. Run this in a local model session to gather information, produce a draft review, and write structured output files for the judge session. Triggered by /review-pr-gather [branch-name].
version: 0.2.0
---

# PR Review — Gather (Local Model Session)

Orchestrates a sequence of focused subagents to gather PR review data and produce draft output files. Each subagent handles one concern in isolation — the orchestrator only coordinates and never accumulates file contents in its own context.

Output is saved to `notes/pr-reviews/{branch}/` for review by the user before the judge session.

## Trigger

`/review-pr-gather [branch-name]`

If no branch is given, use the current branch compared against `main`.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Orchestrator Role

You are the orchestrator. Your context must stay clean. You do **not** read source files, diffs, or output files yourself. You launch subagents, receive their short result summaries, and pass those summaries forward to the next subagent or to the final gather-summary.

## Process

### Step 0: Resolve branch and prepare output directory

Determine the branch name (from argument or `git branch --show-current`). Set:
```
BRANCH={branch}
OUT=notes/pr-reviews/{branch}
```

Create the output directory if it does not exist:
```bash
mkdir -p notes/pr-reviews/{branch}
```

### Step 1: Collect raw data and per-file analysis

Spawn a general-purpose subagent with this exact prompt:

```
Your job: collect PR diff data and analyze each changed file. Save two output files.

BRANCH: {BRANCH}
OUTPUT_DIR: {OUT}

## Task A — Collect raw data

Run these commands and write all output to {OUT}/raw-diff.md:

  git fetch origin
  git log --oneline main..{BRANCH}
  git diff main...{BRANCH} --stat
  git diff main...{BRANCH}

Then read each file listed in the diff stat in full. Append to {OUT}/raw-diff.md with one section per file:

  ## File: path/to/file.rs
  [full file contents]

## Task B — Per-file analysis

For each changed file, write a checklist entry to {OUT}/per-file-analysis.md. Do not make architectural judgments — record observations only.

Format per file:

  ## File: path/to/file.rs

  Intent: [one sentence on what changed, based on the diff]

  Checklist:
  - Unnecessary clone/unwrap/expect? [Yes: cite location / No]
  - Error handling: meaningful types or stringly-typed? [observation]
  - Dead code or unused imports? [Yes / No]
  - New public API: tests present? [Yes / No / Not applicable]
  - Change appears within plan scope? [Yes / No / Unclear — no plan available yet]

  Notes: [other observations — no classifications, just facts]

When both files are saved, respond with EXACTLY this format (fill in the values):
RESULT: raw-diff.md saved. N files changed: [comma-separated list of file paths]. per-file-analysis.md saved.
```

Record the result. The file list from this result is needed for Step 3.

### Step 2: Load context

Spawn a general-purpose subagent with this exact prompt:

```
Your job: load project context and save it to one output file.

BRANCH: {BRANCH}
OUTPUT_DIR: {OUT}

## Task A — Project memory

Derive the memory directory:
  MEMORY_DIR="$HOME/.claude/projects/$(pwd | sd '/' '-')/memory"

Read $MEMORY_DIR/MEMORY.md. If it exists, read every memory file linked in the index.
If the directory is missing or empty: note "No project memory available."

## Task B — Phase plan

Locate the plan for this branch. Try in order:
1. Parse branch name for a phase number N. Search: fd -e md -e toml . plans/ | rg -i 'phase.?N'
2. If plans/ has exactly one file: use it.
3. If notes/plan-reviews/decisions.md exists: check it for a plan path.
4. If none found: note "No phase plan found — scope gating disabled. All issues treated as [Correctness]."

Read the plan file if found.

## Task C — Snapshot

Check if {OUT}/status.md exists. If it does: read it (this is the branch snapshot).
If it does not exist: note "No snapshot — using raw diff from raw-diff.md."

## Output

Write {OUT}/context.md with this structure:

  ## Memory
  [memory file contents, or "No project memory available"]

  ## Phase Plan
  [plan file contents, or "No phase plan found — scope gating disabled"]

  ## Snapshot
  [snapshot contents, or "No snapshot — using raw diff from raw-diff.md"]

When done, respond with EXACTLY:
RESULT: context.md saved. Plan: [found at path / not found]. Snapshot: [found / not found].
```

Record the result.

### Step 3: Draft 4-axis review

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read two already-saved files and produce a draft 4-axis PR review.

FILES TO READ (read these now, do not read anything else):
  {OUT}/context.md
  {OUT}/per-file-analysis.md

BRANCH: {BRANCH}

## Classification rules

Each issue found across ALL axes must be classified as exactly one of:
  [Defect]      — code does not implement what the plan commissioned
  [Correctness] — incorrect behavior independent of the plan (bug, data race)
  [Improvement] — better design but outside plan scope

If the context.md says "No phase plan found": classify ALL issues as [Correctness].

## Four axes to evaluate

A. Plan & Spec Fulfillment
   - Does the code implement what the plan requires?
   - Missing pieces from the stated goal?
   - Out-of-scope additions?

B. Architecture Compliance
   - DAG-centric design preserved?
   - Functional style: iterators over mut Vec, no unnecessary mutation?
   - JobId newtype pattern used where applicable?
   - Async-first with tokio? Sync-over-async bridge only where justified?
   - Crate boundaries respected (workflow_core, workflow_utils, castep_adapter)?

C. Rust Style & Quality
   - Unnecessary clone/unwrap/expect without comment?
   - Error types meaningful (not stringly-typed)?
   - Dead code, unused imports, commented-out blocks?
   - Builder pattern used for complex structs?

D. Test Coverage
   - New public APIs have tests?
   - Integration tests for non-trivial behavior?

## Output format

Write {OUT}/draft-review.md with this structure:

  ## Draft PR Review: `{BRANCH}` → `main`

  **Rating:** [Approve / Request Changes / Reject]

  **Summary:** [2–3 sentences]

  **Axis Scores:**
  - Plan & Spec: [Pass/Partial/Fail] — [one-line reason]
  - Architecture: [Pass/Partial/Fail] — [one-line reason]
  - Rust Style: [Pass/Partial/Fail] — [one-line reason]
  - Test Coverage: [Pass/Partial/Fail] — [one-line reason]

  **Issues Found:**
  - [Defect] Title — file: path/to/file.rs — brief description
  - [Correctness] Title — file: path/to/file.rs — brief description
  - [Improvement] Title — file: path/to/file.rs — brief description

When done, respond with EXACTLY:
RESULT: draft-review.md saved. Issues: [Defect]=X [Correctness]=Y [Improvement]=Z. Rating: [value].
```

Record the result. Extract the issue counts and rating for the final summary.

### Step 4: Draft fix document

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the draft review and produce a draft fix document.

FILE TO READ (read this now, do not read anything else):
  {OUT}/draft-review.md

## Rules

Only include [Defect] and [Correctness] issues. Do NOT include [Improvement] issues.
If there are no [Defect] or [Correctness] issues: write "No fixes required."

## Output format

Write {OUT}/draft-fix-document.md:

  ## Draft Fix Document

  ### Issue N: [Short title]

  **Classification:** [Defect / Correctness]
  **File:** `path/to/file.rs`
  **Severity:** [Blocking / Major / Minor]
  **Problem:** [What is wrong and why it matters]
  **Fix:** [Concrete instruction — what to change, with code snippet if helpful]

Repeat the Issue block for each [Defect] and [Correctness] issue. Use sequential N starting from 1.

When done, respond with EXACTLY:
RESULT: draft-fix-document.md saved. Fix issues written: N.
```

Record the result.

### Step 5: Draft fix-plan.toml

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the fix document and produce a draft TOML fix plan with exact before/after blocks.

FILES TO READ (read these now):
  {OUT}/draft-fix-document.md

For each issue in the fix document, you will also need to read the actual source file to get exact content.
Use: git show {BRANCH}:path/to/file.rs

BRANCH: {BRANCH}

## Critical rules for before blocks

The "before" field MUST be an exact verbatim substring of the target file.
- Copy text character-for-character from the file. No paraphrasing. No "...".
- Include enough surrounding lines so the block uniquely identifies the location.
- After writing each before block, self-check: rg -F "first 20 chars of before" path/to/file.rs
  If grep fails: the before is wrong. Re-read the file and fix it.

## TOML format

  [tasks.TASK-N]
  description = "Short description"
  type = "replace"
  acceptance = ["cargo check -p crate_name", "cargo test -p crate_name"]

  [[tasks.TASK-N.changes]]
  file = "relative/path/from/root.rs"
  before = '''
  exact verbatim content from source file
  '''
  after = '''
  exact replacement content
  '''

If multiple changes for the same task (e.g., two locations in one file, or two files), use multiple [[tasks.TASK-N.changes]] entries.

Add a [dependencies] table if any task must come before another:
  [dependencies]
  TASK-2 = ["TASK-1"]

If there are no fix issues: write:
  # No fix tasks — PR approved without fixes

## Output

Write {OUT}/draft-fix-plan.toml

When done, respond with EXACTLY:
RESULT: draft-fix-plan.toml saved. Tasks written: N. Before-block verification: M/N confirmed. Unverified: [list task IDs or "none"].
```

Record the result. Extract the verification ratio and unverified task IDs.

### Step 6: Write gather summary

Using only the RESULT strings collected from Steps 1–5 (do not read any files), write `notes/pr-reviews/{branch}/gather-summary.md`:

```
## Gather Summary: `{BRANCH}`

**Files analyzed:** [from Step 1 result]
**Issues found:** [Defect]=X [Correctness]=Y [Improvement]=Z (from Step 3 result)
**Draft rating:** [from Step 3 result]

**Gather completeness:**
- [x/o] raw-diff.md — [created / missing]
- [x/o] context.md — [created / missing] — Plan: [found/not found], Snapshot: [found/not found]
- [x/o] per-file-analysis.md — [created / missing]
- [x/o] draft-review.md — [created / missing]
- [x/o] draft-fix-document.md — [created / missing]
- [x/o] draft-fix-plan.toml — [created / missing]

**Before-block verification:** [M/N confirmed] (from Step 5 result)
**Unverified before blocks:** [list from Step 5 result, or "none"]

**Confidence notes:**
[Summarize any uncertainty flagged in Step results — or "No issues flagged"]

**Questions for user:**
[Any questions raised by subagents — or "None"]
```

---

## Boundaries

**Orchestrator will:**
- Stay out of file contents — only read RESULT strings from subagents
- Launch one subagent per step, sequentially (each step feeds the next)
- Write gather-summary.md itself from the collected RESULT strings

**Orchestrator will not:**
- Read raw-diff.md, context.md, or any output file itself
- Accumulate file contents in its own context
- Skip a step if a prior step failed — launch the next step with a note about the failure

**Subagents will:**
- Read only the files explicitly listed in their prompt
- Write exactly one output file per subagent (except Step 1 which writes two)
- End their response with a RESULT: line in the exact format specified
