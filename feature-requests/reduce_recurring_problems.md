# Diagnostic Report: `rust-development-pipeline` Plugin — Post-Task Hotfix Pattern

## Context

Across Phases 2.2 through 5B of the `castep_workflow_framework` project, a recurring pattern has emerged: after the `implementation-executor` or `/fix` skill declares tasks complete, additional hotfix commits are consistently required. The fix-to-implementation task ratio ranges from 1.0x to 3.3x, meaning for every implementation task, 1-3 fix tasks follow. This report diagnoses the root causes within the plugin's architecture and proposes targeted improvements.

---

## 1. Problem Taxonomy

Analysis of all fix plans across 8 phases reveals **10 recurring failure categories**, ordered by frequency:

| # | Category | Phases Observed | Examples |
|---|----------|----------------|----------|
| 1 | Missing `pub mod` declarations | 3, 5B | Created `prelude.rs` but never added `pub mod prelude;` to `lib.rs` |
| 2 | Missing `pub use` re-exports | 3, 4, 5 | `TaskSuccessors`, `JOB_SCRIPT_NAME` not re-exported at crate root |
| 3 | Incomplete task delivery | 5, 5B | "Create prelude modules" → file created but not wired, consumers not updated |
| 4 | Clippy/lint violations left behind | 3, 5B | `uninlined_format_args` in files that were touched but not fully linted |
| 5 | Stale imports after refactoring | 3, 4, 5B | `use ProcessHandle` left after type was removed from scope |
| 6 | Cross-module integration failures | 4 | BFS function placed in CLI instead of `workflow_core`, migrated over 3 rounds |
| 7 | Type mismatch cascades | 5B | Generic `AsRef<str>` change broke 6 test call sites due to ambiguity |
| 8 | Newtype encapsulation churn | 4 | `TaskSuccessors::inner()` introduced then removed one round later |
| 9 | Logic/correctness bugs | 3 | `.with_extension(".tmp")` producing `foo..tmp`; closure never called |
| 10 | Missing OS/infrastructure wiring | 3 | `signal-hook` not in `Cargo.toml` despite handler code being written |

---

## 2. Root Cause Analysis

### 2.1 The Compiled Script Pipeline Has No Module-Wiring Awareness

**The core problem:** The `/compile-plan` skill generates `sd -F` scripts that perform text substitutions. These scripts faithfully apply the `before`/`after` blocks from the TOML plan. But the TOML plans themselves are produced by the `plan-decomposer` agent, which frequently omits the "wiring" changes needed to make new code reachable.

**Why it happens:** Creating a file (`workflow_core/src/prelude.rs`) and declaring it in the module tree (`pub mod prelude;` in `lib.rs`) are treated as the same task by the plan-decomposer. But the plan-decomposer often produces a `[[changes]]` block for the new file only, omitting the `lib.rs` change. Since the compiled script only applies what's in the TOML, the module is dead on arrival.

**Where in the pipeline:** `plan-decomposer` agent → missing `[[changes]]` entries for `lib.rs`/`mod.rs` wiring.

### 2.2 No Workspace-Level Compilation Gate

**The core problem:** The `verify_impl_task.py` hook runs acceptance commands from the TOML plan. These are typically `cargo check -p <single_crate>` or `cargo test -p <single_crate>`. This catches errors within one crate but not cross-crate breakages.

