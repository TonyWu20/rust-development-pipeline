#!/usr/bin/env python3
"""Deterministic PR diff data collector.

Runs git commands to gather authoritative factual data about a branch diff,
reads all changed files, and produces outputs:

  1. raw-diff.md          — human-readable log, diff, and full file contents
  2. file-manifest.json    — machine-readable structured facts per file
  3. per-file-analysis-template.md  — (with --template) pre-filled Facts table
     with Fill In sections for LLM judgment — prevents hallucination of
     manifest data by pre-rendering immutable facts inline.

This is the authoritative data source for all downstream gather and judge
sessions.  Facts produced here are ground truth; LLM subagents must not
contradict them.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


# ── Constants ────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())).resolve()

# Patterns for extracting function/method/type/impl signatures from a line.
_FUNC_RE = re.compile(
    r"^\s*(?:pub\s+)?(?:unsafe\s+)?"
    r"(?:async\s+)?"
    r"(?:fn|struct|enum|trait|impl|type|const|static)\s+"
    r"([a-zA-Z_]\w*)"
)
_IMPORT_RE = re.compile(r"^\s*use\s+(.+);")


# ── Git helpers ──────────────────────────────────────────────────────────────


def git_run(*args: str) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, cwd=PROJECT_DIR, timeout=60,
    )
    if result.returncode != 0:
        print(f"Error: git {' '.join(args)} failed:\n{result.stderr}",
              file=sys.stderr)
        sys.exit(1)
    return result.stdout


# ── Diff parsing ─────────────────────────────────────────────────────────────


def _finalise_current(
    files: list,
    current: dict | None,
    added_lines: list[str],
    removed_lines: list[str],
) -> None:
    """Finalise the current file and append to files list."""
    if current is not None:
        _finalise_file(current, added_lines, removed_lines)
        files.append(current)


def parse_diff_hunks(diff_text: str) -> list[dict]:
    """Parse a unified diff into per-file change info.

    Returns one dict per file with:
      - path: the file path
      - lines_added, lines_removed: integer counts
      - added_functions: function/type signatures introduced in added lines
      - removed_functions: signatures from removed lines
      - modified_functions: signatures on lines with nearby both +/- context
      - added_imports: ``use`` statements from added lines
    """
    files: list[dict] = []
    current: dict | None = None
    added_lines: list[str] = []
    removed_lines: list[str] = []
    current_path: str | None = None

    for line in diff_text.splitlines(keepends=False):
        # Detect new file boundary — "diff --git a/... b/..."
        if line.startswith("diff --git"):
            _finalise_current(files, current, added_lines, removed_lines)
            current = None
            current_path = None
            added_lines = []
            removed_lines = []
            continue

        # Skip metadata lines
        if line.startswith("---"):
            continue
        if line.startswith("index ") or line.startswith("new file") or line.startswith("deleted file"):
            continue

        # +++ b/<path> sets the current file path (also acts as a reset)
        if line.startswith("+++ b/"):
            current_path = line[6:]
            continue

        # @@ hunks — create a new file entry
        if line.startswith("@@") and current_path:
            if current is None:
                current = {
                    "path": current_path,
                    "lines_added": 0,
                    "lines_removed": 0,
                    "added_functions": [],
                    "removed_functions": [],
                    "modified_functions": [],
                    "added_imports": [],
                }
                added_lines = []
                removed_lines = []
            continue

        # Track added and removed lines for this file
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
            if current:
                current["lines_added"] += 1
            continue
        if line.startswith("-") and not line.startswith("---"):
            removed_lines.append(line[1:])
            if current:
                current["lines_removed"] += 1
            continue

    # Finalise last file
    _finalise_current(files, current, added_lines, removed_lines)

    return files


def _finalise_file(
    current: dict,
    added_lines: list[str],
    removed_lines: list[str],
) -> None:
    """Extract function signatures and imports from the accumulated +/- lines."""
    for line in added_lines:
        m = _FUNC_RE.search(line)
        if m:
            current["added_functions"].append(m.group(1))
        m2 = _IMPORT_RE.search(line)
        if m2:
            current["added_imports"].append(m2.group(1))
    for line in removed_lines:
        m = _FUNC_RE.search(line)
        if m:
            current["removed_functions"].append(m.group(1))
    # Deduplicate
    current["added_functions"] = list(dict.fromkeys(current["added_functions"]))
    current["removed_functions"] = list(dict.fromkeys(current["removed_functions"]))
    current["added_imports"] = list(dict.fromkeys(current["added_imports"]))


# ── Trailing newline check ───────────────────────────────────────────────────


def check_trailing_newline(file_path: str, branch: str) -> bool:
    """Check if the file at the given revision ends with a newline (0x0a)."""
    try:
        content = subprocess.run(
            ["git", "show", f"{branch}:{file_path}"],
            capture_output=True, cwd=PROJECT_DIR, timeout=30,
        )
        if content.returncode != 0:
            return True  # binary or deleted — assume OK
        raw = content.stdout
        return len(raw) > 0 and raw[-1:] == b"\n"
    except Exception:
        return True  # fallback


def _yes_no(val: bool) -> str:
    return "YES" if val else "NO"


def _fmt_list(items: list[str]) -> str:
    return ", ".join(items) if items else "—"


# ── Output writers ───────────────────────────────────────────────────────────


def _timestamp() -> str:
    result = subprocess.run(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout.strip()


def write_raw_diff(
    output_dir: Path,
    branch: str,
    log: str,
    stat: str,
    diff: str,
    file_contents: dict[str, str],
) -> None:
    ts = _timestamp()
    lines = [
        f"# Raw Diff: `{branch}` -> `main`\n",
        f"Generated: {ts}\n\n",
        "## Commits\n",
        log,
        "\n",
        "## Diff Stat\n",
        stat,
        "\n",
        "## Full Diff\n",
        diff,
        "\n",
    ]
    for path, content in file_contents.items():
        lines.append(f"## File: {path}\n")
        lines.append(content)
        if not content.endswith("\n"):
            lines.append("\n")
    (output_dir / "raw-diff.md").write_text("".join(lines))


def write_file_manifest(
    output_dir: Path,
    branch: str,
    commits: list[dict],
    files: list[dict],
) -> None:
    manifest = {
        "branch": branch,
        "base": "main",
        "commits": commits,
        "files": files,
    }
    (output_dir / "file-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )


def write_per_file_analysis_template(
    output_dir: Path,
    files: list[dict],
) -> None:
    """Write per-file-analysis-template.md with facts pre-filled.

    The LLM subagent fills in only the judgment fields (Intent, Checklist, Notes)
    on top of the immutable Facts table. This structurally prevents the LLM from
    fabricating or contradicting manifest data.
    """
    lines: list[str] = [
        "# Per-File Analysis Template\n\n",
        "## Instructions\n\n",
        "Read `raw-diff.md` for diff context, then fill in the judgment fields below.\n\n",
        "**Do NOT modify the `### Facts` table.** These values come from file-manifest.json "
        "and are authoritative — they cannot be changed.\n\n",
        "---\n\n",
    ]

    for pf in files:
        has_tn = pf.get("has_trailing_newline", True)
        lines.append(f"## File: {pf['path']}\n\n")
        lines.append("### Facts (from file-manifest.json — authoritative, do not modify)\n\n")
        lines.append("| Property | Value |\n")
        lines.append("|----------|-------|\n")
        lines.append(f"| Lines added | +{pf.get('lines_added', 0)} |\n")
        lines.append(f"| Lines removed | -{pf.get('lines_removed', 0)} |\n")
        lines.append(f"| Trailing newline | {_yes_no(has_tn)} |\n")
        lines.append(f"| Added functions | {_fmt_list(pf.get('added_functions', []))} |\n")
        lines.append(f"| Modified functions | {_fmt_list(pf.get('modified_functions', []))} |\n")
        lines.append(f"| Removed functions | {_fmt_list(pf.get('removed_functions', []))} |\n")
        lines.append(f"| Added imports | {_fmt_list(pf.get('added_imports', []))} |\n\n")

        lines.append("### Intent\n\n[Fill in: one sentence on what changed, based on the diff]\n\n")

        lines.append("### Checklist\n\n")
        lines.append("- Unnecessary clone/unwrap/expect? [Fill in: Yes (cite location) / No]\n")
        lines.append("- Error handling: [Fill in: observation]\n")
        lines.append("- Dead code or unused imports? [Fill in: Yes / No]\n")
        lines.append("- New public API: tests present? [Fill in: Yes / No / Not applicable]\n")
        lines.append("- Change appears within plan scope? [Fill in: Yes / No / Unclear — no plan available yet]\n\n")

        lines.append("### Notes\n\n[Fill in: other observations — no classifications, just facts]\n\n")
        lines.append("---\n\n")

    (output_dir / "per-file-analysis-template.md").write_text("".join(lines))
    print(f"per-file-analysis-template.md saved. {len(files)} file sections.",
          file=sys.stderr)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gather authoritative PR diff data"
    )
    parser.add_argument("--branch", required=True, help="Branch to compare against main")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--template", action="store_true",
        help="Also generate per-file-analysis-template.md with pre-filled Facts table",
    )
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    branch = args.branch

    # ── Collect git data ──────────────────────────────────────────────────
    print(f"Fetching origin...", file=sys.stderr)
    git_run("fetch", "origin", "--quiet")

    print(f"Collecting git log...", file=sys.stderr)
    log = git_run("log", "--oneline", f"main..{branch}")

    print(f"Collecting diff stat...", file=sys.stderr)
    stat = git_run("diff", f"main...{branch}", "--stat")

    print(f"Collecting full diff...", file=sys.stderr)
    diff_text = git_run("diff", f"main...{branch}")

    # ── Parse commits ─────────────────────────────────────────────────────
    commits = []
    for line in log.splitlines(keepends=False):
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append({"hash": parts[0], "message": parts[1]})
        else:
            commits.append({"hash": parts[0], "message": ""})

    # ── Parse diff → file info ────────────────────────────────────────────
    parsed_files = parse_diff_hunks(diff_text)

    # Filter out internal build artifacts — these are generated by
    # compile-plan and hooks, not source code.  They appear in diffs
    # because hooks stage/commit them during execution, but reviewing
    # shell scripts, checkpoints, and hook state wastes effort.
    parsed_files = [
        f for f in parsed_files
        if "/compiled/" not in f["path"]
        and not f["path"].startswith(".claude/hooks/current_task_")
        and not f["path"].startswith("execution_reports/.checkpoint_")
    ]

    # ── Enrich with trailing-newline check and full content ───────────────
    file_contents: dict[str, str] = {}
    for pf in parsed_files:
        fpath = pf["path"]
        pf["has_trailing_newline"] = check_trailing_newline(fpath, branch)

        # Read full file content
        content = git_run("show", f"{branch}:{fpath}")
        file_contents[fpath] = content

    # ── Write outputs ─────────────────────────────────────────────────────
    write_raw_diff(output_dir, branch, log, stat, diff_text, file_contents)
    write_file_manifest(output_dir, branch, commits, parsed_files)

    if args.template:
        write_per_file_analysis_template(output_dir, parsed_files)

    num_files = len(parsed_files)
    file_list = ", ".join(pf["path"] for pf in parsed_files)
    template_note = " per-file-analysis-template.md saved." if args.template else ""
    print(f"RESULT: raw-diff.md saved. {num_files} files changed: {file_list}."
          f"{template_note} file-manifest.json saved.")


if __name__ == "__main__":
    main()
