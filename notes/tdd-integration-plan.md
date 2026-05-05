# Plan: Integrate ch12-04 TDD Pattern into `elaborate-directions`

## Context

The pipeline currently defines TDD as "split test-write tasks from implementation tasks" (`plan-decomposer.md` lines 52, 114, 126). This is **not faithful** to the ch12-04 TDD pattern from the Rust book. True TDD uses the test to **claim the interface first**, then the implementation evolves to meet it — all within the same workflow cycle (same agent context, same task). When tests are a separate task, the implementation agent never sees them and can't use them as a design driver.

**User's insight**: Without a clear TDD reference, LLM agents write shallow, after-the-fact tests that don't drive design. The ch12-04 pattern provides a concrete workflow: claim interfaces/functions via tests first, implement details step by step, and when tests pass, the pre-claimed implementation works naturally.

**Scope**: Library code only (pure logic, no I/O). CLI glue, config wiring, and I/O adapters keep the current workflow.

**Goals**: Reduce fix-to-implement ratio, increase meaningful test coverage, improve implementation quality via interface-first design.

## Approach

Introduce a `kind` field on tasks: `"lib-tdd"` for library code, `"direct"` (default) for everything else. For `lib-tdd` tasks, embed a `tdd_interface` that contains the test-as-specification.

At **elaborate-directions** time: the plan-decomposer produces `lib-tdd` tasks with the test code embedded. The test claims the function signature and expected behavior.

At **explore-implement** time: the orchestrator reads `kind` and dispatches. For `lib-tdd` tasks, it passes `workflow: 'tdd'` to the implementation-executor subagent, which follows the ch12-04 RED → stub compile → GREEN → refactor cycle. For `direct` tasks, the existing edit→check→fix loop is unchanged.

## Path Resolution

All paths to `tdd-pattern.md` use the **relative path from project root**: `skills/elaborate-directions/references/tdd-pattern.md`. This is consistent with the existing convention in `elaborate-directions/SKILL.md` line 121 which references `directions-spec.md` the same way. All subagents and skills launch from the project root, so this relative path resolves correctly from every consumer. No `${CLAUDE_PLUGIN_ROOT}` needed for file paths — that convention is for bash scripts only.

| Consumer | How it references `tdd-pattern.md` | Mechanism |
|----------|-----------------------------------|-----------|
| `elaborate-directions/SKILL.md` step 5 | `skills/elaborate-directions/references/tdd-pattern.md` | Path passed to plan-decomposer subagent via instructions |
| `explore-implement/SKILL.md` step 4 | `skills/elaborate-directions/references/tdd-pattern.md` | Path passed to implementation-executor subagent via instructions |
| `plan-decomposer.md` (agent prompt) | same relative path | Agent reads from project root when instructed by orchestrator |
| `implementation-executor.md` (agent prompt) | same relative path | Agent reads from project root when instructed (for `lib-tdd` tasks) |
| `rust-architect.md` (agent prompt) | same relative path | Agent reads when producing `draft-elaboration.md` |

## `tdd_interface` Schema (the spec)

Added to `directions-spec.md` as a conditional field on tasks. Required when `kind: "lib-tdd"`, must be absent when `kind: "direct"` or absent.

```json
"tdd_interface": {
  "test_file":        "string — path to the .rs file containing (or that will contain) the #[cfg(test)] mod block",
  "test_module":      "string — name of the #[cfg(test)] mod block (e.g. 'tests'). Default 'tests'.",
  "test_fn_name":     "string — the test function name (for cargo test <name> filtering and cross-referencing)",
  "test_code":        "string — the FULL test function definition, including #[test] attribute and fn signature. This is the specification. The implementation agent writes this verbatim.",
  "signature":        "string — the exact function signature being test-driven (the API contract the test calls)",
  "expected_behavior":"string — natural language description of what 'passing' means, for the implementation agent to reason about correctness"
}
```

**Field design rationale:**
- `test_file` + `test_module` are split into two fields (not one ambiguous "path::module" string) to avoid parsing ambiguity. The agent knows exactly which file to edit and which `mod` block to insert into.
- `test_code` contains the **full function definition** (`#[test]\nfn test_foo() { ... }`) — verbatim insertion, no synthesis needed. `test_fn_name` is a convenience field for `cargo test <name>` commands and cross-referencing. Having both means the `test_fn_name` can be used even if `test_code` changes.
- `signature` is the API contract. The implementation must match this signature exactly.
- `expected_behavior` gives the agent a natural-language target to reason about when `cargo test` fails.

## Orchestrator/Agent Handoff

The `explore-implement` orchestrator passes a `workflow` flag to the `implementation-executor` subagent alongside the task data:

