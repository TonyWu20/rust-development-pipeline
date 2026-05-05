# `rust-workspace-map`: Agent-Centric Tool Design for Pipeline Integration

## Meta: A New Development Pattern

This document represents a novel approach: **human user suggests and guides LLM agents to develop tools for agents, with agent perspective and user experience in the first place.**

Traditional developer tools are designed for humans — interactive, navigational, visually-oriented. Agent tools need fundamentally different design: pre-computed, relational, one-shot consumption. The human user observes how agents actually work (and fail), identifies the gap, and guides the development of tools optimized for agent cognition, not human cognition.

---

## 1. The Problem: 60% Structural Failure Rate

Across 8+ phases of the `castep_workflow_framework` project, the `rust-development-pipeline` plugin produced fix tasks at a 1.0x-3.3x ratio to implementation tasks. Analysis of all fix plans (`feature-requests/reduce_recurring_problems.md`) identified 10 recurring failure categories:

| # | Category | Frequency | Root Cause |
|---|----------|-----------|-------------|
| 1 | Missing `pub mod` declarations | ~40% | Agent doesn't know module tree |
| 2 | Missing `pub use` re-exports | ~20% | Agent doesn't know re-export paths |
| 3 | Incomplete consumer updates | ~20% | Agent doesn't know who imports what |
| 5 | Stale imports after refactoring | ~20% | Agent doesn't track import relationships |
| 6 | Cross-module integration failures | ~20% | Agent doesn't know crate membership |

All five top categories share one root cause: **the LLM agent lacks an accurate structural model of the codebase.**

## 2. Two Failed Strategies for Structural Knowledge

### Strategy A: LSP Tools

The pipeline instructs agents to use LSP tools (`documentSymbol`, `references`, `hover`, `definition`) for codebase exploration. This strategy has failed for three reasons:

1. **LSP answers "what is at this point?" not "how is everything connected?"** `documentSymbol` returns a flat list of symbols in a file — no imports, no re-exports, no cross-file context, no module visibility. The agent must synthesize relationships across 4-5 separate LSP calls, which is fundamentally not how LLM attention works.

2. **LSP is stateful and unreliable.** In empirical testing on a trivial 2-crate, 3-file workspace, `findReferences` returned "No references found — server has not fully indexed the workspace." `hover` on a `use core::Task;` import returned "No hover information available." The LSP server flagged files as "not included in any crates." Agents cannot depend on LSP being ready or accurate.

3. **Agents misuse LSP tools.** When agents query `use` as a symbol, LSP sends them to Rust language documentation about the `use` keyword — not to the import statements in the codebase. The tool assumes human intent (navigating to definitions), not agent intent (finding all imports).

**Key insight: LSP is a navigational tool for humans who hold accumulated context in their head.** A human Cmd-clicks through files, building a mental model. The IDE holds visual state; the human does the synthesis. **Agents have no visual state. Each LSP call is a separate tool invocation with zero persistence.** The agent cannot "build up" a picture across sequential queries.

### Strategy B: Manual File Reading by Subagents

The `enrich-plan-gather` Step 2 spawns an LLM subagent to read files one-by-one, extract public APIs and module wiring, and write `codebase-state.md`. Problems:

- **Token-heavy**: reading every file mentioned in a plan consumes significant context
- **Incomplete**: scoped only to files mentioned in the plan, not workspace-wide
- **Error-prone**: LLM extraction of structural information from raw source code is less reliable than AST parsing
- **Slow**: sequential file reading adds latency to every plan enrichment cycle

## 3. The Solution: Pre-Computed Knowledge Graph

`rust-workspace-map` is a deterministic Rust binary that parses a Rust workspace using `syn` and emits a JSON map of the public API surface. Unlike LSP, it:

- **Pre-computes relationships**: cross-crate references, module trees, re-export chains are all computed once, deterministically
- **Answers "how is everything connected?"**: a symbol entry includes its definition site, re-export paths, and all consumers
- **Is stateless**: same output every time for the same commit — no server, no indexing, no "server is starting" errors
- **Is workspace-aware**: knows crate membership, dependency direction, module hierarchy by construction

### Empirical Comparison (tested on 2-crate, 3-file fixture)

