---
name: init-project
description: Stage 0 — grill the user to settle the repo constitution: architecture, coding patterns, domain language, dependency choices. Produces CONTEXT.md (domain glossary) and ADRs (architectural decisions). MUST be run before `/drive-outcomes` on any project. Use when the user says "/init-project", "set up the project constitution", "initialize the repo for the pipeline", or on a fresh project checkout before any planning begins.
---

# Init Project

Stage 0 of the ODD pipeline. Establishes the repo constitution — the shared
vocabulary, architectural principles, and hard-to-reverse decisions that all
downstream stages will reference. Without this, every session re-litigates
patterns and terms, wasting tokens and producing inconsistent design.

The constitution serves two audiences: **agents** (as operational context for
decision-making) and **humans** (as documented proof to push back when agents
drift). Both must be able to read and reference it.

## Trigger

`/init-project [project-root]`

Where `[project-root]` defaults to the current repo root. Run once per project,
before any `/drive-outcomes` or `/make-judgement` sessions.

## Pre-flight

Check for existing constitution:

```bash
cat CONTEXT.md 2>/dev/null || echo "NO_CONTEXT_MD"
fd -e md . docs/adr/ 2>/dev/null || echo "NO_ADRS"
```

If CONTEXT.md already exists and ADRs are present, confirm with the user:
"Constitution already exists. Re-run to update, or skip if the existing one is
still current?"

## Command-line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `bash ${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh` to generate workspace maps

## References

- Context format: `{CLAUDE_PLUGIN_ROOT}/skills/grill-with-docs/CONTEXT-FORMAT.md`
- ADR format: `{CLAUDE_PLUGIN_ROOT}/skills/grill-with-docs/ADR-FORMAT.md`
- ODD pattern: `{CLAUDE_PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md`

## Output

- `CONTEXT.md` — domain glossary with precise definitions, flagged ambiguities,
  and example dialogue
- `docs/adr/{NNNN}-{slug}.md` — architecture decision records (created
  sparingly, only when hard-to-reverse, surprising, and the result of a real
  trade-off)

## Process

### Step 1: Setup

```bash
echo "init-project" > .claude/.current_stage
date +%s%3N > .claude/.session_start
```

### Step 2: Generate Workspace Map

```bash
mkdir -p .pipeline
bash "${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh" \
  "${CLAUDE_PROJECT_DIR}" \
  ".pipeline/workspace-map.json"
```

Use `jq` on the workspace map to understand project structure before the grill:
- What crates exist? (`jq '.crates | keys' .pipeline/workspace-map.json`)
- What are the top-level modules? (`jq '.files | to_entries[] | select(.key | contains("lib.rs"))' .pipeline/workspace-map.json`)
- What's the existing public API surface? (`jq '.symbols | keys | .[0:20]' .pipeline/workspace-map.json`)

### Step 3: Grill — Settle the Constitution

Launch a grill-me subagent that interviews the user, one question at a time,
with the agent providing recommended answers. The griller explores the codebase
to ground every question in real code.

> **Agent**: general-purpose (subagent, discardable context)
>
> **Task**: Grill the user to establish the project constitution.
>
> Context:
> - Workspace map at `.pipeline/workspace-map.json` (use `jq` for lookups)
> - Domain glossary format: `{PLUGIN_ROOT}/skills/grill-with-docs/CONTEXT-FORMAT.md`
> - ADR format: `{PLUGIN_ROOT}/skills/grill-with-docs/ADR-FORMAT.md`
> - ODD pattern: `{PLUGIN_ROOT}/skills/drive-outcomes/references/odd-pattern.md`
>
> Work through these areas in order. For each, propose specific answers based on
> codebase exploration and ask the user to confirm.

#### Area 1: Project purpose

What is this project building? Who is it for? What problem does it solve?

Explore: read `Cargo.toml` description field, README, any existing docs.

If the project builds on specific science/domain knowledge (DFT, quantum
chemistry, etc.), establish that here — it shapes every downstream decision.

#### Area 2: Domain language

What terms are central to this project's domain? For each:
- Propose a precise definition
- List aliases to avoid
- Check if existing code uses the term consistently

Explore: read module names, type names, function names from the workspace map.
Read key source files to verify actual usage.

Example terms to cover (project-dependent):
- "System" vs "Structure" vs "Configuration"
- "Calculator" vs "Engine" vs "Solver"
- "Worker" vs "Task" vs "Job"
- "Input" vs "Parameter" vs "Setting"

Update CONTEXT.md inline as each term is resolved. Create it lazily when the
first term is settled.

#### Area 3: Architecture

What are the crate boundaries? What belongs where?

