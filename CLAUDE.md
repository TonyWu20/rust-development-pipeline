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
