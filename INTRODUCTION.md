# rust-development-pipeline

A Claude Code plugin for running Rust development phases on small local models. Keep the frontier model for planning, compile the plan into deterministic scripts, let any model run them.

---

## Why I Built This

LLM-driven code editing usually fails in two ways that look fine from the outside:

1. The same instruction produces different edits depending on which model runs it.
2. The model misreads what you want and writes something that looks right but is wrong.

Neither failure is obvious. The pipeline reports success either way. This is the
"lucky draw" nature of LLMs.

I hit this wall trying to run the full development cycle on my M4 Mac Mini with 24GB RAM. After the context window takes 10-12GB for Claude Code, there's only room for a ~9B parameter model. Small models are free. But they break on real work.

The breaking point was obvious: as my skill files grew with more rules and edge cases, natural-language instructions became too complex for a 9B model to follow. Ninety percent of errors came from the small model deviating from the plan, not from the API model's planning being bad.

I was simply putting up with it with `git reset` and launch the model again, hoping it gets smarter this time. I have plenty of time to experiment, fortunately.
One day I began to explore the hooks of Claude Code. I just tried to send permission requests to Discord, so I can handle these while I'm away from computer for a break.
Somewhere in that work it clicked: hooks can be scripts. They run outside the context window with their own process lifecycle. Their I/O is deterministic, that makes it the strongest harness because its behavior is predictable.

Then I quickly reflect on myself: what do most tasks actually do?

