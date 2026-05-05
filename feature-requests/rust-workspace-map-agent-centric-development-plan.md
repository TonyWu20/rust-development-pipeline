# Plan: `rust-workspace-map` — Agent-Centric Features for Pipeline Integration

## Context

The `rust-development-pipeline` has a structural knowledge gap: ~60% of fix tasks stem from agents lacking accurate codebase structure — missing `pub mod` (40%), missing `pub use` (~20%), stale imports (~20%), cross-module placement errors (~20%).

The pipeline currently has two strategies for structural knowledge, both broken:

1. **LSP tools** (`documentSymbol`, `references`, `hover`) — Agents are instructed to use these, but rarely do. When they try: `documentSymbol` gives a flat symbol list with no module hierarchy or cross-file context. Querying `use` as a symbol sends the agent to Rust language documentation. Each call is context-free — the agent must synthesize relationships across 4-5 separate LSP invocations, which is fundamentally not how LLM attention works.

2. **Manual file reading by subagents** (`enrich-plan-gather` Step 2) — An LLM subagent reads files one-by-one, extracts public APIs and module wiring, and writes `codebase-state.md`. Slow, token-heavy, and scoped only to files mentioned in the plan (not workspace-wide).

`rust-workspace-map` already produces the right data — workspace-wide public API surface, module trees, cross-crate references — but its output is a **tree organized by code hierarchy** (`crates[] → modules[] → items[]`). Agents don't navigate by tree traversal; they navigate by **lookup** (`symbols["Task"]`, `files["x.rs"].crate`). The fix isn't more data — it's reorganizing the output around agent query patterns.

## Why Not LSP?

LSP is a **navigational tool for humans** who hold accumulated context in their head. A human Cmd-clicks through files, building a mental model of the codebase structure. The IDE holds the visual state; the human does the synthesis.

Agents have no visual state. Each LSP call is a separate tool invocation. Context from prior calls gets compressed. The agent cannot "build up" a picture across 5 sequential queries.

`rust-workspace-map` is a **pre-computed knowledge graph**. All relationships are explicit and available in one output. The agent doesn't synthesize — it looks up.

| Capability | LSP | rust-workspace-map |
|---|---|---|
| List symbols in a file | `documentSymbol` — flat list | Already available (module-level items) |
| Find references to a symbol | `references` — location list | Can be: `consumers["Type"]` — with crate + file + import context |
| Module hierarchy | Requires multiple queries across files, agent must synthesize | Already pre-computed as tree |
| Cross-crate dependency direction | Requires reading multiple `Cargo.toml` files | Already pre-computed |
| "Which crate owns file X?" | Not answerable via LSP | Can be: `files["X"].crate` |
| "What structurally changed in this PR?" | Not answerable via LSP | Can be: `--diff main` |
| "Does every .rs file have a pub mod?" | Not answerable via LSP | Can be: `--validate` |

The critical difference: LSP answers "what is at this point?" Rust-workspace-map answers "how is everything connected?"

## Design Principle

**Output should pre-compute the relationships that a human builds through interactive IDE navigation.**

This means every entry in the output should answer not just "what" but "where it fits":
- A symbol isn't just a name + signature — it's a node in a graph: defined here, re-exported there, imported by X, Y, Z
- A file isn't just a path — it's a node in a graph: belongs to crate A, in module A::B, exports [X, Y], its parent module is Z
- A change isn't just added/removed — it's an edge in a graph: this signature change affects these N consumers

## Features

### 1. Flat symbol index (top-level in output)

Every public symbol with its full relational context. Keyed by name for O(1) lookup.

```
"symbols": {
  "Task": {
    "crate": "core",
    "module": "core::task",
    "file": "core/src/task.rs",
    "line": 5,
    "kind": "struct",
    "sig": "pub struct Task { pub id: JobId, pub name: String }",
    "re_exported_at": ["core/src/lib.rs"],
    "imported_by": [
      {"crate": "engine", "file": "engine/src/pipeline.rs", "line": 3}
    ]
  }
}
```

This single entry answers: what is Task? Where is it? How do I import it? Who depends on it? The agent doesn't need 3 separate LSP calls + synthesis.

Backward compatible: existing tree structure preserved; `symbols` is an additive top-level field. `BTreeMap` for determinism.

### 2. Flat file→crate reverse index (top-level in output)

Every source file with its structural context.

```
"files": {
  "core/src/task.rs": {
    "crate": "core",
    "module": "core::task",
    "exports": ["Task"],
    "parent_module_file": "core/src/lib.rs"
  },
  "core/src/lib.rs": {
    "crate": "core",
    "module": "core",
    "is_crate_root": true,
    "submodules": ["task", "runner"],
    "re_exports": [{"name": "Task", "from": "core::task", "line": 8}]
  }
}
```

