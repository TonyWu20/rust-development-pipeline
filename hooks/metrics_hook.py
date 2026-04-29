#!/usr/bin/env python3
"""
PostToolUse / PostToolUseFailure hook that records tool-usage metrics for
data-driven optimization.

Two data sources:
  1. Per-tool-call proxy metrics (input/output sizes) – recorded on every event.
  2. Per-turn usage from transcript assistant messages (REAL token counts) –
     scanned incrementally from the conversation transcript (transcript_path in
     the hook event).

Stage detection: reads the marker file at .claude/.current_stage, which each
skill writes at startup.  Falls back to "unknown".

State tracking: a small JSON file at .claude/.metrics_state.json remembers the
last transcript byte-position scanned so each call processes only new data.

Output:
  - notes/metrics/{date}.jsonl               – all events (tool + turn)
  - notes/metrics/by-stage/{stage}-{date}.jsonl – per-stage breakdown

Async-safe: intended to run with "async": true in hooks.json so the
conversation thread is never blocked.

Exit codes:
  0 — always (observational hook, never blocks).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ENV_PROJECT_DIR = "CLAUDE_PROJECT_DIR"
METRICS_DIR_REL = Path("notes") / "metrics"
STATE_FILE_REL = Path(".claude") / ".metrics_state.json"

# ── helpers ──────────────────────────────────────────────────────────────


def _project_dir(event: dict) -> str | None:
    for src in (ENV_PROJECT_DIR, "cwd"):
        val = os.environ.get(src) or event.get(src, "")
        if val:
            return val
    try:
        return os.getcwd()
    except OSError:
        return None


def _read_stage(project_dir: str) -> str:
    marker = Path(project_dir) / ".claude" / ".current_stage"
    if not marker.exists():
        return "unknown"
    try:
        return marker.read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def _size(obj: object) -> int:
    try:
        return len(json.dumps(obj, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


# ── state management ─────────────────────────────────────────────────────


def _state_path(project_dir: str) -> Path:
    return Path(project_dir) / STATE_FILE_REL


def _read_state(project_dir: str) -> dict:
    p = _state_path(project_dir)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"transcript_path": "", "transcript_bytes": 0}


def _write_state(project_dir: str, state: dict) -> None:
    p = _state_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False) + "\n")


# ── transcript scanning ──────────────────────────────────────────────────


def _scan_transcript_for_usage(
    transcript_path: str, last_bytes: int
) -> tuple[list[dict], int]:
    """Scan *transcript_path* from *last_bytes* onward and return:
    (new_usage_records, new_file_size).

    Each usage record is a dict with:
      ts, turn_id (message uuid), model,
      input_tokens, cache_creation_input_tokens, cache_read_input_tokens,
      output_tokens, tool_use_ids (list).
    """
    tpath = Path(transcript_path)
    if not tpath.exists():
        return [], 0

    file_size = tpath.stat().st_size
    if file_size <= last_bytes:
        return [], file_size  # nothing new

    records: list[dict] = []
    with open(tpath, "r") as f:
        f.seek(last_bytes)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # We only care about assistant messages that contain usage data.
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message") or {}
            usage = msg.get("usage")
            if not usage:
                continue

            # Extract tool_use_ids from the message content
            tool_use_ids: list[str] = []
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tid = block.get("id", "")
                        if tid:
                            tool_use_ids.append(tid)

            records.append(
                {
                    "ts": entry.get("timestamp", ""),
                    "turn_id": entry.get("uuid", ""),
                    "model": msg.get("model", ""),
                    "hook_event": "assistant_turn",
                    "input_tokens": usage.get("input_tokens", 0),
                    "cache_creation_input_tokens": usage.get(
                        "cache_creation_input_tokens", 0
                    ),
                    "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "tool_use_ids": tool_use_ids,
                }
            )

    return records, file_size


# ── logging ──────────────────────────────────────────────────────────────


def _log(metrics_dir: Path, date_str: str, stage: str, record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"

    # daily file
    daily = metrics_dir / f"{date_str}.jsonl"
    try:
        with open(daily, "a") as f:
            f.write(line)
    except OSError:
        return

    # per-stage file
    stage_dir = metrics_dir / "by-stage"
    stage_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(stage_dir / f"{stage}-{date_str}.jsonl", "a") as f:
            f.write(line)
    except OSError:
        pass


# ── main ─────────────────────────────────────────────────────────────────


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        event = json.loads(raw)
    except (json.JSONDecodeError, EOFError):
        return

    project_dir = _project_dir(event)
    if not project_dir:
        return

    stage = _read_stage(project_dir)
    hook_event = event.get("hook_event_name", "PostToolUse")
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")
    metrics_dir = Path(project_dir) / METRICS_DIR_REL
    metrics_dir.mkdir(parents=True, exist_ok=True)

    tool_use_id = event.get("tool_use_id", "")

    # ── 1. Per-tool-call proxy record --------------------------------
    tool_input = event.get("tool_input", {})
    tool_response = event.get("tool_response", {})
    input_chars = _size(tool_input)
    output_chars = _size(tool_response)

    proxy_record: dict = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "session_id": event.get("session_id", ""),
        "tool_use_id": tool_use_id,
        "stage": stage,
        "tool_name": event.get("tool_name", ""),
        "hook_event": hook_event,
        "input_chars": input_chars,
        "output_chars": output_chars,
    }
    if hook_event == "PostToolUseFailure":
        proxy_record["error"] = event.get("error", "")

    _log(metrics_dir, date_str, stage, proxy_record)

    # ── 2. Per-turn usage from transcript ----------------------------
    transcript_path = event.get("transcript_path", "")
    if not transcript_path:
        return

    state = _read_state(project_dir)

    # Reset state if the transcript changed (new session)
    if state.get("transcript_path") != transcript_path:
        state = {"transcript_path": transcript_path, "transcript_bytes": 0}

    records, file_size = _scan_transcript_for_usage(
        transcript_path, state.get("transcript_bytes", 0)
    )

    if records:
        for rec in records:
            rec["stage"] = stage
            _log(metrics_dir, date_str, stage, rec)

        state["transcript_bytes"] = file_size
        _write_state(project_dir, state)


if __name__ == "__main__":
    main()
