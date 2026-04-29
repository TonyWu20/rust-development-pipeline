---
name: explore-implement
description: Implement code changes in a git worktree with real compiler feedback. Accepts directions.json (new implementation) or fix-directions.json (fixes from make-judgement). Uses edit→check→fix loop with up to 5 iterations per change. Use when the user says "/explore-implement <directions-path>", "implement the directions", "apply the fix directions", or after /elaborate-directions completes.
---

# Explore Implement

Implements code changes in a git worktree with real `cargo check` feedback. The core insight: instead of statically deducing code impact (the old "mental dance"), the agent edits code and the compiler tells it what's wrong. This catches incorrect API usage, missing imports, type errors, and clippy violations immediately.

Accepts either `directions.json` (from `/elaborate-directions`) or `fix-directions.json` (from `/make-judgement`). The edit→check→fix loop is identical for both — the only difference is the input format.

## Trigger

`/explore-implement <directions-path> [--group <group-id>]`

Where `<directions-path>` is the path to a `directions.json` or `fix-directions.json` file.

Optional `--group <group-id>` runs only a single task group (for Tier 2/3 parallelism).

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `python3` for checkpoint scripts
- use `bash scripts/worktree-utils.sh` for worktree management

## Process

### Step 1: Read Input and Setup

Read the directions file and determine the plan slug:

```bash
# Read the directions
cat <directions-path>
```

Plan slug: derive from the directions filename (e.g., `notes/directions/phase-3.1/directions.json` → `phase-3.1`, or `fix-directions.json` → use the source plan slug + `-fix`).

### Step 2: Resume Check

Check for existing worktrees from a prior interrupted session:

```bash
python3 scripts/checkpoint-resume.py status <worktree-path>
```

Also check via deterministic path:
```bash
bash scripts/worktree-utils.sh discover <plan-slug>
```

**If a checkpoint exists** with completed groups, skip those and start from the first incomplete group.

### Step 3: Create Worktree

Create a worktree for isolated implementation:

```bash
bash scripts/worktree-utils.sh create <worktree-path> <branch>
```

Where:
- `<worktree-path>` = `/tmp/<plan-slug>-<group-id>` (e.g., `/tmp/phase-3.1-group-core`)
- `<branch>` = `impl/<plan-slug>/<group-id>` (e.g., `impl/phase-3.1/group-core`)

Initialize the checkpoint:

```bash
python3 scripts/checkpoint-resume.py init <directions-path> <worktree-path>
```

### Step 4: Implementation Loop (per task group)

For each pending task group in the directions:

> **if Tier 1 (Sequential — default)**:
> The orchestrator implements each task group directly.
>
> **if Tier 2 (Subagent Parallelism)**:
> Spawn one subagent per independent task group (see "Parallel Execution" below).

#### Per-Task Implementation Process

For each task in the group:

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
   python3 scripts/checkpoint-resume.py complete <group-id> <worktree-path>
   ```

#### If cargo check fails after 5 iterations

Mark the task group as failed with diagnostic info:

```bash
python3 scripts/checkpoint-resume.py failed <group-id> <worktree-path> "Last error: <diagnostic>"
```

Report the failure — do not block other independent groups.

### Step 5: Cross-Group Validation

After all task groups complete:

```bash
# Per-worktree validation
cargo check --workspace 2>&1
cargo clippy --workspace -- -D warnings 2>&1
```

If the user has specified `--group` (parallel execution mode), skip merge — the merging happens in a separate session.

### Step 6: Merge and Report

Merge worktree changes back:

```bash
bash scripts/worktree-utils.sh merge <worktree-path>
```

Then run workspace-level validation:
```bash
cargo check --workspace
cargo clippy --workspace -- -D warnings
cargo test --workspace 2>&1 | tail -20
```

Clean up:
```bash
python3 scripts/checkpoint-resume.py clear <worktree-path>
bash scripts/worktree-utils.sh remove <worktree-path>
```

### Parallel Execution (Tier 2)

When task groups are independent (no shared `files_in_scope`), the orchestrator may launch subagents. The subagent receives the same implementation process above but limited to its group.

Each subagent receives:
- `worktree-path`: The shared worktree path
- `group-id`: Which group to implement
- `directions-path`: The full directions file
- `tasks`: The list of task IDs in this group

The subagent returns one of:
- **`COMPLETED`**: All tasks passed, committed
- **`FAILED`**: Hit iteration limit, last error reported
- **`INCOMPLETE`**: Partial progress before context saturation

The orchestrator reads each subagent's final message to determine next steps. Failed/incomplete groups can be relaunched — the worktree preserves partial progress.

## Fix Application

When the input is `fix-directions.json` (from `/make-judgement`), the process is identical:
- Read the fix directions
- Create/use a worktree
- Apply each fix with the same edit→check→fix loop
- The fix directions follow the same schema as directions.json

## Worktree Lifecycle

- **Created**: At the start of `/explore-implement`
- **Persists**: Across session crashes/interruptions — the filesystem preserves it
- **Discovered**: Via deterministic path `/tmp/<plan-slug>-<group-id>` or `git worktree list`
- **Removed**: After successful merge and validation
- **Manual cleanup**: If a session crashes without cleanup: `bash scripts/worktree-utils.sh remove <worktree-path>`

## Boundaries

**Will:**
- Create isolated worktrees for safe implementation
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
