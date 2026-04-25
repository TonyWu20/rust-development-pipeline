---
name: review-pr-gather
description: Session 1 of the split PR review pipeline. Run this in a local model session to gather information, produce a draft review, and write structured output files for the judge session. Triggered by /review-pr-gather [branch-name].
version: 0.3.0
---

# PR Review — Gather (Local Model Session)

Orchestrates a sequence of focused subagents to gather PR review data and produce draft output files. Each subagent handles one concern in isolation — the orchestrator only coordinates and never accumulates file contents in its own context.

Fact-gathering (diff data, file contents, trailing newlines) is handled by a **deterministic script** (`gather-diff-data.py`). The script's output is the authoritative source of truth — LLM subagents make judgments on top of these facts but must not contradict them.

Output is saved to `notes/pr-reviews/{branch}/` for review by the user before the judge session.

## Prerequisites

- `uv` (Python package manager) — used to run all Python scripts
- `python3` — managed by `uv`

## Trigger

`/review-pr-gather [branch-name]`

If no branch is given, use the current branch compared against `main`.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Orchestrator Role

You are the orchestrator. Your context must stay clean. You do **not** read source files, diffs, or output files yourself. You launch subagents, receive their short result summaries, and pass those summaries forward to the next subagent or to the final gather-summary.

**New: validation gates.** After each subagent step, run a validation script before accepting the result. If validation fails, re-launch the step with the validation errors appended to the prompt. Never skip validation or add context you don't need — just pass the script's output to a retry.

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

### Step 1: Collect authoritative diff data

Run the deterministic data collector script:

```bash
uv run scripts/gather-diff-data.py --branch {BRANCH} --output {OUT}
```

This produces two files:
- `{OUT}/raw-diff.md` — git log, diff stat, full diff, and full file contents
- `{OUT}/file-manifest.json` — structured machine-readable facts per file (paths, line counts, trailing newline status, function signatures, imports)

Record the result. Extract the file list from the script's output for Step 3.

### Step 2: Per-file analysis (LLM judgment)

Spawn a `rust-development-pipeline:strict-code-reviewer` subagent with this exact prompt:

```
Your job: read the authoritative diff data and produce per-file judgment analysis.

FILES TO READ (read these now, do not read anything else):
  {OUT}/raw-diff.md
  {OUT}/file-manifest.json

## Important: Facts vs Judgment

The file-manifest.json is the AUTHORITATIVE source for factual data (file paths,
trailing newlines, line counts, function signatures).  Do NOT contradict facts
in the manifest — they are ground truth.

Your role is to add JUDGMENT: code review observations that require human
expertise.  Record observations only — do not classify issues yet.

## Per-file checklist

For each changed file, write an entry to {OUT}/per-file-analysis.md:

  ## File: path/to/file.rs

  Intent: [one sentence on what changed, based on the diff]

  Checklist:
  - Unnecessary clone/unwrap/expect? [Yes: cite location / No]
  - Error handling: meaningful types or stringly-typed? [observation]
  - Dead code or unused imports? [Yes / No]
  - New public API: tests present? [Yes / No / Not applicable]
  - Change appears within plan scope? [Yes / No / Unclear — no plan available yet]

  Notes: [other observations — no classifications, just facts]

When done, respond with EXACTLY this format (fill in the values):
RESULT: per-file-analysis.md saved. N files analyzed. Files: [comma-separated list of file paths].
```

Record the result. The file list from this result is needed for Step 4.

### Step 3: Load context

Spawn a general-purpose subagent with this exact prompt (no specialized agent exists for context loading):

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
If it does not exist: note "No snapshot — using authoritative data from file-manifest.json."

## Output

Write {OUT}/context.md with this structure:

  ## Memory
  [memory file contents, or "No project memory available"]

  ## Phase Plan
  [plan file contents, or "No phase plan found — scope gating disabled"]

  ## Snapshot
  [snapshot contents, or "No snapshot — using authoritative data from file-manifest.json"]

When done, respond with EXACTLY:
RESULT: context.md saved. Plan: [found at path / not found]. Snapshot: [found / not found].
```

Record the result.

### Step 4: Draft 4-axis review

Spawn a `rust-development-pipeline:strict-code-reviewer` subagent with this exact prompt:

```
Your job: read the authoritative facts and per-file analysis, then produce a draft 4-axis PR review.

FILES TO READ (read these now, do not read anything else):
  {OUT}/context.md
  {OUT}/per-file-analysis.md
  {OUT}/file-manifest.json

BRANCH: {BRANCH}

## Important: The manifest is authoritative

The file-manifest.json contains ground-truth facts (trailing newlines, file paths,
function signatures).  Do NOT make factual claims that contradict the manifest.
If the manifest says a file is missing a trailing newline, do not claim it "was
verified via hex dump" — you did not run hex dump.  Stick to the facts in the
manifest.

## Classification rules

Each issue found across ALL axes must be classified as exactly one of:
  [Defect]      — code does not implement what the plan commissioned
  [Correctness] — incorrect behavior independent of the plan (bug, data race, breaking state change)
  [Improvement] — better design but outside plan scope

If the context.md says "No phase plan found": classify ALL issues as [Correctness].

