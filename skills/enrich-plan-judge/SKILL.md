---
name: enrich-plan-judge
description: Session 2 of the split plan enrichment pipeline. Run this in a Claude API session after /enrich-plan-gather has completed and you have reviewed the gathered files. Reads gathered output, validates elaboration and TOML plan, runs the Haiku clarity review and dry-run compilation, and produces the final executor-ready TOML plan.
version: 0.1.0
---

# Enrich Phase Plan — Judge (Claude API Session)

Reads the output produced by `/enrich-plan-gather`, validates the elaboration and TOML plan with Claude-level reasoning, corrects architectural oversights, and runs the existing quality gates (Haiku clarity review + dry-run compilation). Produces the final executor-ready TOML plan.

## Trigger

`/enrich-plan-judge [plan-file]`

If no plan file is given, use `AskUserQuestion` to ask the user for the path. The plan slug is derived from the filename.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Prerequisites

Run `/enrich-plan-gather {plan-file}` first and review `notes/plan-enrichment/{plan-slug}/gather-summary.md` before starting this session.

## Process

### Step 1: Read gathered files

Read all files from `notes/plan-enrichment/{plan-slug}/` in this order:

1. `gather-summary.md` — start here for overview, confidence notes, and user questions
2. `deferred-and-patterns.md` — deferred improvements and known failure modes
3. `codebase-state.md` — current state of relevant modules/types/signatures
4. `draft-elaboration.md` — local model's enriched narrative
5. `draft-plan.toml` — local model's TOML task breakdown
6. `task-checklist.md` — per-task self-check results

Also read the original plan file provided by the user.

**Score the gathered output:**
```
Gather completeness: [N/6] files present and non-empty
Before-block accuracy (from gather-summary): [N/M] blocks confirmed
Tasks with unverified before blocks: [list]
```

If fewer than 4/6 files exist: use `AskUserQuestion` to ask the user whether to proceed or re-run `/enrich-plan-gather`.

### Step 2: Incorporate user annotations

Check for user edits or annotations in any gathered file:
- Lines starting with `> [USER]`
- Edits to the confidence notes or questions section of `gather-summary.md`
- Edits directly to `draft-plan.toml` or `draft-elaboration.md`

Treat user annotations as ground truth.

### Step 3: Validate and correct the draft

**Do NOT re-read source files unless you flag a CONTEXT_GAP first** (see below).

**A. Elaboration check**

Using `codebase-state.md` as ground truth (not live file reads):

- Are proposed type signatures consistent with existing patterns in `codebase-state.md`?
- Are proposed module placements consistent with the existing structure?
- Are error handling strategies consistent with existing patterns?
- Any architectural pitfalls the draft missed?
  - Ownership/lifetime issues not flagged?
  - Trait coherence problems?
  - API surface decisions that are hard to reverse?
- Any deferred improvements in `deferred-and-patterns.md` that are directly relevant and should be absorbed into this plan?

**B. TOML plan check**

Using `task-checklist.md` to identify risks, then spot-check:

- Spot-check before blocks for tasks flagged as "Unverified" in task-checklist.md:
  ```bash
  git show HEAD:path/to/file.rs   # or read the file directly
  ```
  Correct any that do not match.

- Verify module wiring completeness:
  - Every task creating a `.rs` file must include `pub mod` in parent
  - Every task creating public cross-crate types must include `pub use` re-export
  - Consumer updates in same task as definition (not split)

- Verify acceptance criteria:
  - Commands must be valid shell that exits 0 on success
  - `cargo check -p crate` is sufficient for non-behavioral changes
  - Behavioral changes need `cargo test -p crate` or specific test names

- Verify dependency ordering:
  - A task that creates a type used by another task must come first
  - Check `[dependencies]` table is consistent with task descriptions

**C. Strategic alignment check**

Compare the TOML plan against the original plan file:

- Does the TOML plan faithfully implement what the plan document describes?
- Any scope creep (tasks that go beyond what the plan commissioned)?
- Any tasks that solve the immediate problem but create a worse problem downstream?
- Any tasks implied by the plan but missing from the TOML?
- Any acceptance criteria that would NOT actually verify correctness?

**CONTEXT_GAP**: If you need to read a source file to validate a claim:
```
CONTEXT_GAP: Need to verify [specific claim] — requires reading [file path]
```
Use `AskUserQuestion` to ask the user whether to read the file or trust the gathered codebase-state.md.

Only read files if the user confirms.

Produce the corrected TOML plan as `CORRECTED_PLAN`.

### Step 4: impl-plan-reviewer clarity review

Launch the `rust-development-pipeline:impl-plan-reviewer` agent with the corrected plan:

```
Review the following decomposed implementation plan. For each task, report whether it is CLEAR, UNCLEAR, or BLOCKED. End with your overall verdict.

<decomposed_plan>
{CORRECTED_PLAN}
</decomposed_plan>
```

- If verdict is **Ready to Implement**: proceed to Step 5.
- If verdict is **Needs More Detail**: collect flagged issues. Revise **only** the flagged tasks directly (Claude makes these changes, not the local model). Repeat (max 3 iterations). If still failing after 3: surface to the user.

### Step 5: Dry-run compilation

Apply all changes from the corrected plan to a temporary worktree:

1. Create worktree:
   ```bash
   git worktree add /tmp/plan-dryrun-$(date +%s) HEAD
   ```

2. Apply each task in dependency order:
   - `type = "create"`: write `after` content to target file
   - `type = "replace"`: `sd -F before after file`
   - `type = "delete"`: `sd -F before '' file`

3. Compile:
   ```bash
   cargo check --workspace 2>&1
   ```

4. Clean up (always, even on failure):
   ```bash
   git worktree remove --force /tmp/plan-dryrun-*
   ```

5. If compilation succeeds: proceed to Step 6.

6. If compilation fails: feed errors back and revise failing tasks directly (Claude):
   ```
   Revise only the tasks causing these errors:
   - Missing `pub mod` → add wiring [[changes]] entry
   - Missing `pub use` → add re-export [[changes]] entry
   - Stale import → update the import path
   - Type mismatch → correct the type in the task
   ```
   Repeat dry-run (max 2 revision iterations). If still failing: present errors to user.

### Step 6: Present final plan

Save the final plan. The output file name follows the existing convention:
```
plans/phase-{X}.{Y}.toml
```
(or wherever the user prefers — use `AskUserQuestion` if unclear)

Present to the user:
- What the gather phase elaborated well
- What the judge session corrected (summary of CORRECTED items from Step 3)
- Any CONTEXT_GAP items that were skipped — the user should be aware
- How many impl-plan-reviewer iterations were needed
- Whether dry-run compilation passed on first attempt or required revisions

---

## Boundaries

**Will:**
- Use gathered files as primary context — ask before reading source files
- Apply user annotations as ground truth
- Spot-check only tasks flagged as uncertain in task-checklist.md
- Flag CONTEXT_GAP explicitly before reading any source file
- Run the same quality gates as the current `/enrich-phase-plan` skill (Haiku review + dry-run)

**Will not:**
- Silently re-read source files without flagging CONTEXT_GAP
- Accept `...` or placeholder text in before blocks
- Skip the dry-run compilation gate
- Run the local model for revisions — all revisions in this session are made directly by Claude