- `workflow: 'direct'` — the existing edit→check→fix loop (default)
- `workflow: 'tdd'` — follow the RED → stub → GREEN → refactor cycle

The `implementation-executor` permanent instructions define both paths. The orchestrator selects which path by including `workflow` in the task instructions it passes. This keeps the separation clean: the agent prompt defines behavior, the orchestrator selects it.

## Files to Change

### Core changes:

**1. NEW: `skills/elaborate-directions/references/tdd-pattern.md`**
- Reference document codifying the ch12-04 TDD workflow
- Sections: the 5-step cycle, "test IS the specification", concrete `search` example from ch12-04, anti-patterns (shallow tests, test-after-implementation, splitting test from impl into separate sessions), when NOT to use this pattern

**2. `skills/elaborate-directions/references/directions-spec.md`**
- Add `kind` field to tasks schema: `"lib-tdd"` | `"direct"` (default: `"direct"`)
- Add `tdd_interface` object (required when `kind: "lib-tdd"`, forbidden otherwise) with the 6 sub-fields defined above
- Add "Task Kinds: `lib-tdd` vs `direct`" section explaining when to use each
- Add validation rule: if `kind: "lib-tdd"`, `tdd_interface` must be present with all 6 required sub-fields. If `kind: "direct"` or absent, `tdd_interface` must be absent
- Add a `lib-tdd` example task showing the format
- For `lib-tdd` tasks: `changes[].guidance` should describe the approach/algorithm (data structures, iterator patterns, edge case handling), NOT the interface — the interface is already claimed by `tdd_interface.signature`

**3. `scripts/validate/validate-directions.py`**
- In `validate_tasks()` (line 121): add validation after the existing acceptance validation
  - Validate `kind` is `"lib-tdd"` or `"direct"` if present (else default is valid)
  - Validate `tdd_interface` presence/absence based on `kind`
  - When `tdd_interface` is present, validate all 6 sub-fields (`test_file`, `test_module`, `test_fn_name`, `test_code`, `signature`, `expected_behavior`) are non-empty strings

**4. `agents/plan-decomposer.md`**
- Line 52: "separate 'write failing test' tasks from 'implement' tasks" → "for library code, embed the test as specification within the same task using `kind: 'lib-tdd'` and `tdd_interface`"
- Line 114-115: "Always separate test tasks from implementation tasks (TDD compliance)" → "For library code: always embed the test as specification within the same task using `kind: 'lib-tdd'` and `tdd_interface` (true TDD: the test claims the interface first). For non-library code, use `kind: 'direct'` without embedded tests"
- Line 126 (quality checklist): "TDD tasks are split (test-write → implement → refactor)" → "Library code tasks use `kind: 'lib-tdd'` with a `tdd_interface` that specifies concrete, falsifiable behavior"
- Add new section "TDD Task Design (library code only)" after the Module Wiring Check section:
  - When a plan calls for a new function/struct/module in a library crate, produce ONE task with `kind: "lib-tdd"`
  - `tdd_interface.test_code`: write a complete `#[test] fn` that asserts concrete, falsifiable behavior. Must include the test function signature and body. Must NOT be `assert!(true)` or equivalent trivial assertions
  - `tdd_interface.signature`: the exact function signature the test calls — this is the public API contract
  - `tdd_interface.expected_behavior`: what "passing" means in natural language
  - `tdd_interface.test_file`: the `.rs` file to add the test to
  - `tdd_interface.test_module`: the `#[cfg(test)] mod <name>` block name (usually `"tests"`)
  - `changes[].guidance`: for lib-tdd tasks, describe the implementation APPROACH — algorithm, data structures, edge cases, patterns to use. Do NOT redefine the interface (the test already claims it via `signature`)
  - If the plan calls for both a library function AND a CLI wrapper, create TWO tasks: one `lib-tdd` for the library function, one `direct` for the CLI glue. The CLI task depends on the library task
  - Read `skills/elaborate-directions/references/tdd-pattern.md` for the canonical TDD workflow
- Quality checklist additions:
  - `[ ] Every lib-tdd task's tdd_interface.test_code asserts concrete, falsifiable behavior (not assert!(true))`
  - `[ ] Every lib-tdd task's tdd_interface.signature matches the function signature used in test_code`
  - `[ ] Every lib-tdd task's test_file and test_module are specified`

**5. `agents/implementation-executor.md`**
- Line 41: Replace "Do NOT propose or write tests" with:
  ```
  - **When instructed with `workflow: 'tdd'`**: Follow the TDD red-green-refactor cycle below. The task's `tdd_interface` contains the test as specification — write it verbatim first, then implement to satisfy it. Do NOT change the test code.
  - **When instructed with `workflow: 'direct'` (or default)**: Do NOT propose or write tests unless the task description explicitly includes test changes. Focus on implementation.
  ```
