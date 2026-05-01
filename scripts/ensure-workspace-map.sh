#!/usr/bin/env bash
# ensure-workspace-map.sh — Run rust-workspace-map with dependency check.
#
# This is the single entry point for all pipeline skills to generate a
# workspace map.  It checks that rust-workspace-map is installed, runs it
# with the requested flags, and writes JSON to the specified path.
#
# Usage:
#   ensure-workspace-map.sh <project-root> <output-json-path> [--validate]
#
#   <project-root>     Absolute path to the target project root
#   <output-json-path>  Path to write the workspace map JSON (e.g.
#                       notes/directions/<slug>/workspace-map.json)
#   --validate          Also run OrphanFile / DeadReExport checks (advisory)
#
# Exit codes:
#   0 — success (JSON written)
#   1 — rust-workspace-map not installed
#   2 — validation warnings found (only with --validate)

set -euo pipefail

PROJECT_ROOT="$1"
OUTPUT_PATH="$2"
VALIDATE_FLAG="${3:-}"

if ! command -v rust-workspace-map &> /dev/null; then
  echo "ERROR: rust-workspace-map is not installed." >&2
  echo "" >&2
  echo "rust-workspace-map is a required dependency of the" >&2
  echo "rust-development-pipeline plugin." >&2
  echo "" >&2
  echo "Install it with:" >&2
  echo "  cargo install --path ../rust-workspace-map" >&2
  echo "" >&2
  echo "(adjust the path to match where you cloned the repo)" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

if [ "$VALIDATE_FLAG" = "--validate" ]; then
  rust-workspace-map index --validate -o "$OUTPUT_PATH" "$PROJECT_ROOT"
  EXIT_CODE=$?
  if [ "$EXIT_CODE" -eq 2 ]; then
    echo "[pipeline] workspace-map: validation warnings found (advisory, continuing)" >&2
    exit 0  # validation warnings are advisory — do not block
  fi
  exit "$EXIT_CODE"
else
  rust-workspace-map index -o "$OUTPUT_PATH" "$PROJECT_ROOT"
fi
