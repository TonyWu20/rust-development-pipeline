# rust-development-pipeline

A Claude Code plugin that provides a complete Rust development pipeline — from architectural planning through implementation with real compiler feedback, code review, and fix generation.

## Features

### Skills (Slash Commands)

| Command | Description |
|---------|-------------|
| `/define-outcomes` | Interactive planning — helps you crystallize vague goals into concrete, falsifiable desired outcomes through Socratic grilling. Produces a **PHASE_PLAN.md** with goals, scope, and design notes. Recommended before `/drive-outcomes` when goals are unclear. |
| `/init-project [root]` | Stage 0 — settles the repo constitution: domain language, architecture, dependency choices, coding patterns. Produces CONTEXT.md and ADRs. Run once per project before any other pipeline stage. |
| `/drive-outcomes [plan]` | **Core pipeline stage** — Merged Stage 1+2: define success criteria grounded in real fixture files, validate by exploring against real data, implement in a worktree with compiler feedback, and produce a forensic record. One continuous session with a checkpoint. The ODD cycle replaces TDD: every test assertion is anchored to ground truth external to the code under test. |
| `/debug-outcomes [symptom]` | **Debug stage** — debug an existing fixture-anchored system that passes its acceptance test but produces wrong output. Classifies prior investigation notes (EXTERNAL/DERIVED/HYPOTHESIZED), establishes anchor criteria, applies upstream-audit rule, implements fix with discriminator-value tests, captures resolution. |
| `/diagnose-tests [path]` | Migration diagnostic — scans a project's test suite for placebo patterns (vacuous assertions, circular round-trip, unbounded thresholds, synthetic-only data). Produces an audit report before adopting ODD stages. |
| `/make-judgement [tasks]` | Cross-group validation against the original **TASKS.md**. Produces `review.md` and optionally `fix-tasks.md` for defects |
| `/file-issue` | Files a bug report or feature request for the pipeline itself, with auto-gathered context |

### Agents

| Agent | Role |
|-------|------|
| `rust-architect` | Senior Rust architect for design guidance, code review, and first-principles analysis |
| `implementation-executor` | Implements delegated tasks in worktrees with compiler feedback, LSP-first navigation, and quality gates. Dual workflow: ODD outcome-driven cycle (criteria→explore→implement→refactor→verify) for `lib-tdd` tasks, edit→check→fix for `direct` tasks |
| `strict-code-reviewer` | Verifies implementations against tasks and architecture; ground-truths every claim |

### Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `metrics_hook.py` | PostToolUse (all tools) | Collects session metrics (tool calls, tokens, timing) for pipeline performance analysis |

## Design Rationale

### Compiler Feedback Loop (Why This is Different)

The old pipeline used TOML before/after blocks with compiled `sd` scripts — a "mental dance" where LLM agents at every stage deduced code impact from static analysis alone, with no compiler feedback loop. This caused cross-task staleness, incorrect API usage, missing `pub mod`/`pub use` declarations, and recurring clippy violations.

The pipeline eliminates the mental dance. Implementation stages (`/drive-outcomes` Session B) operate in isolated git worktrees with the real compiler:

1. **Creates a git worktree** — an isolated copy of the repository
2. **Edits code** — applies descriptive guidance against current file state
3. **Runs `cargo check`** — the compiler tells the agent what's wrong
4. **Fixes errors** — missing imports, wrong types, API misuse, missing module wiring
5. **Repeats** — up to 5 iterations per change, until `cargo check` passes

This means the compiler, not the LLM, is the source of truth for whether code works. The LLM provides architectural judgment and implementation guidance; the compiler validates the output.

### Descriptive Guidance Replaces Exact Replacements

Instead of specifying exact `before`/`after` byte-level replacements that go stale the moment any task shifts file content, tasks use **descriptive guidance** — what structs to define, what functions to add, which patterns to follow. The implementation agent reads current file state at implementation time, so staleness is impossible.

### Worktree-Based Implementation

Implementation stages operate in isolated git worktrees. The worktree IS the checkpoint — interrupted sessions resume by reading worktree files + the last compiler output + the task definition. All task groups run sequentially in a single session; auto-compress handles context management.

## Typical Workflow

```
/init-project              → settle repo constitution → CONTEXT.md + ADRs
/define-outcomes           → define desired outcomes → PHASE_PLAN.md
/drive-outcomes            → Session A (define+explore): forensic TASKS.md
                              Session B (implement): worktree + cargo check
/make-judgement            → validate diff against TASKS.md, produce fixes if needed

# Fix loop (if make-judgement found defects):
/drive-outcomes fix-tasks.md  → apply fixes with same edit→check→fix loop
```

## Plugin Structure

```
rust-development-pipeline/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── rust-architect.md
│   ├── strict-code-reviewer.md
│   └── implementation-executor.md
├── scripts/
│   └── eval-session-metrics.py
├── skills/
│   ├── define-outcomes/
│   │   ├── SKILL.md
│   │   └── references/
│   │       └── context-format.md
│   ├── init-project/
│   │   └── SKILL.md
│   ├── drive-outcomes/
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── odd-pattern.md
│   │       └── forensic-tasks-spec.md
│   ├── debug-outcomes/
│   │   └── SKILL.md
│   ├── diagnose-tests/
│   │   └── SKILL.md
│   ├── make-judgement/
│   │   └── SKILL.md
│   └── file-issue/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── metrics_hook.py
├── LICENSE
└── README.md
```

## Installation

### Remote Installation (GitHub)

```bash
claude plugins install rust-development-pipeline TonyWu20/my-claude-marketplace
```

Or add the marketplace to your `~/.claude/settings.json` to browse and install via the plugin manager:

```json
{
  "extraKnownMarketplaces":
    "my-claude-marketplace": {
        "source": {
          "source": "github",
          "repo": "TonyWu20/my-claude-marketplace"
        }
  }
}
```

### Local Installation

```bash
# From the Claude Code CLI
claude plugins install --local /path/to/rust-development-pipeline
```

Or manually add to `~/.claude/plugins/installed_plugins.json`:

```json
{
  "rust-development-pipeline@local": {
    "source": "local",
    "path": "/path/to/rust-development-pipeline"
  }
}
```

### Hook Configuration

The hook configuration is in `hooks/hooks.json`. After enabling the plugin the
hook will be automatically configured to your Claude Code. You can check it in
the `/hooks` menu in Claude Code.

The current hook (`metrics_hook.py`) runs asynchronously after every tool call
to record session metrics. It does not affect pipeline execution — failures are
logged silently.

## Dependencies

- `uv` — Python package manager for running scripts with a consistent environment
- `rg` (ripgrep) — used by scripts for content search
- `fd` — preferred over `find` for file discovery
- `python3` — managed by `uv`; not invoked directly

## License

MIT
