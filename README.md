# rust-development-pipeline

A Claude Code plugin that provides a complete Rust development pipeline — from architectural planning through code review, fix generation, and deterministic execution.

## Features

### Skills (Slash Commands)

| Command                           | Description                                                                                                                                            |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `/next-phase-plan`                | Orchestrates a multi-agent pipeline (architect → decomposer → reviewer) to produce a detailed, executor-ready **TOML implementation plan** (`phase-X.Y.toml`) |
| `/implementation-executor <plan>` | Takes a **TOML plan** (`phase-X.Y.toml`) and executes it task-by-task via compiled `sd`-based scripts with checkpoint/resume support                   |
| `/fix <document>`                 | Takes a **TOML fix plan** (`fix-plan.toml`) and applies fixes sequentially, with retry logic and execution reports                                     |
| `/review-pr [branch]`             | Reviews a branch against main on four axes (plan fulfillment, architecture, style, tests); produces a rated review and a **TOML fix plan** (`fix-plan.toml`) |
| `/compile-plan <plan>`            | Takes a **TOML plan** and generates compiled `sd`-based scripts; works with plans from both `next-phase-plan` and `review-pr`                          |

### Agents

| Agent                     | Role                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| `rust-architect`          | Senior Rust architect for design guidance, code review, and first-principles analysis      |
| `plan-decomposer`         | Breaks plans into SRP-aligned, dependency-ordered subtasks with parallel execution phases  |
| `implementation-executor` | Executes delegated coding tasks with TDD, LSP-first navigation, and quality gates          |
| `impl-plan-reviewer`      | Reviews plan clarity — flags ambiguous steps before execution begins                       |
| `strict-code-reviewer`    | Verifies implementations against documentation and architecture; ground-truths every claim |
| `fix-plan-reader`         | Validates fix plans for executability — ensures each step is unambiguous                   |

### Hooks

| Hook                      | Trigger            | Purpose                                                                                                      |
| ------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------ |
| `post_compiled_script.py` | PostToolUse (Bash) | Detects compiled script execution and stops the subagent so the SubagentStop verification hook can take over |

## Design Rationale

### Deterministic Execution via TOML Plans and Compiled Scripts

LLM-driven code changes have two fundamental failure modes: **inconsistency** (the same instruction produces different edits across model versions or providers) and **probability failure** (the model misinterprets the intent and writes incorrect code). Both failures are silent — the pipeline appears to succeed while the output is wrong.

This pipeline separates the work into two phases with different reliability requirements:

- **Planning phase** (frontier model): `next-phase-plan` and `review-pr` use a capable model where reasoning quality matters. They produce a structured TOML file with exact `before`/`after` string pairs — no interpretation required.
- **Execution phase** (deterministic): `compile-plan` compiles the TOML into `sd`-based shell scripts. `implementation-executor` and `fix` run those scripts directly. The model is not asked to interpret instructions into code changes — it only drives flow control (which task to run next, whether the acceptance command passed).

This separation enables running the execution phase on **small local LLMs** that lack the reasoning capacity to write code reliably, while keeping the planning phase on a model with strong architectural judgment.

### Token Efficiency

Conventional LLM code editing requires reading source files into context, generating edits, and writing files back — paying token costs on every file touched. Compiled `sd` scripts skip the LLM entirely for file I/O: the exact byte-level replacement is encoded in the script, so no file content needs to enter or leave the context window during execution.

### PostToolUse Hook

The `post_compiled_script.py` hook reinforces the phase boundary. When the execution subagent runs a compiled script, the hook signals it to stop rather than continue reasoning. Control is handed back to the orchestrator, which applies verification (build, test) before advancing to the next task. This prevents the subagent from over-reaching — attempting additional edits or interpretation — after the deterministic step completes.

## Typical Workflow

```
/next-phase-plan          → produces phase-X.Y.toml
/compile-plan phase-X.Y.toml   → generates compiled/*.sh scripts
/implementation-executor phase-X.Y.toml  → executes all tasks
/review-pr feature-branch → rates PR, generates fix-plan.toml
/fix fix-plan.toml        → applies fixes deterministically
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
│   ├── fix-plan-reader.md
│   └── implementation-executor.md
├── scripts/
│   └── task-sidecar.sh
├── skills/
│   ├── fix/
│   │   └── SKILL.md
│   ├── implementation-executor/
│   │   ├── SKILL.md
│   │   └── evals/evals.json
│   ├── next-phase-plan/
│   │   └── SKILL.md
│   └── review-pr/
│       └── SKILL.md
├── hooks/
│   └── post_compiled_script.py
├── LICENSE
└── README.md
```

## Installation

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

The `post_compiled_script.py` hook needs to be registered in your Claude Code settings. Add to your `settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "command": "/path/to/rust-development-pipeline/hooks/post_compiled_script.py"
      }
    ]
  }
}
```

## Customization

Some files contain paths that may need adjustment for your environment:

- **Agent memory paths** — agents with `memory: project` or `memory: user` store memories in directories derived from your `~/.claude/` layout. These are resolved automatically by Claude Code at runtime. The `review-pr` skill dynamically discovers the current project's memory directory the same way.

## Dependencies

- `sd` — used by compiled scripts for deterministic string replacement
- `rg` (ripgrep) — used by `task-sidecar.sh` for task enumeration
- `fd` — preferred over `find` for file discovery
- `python3` — used by `task-sidecar.sh` and by the hook

## License

MIT