- Add "Path B: TDD Workflow (when `workflow: 'tdd'`)" section after the existing implementation process:
  - **T1 (RED)**: Read `tdd_interface`. Write `test_code` verbatim into `test_file` inside `#[cfg(test)] mod <test_module>`. Run `cargo test -p <crate> <test_fn_name>` — must fail or not compile. If it passes on first run, flag as "false green" (test too weak).
  - **T2 (Stub)**: Write a minimal stub for `signature` — just enough to compile. Return empty vec/None/0/default. Run `cargo check` (fix up to 5x). Run `cargo test -p <crate> <test_fn_name>` — should FAIL for behavioral reasons (wrong return value), not panic. If test passes with stub, flag as "false green."
  - **T3 (GREEN)**: Implement the actual logic following `changes[].guidance`. After each meaningful increment, run `cargo check` (fix up to 5x per increment), then `cargo test`. Loop until passing (up to 5 full implementation iterations).
  - **T4 (Refactor)**: If guidance suggests improvements or implementation has obvious duplication, refactor the production code. Run `cargo test` after each step — must stay GREEN.
  - **T5 (Verify)**: Verify `wiring_checklist` items, run `acceptance` commands (which for TDD tasks should include `cargo test -p <crate>`).
- Quality gates additions:
  - `[ ] For tdd tasks: test was written first and confirmed RED before implementation`
  - `[ ] For tdd tasks: test passes (GREEN) after implementation`
  - `[ ] For tdd tasks: test_code was NOT changed during implementation (the spec stays constant)`

**6. `skills/elaborate-directions/SKILL.md`**
- Step 5 (Task Decomposition, line 121): add `- skills/elaborate-directions/references/tdd-pattern.md` to the subagent inputs list (after the existing `directions-spec.md` line)
- Step 5 output instructions (lines 123-130): add:
  - `For library code tasks, use kind: "lib-tdd" with a tdd_interface that embeds the test as specification. Follow the TDD pattern in tdd-pattern.md.`
  - `For non-library code tasks, use kind: "direct" (or omit kind).`
- Step 6 (Clarity Review): add to the subagent instructions:
  - `For each lib-tdd task: is tdd_interface.test_code a meaningful specification (not trivial)? Does it assert concrete, falsifiable behavior? Does signature match the function called in test_code?`
- Step 7 (Orchestrator Refinement): after validation (line 163), add:
  - `If any task uses kind: "lib-tdd", ensure architecture_notes includes: "Library code in this phase follows ch12-04 TDD: tests claim interfaces first via tdd_interface, then implementations evolve to meet them. See skills/elaborate-directions/references/tdd-pattern.md."`

**7. `skills/explore-implement/SKILL.md`**
- Step 4.1 (line 80): add `kind` and `tdd_interface` to the fields read: `description, kind, tdd_interface, files_in_scope, changes, wiring_checklist, type_reference, acceptance`
- Step 4: add dispatch at the top of the per-task loop:
  ```
  Before step 4.1, check task.kind:
    If kind is "lib-tdd": instruct the implementation-executor subagent with workflow: 'tdd' and the task data.
      Tell the agent to read skills/elaborate-directions/references/tdd-pattern.md.
      After the agent reports GREEN:
      - Verify wiring_checklist items
      - Run acceptance commands
      - Commit: "feat(<plan-slug>): <task-id> (TDD): <description>"
    If kind is "direct" or absent: follow the existing 8-step process unchanged.
  ```
- Update failure section: add TDD-specific diagnostics (which phase failed: test compilation, stub, implementation, refactor)
- Step 5 (Workspace Validation): after `cargo check --workspace` and `cargo clippy --workspace`, add `cargo test -p <package>` scoped to the task's crate. (Step 6 already runs `cargo test --workspace` as the final integration gate, so step 5 only needs crate-scoped tests as a pre-merge gate.)

### Secondary changes:

**8. `agents/rust-architect.md`**
- After line 46 (end of TDD section): add `- See skills/elaborate-directions/references/tdd-pattern.md for the canonical ch12-04 TDD workflow.`
- When producing `draft-elaboration.md`, flag which goals are library code (candidates for `lib-tdd`) and which are plumbing (candidates for `direct`)

**9. `agents/impl-plan-reviewer.md`**
- Add check #7: `For lib-tdd tasks: Is the test code in tdd_interface.test_code specific and falsifiable? A test that only calls a function without asserting anything, or that asserts assert!(true), is not a valid specification. Flag it.`
- Add verdict: `WEAK SPEC — the tdd_interface exists but the test code is trivial/underspecified and won't drive implementation`

