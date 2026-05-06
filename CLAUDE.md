## Dependencies

- `rust-workspace-map` v0.3.0+ (required) — pre-computed codebase structure maps
  for LLM agents. All pipeline stages require this binary in PATH. v0.3.0 adds
  automatic single-crate detection; earlier versions only support workspaces.
  - Install: `cargo install --path ../rust-workspace-map` (from sibling repo)
  - Verify: `rust-workspace-map --version` (must be >= 0.3.0)
- `jq` (required) — used to query workspace-map.json without reading the full
  file. Installed by default on macOS; on Linux: `apt install jq` / `dnf install jq`.

## Command-Line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for Python scripts
- use `bash ${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh` to
  generate workspace maps

## Pipeline Stages

The pipeline has 3 core stages + 1 optional:

1. `/next-phase-plan` — Discuss goals with grill-me + first-principle questioning. Produces `PHASE_PLAN.md`.
2. `/elaborate-plan` — Grill design decisions, decompose into tasks. Produces `DECISIONS.md` + `TASKS.md` (markdown).
3. `/explore-implement` — Implement tasks in worktree with compiler feedback + auto-review before commit.
4. `/make-judgement` (optional, for complex multi-group changes) — Cross-group validation against `TASKS.md`. Produces `review.md` + `fix-tasks.md`.

Key design principles:
- **Compiler as oracle**: cargo check catches wiring issues, not static plan constraints
- **Git as oracle**: agents use git directly, not through wrapper scripts
- **Markdown over JSON**: no schema validation, no splitter scripts
- **Review before commit**: each task auto-reviewed before committing, clean history