**Classification guidance**: A change that breaks persistent state (files,
identifiers, serialized data, task IDs) is at minimum [Correctness], never
[Improvement].  Breaking existing identifiers silently changes behaviour and
is not a style suggestion.

## Self-consistency rule

Before writing draft-review.md, cross-check: does any claim in your review
contradict the observations in per-file-analysis.md or the facts in
file-manifest.json?  If yes, resolve the contradiction first.  A review that
contradicts its own analysis document undermines credibility.

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

  ## Draft PR Review: `{BRANCH}` -> `main`

  **Rating:** [Approve / Request Changes / Reject]

  **Summary:** [2-3 sentences]

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

#### Validation gate (Step 4)

After the subagent returns RESULT, run the consistency checker:

```bash
uv run scripts/validate/validate-review-consistency.py {OUT}/draft-review.md {OUT}/file-manifest.json
```

If exit 0: proceed to Step 5.
If exit != 0: the validator found contradictions. Re-launch Step 4 (same prompt, but append the validator's stderr as additional context). Maximum retries: 2.

### Step 5: Draft fix document

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the draft review and produce a draft fix document.

FILE TO READ (read this now, do not read anything else):
  {OUT}/draft-review.md

## Rules

Only include [Defect] and [Correctness] issues. Do NOT include [Improvement] issues.
If there are no [Defect] or [Correctness] issues: write "No fixes required."

**Scope rule**: Every issue MUST be about the PR code — something wrong in the
source files, tests, or build configuration.  Do NOT include meta-issues about
the review process, the gather document, or the analysis itself.  A fix document
describes what to fix in the code, not what to fix in the review process.

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

#### Validation gate (Step 5)

After the subagent returns RESULT, run the fix document validator:

```bash
uv run scripts/validate/validate-fix-document.py {OUT}/draft-fix-document.md --manifest {OUT}/file-manifest.json
```

If exit 0: proceed to Step 6.
If exit != 0: re-launch Step 5 with validator errors as additional context. Maximum retries: 2.

### Step 6: Draft fix-plan.toml

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the fix document and produce a draft TOML fix plan with exact before/after blocks.

FILES TO READ (read these now):
  {OUT}/draft-fix-document.md

Before writing any TOML, read the canonical spec:
  skills/compile-plan/references/compilable-plan-spec.md

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

Refer to the compilable-plan-spec.md for the canonical format.  Key rules:
  - Valid types: "replace", "create", "delete" only — do not invent others
  - Every task must have "acceptance" commands
  - File paths are relative from project root

  [tasks.TASK-N]
  description = "Short description"
  type = "replace"
  acceptance = ["cargo check -p crate_name", "cargo test -p crate_name"]

  [[tasks.TASK-N.changes]]
  file = "relative/path/from/root.rs"
  before = """
  exact verbatim content from source file
  """
  after = """
  exact replacement content
  """

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

#### Validation gate (Step 6)

After the subagent returns RESULT, run the TOML plan validator:

```bash
uv run scripts/validate/validate-toml-plan.py {OUT}/draft-fix-plan.toml --manifest {OUT}/file-manifest.json
```

If exit 0: proceed to Step 7.
If exit != 0: re-launch Step 6 with validator errors as additional context. Maximum retries: 2.

### Step 7: Write gather summary

Using only the RESULT strings collected from Steps 1-6 (do not read any files), write `notes/pr-reviews/{branch}/gather-summary.md`:

```
## Gather Summary: `{BRANCH}`

**Files analyzed:** [from Step 1 or Step 2 result]
**Issues found:** [Defect]=X [Correctness]=Y [Improvement]=Z (from Step 4 result)
**Draft rating:** [from Step 4 result]

**Gather completeness:**
- [x/o] raw-diff.md + file-manifest.json
- [x/o] context.md — [created / missing] — Plan: [found/not found], Snapshot: [found/not found]
- [x/o] per-file-analysis.md — [created / missing]
- [x/o] draft-review.md — [created / missing]
- [x/o] draft-fix-document.md — [created / missing]
- [x/o] draft-fix-plan.toml — [created / missing]

**Before-block verification:** [M/N confirmed] (from Step 6 result)
**Unverified before blocks:** [list from Step 6 result, or "none"]

**Validation gates:**
- review consistency: [PASS / FAIL (N retries)]
- fix document validation: [PASS / FAIL (N retries)]
- toml plan validation: [PASS / FAIL (N retries)]

**Confidence notes:**
[Summarize any uncertainty flagged in Step results — or "No issues flagged"]

**Questions for user:**
[Any questions raised by subagents — or "None"]
```

---

## Boundaries

**Orchestrator will:**
- Stay out of file contents — only read RESULT strings from subagents and exit codes from validators
- Launch one subagent per step, sequentially (each step feeds the next)
- Run validation scripts after Steps 4, 5, 6 and retry on failure
- Write gather-summary.md itself from the collected RESULT strings

**Orchestrator will not:**
- Read raw-diff.md, context.md, or any output file itself
- Accumulate file contents in its own context
- Skip a step if a prior step failed — launch the next step with a note about the failure

**Subagents will:**
- Read only the files explicitly listed in their prompt
- Write exactly one output file per subagent (except Step 1 script)
- End their response with a RESULT: line in the exact format specified
