---
name: review-pr-judge
description: Session 2 of the split PR review pipeline. Run this in a Claude API session after /review-pr-gather has completed and you have reviewed the gathered files. Reads the gathered output, validates, corrects, and produces the final review and fix-plan.toml.
version: 0.1.0
---

# PR Review — Judge (Claude API Session)

Reads the output produced by `/review-pr-gather`, validates it with Claude-level reasoning, corrects any oversights, and produces the final PR review and fix-plan.toml. Designed to be token-efficient: Claude reasons over pre-structured analysis rather than raw diffs.

## Trigger

`/review-pr-judge [branch-name]`

If no branch is given, use the current branch.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Prerequisites

Run `/review-pr-gather {branch}` first and review `notes/pr-reviews/{branch}/gather-summary.md` before starting this session.

## Process

### Step 1: Read gathered files

Read all files from `notes/pr-reviews/{branch}/` in this order:

1. `gather-summary.md` — start here for overview, confidence notes, and user questions
2. `context.md` — phase plan and memory
3. `per-file-analysis.md` — checklist evaluation per file
4. `draft-review.md` — local model's review attempt
5. `draft-fix-document.md` — local model's fix document
6. `draft-fix-plan.toml` — local model's TOML plan

**Score the gathered output immediately:**
```
Gather completeness: [N/7] files present and non-empty
Before-block accuracy (from gather-summary): [N/M] blocks confirmed
```

If fewer than 5/7 files exist or are non-empty: inform the user that the gather phase was incomplete and ask whether to proceed or re-run `/review-pr-gather`.

### Step 2: Incorporate user annotations

Check if the user has edited any gathered file or added annotations. Look for:
- Lines starting with `> [USER]` or `<!-- USER NOTE -->`
- Edits to the confidence notes or questions section of `gather-summary.md`

Treat user annotations as ground truth. Incorporate them before validation.

If no annotations are found: proceed with a note that the draft is treated as-is.

### Step 3: Validate and correct

Using the gathered context (do **not** re-read source files yet), validate the draft across three dimensions:

**A. Detail check**

For each issue in `draft-review.md`:
- Is the classification correct? (`[Defect]` vs `[Correctness]` vs `[Improvement]`)
- Is the severity assignment justified? (`Blocking` vs `Major` vs `Minor`)
- Does the cited file appear in `raw-diff.md`?
- Are there observations in `per-file-analysis.md` that the draft review missed?

For each `before` block in `draft-fix-plan.toml`:
- Is it consistent with the fix document's described problem?
- Does the `after` block implement the described fix?

Output per issue:
- `CONFIRMED:` — draft is correct
- `CORRECTED: [what changed]` — with brief reason
- `ADDED: [new issue]` — found in per-file analysis but missing from draft
- `REMOVED: [issue title]` — draft claimed this but context does not support it

**B. Strategic alignment check**

Step back from the individual issues:
- Is the review trapped in a local optimum? (Fixing symptoms rather than root causes?)
- Does the overall assessment align with the project's architectural direction (from memory)?
- Are there higher-leverage issues the draft prioritized incorrectly?
- Is the PR rating (Approve/Request Changes/Reject) consistent with the found issues?

**C. Omission check**

Cross-reference `per-file-analysis.md` against `draft-review.md`:
- Any changed files with observations not addressed in the review?
- Any edge cases in new code paths?
- Any architectural patterns known to be important (from memory) that were not checked?

**CONTEXT_GAP**: If you find you need information not in the gathered files to validate a claim:
```
CONTEXT_GAP: [description of what's missing]
```
List all gaps, then ask the user: "The gathered files don't contain [X]. Should I read [specific file] to verify, or trust the draft's assessment?"

Only read source files if the user confirms. This keeps costs predictable.

### Step 4: Produce final output

Apply all corrections. Produce the final review using **exactly** these templates:

---

> **PR REVIEW TEMPLATE**

```
## PR Review: `{branch}` → `main`

**Rating:** [Approve / Request Changes / Reject]

**Summary:** [2–3 sentences on overall quality and direction]

**Cross-Round Patterns:** [None / list items — see Step 5]

- [Recurring] [issue title] — flagged in vX, vY (regression)
- [Contradictory] vX "[action]" vs vY "[opposite action]"

**Deferred Improvements:** [None / N items → `notes/pr-reviews/{branch}/deferred.md`]

**Axis Scores:**

- Plan & Spec: [Pass / Partial / Fail] — [one-line reason]
- Architecture: [Pass / Partial / Fail] — [one-line reason]
- Rust Style: [Pass / Partial / Fail] — [one-line reason]
- Test Coverage: [Pass / Partial / Fail] — [one-line reason]
```

