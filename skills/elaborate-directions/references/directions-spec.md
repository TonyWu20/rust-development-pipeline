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
| `description` | Yes | What this task accomplishes |
| `files_in_scope` | Yes | All files this task may touch |
| `changes` | Yes | Descriptive guidance per file |
| `wiring_checklist` | No | Module wiring to verify after implementation |
| `type_reference` | No | Key type signatures for reference |
| `acceptance` | Yes | Validation commands |
| `depends_on` | No | Task-level dependencies |

### changes[].action

- **`create`**: Create a new file. `guidance` should describe the structs/traits/functions to define.
- **`modify`**: Modify an existing file. `guidance` should describe what to add/change.
- **`delete`**: Remove a file. `guidance` is optional.

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
    }
  ]
}
```