Explore: read module tree from workspace map. Check existing boundary decisions
(what's pub vs private, which crates depend on which).

Decisions to settle:
- Monorepo vs multi-repo? (Already decided — you're in a workspace.)
- Layered or flat crate structure?
- Which crate owns the domain types?
- Where do I/O adapters live?
- Shared types crate or per-crate types?

#### Area 4: Dependencies and tooling

Which crates should the project use for common patterns?

Explore: check Cargo.toml files for existing dependencies. Read current usage
to see what's already in play.

Decision tree (propose based on project type):
- **Parser project**: `nom` vs `winnow` vs hand-rolled. For CASTEP/molecular
  formats specifically, is the format binary (needs state machine) or text (line-by-line)?
- **Serialization**: `serde + ron` vs `serde + json` vs `bincode`?
- **Error handling**: `thiserror` (lib) vs `anyhow` (app) — or both?
- **Linear algebra**: `nalgebra` vs `ndarray` vs custom?
- **CLI**: `clap` vs `argh` vs hand-rolled?
- **Testing/property-based**: `proptest`, `quickcheck`?

Does the feature being planned have a well-known crate that handles it already?
Explore crates.io / lib.rs for established solutions before deciding to build
custom. The agent should act as "the one who knows" — if this is a parser format,
which crate parsers exist? If this is DFT, which Rust crates exist for linear
algebra, unit conversions, or format I/O?

#### Area 5: Coding patterns

What conventions should downstream agents follow?

Explore: read existing source files for actual style patterns used.

Decisions to settle:
- Error handling pattern (typed errors from `thiserror` vs `anyhow` context?)
- Module visibility (flat with `pub use` re-exports vs deep nesting?)
- Async strategy (tokio? async-std? sync-only with rayon for parallelism?)
- Testing conventions (unit tests inline, integration tests in `tests/`?)
- Documentation (rustdoc on all pub items? README per crate?)

#### Area 6: Downstream pipeline expectations

Which pipeline stages will this project use, and in what order?

Decisions to settle:
- First phase: what's the most valuable thing to build first?
- Ground truth: what fixture files exist or need to be created?
- Review cadence: after every group? after every phase? PR-based?

**Terminology validation** — challenge against the glossary:
- If the user uses a term that conflicts with a settled definition, call it out
  immediately.
- When the user uses vague or overloaded terms, propose a precise canonical term
  and confirm it.
- Cross-reference claims about how the system works against actual code (use `jq`
  on workspace map, then read files). If you find a contradiction, surface it.

**ADR creation** — offer sparingly:
- Only offer to create an ADR when ALL THREE are true:
  1. **Hard to reverse** — changing it later would be expensive
  2. **Surprising without context** — a future reader will wonder why
  3. **Result of a real trade-off** — genuine alternatives existed
- If any criterion is missing, skip the ADR. Record in CONTEXT.md instead.
- When an ADR is warranted: scan `docs/adr/` for highest number, increment by one,
  create `docs/adr/{NNNN}-{slug}.md`.

After each question, provide your recommended answer. Continue until all six
areas are resolved and the user confirms shared understanding.

Output: {will be captured by the orchestrator; the griller updates CONTEXT.md
and creates ADRs inline as decisions crystallise}

### Step 4: Synthesize

After the grill completes, verify all outputs are coherent:

1. Read CONTEXT.md — does it read as a single consistent glossary?
2. Scan `docs/adr/` — are ADRs properly numbered? Does each reference valid
   decisions that were actually discussed?
3. Does the constitution cover all six areas? If any were skipped, flag them.

Write a session summary:

```markdown
# Project Constitution: {Project Name}

**Established**: {date}

## Areas Covered

- **Domain language**: {N} terms defined, {N} ambiguities resolved
- **Architecture**: {N} crate boundaries, {N} ADRs created
- **Dependencies**: {N} crate choices settled
- **Coding patterns**: {N} conventions established
- **Pipeline expectations**: {N} decisions

## ADR Index

{List of ADRs created during this session — number, title, one-line summary}
```

### Step 5: Handoff

Stage the artifacts:

```bash
git add CONTEXT.md 2>/dev/null
git add docs/adr/ 2>/dev/null
git commit -m "docs: establish project constitution ($(basename $PWD))"
```

Report to the user:

> "Project constitution established for {Project Name}.
>
> - `CONTEXT.md` — {N} domain terms defined
> - `docs/adr/` — {N} architecture decision records
>
> The constitution is committed. Downstream stages (`/drive-outcomes`,
> `/make-judgement`) will reference it automatically.
>
> Next steps:
> 1. `/drive-outcomes <phase-plan>` — start the first phase with ground-truth
>    anchoring
> 2. Review the constitution yourself — it's your source of truth for pushing
>    back when agents drift"

## Boundaries

**Will:**
- Grill all six areas (purpose, language, architecture, dependencies, patterns,
  pipeline expectations)
- Explore the codebase to ground every question in real code
- Update CONTEXT.md inline as terms are resolved
- Create ADRs sparingly — only when all three criteria are met
- Propose specific recommendations based on codebase exploration and domain
  knowledge
- Act as domain expert: suggest existing crates, established patterns, known
  solutions before building custom

**Will not:**
- Write any implementation code
- Decompose into tasks (that's `/drive-outcomes`)
- Create ADRs unnecessarily (if it's not surprising or not a trade-off, skip it)
- Accept vague language without proposing a precise term