**10. `skills/make-judgement/SKILL.md`**
- Step 4 (Per-Group Validation): add to strict-code-reviewer instructions: `For each lib-tdd task: verify the test from tdd_interface.test_code exists in the codebase, that it passes (cargo test confirmed during implementation), and that the implementation function matches tdd_interface.signature.`
- Step 5 (Strategic Review): add to rust-architect instructions: `For lib-tdd tasks: does the implementation satisfy tdd_interface.expected_behavior? Is the test adequate (not just happy-path)?`

## Key Design Decisions

**Why embed test_code as a complete `#[test] fn` rather than natural language?**
The user's core concern is that LLM agents write trivial tests when given only natural language descriptions. A concrete, compilable `#[test]` function IS the specification — the implementation agent writes it verbatim, then implements to satisfy it. This prevents shallow tests.

**Why merge test + implementation into one task?**
In ch12-04, the test is not a separate deliverable — it's part of HOW the implementation is done. The test claims the interface; the implementation fills it in. Giving both to the same agent in the same task ensures the test actually drives the implementation.

**Why `kind` field instead of separate task types?**
A single field with dispatch is simpler than separate task schemas. It's backward-compatible (absent `kind` = `"direct"`). It allows mixed groups (some TDD, some direct).

**Why library code only?**
The ch12-04 pattern requires: a pure function with deterministic inputs/outputs, testable without I/O setup, interface designable from caller perspective. CLI glue, config wiring, and I/O adapters violate these constraints.

**Why `test_file` and `test_module` as separate fields?**
A combined "path::module" string is ambiguous to parse. Two explicit fields mean the agent knows exactly which file to edit and which `#[cfg(test)] mod <name>` block to insert into, with no guessing.

**Why explicit `workflow` flag in orchestrator/agent handoff?**
The `implementation-executor` prompt is a static file — it can't inspect the task's `kind` field at runtime. The orchestrator selects the workflow and passes it explicitly, so the agent knows which set of instructions to follow.

## Files NOT Changed

- **`scripts/split-directions.py`**: Copies task objects as-is (`group_tasks.append(all_tasks[tid])` — line 54), so `kind` and `tdd_interface` pass through automatically.
- **`scripts/checkpoint-resume.py`**: Operates at the group level, never inspects individual task fields.

## Implementation Order

| Order | File (full path) | Why |
|-------|------|-----|
| 1 | `skills/elaborate-directions/references/tdd-pattern.md` (NEW) | Foundation — all other changes reference this |
| 2 | `skills/elaborate-directions/references/directions-spec.md` | Schema definition for `kind` and `tdd_interface` |
| 3 | `scripts/validate/validate-directions.py` | Validator depends on schema from step 2 |
| 4 | `agents/plan-decomposer.md` | Producer of tasks; depends on steps 1, 2 |
| 5 | `agents/implementation-executor.md` | Consumer of tasks; depends on steps 1, 2 |
| 6 | `skills/elaborate-directions/SKILL.md` | Orchestrator invoking step 4, validated by step 3 |
| 7 | `skills/explore-implement/SKILL.md` | Orchestrator invoking step 5; steps 5 and 7 designed together |
| 8 | `agents/rust-architect.md` | Light addition; can parallelize with steps 3-7 |
| 9 | `agents/impl-plan-reviewer.md` | Light addition; depends on schema from step 2 |
| 10 | `skills/make-judgement/SKILL.md` | Post-implementation review; last |

Steps 5 and 7 are tightly coupled (orchestrator handoff must align with agent instructions) — they should be designed together before implementing separately.

## Verification

1. **Validator unit tests**: Create test JSON files for: valid lib-tdd (all 6 fields), lib-tdd missing tdd_interface, direct with tdd_interface, lib-tdd missing test_code, lib-tdd with empty test_code, no kind with tdd_interface. Run `validate-directions.py` on each — expect correct pass/fail.

2. **Backward compatibility**: Run `validate-directions.py` on existing directions.json files — expect PASS (all tasks treated as `"direct"`).

3. **End-to-end**: Run `/elaborate-directions` on a phase plan with a library function. Verify output has `kind: "lib-tdd"` tasks with populated `tdd_interface`. Then run `/explore-implement` on the per-group file — verify the orchestrator dispatches `workflow: 'tdd'`, the implementation-executor writes the test first (RED), writes stub, iterates to GREEN, and commits with `(TDD)` suffix.

4. **Mixed plan regression**: Run on a plan with both library and CLI tasks. Verify only library tasks get `kind: "lib-tdd"`, CLI tasks remain `"direct"`, and the explore-implement loop dispatches correctly for both.
