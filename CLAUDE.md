## Command-Line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for Python scripts

## Pipeline Stages

0. `/init-project` — Stage 0. Settle repo constitution: domain language, architecture, dependency choices. Produces `CONTEXT.md` + ADRs. Run once per project before any other stage.
0.5 `/define-outcomes` — Interactive planning. Helps you crystallize vague goals into concrete, falsifiable desired outcomes through Socratic grilling. Produces `PHASE_PLAN.md`. Recommended before `/drive-outcomes` when goals are unclear.
1. `/drive-outcomes` — Stage 1+2 merged. Session A defines success criteria grounded in real fixture files and produces forensic `TASKS.md`; Session B implements on a branch with compiler feedback and auto-review before commit.
2. `/make-judgement` (optional, for complex multi-group changes) — Cross-group validation against `TASKS.md`. Produces `review.md` + `fix-tasks.md`.
3. `/debug-outcomes` (optional, for debugging) — Debug an existing fixture-anchored system that passes its acceptance test but produces wrong output. Classifies prior investigation notes, establishes external anchor criteria, applies upstream-audit rule, implements fix with discriminator-value tests, captures resolution.

Key design principles:
- **Compiler as oracle**: cargo check catches wiring issues, not static plan constraints
- **Git as oracle**: agents use git directly, not through wrapper scripts
- **Markdown over JSON**: no schema validation, no splitter scripts
- **Review before commit**: each task auto-reviewed before committing, clean history
- **ODD over TDD**: every test assertion anchored to ground truth external to the code under test
- **Verify subagent claims**: subagent summaries are search results, not authority. Before taking action on any factual claim from a subagent summary, re-verify by reading the cited source directly.
