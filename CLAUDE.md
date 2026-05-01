## Dependencies

- `rust-workspace-map` (required) — pre-computed codebase structure maps for
  LLM agents. All pipeline stages (elaborate-directions, explore-implement,
  make-judgement) require this binary in PATH.
  - Install: `cargo install --path ../rust-workspace-map` (from sibling repo)
  - Verify: `rust-workspace-map --help`

## Command-Line Tools

- use `fd` instead of `find`
- use `rg` instead of `grep`
- use `uv run --directory ${CLAUDE_PLUGIN_ROOT} python` for Python scripts
- use `bash ${CLAUDE_PLUGIN_ROOT}/scripts/ensure-workspace-map.sh` to
  generate workspace maps
