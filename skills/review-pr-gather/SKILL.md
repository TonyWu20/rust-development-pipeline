---
name: review-pr-gather
description: Session 1 of the split PR review pipeline. Run this in a local model session to gather information, produce a draft review, and write structured output files for the judge session. Triggered by /review-pr-gather [branch-name].
version: 0.4.0
---

# PR Review — Gather (Local Model Session)

Orchestrates a sequence of focused subagents to gather PR review data and produce draft output files. Each subagent handles one concern in isolation — the orchestrator only coordinates and never accumulates file contents in its own context.

Fact-gathering (diff data, file contents, trailing newlines) is handled by a **deterministic script** (`gather-diff-data.py`). The script's output is the authoritative source of truth — LLM subagents make judgments on top of these facts but must not contradict them.

The script also generates a **pre-populated per-file analysis template** (`per-file-analysis-template.md`) that renders manifest facts inline as an immutable table. The Step 2 subagent fills in only judgment fields on top of this template — structurally preventing factual hallucination.

After the draft review subagent writes its output, an **isolated cross-reference validator** checks the review's claims against the source documents (per-file-analysis, manifest, context) and catches contradictions before they reach the judge session.

Output is saved to `notes/pr-reviews/{branch}/` for review by the user before the judge session.

## Prerequisites

- `uv` (Python package manager) — used to run all Python scripts
- `python3` — managed by `uv`

## Trigger

`/review-pr-gather [branch-name]`

If no branch is given, use the current branch compared against `main`.

## Plugin Root Resolution

All script paths in this skill (e.g., `scripts/gather-diff-data.py`, `scripts/validate/...`) are relative to the **plugin root**. Resolve it dynamically — never hardcode or guess the path:

```bash
uv run python -c "
import json; from pathlib import Path
p = Path.home() / '.claude/plugins/installed_plugins.json'
data = json.loads(p.read_text())
for key in ['rust-development-pipeline@my-claude-marketplace', 'rust-development-pipeline@local']:
    if key in data['plugins']:
        print(data['plugins'][key][0]['installPath']); break
"
```

If the command prints nothing, the plugin is not registered — stop immediately and report: "Plugin root could not be resolved from installed_plugins.json." Do not guess or construct the path manually.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Orchestrator Role

You are the orchestrator. Your context must stay clean. You do **not** read source files, diffs, or output files yourself. You launch subagents, receive their short result summaries, and pass those summaries forward to the next subagent or to the final gather-summary.

**New in v0.4.0: Two-layer validation.** After each subagent step, run a validation layer before accepting the result:

1. **LLM validator gates** (Steps 4b, 5, 6): A separate subagent reads the output and source documents fresh, catching semantic contradictions and reasoning errors. Agent isolation means the validator doesn't inherit the writer's hallucinations.
2. **Python script gates** (Steps 4b→check, 5, 6): Deterministic scripts check format, types, file paths, trailing newline consistency, and before-block accuracy.

If any gate fails, re-launch the step with the validator's findings appended to the prompt. Never skip validation or add context you don't need — just pass the script's output to a retry.

## Process

### Step 0: Resolve plugin root, branch, and output directory

**Resolve `<plugin-root>` first.** Run the following command once and record the printed path — use it as the literal value everywhere `<plugin-root>` appears below:

```bash
uv run python -c "
import json; from pathlib import Path
p = Path.home() / '.claude/plugins/installed_plugins.json'
data = json.loads(p.read_text())
for key in ['rust-development-pipeline@my-claude-marketplace', 'rust-development-pipeline@local']:
    if key in data['plugins']:
        print(data['plugins'][key][0]['installPath']); break
"
```

If the command prints nothing, the plugin is not registered — stop immediately and report: "Plugin root could not be resolved from installed_plugins.json." Do not guess or construct the path manually.

Then determine the branch name (from argument or `git branch --show-current`). Record the printed path from above as `<plugin-root>` and use it as the literal value in every command below. Set:
```
BRANCH={branch}
OUT=notes/pr-reviews/{branch}
```

Create the output directory if it does not exist:
```bash
mkdir -p notes/pr-reviews/{branch}
```

### Step 1: Collect authoritative diff data + generate analysis template

Run the deterministic data collector script with the `--template` flag:

```bash
uv run <plugin-root>/scripts/gather-diff-data.py --branch <branch> --output <out> --template
```

The `--template` flag also generates `per-file-analysis-template.md` with manifest facts pre-rendered as immutable tables. The Step 2 subagent fills in judgment fields on top of these facts — this structurally prevents hallucination of factual claims.