Most of them either modify existing lines (that's plain substitution) or write new files. Both are trivial and can be "compiled" into script operations. So the pipeline became:

```
Old:  Read plan → model interprets → model writes code → verify
                          ↑ model gets lost here

New:  Read plan → plan compiles to scripts → model runs them → verify
                          ↑ model just runs, no interpretation
```

The LLM was then forced to execute without possibilities of interpreting something new and whacky on its own.
It became a flow controller: which task next, did the acceptance command pass, advance or retry, and these are guaranteed by the
hook events and scripts scheduled by Claude Code.

---

## How It Got Here

I started by reading about agent cooperation and building four agents from theory — `rust-architect`, `strict-code-reviewer`, `plan-decomposer`, `implementation-executor`. Parallel agents are powerful if you can decompose plans correctly. Without dependency ordering, parallelism is just chaos with better timing.

Then I made skills to stop manually typing prompts. `/next-phase-plan`, `/implementation-executor`, `/review-pr`. This was still agent-centric — the pipeline existed to call agents more efficiently.

The hardware constraint hit hard. Running Claude Code is completely different from setting up a chatbot. It sends 10-20K tokens right at your first message in each session.
The small model needs 5-7GB for its own and 5-10GB for the context in agentic coding sessions. So far, on my 24GB M4 Mac Mini, only models up to 9B fit.
When I actually ran those skills on real Rust projects, the small model fell apart. The instructions I'd written for Opus weren't something a 9B model could parse. It flagged things as contradictory. Got stuck on basic edits. The skills themselves were now the bottleneck. The fix wasn't smarter instructions — it was having Haiku review what Opus wrote before the local model ever saw them.

The hooks idea came out of the Discord experiment — I was just routing permission requests. One thing led to another. Compiled scripts followed from the same dumb question about what tasks actually do.

I tested it on `castep_workflow_framework` before the repo even existed. Multiple phases ran. The same problems kept surfacing: module wiring left incomplete, single-crate checks missing cross-crate breaks, review catching things that should have been stopped at plan time. Fix-to-implementation ratio: 1.0x to 3.3x. Every implementation task dragged 1-3 fix tasks behind it.

Those patterns drove v2.0 and v2.1. I created the repo to package it up.

---

## Principles That Survived

| Principle                                         | Where it came from                                                              |
| ------------------------------------------------- | ------------------------------------------------------------------------------- |
| Separate planning from execution                  | Small models broke on Opus-generated instructions                               |
| Compiled scripts are the only execution path      | Natural-language skills became too complex for 9B models                        |
| Hooks enforce phase boundaries                    | Hooks run outside the LLM, independent of model capability                      |
| `before` content is the address, not line numbers | Prior tasks shift content; byte-level matching is the only reliable address     |
| Diagnose-before-retry                             | Three identical retries of a failing script won't fix it — the model can't diagnose what went wrong |
| Prevent at source, catch later                    | Each fix round costs 10+ agent invocations; prevention saves resources          |
| Scope classification                              | `[Improvement]` items go to `deferred.md`, not fix plans                        |

---

## How It Works

### The Pipeline

```
/next-phase-plan          → discuss goals → PHASE_PLAN.md
/plan-review              → validate architecture
/enrich-phase-plan        → architect → decomposer → dry-run compile → phase-X.Y.toml
/compile-plan             → TOML → compiled/*.sh (sd -F scripts)
/implementation-executor  → task-by-task script execution
/review-pr                → four-axis review → fix-plan.toml + deferred.md
/fix                      → deterministic fix application
```

### The Pieces

**Instruction review** — Task descriptions pass through a Haiku agent before the plan is finalized. Opus writes them, Haiku reads and flags anything ambiguous or unclear, the decomposer revises. Using a smaller model to review instructions written for a smaller model is the point — Haiku catches what Opus wouldn't notice when reading its own output.

**TOML plans** use exact `before`/`after` string pairs. No interpretation during execution. The `before` field is content-addressing — not line numbers — so it survives prior edits.

**Compiled `sd` scripts** (`sd -F <before> <after> <file>`) do literal string replacement. The LLM doesn't interpret instructions into code changes. It drives flow control.

**PostToolUse hook** (`post_compiled_script.py`) stops the execution subagent after it runs a compiled script. Control goes back to the orchestrator. The subagent doesn't keep going, trying to interpret what happens next.

**SubagentStop hook** (`verify_impl_task.py`) runs acceptance commands, updates checkpoints, auto-commits after each task. Includes a workspace-level `cargo check --workspace` gate for cross-crate validation.

**Checkpoint/resume** writes task state to disk. If the pipeline crashes mid-phase, it picks back up at the last good task. No rework.

**Scope classification** tags every review issue as `[Defect]`, `[Correctness]`, or `[Improvement]`. Only the first two enter fix plans. `[Improvement]` items go to `deferred.md` to think about next phase.

**Completeness envelope** requires every task to leave the codebase compilable and reachable. "Create file" + "wire module" + "update consumers" is one task, not three. This prevents unreachable dead code, which was the most common recurring failure.

**Dry-run compilation** applies the full TOML plan to a temporary worktree, runs `cargo check --workspace`, and feeds errors back to the decomposer before execution begins. Max 2 revision iterations.

**Cross-round pattern extraction** reads prior `fix-plan.toml` files for recurring failure categories (missing wiring, stale imports, type mismatches) and passes them to the decomposer as `KNOWN_FAILURE_MODES`. Proactive checks instead of reactive fixes.

---

## Directory Layout

```
rust-development-pipeline/
├── agents/                    # Agent definitions
├── hooks/                     # PostToolUse & SubagentStop hooks
├── scripts/                   # Sidecar utilities
├── skills/                    # Slash commands
│   └── compile-plan/          # TOML → sd script compiler
│       └── references/        # TOML format spec
└── plugin.json
```

---

## Why This Exists

If I had unlimited hardware, this project probably wouldn't exist. The 24GB RAM constraint pushed me down a path I wouldn't have found otherwise: the LLM should control the flow. Writing code is a job for scripts.

Planning needs reasoning quality. Execution needs determinism. Separate them and execution runs on whatever cheap local model fits. Planning stays on the frontier model.

The pipeline learns from its mistakes. `deferred.md` accumulates out-of-scope improvements across review cycles so they don't get lost. Cross-round pattern extraction pulls recurring failure modes from previous fix-plans and hands them to the decomposer up front. Each fix round costs 10+ agent invocations. Prevention at plan time is orders of magnitude cheaper.

Every byte of LLM context goes to reasoning, not file I/O.

---

## License

MIT
