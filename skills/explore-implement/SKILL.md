---
name: explore-implement
description: Implement code changes from a single-group directions file in a git worktree with real compiler feedback. Accepts a per-group directions file (from /elaborate-directions) or fix-directions.json (from /make-judgement). Uses edit→check→fix loop with up to 5 iterations per change. Use when the user says "/explore-implement <directions-path>", "implement the directions", "apply the fix directions", or after /elaborate-directions completes.
---

# Explore Implement

Implements code changes in a git worktree with real `cargo check` feedback. The core insight: instead of statically deducing code impact (the old "mental dance"), the agent edits code and the compiler tells it what's wrong. This catches incorrect API usage, missing imports, type errors, and clippy violations immediately.

Accepts either `directions.json` (from `/elaborate-directions`) or `fix-directions.json` (from `/make-judgement`). The edit→check→fix loop is identical for both — the only difference is the input format.

## Trigger

`/explore-implement <directions-path>`

Where `<directions-path>` is the path to a single-group `directions.json` or `fix-directions.json` file.

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory "${CLAUDE_PLUGIN_ROOT}" python` for Python scripts
- use `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh"` for worktree management

## Process

### Step 1: Read Input and Setup

Set the stage marker for metrics, then read the directions file and determine the plan slug:

```bash
# Set stage marker and session start for metrics tracking
echo "explore-implement" > .claude/.current_stage
date +%s%3N > .claude/.session_start

# Ensure worktree directory is gitignored in the user project
grep -qx '.pipeline-worktrees/' .gitignore 2>/dev/null || echo '.pipeline-worktrees/' >> .gitignore

# Read the directions
cat <directions-path>
```

Plan slug: derive from the directions filename (e.g., `notes/directions/phase-3.1/directions-phase-3.1-group-core.json` → `phase-3.1`). Group ID: derive from the filename suffix after the last `-group-` (e.g., `...-group-core.json` → `group-core`).

Worktree path: `${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>`
Branch: `impl/<plan-slug>/<group-id>`

### Step 2: Resume Check

