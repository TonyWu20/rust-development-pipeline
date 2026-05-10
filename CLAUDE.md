## Command-Line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for Python scripts

## Pipeline Stages

The pipeline has 2 required stages + 2 optional:

0. `/init-project` — Settle repo constitution: domain language, architecture, dependency choices. Produces `CONTEXT.md` + ADRs. Run once per project before any other stage.
1. `/drive-outcomes` (replaces old `/elaborate-plan` + `/explore-implement`) — Two-session merged stage: Session A defines success criteria grounded in real fixture files and produces forensic `TASKS.md`; Session B implements in a worktree with compiler feedback and auto-review before commit.
2. `/make-judgement` (optional, for complex multi-group changes) — Cross-group validation against `TASKS.md`. Produces `review.md` + `fix-tasks.md`.
3. `/debug-outcomes` (optional, for debugging) — Debug an existing fixture-anchored system that passes its acceptance test but produces wrong output. Classifies prior investigation notes, establishes external anchor criteria, applies upstream-audit rule, implements fix with discriminator-value tests, captures resolution.

The deprecated `/elaborate-plan` and `/explore-implement` skills remain available for existing phases during migration but new phases should use `/drive-outcomes`.

Key design principles:
- **Compiler as oracle**: cargo check catches wiring issues, not static plan constraints
- **Git as oracle**: agents use git directly, not through wrapper scripts
- **Markdown over JSON**: no schema validation, no splitter scripts
- **Review before commit**: each task auto-reviewed before committing, clean history
- **ODD over TDD**: every test assertion anchored to ground truth external to the code under test