This produces three files:
- `<out>/raw-diff.md` — git log, diff stat, full diff, and full file contents
- `<out>/file-manifest.json` — structured machine-readable facts per file (paths, line counts, trailing newline status, function signatures, imports)
- `<out>/per-file-analysis-template.md` — per-file template with pre-filled Facts table and Fill In sections for Intent, Checklist, Notes

Record the result. Extract the file list from the script's output for Step 3.

### Step 1.5: Audit prior fix-plan application

If a prior fix-plan exists at `<out>/fix-plan.toml`, audit whether its tasks were actually applied. This catches the pattern where fixes from a prior round were planned but never executed:

```bash
uv run <plugin-root>/scripts/validate/validate-fix-plan-application.py \
    --fix-plan <out>/fix-plan.toml \
    --workspace .
```

The script parses every `before` block in the committed fix-plan and runs `rg -F` with the full block content against its target file.

- If the full `before` block is still found in the source → the fix was NOT applied → flagged as unapplied
- If the `before` block is NOT found → the fix was applied → OK
- If `<out>/fix-plan.toml` does not exist → nothing to audit → OK

**Exit 0:** All applied (or no fix-plan). Proceed to Step 2.

**Exit 1:** Unapplied tasks found. Record the audit result — it feeds into Step 4a as additional context for the draft review, so unapplied prior tasks are re-flagged as current issues.

Record the result for the gather-summary:
```
RESULT: fix-plan audit: [all applied / N unapplied tasks found].
```
If unapplied tasks were found, append:
```
Unapplied tasks: [task IDs and files]
```

### Step 2: Per-file analysis (LLM judgment — uses pre-populated template)

Spawn a `rust-development-pipeline:strict-code-reviewer` subagent with this exact prompt:

```
Your job: read the authoritative diff data and the pre-populated analysis template,
then fill in the judgment fields to produce the per-file analysis.

FILES TO READ (read these now, do not read anything else):
  <out>/raw-diff.md
  <out>/per-file-analysis-template.md

## Important: Facts vs Judgment

The per-file-analysis-template.md contains a ### Facts table per file with
manifest-derived data (line counts, trailing newline, functions, imports).
These facts are AUTHORITATIVE and IMMUTABLE — do not modify them.

Your role is to add JUDGMENT: code review observations that require human
expertise.  Fill in the ### Intent, ### Checklist, and ### Notes sections
for each file.  Do NOT write new ## File: sections — use the ones already
in the template.

## Per-file checklist

For each file in the template, fill in the checklist:

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

BRANCH: <branch>
OUTPUT_DIR: <out>

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

Check if <out>/status.md exists. If it does: read it (this is the branch snapshot).
If it does not exist: note "No snapshot — using authoritative data from file-manifest.json."

## Output

Write <out>/context.md with this structure:

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

### Step 4a: Draft 4-axis review with externalized cross-reference

Spawn a `rust-development-pipeline:strict-code-reviewer` subagent with this exact prompt:

```
Your job: read the per-file analysis, manifest, and context — then produce a
cross-reference document (cross-reference.md) and a draft 4-axis PR review
(draft-review.md).

FILES TO READ (read these now, do not read anything else):
  <out>/context.md
  <out>/per-file-analysis.md
  <out>/file-manifest.json

BRANCH: <branch>

[If the fix-plan audit (Step 1.5) found unapplied tasks, include this line:]
[PRIOR UNAPPLIED TASKS: <details from Step 1.5> — re-flag these as current issues.]

## Required: Externalized cross-reference

Before writing draft-review.md, you MUST write cross-reference.md documenting
how each planned issue was validated against source documents.

## Cross-reference format

Write <out>/cross-reference.md:

  ## Cross-Reference: Draft Review Issues for `<branch>`

  ### Review Framing Decision
  - Context snapshot: [found / not found]
  - Prior fix round: [date / none]
  - Framing: [first review / re-review round N]
  - Rating rationale: [why Approve/Changes/Reject given the framing]

  ### Per-Issue Cross-Reference

  For each issue you considered (including those you dropped):
  #### Issue N: [Classification] Title
  - File: `path/to/file.rs`
  - Claim: [what the review asserts is wrong]
  - Per-file analysis Checklist check: [category → answer]
  - Manifest fact check: [property → value]
  - Context snapshot check: [already resolved? yes/no]
  - Verdict: [CONSISTENT / CONTRADICTION → DROPPED]
  - Action: [Included in draft-review.md / Dropped]

Every issue you considered MUST get an entry — including DROPPED issues.
If no issues were found, write "# No issues found — cross-reference empty."

### Cross-reference procedure

