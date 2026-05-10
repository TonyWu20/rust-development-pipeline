---
name: explore-implement
description: Implement code changes from a single task group directly on a per-group sub-branch with real compiler feedback, then auto-review before commit. Accepts a TASKS.md group section (from /elaborate-plan) or fix-tasks.md (from /make-judgement). Uses edit→check→fix loop with auto-review per task.
---

# Explore Implement

> **DEPRECATED**: Replaced by `/drive-outcomes`. This skill continues to work for
> existing phases but will be removed after the migration period. New phases should
> use `/drive-outcomes`.

Implements a task group on a per-group sub-branch with real `cargo check` feedback. The core insight: instead of statically deducing code impact, the agent edits code and the compiler tells it what's wrong. Each task is auto-reviewed before commit — the sub-branch has clean, pre-reviewed commits. No fix commits, no noise.

Accepts either `TASKS.md` (from `/elaborate-plan`) or `fix-tasks.md` (from `/make-judgement`).

## Trigger

`/explore-implement <tasks-path> [group-id]`

Where `<tasks-path>` is the path to `TASKS.md` or `fix-tasks.md`. For multi-group files, `[group-id]` selects which group to implement. If omitted and the file has a single group, implement that group. If omitted and the file has multiple groups, the user must specify one.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`

## Process

### Step 1: Read Input and Setup

Set the stage marker, then read the task group from TASKS.md:

```bash
echo "explore-implement" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Ensure pipeline artifact directories are gitignored
grep -qx '.pipeline-worktrees/' .gitignore 2>/dev/null || echo '.pipeline-worktrees/' >> .gitignore
grep -qx '.claude/' .gitignore 2>/dev/null || echo '.claude/' >> .gitignore

# Commit the tasks file (and any new gitignore entries) before implementation
TASKS_DIR=$(dirname <tasks-path>)
git add .gitignore "$TASKS_DIR/"
git commit -m "docs: add $(basename <tasks-path>)" 2>/dev/null || true
```

Read the TASKS.md file. Extract the task group matching `[group-id]` by finding the `## Task Group: <group-id>` section. Parse all tasks under that header until the next `## Task Group:` or end of file.

For each task in the group, extract:
- `id` — from the `### TASK-{N}:` header
- `description` — the header text after the ID
- `goal` — from `**Goal:** G{N}`
- `files` — from `**Files:**`
- `deps` — from `**Depends on:**`
- `kind` — from `**Kind:**` (default: `direct`)
- `tdd_interface` — if kind is `lib-tdd`, the TDD fields: test_file, test_module, test_fn_name, test_code, signature, expected_behavior
- `changes` — bullets under `**Changes:**`
- `acceptance` — commands under `**Acceptance:**`

Plan slug: derive from the tasks file path (e.g., `notes/plans/phase-3.1/TASKS.md` → `phase-3.1`).

**Feature branch check**: Read the current branch name:
```bash
git rev-parse --abbrev-ref HEAD
```
If it is `main` or `master`, warn the user: "You are on `main`. `/explore-implement` expects a feature branch. Create one first with `git checkout -b <feature-branch>` and re-invoke." Then stop.

Record the feature branch name — it is the branch that was checked out at invocation time.

### Step 2: Resume Check

Check for a resume note from a prior interrupted session:

```bash
RESUME_NOTE="${CLAUDE_PROJECT_DIR}/.claude/resume-<plan-slug>-<group-id>.md"
[ -f "$RESUME_NOTE" ] && cat "$RESUME_NOTE"
```

If the resume note exists:
1. Read it to find the sub-branch name and completed tasks.
2. Check out the existing sub-branch: `git checkout impl/<plan-slug>/<group-id>`
3. Skip tasks listed under **Tasks done** in the note.
4. Start implementation from **Next task**.

If no resume note, proceed to Step 3.

### Step 3: Create Sub-branch

```bash
git checkout -b impl/<plan-slug>/<group-id>
```

This creates a sub-branch from the feature branch tip. All implementation commits go here.

### Step 4: Implementation Loop

Implement each task sequentially. Dispatch on `kind` field.

**IMPORTANT**: Never launch subagents in background mode (`run_in_background`). Permission requests from background subagents are invisible in the Claude Code interface — they can only be approved via the Discord hook, which has a 2-minute timeout. Always launch subagents in foreground.

For each task in the group:

