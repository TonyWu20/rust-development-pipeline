---
name: explore-implement
description: Implement code changes from a single task group in a git worktree with real compiler feedback, then auto-review before commit. Accepts a TASKS.md group section (from /elaborate-plan) or fix-tasks.md (from /make-judgement). Uses edit→check→fix loop with auto-review per task.
---

# Explore Implement

Implements a task group in a git worktree with real `cargo check` feedback. The core insight: instead of statically deducing code impact, the agent edits code and the compiler tells it what's wrong. Each task is auto-reviewed before commit — the worktree branch has clean, pre-reviewed commits. No fix commits, no noise.

Accepts either `TASKS.md` (from `/elaborate-plan`) or `fix-tasks.md` (from `/make-judgement`).

## Trigger

`/explore-implement <tasks-path> [group-id]`

Where `<tasks-path>` is the path to `TASKS.md` or `fix-tasks.md`. For multi-group files, `[group-id]` selects which group to implement. If omitted and the file has a single group, implement that group. If omitted and the file has multiple groups, the user must specify one.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh"` for worktree management

## Process

### Step 0: Pre-flight Validation

Run workspace-map validation to catch structural issues before implementation:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  ".pipeline-worktrees/.workspace-map.json" \
  --validate
```

On exit code 1 (tool not installed), fail immediately — `rust-workspace-map` is a required dependency. On validation warnings (advisory), surface them to the orchestrator as known-broken wiring that the implementation should avoid introducing more of.

Generate a full map for per-task structural context:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  ".pipeline-worktrees/.workspace-map.json"
```

### Step 1: Read Input and Setup

Set the stage marker, then read the task group from TASKS.md:

