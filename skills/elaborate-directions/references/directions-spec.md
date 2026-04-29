# directions.json Specification

## Overview

`directions.json` replaces the TOML before/after block format. Instead of specifying exact text replacements that go stale, it provides **descriptive guidance + wiring checklists** that a local LLM agent interprets at implementation time against current file state.

## Schema

```json
{
  "meta": {
    "title": "string — phase/sprint identifier",
    "source_branch": "string — the branch this plan targets"
  },
  "architecture_notes": [
    "string — crate boundary decisions, pattern requirements, design constraints"
  ],
  "known_pitfalls": [
    "string — things to watch out for, common mistakes, anti-patterns to avoid"
  ],
  "task_groups": [
    {
      "group_id": "string — unique group identifier (e.g. 'group-core')",
      "reason": "string — why these tasks are grouped (shared files, shared concern)",
      "tasks": ["string — task IDs in this group"],
      "depends_on_groups": ["string — group IDs that must complete first"]
    }
  ],
  "tasks": [
    {
      "id": "string — unique task identifier (e.g. 'TASK-1')",
      "description": "string — what this task accomplishes",
      "files_in_scope": [
        "string — file paths relative to repo root that this task touches"
      ],
      "changes": [
        {
          "path": "string — file path relative to repo root",
          "action": "create|modify|delete",
          "guidance": "string — descriptive instructions on what to change (NOT exact before/after blocks)"
        }
      ],
      "kind": "string — 'lib-tdd' for library code with test-driven development; 'direct' (or absent) for all other tasks. Defaults to 'direct'.",
      "tdd_interface": {
        "test_file": "string — path to the .rs file containing the #[cfg(test)] mod block",
        "test_module": "string — name of the #[cfg(test)] mod block (e.g. 'tests'). Default: 'tests'.",
        "test_fn_name": "string — the test function name (for cargo test <name> filtering)",
        "test_code": "string — the FULL test function definition, including #[test] attribute and fn signature. The implementation agent writes this verbatim.",
        "signature": "string — the exact function signature being test-driven (the API contract)",
        "expected_behavior": "string — natural language description of what 'passing' means"
      },
      "wiring_checklist": [
        {
          "kind": "pub_mod|pub_use|fn_call|type_annotation",
          "file": "string — file to verify",
          "detail": "string — what to check (e.g. module name, imported items)"
        }
      ],
      "type_reference": {
        "TypeName": "string — type signature/definition for reference"
      },
      "acceptance": [
        "string — shell commands to validate (e.g. 'cargo check -p foo')"
      ],
      "depends_on": ["string — task IDs that must complete first"]
    }
  ]
}
```

## Field Semantics

### Top-level

| Field | Required | Description |
|-------|----------|-------------|
| `meta` | Yes | Plan metadata |
| `meta.title` | Yes | Human-readable plan name |
| `meta.source_branch` | Yes | The feature branch this plan targets |
| `architecture_notes` | No | Design constraints that apply to ALL tasks |
| `known_pitfalls` | No | Anti-patterns and known failure modes |
| `task_groups` | Yes | Defines grouping and ordering of tasks |
| `tasks` | Yes | The actual task definitions |

### task_groups[]

| Field | Required | Description |
|-------|----------|-------------|
| `group_id` | Yes | Unique identifier within this plan |
| `reason` | Yes | Justification for grouping — used by orchestrator to decide parallelism |
| `tasks` | Yes | Array of task IDs belonging to this group |
| `depends_on_groups` | No | Groups that must be implemented before this one |

### tasks[]

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique task identifier |
| `kind` | No | Task workflow: `"lib-tdd"` for library code with TDD (see Task Kinds below); `"direct"` (default) for all other tasks. |
| `description` | Yes | What this task accomplishes |
| `files_in_scope` | Yes | All files this task may touch |
| `changes` | Yes | Descriptive guidance per file |
| `tdd_interface` | Conditional | Required when `kind: "lib-tdd"`. Embeds the test-as-specification that drives implementation. Forbidden when `kind: "direct"` or absent. |
| `wiring_checklist` | No | Module wiring to verify after implementation |
| `type_reference` | No | Key type signatures for reference |
| `acceptance` | Yes | Validation commands |
| `depends_on` | No | Task-level dependencies |

### tdd_interface[]

| Field | Required | Description |
|-------|----------|-------------|
| `test_file` | Yes | Path to the `.rs` file containing the `#[cfg(test)]` module where the test goes |
| `test_module` | No | Name of the `#[cfg(test)] mod <name>` block. Default: `"tests"` |
| `test_fn_name` | Yes | The test function name (used for `cargo test <name>` filtering) |
| `test_code` | Yes | The FULL test function definition, including `#[test]` attribute and `fn` signature. Written verbatim by the implementation agent. |
| `signature` | Yes | The exact function signature being test-driven — the API contract the implementation must satisfy |
| `expected_behavior` | Yes | Natural language description of what passing means (guides the implementation agent when tests fail) |

### changes[].action

- **`create`**: Create a new file. `guidance` should describe the structs/traits/functions to define.
- **`modify`**: Modify an existing file. `guidance` should describe what to add/change.
- **`delete`**: Remove a file. `guidance` is optional.

### change guidance for `lib-tdd` tasks

When `kind` is `"lib-tdd"`, `changes[].guidance` should describe the
implementation approach — algorithm, data structures, iterator patterns, edge
case handling. The guidance must NOT redefine the function signature or
interface, because the interface is already claimed by
`tdd_interface.signature` (the test-as-specification).

## Task Kinds: `lib-tdd` vs `direct`

The `kind` field determines how `explore-implement` processes the task.

### `direct` (default)