0. **Check task kind**: Read `kind` from the parsed task (default: `"direct"`).

   #### If `kind` is `"lib-tdd"`:

   1. **Read the task**: description, tdd_interface (test_file, test_module, test_fn_name, test_code, signature, expected_behavior), success_criteria, changes, acceptance.

   2. **Resolve the odd-pattern.md path**:
      ```bash
      echo "${CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md"
      ```

   3. **Launch the implementation-executor subagent** with `workflow: 'odd'`:
      > **Agent**: rust-development-pipeline:implementation-executor (subagent, discardable context)
      >
      > **Task**: Implement this lib-tdd task following the Outcome-Driven Development cycle.
      >
      > **workflow**: odd
      > **PROJECT_PATH**: <CLAUDE_PROJECT_DIR>
      >
      > ALL file reads, edits, and git operations MUST target `PROJECT_PATH`. Use absolute
      > paths rooted at `PROJECT_PATH` for every file access.
      >
      > Read the odd-pattern.md reference at `{CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md`.
      >
      > Use the task's success criteria to anchor tests against real values. Write tests
      > that reference declared fixture files and assert against known-good expected values.

   4. **After the agent reports VERIFIED**:
      - Run acceptance commands against declared fixtures
      - **Auto-review**: verify test assertions are anchored to ground truth (no is_finite(), no circular round-trip, no unbounded thresholds)
      - Commit: `git commit -m "feat(<plan-slug>): <task-id> (ODD): <description>"`
      - Update resume note

   #### If `kind` is `"direct"` (default):

   1. **Read the task**: description, files, changes, acceptance.

   2. **Explore current state**: Read files from `CLAUDE_PROJECT_DIR` using `fd` and `rg`.

   3. **Implement changes**: Apply each change bullet. The action type is the bold first word:
      - `**create** <path>: <guidance>` — create file with described content
      - `**modify** <path>: <guidance>` — edit existing file
      - `**delete** <path>` — remove the file

   4. **Run cargo check**:
      ```bash
      cd "${CLAUDE_PROJECT_DIR}" && cargo check 2>&1
      ```
      Fix errors, re-run, repeat up to **5 iterations**.

   5. **Run acceptance commands**: Execute each command in `**Acceptance:**`.

   6. **Auto-review before commit**: Run the pre-commit review (see below).

   7. **Commit**:
      ```bash
      git add -A
      git commit -m "feat(<plan-slug>): <task-id>: <description>"
      ```

   8. **Update resume note**.

#### Auto-review before commit (both kinds)

Before committing each task, run this internal review:

1. **Diff check**: `git diff --stat HEAD` — list changed files
2. **Scope check**: Did the diff only touch files listed in `**Files:**`? If extra files are changed, verify they're intentional. Revert unintended changes.
3. **Intent check**: Re-read the task guidance. Does the diff match what was described?
4. **Acceptance check**: Re-run acceptance commands. Confirm they pass.
5. **Self-review**: Read through uncommitted diff. Are there obvious bugs, dead code, or debug artifacts? Fix any found.
6. Only proceed to commit if all checks pass.

#### Update resume note

After each task completes, write `.claude/resume-<plan-slug>-<group-id>.md`:

```markdown
# Resume: <plan-slug> / <group-id>

**Feature branch**: <feature-branch>
**Sub-branch**: impl/<plan-slug>/<group-id>
**Tasks done**: TASK-1, TASK-2
**Next task**: TASK-3
**Status**: in-progress
```

Update the **Tasks done** list and **Next task** field after each commit.

#### If cargo check fails after 5 iterations

Report failure with diagnostic info and stop. For `lib-tdd` tasks, prefix with the ODD phase that failed:
- "ODD CRITERIA: Fixture files declared but not used in tests"
- "ODD EXPLORE: Exploratory snippet failed against real fixture data"
- "ODD PLACEBO: Test uses vacuous assertions (is_finite, circular round-trip, unbounded threshold)"
- "ODD VERIFY: Implementation failed acceptance against real fixtures"

### Step 5: Workspace Validation

After all tasks in the group complete:

```bash
cd "${CLAUDE_PROJECT_DIR}" && cargo check --workspace 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo clippy --workspace -- -D warnings 2>&1
# If any task used lib-tdd, also run crate-scoped tests
cd "${CLAUDE_PROJECT_DIR}" && cargo test -p <relevant-crate> 2>&1 | tail -20
```

### Step 6: Merge

Fast-forward merge the sub-branch into the feature branch:

```bash
FEATURE_BRANCH=<feature-branch>
git checkout "$FEATURE_BRANCH"
git merge --ff-only impl/<plan-slug>/<group-id>
git branch -d impl/<plan-slug>/<group-id>
```

Then workspace-level validation on the feature branch:

```bash
cd "${CLAUDE_PROJECT_DIR}" && cargo check --workspace 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo clippy --workspace -- -D warnings 2>&1
cd "${CLAUDE_PROJECT_DIR}" && cargo test --workspace 2>&1 | tail -20
```

Clean up the resume note:

```bash
rm -f "${CLAUDE_PROJECT_DIR}/.claude/resume-<plan-slug>-<group-id>.md"
```

### Step 7: Report

Run the session metrics eval and report results:

```bash
CLAUDE_PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}" CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR}" uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" explore-implement
```

Report to the user:

> "Implementation complete for group \"{group-id}\".
>
> {N} tasks implemented, each auto-reviewed before commit.
> Branch history is clean — {N} commits, no fix commits.
>
> {eval output}
>
> For single-group features: you're done. Merge the feature branch.
> For multi-group features: implement remaining groups or run `/make-judgement <tasks-path>` for cross-group review."

## Fix Application

When the input is `fix-tasks.md` (from `/make-judgement`), the process is identical. Read the fix tasks, create/use sub-branch, apply with edit→check→fix loop + auto-review.

## Boundaries

**Will:**
- Create per-group sub-branches for clean group isolation
- Use real compiler feedback (cargo check) to catch errors
- Apply descriptive guidance from markdown against current file state
- Auto-review each task before commit (scope check + intent check + acceptance check)
- Run acceptance commands as validation
- Commit per-task with clean, pre-reviewed commits
- Recover from interrupted sessions via markdown resume note
- Handle both new implementation and fix application identically

**Will not:**
- Use exact before/after TOML blocks
- Implement without compiler feedback
- Run groups in parallel
- Skip auto-review or cargo check at any step
