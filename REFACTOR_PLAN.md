# Refactor Pipeline: Eliminate the "Mental Dance"

## Context

The `rust-development-pipeline` orchestrates LLM agents to plan, implement, and review Rust code changes. Its current architecture (split-session branch) separates planning (TOML before/after blocks) from execution (compiled `sd` scripts). After real-world usage across multiple projects, 9 GitHub issues reveal a fundamental flaw: **LLM agents at every stage deduce code impact from static analysis only — a "mental dance" with no compiler feedback loop.**

This causes:
- Cross-task before-block staleness (Issue #9): 32 before-blocks verified against pre-execution snapshot go stale during execution
- Incorrect API usage, unused imports, clippy violations (Issue #9): 38 errors survive Sonnet+Opus chain
- Recurring missing `pub mod`/`pub use` (Issue #3, feature-request): ~40% of all fix tasks
- Gather output quality failures (Issues #3, #5): invalid TOML, self-contradictions, invented fields

The split-session gather/judge pattern added complexity but didn't fix the root cause — neither session touches a compiler.

## Vision (from REFACTOR_PROPOSAL.md + user confirmation)

1. **Replace "gather" with "explore/experiment"**: Local LLM agents implement in worktrees with real `cargo check` feedback, adjusting from errors — no more static drafting
2. **Cloud LLMs only plan and judge**: Cloud LLM → architectural direction + final validation. Local LLM → all implementation
3. **"Elaborated directions" replace TOML before/after blocks**: Descriptive guidance (which files, what to change), not exact text replacements that go stale
4. **Context management by role**: Each agent gets minimum viable context for its role, not the entire codebase

## Refactored Pipeline (5 stages, down from 9)

```
PLAN AND JUDGE (high-capability model)
=======================================
Stage 1: /next-phase-plan        → PHASE_PLAN.md
Stage 2: /plan-review            → decisions.md
Stage 3: /elaborate-directions   → directions.json  (NEW — replaces enrich-plan-gather+judge)

EXPLORE AND IMPLEMENT (cost-effective model)
=============================================
Stage 4: /explore-implement      → validated commits  (NEW — replaces compile-plan+implementation-executor + fix)

VALIDATE (high-capability model)
=================================
Stage 5: /make-judgement         → review.md + fix-directions.json  (NEW — replaces review-pr-gather+judge)

LOOP: fix-directions.json from Stage 5 feeds back into Stage 4 for fix application.
```

### Key Design Decisions

1. **No TOML before/after blocks**: Replaced by `directions.json` with descriptive guidance + type references + wiring checklists. The local LLM reads current file state at implementation time — staleness impossible.

2. **Worktree-based implementation**: `/explore-implement` creates a git worktree. Local LLM agents edit code, run `cargo check`, read compiler errors, fix, repeat — capped at 5 iterations per task.

3. **Task groups replace per-task isolation**: Cloud LLM groups related tasks (e.g., all touching `workflow_core/`). Local LLM gets all tasks in a group simultaneously — eliminates cross-task staleness.

4. **Judge works from diff, not raw files**: `/make-judgement` reads `git diff` against directions.json. Strategic validation only — compiler already caught syntax/type errors.

5. **`rust-workspace-map` designed for but not depended on**: Pipeline works without it via LSP/Glob. When ready, provides O(1) codebase lookups that reduce token costs ~50%.

6. **Three-tier exploration model**: The `/explore-implement` stage supports three levels of parallelism, escalating as task complexity grows. See "Exploration Model" below. Also handles fix application — when fed `fix-directions.json` (output of `/make-judgement`), it applies the same edit→check→fix loop to resolve defects.

7. **Structured issue filing**: A `/file-issue` skill lets pipeline users file bug reports from any project directly to the `rust-development-pipeline` repo with auto-gathered context — lowering friction for reporting pipeline defects encountered during daily use.

8. **Fix loop is integrated**: `/fix` is merged into `/explore-implement`. The judge produces `fix-directions.json`, which feeds back into the same worktree-based explore→implement→validate cycle. No separate `/fix` skill needed — the edit→check→fix loop is identical for both first-time implementation and fix application.

### Exploration Model (replaces "Breakpoint Resume")

The original "breakpoint resume" design assumed we could instrument a subagent mid-execution. In reality, Claude Code hooks only see `last_assistant_message` when the subagent stops — we cannot peek into a running subagent's context. The practical design is simpler and more honest.

**Core insight**: The worktree IS the checkpoint. A fresh agent can always resume by reading the worktree files + the last compiler output + the directions.

**Worktree persistence**: Git worktrees are filesystem entities, not tied to Claude Code's process lifecycle. If a session crashes, is killed, or is closed by the user, the worktree directory (e.g., `/tmp/phase-3.1-group-core`) and all its files survive. They persist until explicitly removed via `git worktree remove`. The worktree metadata is stored in the main repo's `.git/worktrees/` directory. This means:

- A session can be interrupted at any point — the worktree preserves all changes
- The next session reads `git worktree list` to discover existing worktrees
- Deterministic naming (`/tmp/{plan-slug}-{group-id}`) makes worktrees discoverable without a separate registry

**Resume protocol** (when `/explore-implement` starts):
1. Check for existing worktree at the deterministic path, or via `git worktree list | grep {plan-slug}`
2. If found: inspect `git -C {worktree} log --oneline` to see completed commits, `git -C {worktree} diff HEAD` for uncommitted changes, and any `exploration_checkpoint.json` in the worktree root
3. Cross-reference against `directions.json` to determine which task groups are done vs remaining
4. Continue from the first incomplete task group

#### Tier 1: Main Agent Sequential (default for most tasks)

The `/explore-implement` orchestrator implements each task group sequentially. This same process applies whether the input is `directions.json` (new implementation) or `fix-directions.json` (fixes):

```
For each task_group in directions:
  1. Read directions for all tasks in group
  2. Read files_in_scope for all tasks
  3. Implement changes with Edit tool
  4. Run cargo check → read errors → fix → goto 4 (max 5 iterations per change)
  5. Verify wiring_checklist (rg for pub mod, pub use)
  6. Run acceptance commands
  7. Commit to worktree
```

**Why this works**: Claude Code's **auto-compress** handles context saturation automatically. As the conversation grows, old messages (early compiler outputs, earlier task implementations) get compressed. The agent retains the current task's context + compressed summaries of prior work. No explicit checkpoint mechanism needed — auto-compress IS the context management.

**Resume on interruption**: If the user interrupts (or the session crashes), the worktree preserves all changes. Restarting `/explore-implement` detects the existing worktree, reads current state, and continues from the last incomplete task group. Users naturally monitor local LLM sessions and manually interrupt when the agent hangs due to context saturation — the worktree ensures no work is lost.

#### Tier 2: Subagent Parallelism (independent task groups)

When task groups are truly independent (no shared files), the main agent spawns one subagent per group:

```
For each independent task_group (parallel):
  Spawn implementation-executor subagent:
    - worktree: {shared_worktree_path}
    - directions: {directions_path}#task_group
    - Tasks: {task_ids in group}
    - Iteration limit: 5 per change
```

Each subagent returns one of three states:
- **`COMPLETED`**: All tasks in group done, acceptance passed, committed
- **`FAILED`**: Hit iteration limit, last compiler error reported in message
- **`INCOMPLETE`**: Made partial progress before context saturation

The orchestrator reads each subagent's `last_assistant_message` (available via SubagentStop hook or direct inspection). For FAILED/INCOMPLETE groups, the orchestrator can relaunch a fresh subagent — the worktree already has the partial changes, and the last message describes what to do next.

**The "checkpoint" is just the subagent's final message + the worktree files.** The hook (or orchestrator) reads `last_assistant_message`, extracts the structured state (task progress, last error, resume hint), and passes it to the next subagent.

#### Tier 3: Multi-Session via tmux (maximum parallelism)

For large plans with many independent task groups, the user or a launcher script spawns separate Claude Code sessions, each with its own worktree:

```
tmux new-session -s phase-3.1-group-core  "claude -p '/explore-implement notes/directions/phase-3.1/directions.json --group group-core'"
tmux new-window -t phase-3.1-group-consumer "claude -p '/explore-implement notes/directions/phase-3.1/directions.json --group group-consumer'"
...
```

Each session:
- Gets its own Claude Code process + full context window
- Has its own git worktree (no file conflicts between sessions)
- Benefits from auto-compress within its session
- The user monitors all tmux panes

When all sessions complete, merge and validate:

```bash
# Step 1: Per-worktree validation (fast feedback — already done in each session)
# Step 2: Merge all worktrees into the feature branch
for worktree in /tmp/phase-3.1-group-*; do
    git -C "$worktree" diff HEAD~N..HEAD > /tmp/patch-$(basename $worktree).patch
done
git apply /tmp/patch-*.patch

# Step 3: Workspace-level validation (catches part/whole misalignment)
cargo check --workspace
cargo clippy --workspace -- -D warnings
cargo test --workspace
```

**Why two-phase validation**: Per-worktree checks catch group-specific errors fast. The "part/whole misalignment" problem — where two groups independently pass but together break the workspace — requires the final merge-then-validate gate.

#### When to Use Each Tier

| Tier | When | Context Management |
|------|------|--------------------|
| Tier 1 (main agent) | Small-medium plans, sequential task groups | Auto-compress built-in |
| Tier 2 (subagents) | 2-4 independent task groups, want parallelism | Subagent final message + worktree state → relaunch |
| Tier 3 (tmux sessions) | 4+ independent groups, large plan | Full context per session, user monitors |

### The `directions.json` Format (core new artifact)

```json
{
  "meta": { "title": "...", "source_branch": "..." },
  "architecture_notes": ["Crate boundary decisions", "Pattern requirements"],
  "known_pitfalls": ["Do NOT separate create-file from wire-module"],
  "task_groups": [
    {
      "group_id": "group-core",
      "reason": "All tasks modify workflow_core/ — shared context",
      "tasks": ["TASK-1", "TASK-2"],
      "depends_on_groups": []
    }
  ],
  "tasks": [
    {
      "id": "TASK-1",
      "description": "Add RetryConfig struct",
      "files_in_scope": ["crates/foo/src/retry.rs", "crates/foo/src/lib.rs"],
      "changes": [
        {
          "path": "crates/foo/src/retry.rs",
          "action": "create",
          "guidance": "Define pub struct RetryConfig with fields: max_retries (u32), backoff (BackoffStrategy enum). Use builder pattern matching existing JobConfig in job.rs."
        }
      ],
      "wiring_checklist": [
        {"kind": "pub_mod", "file": "crates/foo/src/lib.rs", "detail": "retry"},
        {"kind": "pub_use", "file": "crates/foo/src/lib.rs", "detail": "RetryConfig"}
      ],
      "type_reference": {
        "RetryConfig": "pub struct RetryConfig { pub max_retries: u32, ... }"
      },
      "acceptance": ["cargo check -p foo", "cargo test -p foo -- retry"],
      "depends_on": []
    }
  ]
}
```

### Subagent Assignment Principle

Agent model names (Opus, Sonnet, Haiku) are **not changed in agent definitions**. The assignment of subagent vs orchestrator is determined by context management:
- **Subagent**: Process context (intermediate reasoning, tool calls, iterations) can be discarded after the step. Only the output artifact matters.
- **Orchestrator**: Step requires context continuity — later steps build on what was learned.

A `PostToolUse` hook records token usage per stage to `notes/metrics/{stage}-{date}.jsonl` for data-driven optimization.

### Skill Workflows

#### `/elaborate-directions`

All 5 elaboration steps are **subagents** — each produces one output file; process context is discardable. Only final refinement runs in the orchestrator.

| Step | Who | Input → Output | Purpose |
|------|-----|----------------|---------|
| 1 | **Subagent** (general-purpose) | Prior deferred.md + fix-plan history → `deferred-and-patterns.md` | Load known failure modes |
| 2 | **Subagent** (Explore) | Phase plan + `fd`/`rg` → `codebase-state.md` | Explore codebase (future: workspace-map) |
| 3 | **Subagent** (rust-architect) | Plan + codebase-state + patterns → `draft-elaboration.md` | Design decisions |
| 4 | **Subagent** (plan-decomposer) | Elaboration + codebase-state + spec → `draft-directions.json` | Decompose into tasks |
| 5 | **Subagent** (impl-plan-reviewer) | draft-directions.json + codebase-state → `task-checklist.md` | Clearness assessment |
| 6 | **Orchestrator** | All artifacts → `directions.json` (final) | Refinement, synthesis |

**Key differences from current enrich-plan-gather:**
- Step 4 produces `directions.json` (descriptive guidance + wiring checklists) instead of `draft-plan.toml` (exact before/after blocks).
- Step 5 checks for **guidance clarity** rather than before-block grep verification.
- Step 6 (orchestrator refinement) replaces the separate `enrich-plan-judge` session.
- No TOML compile dry-run. Validation runs `validate-directions.py` instead.

#### `/explore-implement`

Accepts either `directions.json` (new implementation) or `fix-directions.json` (fixes from make-judgement). The exploration loop is identical for both.

| Step | Who | Why | Action |
|------|-----|-----|--------|
| 1 | **Orchestrator** | Context continuity needed | Read input, determine execution tier |
| 2 | **Orchestrator** | Track worktree paths | Create worktree(s) at `/tmp/{plan-slug}-{group-id}` |
| 3a | **Orchestrator** (Tier 1) | Sequential context continuity | Implement groups with edit→check→fix loop |
| 3b | **Subagent** per group (Tier 2) | Independent groups, discardable context | Parallel subagents |
| 3c | **Separate session** (Tier 3) | Full isolation | tmux sessions |
| 4 | **Orchestrator** | Cross-reference results against input | Per-worktree validation |
| 5 | **Orchestrator** | Hold merge state, attribute errors | Merge → `cargo check --workspace` → `cargo clippy` |
| 6 | **Orchestrator** | Synthesize | Write report, clean up |

#### `/make-judgement`

Two analysis steps are **subagents** (process context discardable). Orchestrator synthesizes.

| Step | Who | Action |
|------|-----|--------|
| 1 | **Script** | `gather-diff-data.py` |
| 2 | **Orchestrator** | Read `directions.json` + diff |
| 3 | **Subagent** (strict-code-reviewer) | Validate diff against directions |
| 4 | **Subagent** (rust-architect) | Strategic review |
| 5 | **Orchestrator** | Classify issues → `review.md` + `fix-directions.json` + `deferred.md` |
| 6 | **Script** | `validate-review-consistency.py` |

#### `/file-issue`

| Step | Who | Action |
|------|-----|--------|
| 1 | **Subagent** (general-purpose) | Gather context |
| 2 | **Orchestrator** | Format issue template, present for review |
| 3 | **User** | Review and edit |
| 4 | **Script** | `gh issue create --repo TonyWu20/rust-development-pipeline` |

## What to Keep, Refactor, Remove

### KEPT (unchanged)
- `skills/next-phase-plan/SKILL.md`
- `skills/plan-review/SKILL.md`
- `agents/rust-architect.md`
- `agents/plan-decomposer.md` (repurposed)
- `agents/impl-plan-reviewer.md`
- `agents/strict-code-reviewer.md`
- `scripts/gather-diff-data.py`
- `scripts/validate/validate-review-consistency.py`
- `scripts/validate/validate-fix-document.py`
- `hooks/verify_impl_task.py` (refactored for worktree)

### REFACTORED
- `skills/implementation-executor/SKILL.md` → `skills/explore-implement/SKILL.md` (also handles fix application)
- `hooks/verify_impl_task.py` → extended for checkpoint writes on SubagentStop

### REMOVED
- `skills/compile-plan/` (including `compile_plan.py`, `compilable-plan-spec.md`)
- `skills/enrich-plan-gather/`, `skills/enrich-plan-judge/`, `skills/enrich-phase-plan/`
- `skills/review-pr/`, `skills/review-pr-gather/`, `skills/review-pr-judge/`
- `skills/fix/SKILL.md` (merged into `/explore-implement`)
- `hooks/post_compiled_script.py`
- `scripts/validate/validate-toml-plan.py`, `scripts/validate/validate-fix-plan-application.py`

### NEW
- `skills/elaborate-directions/SKILL.md`
- `skills/explore-implement/SKILL.md`
- `skills/make-judgement/SKILL.md`
- `skills/file-issue/SKILL.md`
- `scripts/validate/validate-directions.py`
- `scripts/worktree-utils.sh`
- `scripts/checkpoint-resume.py`
- `skills/elaborate-directions/references/directions-spec.md`

## Migration Path (4 phases)

### Phase A: New stages (coexist with old)
1. Create `elaborate-directions` + `validate-directions.py` + `directions-spec.md`
2. Create `explore-implement` + `worktree-utils.sh` + `checkpoint-resume.py`
3. Create `file-issue`
4. Update `agents/implementation-executor.md` (role: implement with compiler feedback)
5. Extend `hooks/verify_impl_task.py`
6. Create evals
7. Test on real Rust project

### Phase B: Add make-judgement
1. Create `skills/make-judgement/SKILL.md`
2. Create evals

### Phase C: Deprecate old stages
1. Remove deprecated skills and scripts
2. Update README.md, CHANGELOG.md

### Phase D: Integrate rust-workspace-map (active)
1. Create `scripts/ensure-workspace-map.sh` — dependency check + invocation wrapper
2. Add workspace-map generation to elaborate-directions Step 2.5; update Step 3 to consume map
3. Add workspace-map pre-flight to explore-implement Step 0; feed per-task map context
4. Add workspace-map generation to make-judgement Step 2; update reviewers to use map as ground truth
5. Update rust-architect agent: LSP-First → Map-First exploration
6. Update plan-decomposer agent: add Workspace Map Context section
7. Update implementation-executor agent: map reference in before-code section
8. Update strict-code-reviewer agent: map-first exploration
9. Add rust-workspace-map to pipeline's CLAUDE.md as required dependency
10. Benchmark token reduction

## Verification Strategy

### Per-stage testing
- **elaborate-directions**: Validate directions.json structure and wiring checklist completeness
- **explore-implement**: Verify acceptance commands pass, workspace compiles, clippy clean
- **make-judgement**: Validate fix-directions.json against known defects

### End-to-end test
Go through the full pipeline with a real feature request. Compare error rate against baseline (1.0-3.3x fix-to-implementation task ratio).

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Local LLM can't implement from directions | Keep compile-plan as fallback |
| Context saturation mid-task | Auto-compress (Tier 1) or worktree resume (Tier 2/3) |
| Part/whole misalignment | Two-phase validation: per-worktree + workspace gate |
| Worktree management fragile | `worktree-utils.sh` with cleanup guarantees |
| Breaking existing workflows | Phase A/B coexistence before deprecation |