For each issue you plan to flag in draft-review.md:
1. Find the same file in per-file-analysis.md
2. Check the Checklist section for that file
3. If the Checklist says "No" for the category you're about to flag (e.g.,
   "Dead code: No" when you're about to flag dead code) → DROP the issue.
   The per-file analysis already confirmed it's clean.
4. Check the Facts table in the template (or file-manifest.json):
   If the manifest says something different from what you're about to claim
   (e.g., Trailing newline: NO when you think it's present) → DROP the claim.
5. Check context.md → Snapshot: if a prior fix round resolved this issue,
   do NOT re-flag it. Frame as re-review.
6. Check context.md → Phase Plan: if no plan found, classify ALL issues as [Correctness].

### Classification rules

Each issue found across ALL axes must be classified as exactly one of:
  [Defect]      — code does not implement what the plan commissioned
  [Correctness] — incorrect behavior independent of the plan (bug, data race, breaking state change)
  [Improvement] — better design but outside plan scope

If the context.md says "No phase plan found": classify ALL issues as [Correctness].

**Classification guidance**: A change that breaks persistent state (files,
identifiers, serialized data, task IDs) is at minimum [Correctness], never
[Improvement].  Breaking existing identifiers silently changes behaviour and
is not a style suggestion.

### Four axes to evaluate

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

## Draft review output format

Write <out>/draft-review.md with this structure:

  ## Draft PR Review: `<branch>` -> `main`

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

Only include issues with Verdict=CONSISTENT in draft-review.md.
DROPPED issues go in cross-reference.md only.

When done, respond with EXACTLY:
RESULT: draft-review.md saved. Issues: [Defect]=X [Correctness]=Y [Improvement]=Z. Rating: [value].
```

Record the result. Extract the issue counts and rating for the final summary.

### Step 4b: Cross-reference validator (isolated LLM agent)

Spawn a general-purpose subagent with this exact prompt:

```
Your job: validate the cross-reference document against source documents.

FILES TO READ (read these now, do not read anything else):
  <out>/cross-reference.md
  <out>/per-file-analysis.md
  <out>/file-manifest.json
  <out>/context.md

## Validation procedure

For each issue entry in cross-reference.md, independently verify:

1. **Per-file analysis Checklist check**: Does the checklist really say what
   cross-reference.md claims?
   - Read the actual per-file-analysis.md entry for the file
   - If cross-reference.md says "Dead code: No" but per-file-analysis says
     "Dead code: Yes" → this is a CONTRADICTION (flag it)
   - If cross-reference.md says "CONSISTENT" but the actual checklist says
     the opposite of the issue's direction → flag as CONTRADICTION

2. **Manifest fact check**: Does the manifest really say what cross-reference.md
   claims?
   - Read file-manifest.json and find the file's entry
   - If cross-reference.md says "has_trailing_newline: true" but manifest says
     false → CONTRADICTION
   - If cross-reference.md says "CONSISTENT" but the manifest contradicts the
     claim → flag it

3. **Context snapshot check**: Does the snapshot really say what cross-reference.md
   claims about prior review state?
   - If a claim is marked as "already resolved" but the snapshot doesn't mention it
     → flag it
   - If a claim should be DROPPED due to prior resolution but cross-reference.md
     marks it as CONSISTENT → flag it

4. **Dropped issues review**: Are there DROPPED issues that should have been kept?
   - If an issue was dropped but the source documents don't support the DROP
     decision → flag it

5. **Framing check**: Does the review framing match the snapshot?
   - If snapshot exists but framing says "first review" → flag as CONTEXT BLINDNESS
   - If prior fix round is recorded but rating doesn't account for it → flag

6. **Unapplied tasks check**: If cross-reference.md mentions prior unapplied tasks
   from the fix-plan audit, verify they are indeed re-flagged in draft-review.md as
   current issues.

## Output

Write <out>/cross-reference-validation.md with:

  ## Cross-Reference Validation

  **Issues validated:** N
  **Contradictions found:** M
  **Verdict:** PASS / FAIL

  ### Details

  For each issue examined:
  - Issue N: [description]
  - Per-file analysis check: [CORRECT / MISMATCH]
  - Manifest fact check: [CORRECT / MISMATCH]
  - Context snapshot check: [CORRECT / MISMATCH]
  - Overall: [PASS / FAIL]

  ### Contradictions (if any):
  [List each contradiction with the specific mismatch]

When done, respond with EXACTLY:
RESULT: cross-reference validation complete. Issues validated: N. Contradictions found: M. Verdict: PASS/FAIL.
```

Record the result. Extract the verdict for the final summary.

#### Validation gate (Step 4b)

If Step 4b returns Verdict: PASS, proceed to the Python consistency checker.
If Step 4b returns Verdict: FAIL (contradictions found), re-launch Step 4a with the validator's findings as additional context. Maximum retries: 2.

After Step 4b passes, also run the existing Python consistency checker:

```bash
uv run <plugin-root>/scripts/validate/validate-review-consistency.py <out>/draft-review.md <out>/file-manifest.json
```

If exit 0: proceed to Step 5.
If exit != 0: the Python validator found structural contradictions. Re-launch Step 4a (same prompt, but append the validator's stderr as additional context). Maximum retries: 2.

### Step 5: Draft fix document

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the draft review and produce a draft fix document.

FILE TO READ (read this now, do not read anything else):
  <out>/draft-review.md

## Rules

Only include [Defect] and [Correctness] issues. Do NOT include [Improvement] issues.
If there are no [Defect] or [Correctness] issues: write "No fixes required."

**Scope rule**: Every issue MUST be about the PR code — something wrong in the
source files, tests, or build configuration.  Do NOT include meta-issues about
the review process, the gather document, or the analysis itself.  A fix document
describes what to fix in the code, not what to fix in the review process.

## Output format

Write <out>/draft-fix-document.md:

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
uv run <plugin-root>/scripts/validate/validate-fix-document.py <out>/draft-fix-document.md --manifest <out>/file-manifest.json
```

If exit 0: proceed to Step 6.
If exit != 0: re-launch Step 5 with validator errors as additional context. Maximum retries: 2.

### Step 6: Draft fix-plan.toml

Spawn a general-purpose subagent with this exact prompt:

```
Your job: read the fix document and produce a draft TOML fix plan with exact before/after blocks.

FILES TO READ (read these now):
  <out>/draft-fix-document.md

Before writing any TOML, read the canonical spec:
  skills/compile-plan/references/compilable-plan-spec.md

For each issue in the fix document, you will also need to read the actual source file to get exact content.
Use: git show <branch>:path/to/file.rs

BRANCH: <branch>

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

Write <out>/draft-fix-plan.toml

When done, respond with EXACTLY:
RESULT: draft-fix-plan.toml saved. Tasks written: N. Before-block verification: M/N confirmed. Unverified: [list task IDs or "none"].
```

Record the result. Extract the verification ratio and unverified task IDs.

#### Validation gate (Step 6)

After the subagent returns RESULT, run the TOML plan validator:

```bash
uv run <plugin-root>/scripts/validate/validate-toml-plan.py <out>/draft-fix-plan.toml --manifest <out>/file-manifest.json
```

If exit 0: proceed to Step 7.
If exit != 0: re-launch Step 6 with validator errors as additional context. Maximum retries: 2.

### Step 7: Write gather summary

Using only the RESULT strings collected from Steps 1-6 (do not read any files), write `notes/pr-reviews/{branch}/gather-summary.md`:

```
## Gather Summary: `<branch>`

**Files analyzed:** [from Step 1 or Step 2 result]
**Issues found:** [Defect]=X [Correctness]=Y [Improvement]=Z (from Step 4 result)
**Draft rating:** [from Step 4 result]

**Gather completeness:**
- [x/o] raw-diff.md + file-manifest.json
- [x/o] per-file-analysis-template.md — [generated] (Step 1)
- [x/o] context.md — [created / missing] — Plan: [found/not found], Snapshot: [found/not found]
- [x/o] per-file-analysis.md — [created / missing]
- [x/o] cross-reference.md + cross-reference-validation.md — [created / missing]
- [x/o] draft-review.md — [created / missing]
- [x/o] draft-fix-document.md — [created / missing]
- [x/o] draft-fix-plan.toml — [created / missing]

**Prior fix-plan audit:** [all applied / N unapplied tasks found / no prior fix-plan] (from Step 1.5)

**Cross-reference validation:** [PASS / FAIL (N retries)] (from Step 4b)

**Before-block verification:** [M/N confirmed] (from Step 6 result)
**Unverified before blocks:** [list from Step 6 result, or "none"]

**Validation gates:**
- cross-reference validator: [PASS / FAIL (N retries)]
- review consistency (Python): [PASS / FAIL (N retries)]
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
- Run LLM validator gates (Step 4b) and Python validation script gates (Steps 4b→check, 5, 6) and retry on failure
- Write gather-summary.md itself from the collected RESULT strings

**Orchestrator will not:**
- Read raw-diff.md, context.md, or any output file itself
- Accumulate file contents in its own context
- Skip a step if a prior step failed — launch the next step with a note about the failure

**Subagents will:**
- Read only the files explicitly listed in their prompt
- Write exactly one output file per subagent (except Step 1 script and Step 4a which writes two)
- End their response with a RESULT: line in the exact format specified
