# TASKS.md Format Specification

Replaces the old `directions.json` schema. Everything is natural markdown — no JSON, no schema validation scripts, no splitter scripts.

## Top-Level Structure

```markdown
# Phase {N}: {Phase Name}
**Source branch:** feature/xxx
**Plan:** plans/phase-{N}/PHASE_PLAN.md
**Decisions:** plans/phase-{N}/DECISIONS.md

## Architecture Notes
{Design constraints applying to ALL tasks. Omit if none.}

## Known Pitfalls
{Anti-patterns and failure modes to avoid. Omit if none.}

## Task Group: {group-id}
**Reason:** {why these tasks share a worktree}
**Depends on groups:** {group-id(s) or "none"}

### TASK-{N}: {short description}
**Goal:** {G1 | G2 | ...}  (links to a plan goal — bidirectional traceability)
**Files:** `path/to/file1.rs`, `path/to/file2.rs`
**Depends on:** {TASK-ID(s) or "none"}
**Kind:** direct | lib-tdd

{Task body — see sections below}
```

## Task Body

### `direct` tasks

```markdown
**Changes:**
- **{create|modify|delete}** `path/to/file.rs`:
  {descriptive guidance — what to define, what patterns to use, what to watch for}

**Acceptance:** {command(s) to verify, separated by `; ` or as a list}
```

### `lib-tdd` tasks

```markdown
**TDD Interface:**
- **Test file:** `path/to/test_file.rs`
- **Test module:** {module name, default "tests"}
- **Test function:** `test_fn_name`
- **Test code:**
  ```rust
  #[test]
  fn test_fn_name() {
      // concrete, falsifiable assertions
  }
  ```
- **Signature:** `pub fn foo(...) -> ...`
- **Expected behavior:** {what "passing" means in natural language}

**Changes:**
- **{create|modify|delete}** `path/to/file.rs`:
  {implementation approach — algorithm, data structures, edge cases}

**Acceptance:** {command(s) to verify}
```

## Format Rules

1. **Group boundaries** are `## Task Group:` headers — no index.json needed.
2. **Task boundaries** are `### TASK-{N}:` headers.
3. **Files** are backtick-quoted paths in the `**Files:**` line.
4. **Changes bullets** use bold action keyword first: `**create**`, `**modify**`, `**delete**`.
5. **TDD test code** goes inside a fenced rust code block under `**Test code:**`.
6. **Acceptance** is one or more commands (semicolon-separated or bullet list).
7. **Goal links** use `**Goal:** G{N}` to enable bidirectional traceability.

## What's Removed (and why)

| Removed | Why |
|---------|-----|
| `wiring_checklist` (pub_mod, pub_use, fn_call, type_annotation) | Compiler catches missing pub mod/pub use during cargo check |
| `type_reference` (TypeName → signature map) | Types described inline in guidance text |
| `changes[].action` enum validation | Action type is just the first word of the markdown bullet |
| `tdd_interface` nested JSON | TDD interface is flat markdown fields |
| `files_in_scope` (separate field) | Files listed once in `**Files:**` line |
| Schema validation scripts | Markdown is self-validating; orchestrator does read-through |
| Index files | Group sections extracted via header regex |
