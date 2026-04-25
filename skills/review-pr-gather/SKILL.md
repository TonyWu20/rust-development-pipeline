---
name: review-pr-gather
description: Session 1 of the split PR review pipeline. Run this in a local model session to gather information, produce a draft review, and write structured output files for the judge session. Triggered by /review-pr-gather [branch-name].
version: 0.1.0
---

# PR Review — Gather (Local Model Session)

Collects all information needed for a PR review and produces draft output files. Designed to run in a Claude Code session pointed at a local llama-server backend (free compute). Output is saved to `notes/pr-reviews/{branch}/` for review by the user before the judge session.

## Trigger

`/review-pr-gather [branch-name]`

If no branch is given, use the current branch compared against `main`.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Process

### Step 1: Collect raw data

Run the following commands and save all output to `notes/pr-reviews/{branch}/raw-diff.md`:

```bash
git fetch origin
git log --oneline main..{branch}
git diff main...{branch} --stat
git diff main...{branch}
```

Also read each changed file in full using the Read tool. Append a section per file to `raw-diff.md`:

```
## File: path/to/file.rs
[full file contents]
```

Save to: `notes/pr-reviews/{branch}/raw-diff.md`

### Step 2: Load context

1. **Project memory**: Derive memory directory:
   ```bash
   MEMORY_DIR="$HOME/.claude/projects/$(pwd | sd '/' '-')/memory"
   ```
   Read `$MEMORY_DIR/MEMORY.md` and all linked memory files.

2. **Phase plan**: Locate the authoritative spec for this branch. Try in order:
   - Parse branch name for phase identifier. Search: `fd -e md -e toml . plans/ | rg -i 'phase.?{N}'`
   - If `plans/` has exactly one file, use it.
   - If `notes/plan-reviews/decisions.md` exists, check for a plan path.
   - If none found: note "No phase plan found — scope gating disabled."

3. **Snapshot** (if it exists): `notes/pr-reviews/{branch}/status.md`
   If the snapshot exists: use it as the primary source of truth. Read it instead of re-running git commands.

Save to: `notes/pr-reviews/{branch}/context.md`

Format:
```
## Memory
[memory file contents]

## Phase Plan
[plan contents — or "No phase plan found"]

## Snapshot
[snapshot contents — or "No snapshot — using raw diff"]
```

### Step 3: Per-file analysis

For each file listed in the diff stat (Step 1), produce a checklist entry.

**Do not make architectural judgments here — record observations only.**

For each changed file:

```
## File: path/to/file.rs

Intent: [one sentence on what changed here based on the diff]

Checklist:
- [ ] Unnecessary clone/unwrap/expect? [Yes/No — cite line if yes]
- [ ] Error handling: meaningful types or stringly-typed? [observation]
- [ ] Dead code or unused imports present? [Yes/No]
- [ ] If new public API: are there tests for it? [Yes/No/Not applicable]
- [ ] Does this change appear to be within the phase plan scope? [Yes/No/Unclear]

Notes: [any other observations — do not classify, just note]
```

Save to: `notes/pr-reviews/{branch}/per-file-analysis.md`

### Step 4: Draft 4-axis review

Using the per-file analysis and context, produce a draft review.

**Each issue found across all axes must be classified as exactly one of:**
- `[Defect]` — code does not implement what the plan commissioned
- `[Correctness]` — incorrect behavior independent of the plan (bug, data race)
- `[Improvement]` — better design, but outside plan scope

**If no phase plan was found: treat all issues as `[Correctness]`.**

Evaluate four axes:

**A. Plan & Spec Fulfillment**
- Does the code implement what the plan requires?
- Missing pieces from the stated goal?
- Out-of-scope additions?

**B. Architecture Compliance**
- DAG-centric design preserved?
- Functional style: iterators over `mut Vec`, no unnecessary mutation?
- `JobId` newtype pattern used where applicable?
- Async-first with tokio? Sync-over-async bridge only where justified?
- Crate boundaries respected (`workflow_core`, `workflow_utils`, `castep_adapter`)?

**C. Rust Style & Quality**
- No unnecessary `clone`, `unwrap`, or `expect` without comment?
- Error types are meaningful?
- No dead code, unused imports, or commented-out blocks?
- Builder pattern used for complex structs?