Check for existing worktree from a prior interrupted session:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" status "${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>"
```

If the worktree exists with completed commits, skip checkpoint — just implement the remaining tasks in the group. If no worktree, proceed to Step 3.

### Step 3: Create Worktree

Create a worktree for isolated implementation:

```bash
WT_PATH="${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>"
BRANCH="impl/<plan-slug>/<group-id>"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" create "$WT_PATH" "$BRANCH"
```

Initialize the checkpoint:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" init <directions-path> "$WT_PATH"
```

### Step 4: Implementation Loop

The directions file contains a single task group. Implement each task sequentially.
Dispatch on the task's `kind` field to select the implementation workflow:

For each task in the group:

0. **Check task kind**: Read `kind` from the task (default: `"direct"` if absent).

   #### If `kind` is `"lib-tdd"`:
   
   1. **Read the task**: `description`, `kind`, `tdd_interface`, `files_in_scope`, `changes`, `wiring_checklist`, `type_reference`, `acceptance`
   
   2. **Launch the implementation-executor subagent** with `workflow: 'tdd'`:
      > **Agent**: rust-development-pipeline:implementation-executor (subagent, discardable context)
      >
      > **Task**: Implement this lib-tdd task following the TDD red-green-refactor cycle.
      >
      > **workflow**: tdd
      >
      > Read `skills/elaborate-directions/references/tdd-pattern.md` for the canonical TDD workflow.
      >
      > Use the task's `tdd_interface` to write the failing test first (RED), then implement per `changes[].guidance` to make it pass (GREEN). Do NOT change the test code. See your permanent instructions (Path B) for the full workflow.
   
   3. **After the agent reports GREEN**:
      - Verify `wiring_checklist` items
      - Run `acceptance` commands
      - Commit: `git -C <worktree-path> commit -m "feat(<plan-slug>): <task-id> (TDD): <description>"`
      - Update checkpoint:
        ```bash
        uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" complete <group-id> <worktree-path>
        ```

   #### If `kind` is `"direct"` or absent (the existing workflow):

   1. **Read the task**: `description`, `files_in_scope`, `changes`, `wiring_checklist`, `type_reference`, `acceptance`

   2. **Explore current state**: Read the files in `files_in_scope` from the worktree (not from the main repo — worktree has the latest state). Use LSP to understand structure.

   3. **Implement changes**: Apply each change entry:
      - For `create`: Create the file with the described structs/traits/functions
      - For `modify`: Edit the existing file per guidance
      - For `delete`: Remove the file

   4. **Run cargo check**:
      ```bash
      cargo check 2>&1
      ```
      Read the compiler output. If errors:
      - Fix each error
      - Re-run cargo check
      - Repeat up to **5 iterations** per change

   5. **Verify wiring checklist**: For each item in `wiring_checklist`:
      - `pub_mod`: `rg "^pub mod" <file>` to verify the module is declared
      - `pub_use`: `rg "^pub use" <file>` to verify the re-export
      - `fn_call`, `type_annotation`: Verify as described

   6. **Run acceptance commands**: Execute each command in `acceptance`:
      ```bash
      <acceptance command>
      ```
      All must pass (exit code 0).

   7. **Commit to worktree**:
      ```bash
      git -C <worktree-path> add -A
      git -C <worktree-path> commit -m "feat(<plan-slug>): <task-id>: <description>"
      ```

   8. **Update checkpoint**:
      ```bash
      uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" complete <group-id> <worktree-path>
      ```

#### If cargo check fails after 5 iterations

Mark the task group as failed with diagnostic info:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/checkpoint-resume.py" failed <group-id> <worktree-path> "Last error: <diagnostic>"
```

For `lib-tdd` tasks, prefix the diagnostic with the TDD phase that failed:
- "TDD RED: Test failed to compile after 5 iterations"
- "TDD RED: Test passed immediately (false green - test too weak)"
- "TDD STUB: Implementation stub failed to compile after 5 iterations"
- "TDD GREEN: Implementation failed to pass test after 5 iterations"

Report the failure and stop — this group could not be implemented.

### Step 5: Workspace Validation

After all tasks in the group complete:

```bash
# Per-worktree validation
cargo check --workspace 2>&1
cargo clippy --workspace -- -D warnings 2>&1
# If any task in this group used kind: "lib-tdd", also run crate-scoped tests
cargo test -p <relevant-crate> 2>&1 | tail -20
```
Note: step 6 runs `cargo test --workspace` as the final integration gate after
merge. The crate-scoped test here is a pre-merge check.

### Step 6: Merge and Report

Merge worktree changes back:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" merge <worktree-path>
```

Then run workspace-level validation:
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

Run the session metrics eval and report results:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python "${CLAUDE_PLUGIN_ROOT}/scripts/eval-session-metrics.py" explore-implement
```

Report to the user:

> "Implementation complete for group \"{group-id}\".
>
> {eval output}
>
> Next step: `/make-judgement <index-path>` to review the changes against all groups.
>
> The index path is `<directions-dir>/directions-index.json` (e.g., `notes/directions/<plan-slug>/directions-index.json`).

### Parallel Execution (Tier 2)

For multiple independent groups, run separate `/explore-implement` sessions in parallel (one per group file). Each session gets its own worktree under `${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/`.

## Fix Application

When the input is `fix-directions.json` (from `/make-judgement`), the process is identical:
- Read the fix directions
- Create/use a worktree
- Apply each fix with the same edit→check→fix loop
- The fix directions follow the same schema as directions.json

## Worktree Lifecycle

- **Created**: At the start of `/explore-implement`
- **Persists**: Across session crashes/interruptions — the filesystem preserves it
- **Discovered**: Via `${CLAUDE_PROJECT_DIR}/.pipeline-worktrees/<plan-slug>-<group-id>` or `git worktree list`
- **Removed**: After successful merge and validation
- **Manual cleanup**: If a session crashes without cleanup: `bash "${CLAUDE_PLUGIN_ROOT}/scripts/worktree-utils.sh" remove <worktree-path>`

## Boundaries

**Will:**
- Create isolated worktrees for safe implementation (one per group)
- Use real compiler feedback (cargo check) to catch errors
- Apply descriptive guidance from directions.json against current file state
- Verify wiring checklists (pub mod, pub use) after each task
- Run acceptance commands as validation
- Commit per-task with descriptive messages
- Recover from interrupted sessions via worktree + checkpoint
- Handle both new implementation and fix application identically

**Will not:**
- Use exact before/after TOML blocks (that's the old approach)
- Implement without compiler feedback
- Modify the main working tree directly (always uses worktree)
- Skip cargo check at any step
- Leave worktrees behind without cleanup