---

> **FIX DOCUMENT TEMPLATE**

```
## Fix Document for Author

### Issue N: [Short title]

**Classification:** [Defect / Correctness]
**File:** `path/to/file.rs`
**Severity:** [Blocking / Major / Minor]
**Problem:** [What is wrong and why it matters]
**Fix:** [Concrete instruction]
```

**Format rules:**
| Field | Rule |
|-------|------|
| `### Issue N:` | Must use colon after number — not em dash |
| `**Classification:**` | Exactly one of: `Defect`, `Correctness`. Never `Improvement`. |
| `**File:**` | Path only, no line number |
| `**Severity:**` | Exactly one of: `Blocking`, `Major`, `Minor` |

---

> **DEFERRED IMPROVEMENTS TEMPLATE** — write to `notes/pr-reviews/{branch}/deferred.md` when `[Improvement]` items exist

```
## Deferred Improvements: `{branch}` — {YYYY-MM-DD}

### [Short title]
**Source:** Round {N} review
**Rationale:** [Why this is better design — one paragraph]
**Candidate for:** Phase {N+1} plan
**Precondition:** [A concrete trigger, e.g. "second consumer of this API exists"]
```

---

### Step 5: Cross-round pattern detection (conditional)

**Skip if** neither `notes/pr-reviews/{branch}/fix-plan.toml` nor `notes/pr-reviews/{branch}/fix-plan.md` has fewer than 2 git commits.

If prior fix plans exist:
```bash
git log --reverse --format='%H %s' -- notes/pr-reviews/{branch}/fix-plan.toml notes/pr-reviews/{branch}/fix-plan.md
git log --reverse --format='%H %s' -- notes/pr-reviews/{branch}/review.md
```

For each commit: `git show {hash}:notes/pr-reviews/{branch}/fix-plan.toml`

Detect:
- **Recurring**: same problem appears in non-consecutive versions
- **Contradictory**: a task in one version directly reverses a task from a prior version

Report: max 5 items. Include in the PR Review output under `**Cross-Round Patterns:**`.

### Step 6: Validate and correct fix-plan.toml

Review `draft-fix-plan.toml` from the gather phase:

1. **Spot-check before blocks**: Read specific source files for the 2-3 highest-severity issues. Verify the `before` block is an exact substring.
   ```bash
   git show {branch}:path/to/file.rs
   ```
   Correct any `before` blocks that do not match.

2. **Verify after blocks**: Each `after` block must implement the fix described in the Fix Document. No unrelated changes.

3. **Run `rust-development-pipeline:fix-plan-reader`** on the corrected plan to check clarity for the executor agent.

4. Save final plan to `notes/pr-reviews/{branch}/fix-plan.toml` (overwrite the draft):
   ```bash
   git add notes/pr-reviews/{branch}/fix-plan.toml
   git commit -m "review({branch}): update fix plan"
   ```

### Step 7: Save deferred improvements and commit review

If `[Improvement]` items were identified:
- Write or append to `notes/pr-reviews/{branch}/deferred.md`
- If file exists: append under a new dated heading
- ```bash
  git add notes/pr-reviews/{branch}/deferred.md
  git commit -m "review({branch}): record deferred improvements"
  ```

Save the final PR Review output to `notes/pr-reviews/{branch}/review.md`:
```bash
git add notes/pr-reviews/{branch}/review.md
git commit -m "review({branch}): final review"
```

---

## Boundaries

**Will:**
- Use gathered files as primary context — ask before reading source files
- Apply user annotations as ground truth
- Flag CONTEXT_GAP explicitly rather than silently re-exploring
- Produce output using exact templates for downstream compatibility
- Spot-check before blocks for high-severity fixes only

**Will not:**
- Silently re-read source files without flagging CONTEXT_GAP
- Accept `...` or placeholder text in before blocks
- Merge `[Improvement]` items into the Fix Document
- Skip the cross-round pattern check if prior fix plans exist