**D. Test Coverage**
- New public APIs have tests?
- Integration tests for non-trivial behavior?

Rate each axis: Pass / Partial / Fail — one-line reason.
Overall rating: Approve / Request Changes / Reject.

Save to: `notes/pr-reviews/{branch}/draft-review.md`

Use this format:
```
## Draft PR Review: `{branch}` → `main`

**Rating:** [Approve / Request Changes / Reject]

**Summary:** [2-3 sentences]

**Axis Scores:**
- Plan & Spec: [Pass/Partial/Fail] — [reason]
- Architecture: [Pass/Partial/Fail] — [reason]
- Rust Style: [Pass/Partial/Fail] — [reason]
- Test Coverage: [Pass/Partial/Fail] — [reason]

**Issues Found:**
[list each issue with classification]
- [Defect] Issue title — file: path/to/file.rs — [brief description]
- [Correctness] Issue title — file: path/to/file.rs — [brief description]
- [Improvement] Issue title — file: path/to/file.rs — [brief description]
```

### Step 5: Draft fix document

For each `[Defect]` and `[Correctness]` issue from Step 4, produce one block.

**Do not include `[Improvement]` issues here — they are improvements, not fixes.**

```
## Draft Fix Document

### Issue N: [Short title]

**Classification:** [Defect / Correctness]
**File:** `path/to/file.rs`
**Severity:** [Blocking / Major / Minor]
**Problem:** [What is wrong and why it matters]
**Fix:** [Concrete instruction — what to change. Include a code snippet if helpful.]
```

If there are no `[Defect]` or `[Correctness]` issues, write:
```
## Draft Fix Document

No fixes required. All issues are improvements (deferred).
```

Save to: `notes/pr-reviews/{branch}/draft-fix-document.md`

### Step 6: Draft fix-plan.toml

For each issue in the fix document:

1. Read the actual source file on the branch to get exact content:
   ```bash
   git show {branch}:path/to/file.rs
   ```

2. Find the exact text that needs to change. Copy it verbatim — no paraphrasing, no `...`.

3. Write the replacement content.

4. **Self-check**: After writing each `before` block, verify it appears in the file:
   ```bash
   rg -F "{first 20 chars of before block}" path/to/file.rs
   ```
   If the grep fails: the before block is wrong. Re-read the file and fix it.

Format each task:
```toml
[tasks.TASK-N]
description = "Short description"
type = "replace"
acceptance = ["cargo check -p crate_name", "cargo test -p crate_name"]

[[tasks.TASK-N.changes]]
file = "relative/path/from/root.rs"
before = '''
exact content copied verbatim — no paraphrasing, no ellipsis
'''
after = '''
exact replacement content
'''
```

Include dependencies if any task depends on another:
```toml
[dependencies]
TASK-2 = ["TASK-1"]
```

If no fixes are needed, write:
```toml
# No fix tasks — PR approved without fixes
```

Save to: `notes/pr-reviews/{branch}/draft-fix-plan.toml`

### Step 7: Summary for user review

Produce a concise summary for the user to review before starting the judge session.

```
## Gather Summary: `{branch}`

**Files analyzed:** N
**Issues found:** N total
  - [Defect]: X
  - [Correctness]: Y
  - [Improvement]: Z (deferred — not in fix plan)
**Draft rating:** [Approve / Request Changes / Reject]

**Gather completeness:**
- [ ] raw-diff.md — [created / missing]
- [ ] context.md — [created / missing]
- [ ] per-file-analysis.md — [created / missing]
- [ ] draft-review.md — [created / missing]
- [ ] draft-fix-document.md — [created / missing]
- [ ] draft-fix-plan.toml — [created / missing]

**Before-block verification:**
- [N/M] before blocks confirmed to match source files
- [list any unconfirmed blocks here]

**Confidence notes:**
[Things I am uncertain about — flag these for the user to check]

**Questions for user (if any):**
[Specific questions about intent, scope, or context]
```

Save to: `notes/pr-reviews/{branch}/gather-summary.md`

---

## Boundaries

**Will:**
- Record observations, not judgments
- Verify before blocks against actual source
- Save every output file even if partial
- Ask specific questions when intent is unclear

**Will not:**
- Make final architectural decisions
- Skip saving a file due to uncertainty — save partial output and note the gap
- Rewrite code for the author
- Use `...` or placeholder text in before blocks