The `parent_module_file` field is particularly important for the plan-decomposer: when creating `core/src/validation.rs`, the agent looks up `files["core/src/validation.rs"]` (doesn't exist yet), looks up `files["core/src/lib.rs"].submodules` to see existing modules, and knows exactly where and how to add `pub mod validation;`.

### 3. Module wiring validation (`--validate` flag)

Catches the #1 failure category deterministically — no LLM judgment.

```
"warnings": [
  {"file": "core/src/validation.rs", "kind": "orphan_file",
   "msg": "no pub mod validation in parent core/src/lib.rs"},
  {"file": "core/src/lib.rs:12", "kind": "dead_re_export",
   "msg": "pub use core::task::OldType points to undefined type"}
]
```

Checks:
- **Orphan files**: `.rs` files in crate source dirs with no `pub mod` in parent (40% of fix tasks)
- **Dead re-exports**: `pub use` pointing to nonexistent items (~20% of fix tasks)
- **Unreachable pub items**: `pub` items in modules whose path to crate root has a private segment
- **Leaked types**: types from crate A used in crate B's public API but not re-exported from B

### 4. Structural diff mode (`--diff <base-ref>`)

For PR review. Compares HEAD against a git ref, emits what changed with impact.

```
"diff": {
  "base": "main",
  "added": {
    "modules": ["core::validation"],
    "symbols": ["Validator", "CheckResult"],
    "files": ["core/src/validation.rs"]
  },
  "removed": {...},
  "changed": {
    "symbols": [{
      "name": "Runner",
      "file": "core/src/runner.rs",
      "change": "signature",
      "before": "pub trait Runner { fn run(&self, task: &Task) -> Result<Output>; }",
      "after": "pub trait Runner { fn run(&self, task: &Task) -> Result<Output>;\n    fn validate(&self, task: &Task) -> Result<CheckResult>; }",
      "consumers_affected": [
        {"crate": "engine", "file": "engine/src/pipeline.rs", "reason": "imports Runner"}
      ]
    }]
  }
}
```

This gives the review-pr agent an independent, deterministic structural delta to cross-reference against the LLM's per-file analysis. If the LLM missed that `Runner` grew a method and didn't flag `engine/src/pipeline.rs` for review, the structural diff catches it.

Implementation: generate map for HEAD, generate map for `base-ref` (via `git show base-ref:path` for each source file), diff the two maps.

### 5. Compact output (`--compact` flag)

Single-line JSON. Same schema, no whitespace. For LLM context efficiency.

### 6. Scope filtering (`--crates X,Y` / `--files A,B`)

Limit output to specified scope. For large workspaces where full output exceeds context.

## Integration Points

| Pipeline Stage | Current | After |
|---|---|---|
| `enrich-plan-gather` Step 2 | LLM subagent reads files one-by-one | Run `rust-workspace-map` → feed `symbols` + `files` as context |
| `plan-decomposer` Module Wiring Check | Agent guesses module tree from plan text | Agent looks up `files["parent.rs"].submodules`, uses `symbols["Type"].sig` for exact signatures |
| `review-pr-gather` Step 1 | `gather-diff-data.py` regex on diff lines | Add `rust-workspace-map --diff main` as structural ground truth |
| `review-pr` Architecture Compliance | Hardcoded crate names in prompt | `files[path].crate` for dynamic crate membership |
| `compile-plan` pre-check | None | Run `--validate` to catch wiring errors before execution |

## Files to Modify

| File | Changes |
|---|---|
| `src/schema.rs` | Add `SymbolEntry`, `FileEntry`, `WarningEntry`, `DiffOutput`. Add `symbols`, `files` to `WorkspaceMap`. `imported_by` gets file+line. |
| `src/lib.rs` | Build `symbols`/`files` indexes from `crate_infos`. Add `run_diff()`. |
| `src/render.rs` | `--compact` support. |
| `src/main.rs` | CLI: `--diff REF`, `--validate`, `--compact`, `--crates`, `--files`. |
| New: `src/diff.rs` | Structural diff logic. |
| New: `src/validate.rs` | Wiring validation logic. |

## Verification

1. Run on `tests/fixtures/sample-workspace/` — verify symbol/file indexes correct
2. Add orphan `.rs` file — `--validate` catches it
3. `--diff main` on fixture git history — correct structural delta
4. Manual pipeline dry-run: feed map into enrich-plan-gather, plan-decomposer — verify agents use indexes
