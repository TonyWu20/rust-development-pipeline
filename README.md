# rust-development-pipeline

A Claude Code plugin that provides a complete Rust development pipeline — from architectural planning through implementation with real compiler feedback, code review, and fix generation.

## Features

### Skills (Slash Commands)

| Command | Description |
|---------|-------------|
| `/next-phase-plan` | Interactive skill that discusses next phase goals and scope with the user, producing a high-level **markdown plan document** (`PHASE_PLAN.md`) |
| `/plan-review [plan]` | Reviews a phase plan for architectural soundness before implementation; decides on deferred improvements from prior phases |
| `/elaborate-directions [plan]` | Decomposes a reviewed plan into **directions.json** — structured task groups with descriptive guidance, wiring checklists, and type references. Supports `kind: "lib-tdd"` for test-driven library code tasks with embedded test specifications. Replaces the old TOML before/after block approach |
| `/explore-implement [directions]` | Implements code in a git worktree with real `cargo check` feedback. The edit→check→fix loop catches incorrect API usage, missing imports, and type errors immediately. Dispatches on `task.kind`: TDD red-green-refactor for `lib-tdd` tasks, edit→check→fix for `direct` tasks. Accepts both `directions.json` and `fix-directions.json` |
| `/make-judgement [directions]` | Validates the implementation diff against the original directions. Produces `review.md` and optionally `fix-directions.json` for defects |
| `/file-issue` | Files a bug report or feature request for the pipeline itself, with auto-gathered context |

### Agents

| Agent | Role |
|-------|------|
| `rust-architect` | Senior Rust architect for design guidance, code review, and first-principles analysis |
| `plan-decomposer` | Breaks plans into SRP-aligned, dependency-ordered subtasks with parallel execution phases. Supports TDD task design — produces `kind: "lib-tdd"` tasks with `tdd_interface` for library code, `kind: "direct"` for plumbing |
| `implementation-executor` | Implements delegated tasks in worktrees with compiler feedback, LSP-first navigation, and quality gates. Dual workflow: TDD red-green-refactor (RED→stub→GREEN→refactor→verify) for `lib-tdd` tasks, edit→check→fix for `direct` tasks |
| `impl-plan-reviewer` | Reviews directions.json clarity — flags ambiguous steps before implementation begins. Detects weak TDD specifications (`WEAK SPEC` verdict for trivial test code) |
| `strict-code-reviewer` | Verifies implementations against directions and architecture; ground-truths every claim |

### Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `verify_impl_task.py` | SubagentStop (`implementation-executor`, `explore-implement`) | Runs acceptance checks, writes checkpoint, commits changes |

## Design Rationale

### Compiler Feedback Loop (Why This is Different)

The old pipeline used TOML before/after blocks with compiled `sd` scripts — a "mental dance" where LLM agents at every stage deduced code impact from static analysis alone, with no compiler feedback loop. This caused cross-task staleness, incorrect API usage, missing `pub mod`/`pub use` declarations, and recurring clippy violations.

The new pipeline eliminates the mental dance. The `/explore-implement` stage:

1. **Creates a git worktree** — an isolated copy of the repository
2. **Edits code** — applies descriptive guidance from `directions.json` against current file state
3. **Runs `cargo check`** — the compiler tells the agent what's wrong
4. **Fixes errors** — missing imports, wrong types, API misuse, missing module wiring
5. **Repeats** — up to 5 iterations per change, until `cargo check` passes

This means the compiler, not the LLM, is the source of truth for whether code works. The LLM provides architectural judgment and implementation guidance; the compiler validates the output.

### Descriptive Guidance Replaces Exact Replacements

Instead of specifying exact `before`/`after` byte-level replacements that go stale the moment any task shifts file content, `directions.json` uses **descriptive guidance** — what structs to define, what functions to add, which patterns to follow. The implementation agent reads current file state at implementation time, so staleness is impossible.

### Three-Tier Exploration Model

The `/explore-implement` stage supports three levels of parallelism:

- **Tier 1 (Sequential)**: The main orchestrator implements task groups one at a time. Auto-compress handles context management. Best for small-medium plans.
- **Tier 2 (Subagent Parallelism)**: One subagent per independent task group. Each subagent's context is discardable after completion. Best for 2-4 independent groups.
- **Tier 3 (Multi-Session via tmux)**: Separate Claude Code sessions, each with its own worktree. Full context per session. Best for 4+ independent groups.

The worktree IS the checkpoint — interrupted sessions resume by reading worktree files + the last compiler output + the directions.

### Token Efficiency

- **Planning phase** (high-capability model): `next-phase-plan`, `plan-review`, `elaborate-directions`, `make-judgement` use capable models where reasoning quality matters.
- **Implementation phase** (cost-effective model): `explore-implement` runs on a cost-effective model. The compiler catches errors, not expensive re-reviews.

## Typical Workflow

```
/next-phase-plan             → discuss goals with user → PHASE_PLAN.md
/plan-review                 → validate plan, decide on deferred items
/elaborate-directions        → decompose into directions.json with task groups
/explore-implement           → implement in worktree with cargo check feedback
/make-judgement              → validate diff against directions, produce fixes if needed

# Fix loop (if make-judgement found defects):
/explore-implement fix-directions.json  → apply fixes with same edit→check→fix loop
```

## Plugin Structure

```
rust-development-pipeline/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   ├── rust-architect.md
│   ├── plan-decomposer.md
│   ├── impl-plan-reviewer.md
│   ├── strict-code-reviewer.md
│   └── implementation-executor.md
├── scripts/
│   ├── gather-diff-data.py
│   ├── worktree-utils.sh
│   ├── checkpoint-resume.py
│   └── validate/
│       ├── validate-directions.py
│       ├── validate-fix-document.py
│       └── validate-review-consistency.py
├── skills/
│   ├── elaborate-directions/
│   │   ├── SKILL.md
│   │   └── references/directions-spec.md
│   │   └── references/tdd-pattern.md
│   ├── explore-implement/
│   │   └── SKILL.md
│   ├── make-judgement/
│   │   └── SKILL.md
│   ├── file-issue/
│   │   └── SKILL.md
│   ├── next-phase-plan/
│   │   └── SKILL.md
│   └── plan-review/
│       └── SKILL.md
├── hooks/
│   ├── hooks.json
│   └── verify_impl_task.py
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

## Dependencies

- `uv` — Python package manager for running scripts with a consistent environment
- `rg` (ripgrep) — used by scripts for content search
- `fd` — preferred over `find` for file discovery
- `python3` — managed by `uv`; not invoked directly

## License

MIT