The existing workflow. The implementation agent applies changes per guidance,
runs `cargo check`, verifies wiring checklists. No test-driven workflow. Use
for:

- CLI argument parsing and command wiring
- Configuration file generation
- `Cargo.toml` and build configuration changes
- I/O adapters (database, HTTP, filesystem)
- `main.rs` glue code
- Any code where the interface is dictated by external constraints

### `lib-tdd`

The ch12-04 TDD workflow. The `tdd_interface` embeds a complete test function
that the implementation agent writes FIRST — before any implementation code.
The test claims the interface; the implementation evolves to satisfy it. Use
for:

- Library crate functions with deterministic input/output
- Data structure implementations
- Pure logic where the interface can be designed from the caller's perspective
- Any code testable without I/O setup

**Process**: See `skills/elaborate-directions/references/tdd-pattern.md` for
the full workflow. In summary: RED (write failing test) → stub → GREEN
(implement) → refactor → verify.

## Validation Rules

1. Every `task_id` referenced in `task_groups[].tasks` must exist in `tasks[]`.
2. Every `task_id` referenced in `depends_on` must exist in `tasks[]`.
3. Every `group_id` referenced in `depends_on_groups` must exist in `task_groups[]`.
4. No circular dependencies between task groups.
5. No circular dependencies between tasks.
6. Each `task.id` must be unique across the document.
7. Each `group_id` must be unique across the document.
8. Every `changes[].path` must be unique within a task (no two changes to the same file in one task).
9. `changes[].action` must be one of: `create`, `modify`, `delete`.
10. If `kind` is `"lib-tdd"`, `tdd_interface` must be present with all required sub-fields. If `kind` is `"direct"` or absent, `tdd_interface` must be absent.

## Example

```json
{
  "meta": {
    "title": "Phase 3.1: Add retry logic to workflow_core",
    "source_branch": "feature/retry-logic"
  },
  "architecture_notes": [
    "RetryConfig lives in workflow_core; the CLI crate imports it via lib.rs re-export"
  ],
  "known_pitfalls": [
    "Do NOT add new dependencies to Cargo.toml — use existing deps only"
  ],
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
      "description": "Add RetryConfig struct and BackoffStrategy enum to workflow_core",
      "files_in_scope": [
        "crates/workflow_core/src/retry.rs",
        "crates/workflow_core/src/lib.rs"
      ],
      "changes": [
        {
          "path": "crates/workflow_core/src/retry.rs",
          "action": "create",
          "guidance": "Define pub enum BackoffStrategy with variants: Exponential, Constant, Linear. Each variant carries a duration_secs: u64. Define pub struct RetryConfig with fields: max_retries (u32), backoff (BackoffStrategy), timeout_secs (u64). Implement Default for RetryConfig with reasonable defaults. Derive Debug, Clone, PartialEq."
        },
        {
          "path": "crates/workflow_core/src/lib.rs",
          "action": "modify",
          "guidance": "Add pub mod retry; in the module declarations section."
        }
      ],
      "wiring_checklist": [
        {"kind": "pub_mod", "file": "crates/workflow_core/src/lib.rs", "detail": "retry"},
        {"kind": "pub_use", "file": "crates/workflow_core/src/lib.rs", "detail": "RetryConfig, BackoffStrategy"}
      ],
      "type_reference": {
        "RetryConfig": "pub struct RetryConfig { pub max_retries: u32, pub backoff: BackoffStrategy, pub timeout_secs: u64 }",
        "BackoffStrategy": "pub enum BackoffStrategy { Exponential(u64), Constant(u64), Linear(u64) }"
      },
      "acceptance": ["cargo check -p workflow_core", "cargo test -p workflow_core"],
      "depends_on": []
    },
    {
      "id": "TASK-2",
      "kind": "lib-tdd",
      "description": "Implement search function via TDD — test claims interface, implementation evolves to meet it",
      "files_in_scope": ["crates/minigrep/src/lib.rs"],
      "changes": [
        {
          "path": "crates/minigrep/src/lib.rs",
          "action": "modify",
          "guidance": "Add the search function per the TDD cycle. The test (tdd_interface.test_code) defines the contract. Implementation approach: iterate with lines(), filter using contains(), collect matching lines into Vec<String>. Handle edge case: empty query returns empty vec. The signature is defined in tdd_interface.signature — match it exactly."
        }
      ],
      "tdd_interface": {
        "test_file": "crates/minigrep/src/lib.rs",
        "test_module": "tests",
        "test_fn_name": "test_search_one_result",
        "test_code": "#[test]\nfn test_search_one_result() {\n    let query = \"duct\";\n    let contents = \"\\\nRust:\nsafe, fast, productive.\nPick three.\";\n    assert_eq!(vec![\"safe, fast, productive.\"], search(query, contents));\n}",
        "signature": "pub fn search(query: &str, contents: &str) -> Vec<&str>",
        "expected_behavior": "Returns only the lines from contents that contain the query string. Returns empty vec if no lines match."
      },
      "wiring_checklist": [
        {"kind": "pub_mod", "file": "crates/minigrep/src/lib.rs", "detail": "search function is pub"}
      ],
      "type_reference": {
        "search": "pub fn search(query: &str, contents: &str) -> Vec<&str>"
      },
      "acceptance": ["cargo test -p minigrep"],
      "depends_on": []
    }
  ]
}
```

> **Note**: TASK-1 uses `kind: "direct"` (implicit) — the TOML-style approach with
descriptive guidance for struct/enum creation. TASK-2 uses `kind: "lib-tdd"` —
the test in `tdd_interface.test_code` IS the specification; the implementation
agent writes it FIRST, then implements to satisfy it.