| Information | LSP `documentSymbol` | LSP `references`/`hover` | `rust-workspace-map` |
|---|---|---|---|
| Public items (name, kind) | Flat list, no visibility | — | With visibility, fields, variants, attrs |
| Imports (`use ...`) | **Not shown at all** | `hover` returned nothing | Full list with paths |
| Re-exports (`pub use`) | **Not shown at all** | — | Full list with import→export path |
| Cross-crate references | — | **Failed**: "server not fully indexed" | Pre-computed: "Task imported by engine" |
| Module visibility | Not shown | — | `pub` / `private` |
| File→crate ownership | **"not included in any crates"** | — | Guaranteed correct |
| Crate dependency graph | — | — | Pre-computed |

**Conclusion: LSP answers "what is at this point?" — `rust-workspace-map` answers "how is everything connected?" These are different categories of tool.**

## 4. Design Principle: Agent-Centric Output

The current `rust-workspace-map` output is a tree organized by code hierarchy (`crates[] → modules[] → items[]`). But agents navigate by **lookup, not traversal**. When an agent needs to find `Task`, it should access `symbols["Task"]` — not walk `crates[0].modules[0].publicItems[2]`.

### The output should mirror the agent's mental model:

| Agent thinks in... | Needs output organized as... |
|---|---|
| Symbols ("I need `Task`") | `symbols["Task"]` — O(1) lookup |
| Files ("I'm changing `x.rs`") | `files["x.rs"]` — O(1) lookup with crate/module context |
| Changes ("What did this PR do?") | `--diff main` — structural delta |
| Impact ("Who will this break?") | `consumers["Task"]` — with file:line precision |
| Errors ("What's broken?") | `warnings[]` — pre-computed diagnostics |

### Every entry should be a node in a graph, not just a listing:

- A **symbol** entry: defined here, re-exported there, imported by X, Y, Z — complete relational context in one value
- A **file** entry: belongs to crate A, in module A::B, exports [X, Y], parent module is Z — structural position in one value
- A **change** entry: signature changed from X to Y, affecting N consumers at specific file:line locations — impact in one value

## 5. Features Needed

### Phase 1: Agent Query Support (makes the map actually usable by agents)

1. **Flat symbol index** — `symbols: { "TypeName": { crate, module, file, line, kind, sig, re_exported_at, imported_by } }` — always-on, top-level
2. **Flat file→crate reverse index** — `files: { "path.rs": { crate, module, exports, parent_module_file, submodules, re_exports } }` — always-on, top-level
3. **Consumer detail** — `imported_by` entries include file path and line number, not just crate name

### Phase 2: Error Prevention (catches failures deterministically)

4. **Module wiring validation** (`--validate`) — detects orphan files (no `pub mod`), dead re-exports, unreachable pub items, cross-crate type leaks
5. **Structural diff mode** (`--diff <base-ref>`) — added/removed/changed modules, symbols, files between HEAD and base ref; changed signatures annotated with affected consumers

### Phase 3: Efficiency

6. **Compact output** (`--compact`) — single-line JSON for token efficiency
7. **Scope filtering** (`--crates`, `--files`) — limit output to specified scope

## 6. Pipeline Integration Points

| Pipeline Stage | Current | After `rust-workspace-map` integration |
|---|---|---|
| `enrich-plan-gather` Step 2 | LLM subagent reads files one-by-one | Run map, feed `symbols` + `files` as context |
| `plan-decomposer` Module Wiring Check | Agent guesses from plan text | Agent looks up `files["parent.rs"].submodules` |
| `review-pr-gather` Step 1 | `gather-diff-data.py` regex on diffs | Add `--diff main` as structural ground truth |
| `review-pr` Architecture Compliance | Hardcoded crate names in prompts | `files[path].crate` for dynamic crate membership |
| `compile-plan` pre-check | None (errors caught at review time) | `--validate` catches wiring errors before execution |

## 7. Development Philosophy

This analysis was produced through a novel collaboration pattern:

1. **Human observes agent failures** (60% fix rate, LSP tools unused/misused)
2. **Human identifies the gap** (agents need pre-computed structural knowledge, not interactive navigation)
3. **Agent investigates its own cognitive limitations** (first-principles analysis of why LSP fails for LLMs, empirical testing to validate)
4. **Co-design of agent-optimized tool** (output organized around agent query patterns, not code hierarchy)

The key principle: **build tools for how agents actually think, not for how humans navigate IDEs.**