```bash
# Set stage marker and session start for metrics tracking
echo "explore-implement" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Ensure worktree and pipeline artifact directories are gitignored
grep -qx '.pipeline-worktrees/' .gitignore 2>/dev/null || echo '.pipeline-worktrees/' >> .gitignore
grep -qx '.claude/' .gitignore 2>/dev/null || echo '.claude/' >> .gitignore
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

Worktree path: `${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>`
Branch: `impl/<plan-slug>/<group-id>`

### Step 2: Resume Check

Check for existing worktree from a prior interrupted session. Use `git worktree list` as the authoritative source — NOT a directory existence check:

```bash
WT_PATH="${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>"
# Check if git knows about this worktree (authoritative), not just directory exists
git worktree list | grep -q "$WT_PATH" && bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" status "$WT_PATH" || true
```

If the worktree exists AND git lists it:

1. **Inspect commit history** to see which tasks were already done:
   ```bash
   git -C "$WT_PATH" log --oneline --grep="^feat(<plan-slug>): " 2>/dev/null || true
   ```

2. **Check checkpoint state** for task-level progress:
   ```bash
   uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" status "$WT_PATH"
   ```

3. **Resume from first incomplete task**: Skip completed tasks. Start implementation loop from the first uncompleted task. If all tasks are done, skip to Step 6 (Merge).

If no worktree (git doesn't list it), proceed to Step 3. If a directory exists but git doesn't list it as a worktree, warn the user and abort — it's not a valid worktree.

### Step 3: Create Worktree

```bash
WT_PATH="${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>"
BRANCH="impl/<plan-slug>/<group-id>"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" create "$WT_PATH" "$BRANCH"
```

Initialize the checkpoint:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" init <tasks-path> "$WT_PATH"
```

### Step 4: Implementation Loop

The task group contains tasks from TASKS.md. Implement each task sequentially. Dispatch on `kind` field.

**IMPORTANT**: Never launch subagents in background mode (`run_in_background`). Permission requests from background subagents are invisible in the Claude Code interface — they can only be approved via the Discord hook, which has a 2-minute timeout. Always launch subagents in foreground.

For each task in the group:

0. **Check task kind**: Read `kind` from the parsed task (default: `"direct"`).

   #### If `kind` is `"lib-tdd"`:

   1. **Read the task**: description, tdd_interface (test_file, test_module, test_fn_name, test_code, signature, expected_behavior), changes, acceptance.

   2. **Resolve the tdd-pattern.md path**:
      ```bash
      echo "${CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/tdd-pattern.md"
      ```

   3. **Launch the implementation-executor subagent** with `workflow: 'tdd'`:
      > **Agent**: rust-development-pipeline:implementation-executor (subagent, discardable context)
      >
      > **Task**: Implement this lib-tdd task following the TDD red-green-refactor cycle.
      >
      > **workflow**: tdd
      > **WT_PATH**: <worktree-path>
      >
      > ALL file reads, edits, and git operations MUST target `WT_PATH`. Use absolute
      > paths rooted at `WT_PATH` for every file access.
      >
      > Read the tdd-pattern.md reference at `{CLAUDE_PLUGIN_ROOT}/skills/elaborate-plan/references/tdd-pattern.md`.
      >
      > Use the task's TDD interface to write the failing test first (RED), then implement
      > per guidance to make it pass (GREEN). Do NOT change the test code.

   4. **After the agent reports GREEN**:
      - Run acceptance commands
      - **Auto-review**: run the pre-commit review (see below)
      - Commit: `git -C <worktree-path> commit -m "feat(<plan-slug>): <task-id> (TDD): <description>"`
      - Update checkpoint

   #### If `kind` is `"direct"` (default):

   1. **Read the task**: description, files, changes, acceptance.

   2. **Set worktree context**: All operations target `<worktree-path>`. Prepend worktree path to all file reads/edits. Use `git -C <worktree-path>` for git operations.

   3. **Explore current state**: Read files from the worktree. Use `.pipeline-worktrees/.workspace-map.json` for structural context.

   4. **Implement changes**: Apply each change bullet. The action type is the bold first word:
      - `**create** <path>: <guidance>` — create file with described content
      - `**modify** <path>: <guidance>` — edit existing file
      - `**delete** <path>` — remove the file

   5. **Run cargo check**:
      ```bash
      cargo check 2>&1
      ```
      Fix errors, re-run, repeat up to **5 iterations**.

   6. **Run acceptance commands**: Execute each command in `**Acceptance:**`.

   7. **Auto-review before commit**: Run the pre-commit review (see below).

   8. **Commit to worktree**:
      ```bash
      git -C <worktree-path> add -A
      git -C <worktree-path> commit -m "feat(<plan-slug>): <task-id>: <description>"
      ```

   9. **Update checkpoint**.

#### Auto-review before commit (both kinds)

Before committing each task, run this internal review:

1. **Diff check**: `git -C <worktree-path> diff --stat` — list changed files
2. **Scope check**: Did the diff only touch files listed in `**Files:**`? If extra files are changed, verify they're intentional (wiring a re-export in lib.rs is expected; accidentally editing an unrelated test file is not). Revert unintended changes.
3. **Intent check**: Re-read the task guidance. Does the diff match what was described? If the implementation took a different approach than the guidance intended, flag it.
4. **Acceptance check**: Re-run acceptance commands. Confirm they pass.
5. **Self-review**: Read through uncommitted diff. Are there obvious bugs, dead code, or debug artifacts? Fix any found.
6. Only proceed to commit if all checks pass.

This ensures every commit in the worktree is clean and pre-reviewed. No fix commits, no noise.

#### If cargo check fails after 5 iterations

Mark the task group as failed with diagnostic info:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" failed <group-id> <worktree-path> "Last error: <diagnostic>"
```

For `lib-tdd` tasks, prefix with the TDD phase that failed:
- "TDD RED: Test failed to compile after 5 iterations"
- "TDD RED: Test passed immediately (false green - test too weak)"
- "TDD STUB: Implementation stub failed to compile after 5 iterations"
- "TDD GREEN: Implementation failed to pass test after 5 iterations"

Report failure and stop.

### Step 5: Workspace Validation

After all tasks in the group complete:

```bash
# Per-worktree validation
cargo check --workspace 2>&1
cargo clippy --workspace -- -D warnings 2>&1
# If any task used lib-tdd, also run crate-scoped tests
cargo test -p <relevant-crate> 2>&1 | tail -20
```

### Step 6: Merge

Derive the worktree branch from git (don't assume slug == branch):

```bash
WT_BRANCH=$(git -C "$WT_PATH" rev-parse --abbrev-ref HEAD)
FEATURE_BRANCH="<source-branch>"  # from TASKS.md metadata (## **Source branch:**)

# Checkout feature branch and merge
git checkout "$FEATURE_BRANCH"
git merge "$WT_BRANCH" --no-ff -m "merge(<plan-slug>): <group-id> from worktree"
```

If HEAD is detached in the worktree, use `git cherry-pick` with the worktree commits instead.

If merge conflicts arise, resolve them then commit.

Then workspace-level validation:
```bash
cargo check --workspace
cargo clippy --workspace -- -D warnings
cargo test --workspace 2>&1 | tail -20
```

Clean up:
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" clear <worktree-path>
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" remove <worktree-path>
```

### Step 7: Report

Stage the tasks artifacts:

```bash
# Derive the tasks directory from the input file path
TASKS_DIR=$(dirname <tasks-path>)
git add "$TASKS_DIR/"
```

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

### Parallel Execution (Tier 2)

For multiple independent groups, run separate `/explore-implement` sessions in parallel (one per group ID). Each session gets its own worktree.

## Fix Application

When the input is `fix-tasks.md` (from `/make-judgement`), the process is identical. Read the fix tasks, create/use worktree, apply with edit→check→fix loop + auto-review.

## Worktree Lifecycle

- **Created**: At the start of `/explore-implement`
- **Persists**: Across session crashes/interruptions
- **Discovered**: Via `git worktree list` (authoritative), not directory existence
- **Removed**: After successful merge and cleanup
- **Manual cleanup**: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" remove <worktree-path>`

## Boundaries

**Will:**
- Create isolated worktrees for safe implementation (one per group)
- Use real compiler feedback (cargo check) to catch errors
- Apply descriptive guidance from markdown against current file state
- Auto-review each task before commit (scope check + intent check + acceptance check)
- Run acceptance commands as validation
- Commit per-task with clean, pre-reviewed commits
- Recover from interrupted sessions via git worktree list + checkpoint
- Handle both new implementation and fix application identically

**Will not:**
- Use exact before/after TOML blocks
- Implement without compiler feedback
- Modify the main working tree directly
- Skip auto-review or cargo check at any step
- Leave worktrees behind without cleanup