**Why it matters:** Missing re-exports (category #2) and stale imports (category #5) only surface when a downstream crate tries to use the symbol. Per-crate checks pass because the crate compiles fine in isolation — the missing `pub use` doesn't cause an error in the crate that defines the symbol, only in the crate that imports it.

**Where in the pipeline:** `verify_impl_task.py` hook → runs only task-specific acceptance commands. No workspace-wide validation between tasks.

### 2.3 The Implementation-Executor Agent Model Is `haiku` — Low Reasoning Capacity

**The core problem:** The `implementation-executor` agent uses `model: haiku`. In the current pipeline design, this agent only runs a pre-compiled script (2 bash commands: prepare sidecar + run script). The PostToolUse hook stops it immediately after. So the model choice is defensible for execution.

**However:** When the compiled script fails (exit code != 0), the agent prompt says "Do NOT attempt manual implementation." This means a haiku-level agent cannot diagnose or recover from failures. The retry mechanism just re-runs the same script 3 times. If the failure is due to a wrong `before` pattern in the TOML (which is common after prior tasks have shifted content), all 3 retries fail identically.

**Where in the pipeline:** `agents/implementation-executor.md` → `model: haiku` + retry-same-script-3-times logic.

### 2.4 The Review Pipeline Catches Issues Too Late

**The core problem:** The `/review-pr` skill is thorough — 5 agents evaluate the code across 4 axes. But it runs *after* implementation is done. The errors it catches (categories #1-5) are structural and predictable. They could be prevented by validation rules at plan time or execution time, rather than caught at review time.

**The cost:** Each review-fix cycle involves:
1. `/review-pr` launches 5 agents (rust-architect, strict-code-reviewer x2, plan-decomposer, fix-plan-reader)
2. Produces a new `fix-plan.toml`
3. `/fix` compiles and executes it (1 agent per task)
4. `/review-pr` runs again to verify

This is 10+ agent invocations per cycle. Phases with 3+ cycles (Phase 3: ~6 rounds, Phase 4: 5 rounds) consume substantial resources for issues that are structurally preventable.

### 2.5 The Plan-Decomposer Produces Narrowly-Scoped Tasks

**The core problem:** The `plan-decomposer` agent follows strict SRP (Single Responsibility Principle), which is correct for code but counterproductive for task scoping. It separates "create the file" from "wire the module" from "update consumers" — each as independent tasks. But these are semantically atomic: a file without a `pub mod` declaration is unreachable dead code.

**Evidence:**
- Phase 5B TASK-9: "Create prelude modules" created the file but scope excluded `lib.rs` wiring and consumer updates. Review scored it 55% complete.
- Phase 5 TASK-1: `JOB_SCRIPT_NAME` constant defined but consumers still used hardcoded `"job.sh"`.
- Phase 4: `TaskSuccessors` introduced without re-export, fixed in next round.

**Where in the pipeline:** `agents/plan-decomposer.md` → SRP enforcement without "completeness envelope" checks.

---

## 3. Proposed Improvements

### 3.1 Add a Module-Wiring Checklist to the Plan-Decomposer

**Target:** `agents/plan-decomposer.md`

Add a mandatory post-decomposition validation rule:

> **Module Wiring Check (Rust-specific):** For every task that creates a new `.rs` file:
> 1. The task MUST include a `[[changes]]` entry adding `pub mod <name>;` to the parent module's `lib.rs` or `mod.rs`
> 2. If the new file defines public types/functions intended for external use, the task MUST include a `[[changes]]` entry adding them to the crate's `pub use` re-exports
> 3. If the plan mentions "update consumers" or "adopt X in Y", the consumer-side changes are part of the SAME task, not a separate one

This converts a post-hoc review finding into a structural plan-time guarantee.

### 3.2 Add Workspace-Level Validation to the SubagentStop Hook

**Target:** `hooks/verify_impl_task.py`

After running task-specific acceptance commands, add a mandatory `cargo check --workspace` step:

```python
# After task-specific acceptance commands pass:
workspace_check = run_command("cargo check --workspace 2>&1", PROJECT_DIR)
results.append(workspace_check)
if workspace_check["exit_code"] != 0:
    all_passed = False
```

This catches cross-crate breakages (missing re-exports, stale imports) immediately, rather than deferring to the next review cycle. The cost is ~5-15 seconds per task but saves entire review-fix cycles.

**Consider:** Making this configurable via a sidecar field (`workspace_check: true/false`) so it can be disabled for known single-crate tasks.

### 3.3 Add a Post-Execution Lint Sweep to `/fix` and `/implementation-executor` Skills

**Target:** `skills/fix/SKILL.md`, `skills/implementation-executor/SKILL.md`

After all tasks complete but before the final commit, add:

```
4. **Run workspace-wide lint sweep**:
   - `cargo clippy --workspace -- -D warnings`
   - If clippy finds warnings in files touched by ANY task in this round, create inline fix tasks
   - This catches lint regressions (category #4) before the review cycle
```

Currently, step 4 in `/fix` says "run `cargo clippy`" but only suggests `--fix` to the user. It should be automated: if clippy warnings exist in files the round touched, fix them in-place.

### 3.4 Add a "Completeness Envelope" Rule to the Plan-Decomposer

**Target:** `agents/plan-decomposer.md`

Add to the quality checklist:

> **Completeness Envelope:** Every task must leave the codebase in a compilable, reachable state. A task that creates a new symbol must also wire it (module declaration + re-export + at least one consumer call site). If the plan says "create X and update Y to use X", both changes are one task — not two. Test with the question: "If I run `cargo check --workspace` after this task alone, does it pass? Is the new code reachable?"

### 3.5 Upgrade Failure Recovery Beyond "Retry Same Script"

**Target:** `skills/fix/SKILL.md`, `skills/implementation-executor/SKILL.md`

Current retry logic re-runs the same compiled script 3 times. If the `before` pattern doesn't match (because a prior task shifted content), all 3 retries fail.

Proposed: On compiled script failure, before retrying:
1. Read the TOML task to extract the `before` content
2. Grep the target file for a substring of the `before` content
3. If the substring exists but the full match doesn't (content shifted), regenerate the script with updated context
4. If the substring doesn't exist at all, the change may already be applied — check if `after` content is present

This converts brittle pattern-matching failures into diagnosable, recoverable situations.

### 3.6 Add Cross-Round Pattern Data to the Plan-Decomposer Context

**Target:** `skills/enrich-phase-plan/SKILL.md`

Step 1.5 already loads deferred improvements. Add:

> Also load cross-round pattern data from prior fix plans:
> - Read `notes/pr-reviews/*/fix-plan.toml` for the most recent 3 phases
> - Extract the recurring issue categories (missing `pub mod`, missing re-exports, incomplete consumer updates)
> - Pass these to the plan-decomposer as "known failure modes" so it can proactively check for them

### 3.7 Consider a "Dry-Run Compilation" Step After Plan Decomposition

**Target:** `skills/enrich-phase-plan/SKILL.md` or new skill

After the plan-decomposer produces the TOML, but before execution:
1. Apply all changes to a temporary worktree (`git worktree add`)
2. Run `cargo check --workspace` on the worktree
3. If compilation fails, feed errors back to the plan-decomposer for plan revision
4. Clean up the worktree

This is the nuclear option — it validates the entire plan's end state before any execution begins. It catches categories #1-2 and #5-6 structurally. The cost is one full compilation cycle, but it eliminates multi-round review-fix loops entirely.

---

## 4. Priority Matrix

| # | Improvement | Effort | Impact | Categories Addressed |
|---|-------------|--------|--------|---------------------|
| 3.1 | Module-wiring checklist | Low | High | #1, #2, #3 |
| 3.4 | Completeness envelope rule | Low | High | #3, #5 |
| 3.2 | Workspace-level validation in hook | Medium | High | #2, #5, #6 |
| 3.3 | Post-execution lint sweep | Low | Medium | #4 |
| 3.5 | Smarter failure recovery | Medium | Medium | All script failures |
| 3.6 | Cross-round pattern data | Low | Low-Medium | Systemic prevention |
| 3.7 | Dry-run compilation | High | Very High | #1-2, #5-7 |

**Recommended implementation order:** 3.1 → 3.4 → 3.2 → 3.3 → 3.5 → 3.6 → 3.7

---

## 5. Quantitative Impact Estimate

Based on historical data:
- Categories #1-3 (module wiring + incomplete delivery) account for ~40% of all fix tasks
- Category #4 (lint violations) accounts for ~15%
- Categories #5-6 (stale imports + cross-module integration) account for ~20%

Implementing improvements 3.1, 3.2, 3.3, and 3.4 would address ~75% of recurring fix tasks. At current rates (5-30 fix tasks per phase, each requiring an agent invocation + review cycle), this could reduce post-implementation fix rounds from 3-5 per phase to 1-2.
