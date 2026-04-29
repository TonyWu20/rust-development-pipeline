#!/usr/bin/env python3
"""
Evaluate performance and token usage for a completed skill session.

Reads the metrics collected by hooks/metrics_hook.py during a skill run and
prints a summary suitable for inclusion in the skill's handoff message.

Usage:
    python3 scripts/eval-session-metrics.py <stage-name>

Where <stage-name> is e.g. "elaborate-directions", "explore-implement",
"make-judgement".

The script reads:
  1. .claude/.session_start — timestamp (ms epoch) written by the skill at
     startup; only metrics after this point are counted.
  2. notes/metrics/by-stage/{stage}-{date}.jsonl — the per-stage metrics file
     for today.

Exit code 0 always. Output is plain text for the handoff message.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Approximate API pricing per 1M tokens (USD) — update when rates change.
MODEL_COST = {
    "claude-opus-4-6": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 15.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.0},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_create": 1.0},
    # fallback for unknown models
    "default": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_create": 3.0},
}


def _project_dir() -> str | None:
    for var in ("CLAUDE_PROJECT_DIR", "PWD"):
        val = os.environ.get(var)
        if val:
            return val
    try:
        return os.getcwd()
    except OSError:
        return None


def _read_session_start(project_dir: str) -> int:
    """Read session start timestamp in ms epoch. Returns 0 if missing."""
    p = Path(project_dir) / ".claude" / ".session_start"
    if not p.exists():
        return 0
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return 0


def _read_metrics(path: Path, session_start_ms: int) -> list[dict]:
    """Read and parse a JSONL metrics file, filtering to records after
    *session_start_ms*."""
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        text = path.read_text()
    except OSError:
        return []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        # filter by session start time
        ts = rec.get("ts", "")
        if ts and session_start_ms > 0:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                rec_ms = int(dt.timestamp() * 1000)
                if rec_ms < session_start_ms:
                    continue
            except (ValueError, TypeError):
                pass
        records.append(rec)
    return records


def _summarize(records: list[dict]) -> str:
    """Produce a plain-text summary from metrics records."""
    # Separate turn records from tool records
    turn_records = [r for r in records if r.get("hook_event") == "assistant_turn"]
    tool_records = [r for r in records if r.get("hook_event") != "assistant_turn"]

    # ── Token aggregation (from assistant turns) ──────────────
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_create = 0
    model_turns: dict[str, int] = {}
    model_input: dict[str, int] = {}
    model_output: dict[str, int] = {}

    for rec in turn_records:
        inp = rec.get("input_tokens", 0) or 0
        out = rec.get("output_tokens", 0) or 0
        cr = rec.get("cache_read_input_tokens", 0) or 0
        cc = rec.get("cache_creation_input_tokens", 0) or 0
        total_input += inp
        total_output += out
        total_cache_read += cr
        total_cache_create += cc
        model = rec.get("model", "unknown")
        model_turns[model] = model_turns.get(model, 0) + 1
        model_input[model] = model_input.get(model, 0) + inp
        model_output[model] = model_output.get(model, 0) + out

    # ── Tool call aggregation ─────────────────────────────────
    tool_counts: dict[str, int] = {}
    for rec in tool_records:
        tn = rec.get("tool_name", "unknown")
        tool_counts[tn] = tool_counts.get(tn, 0) + 1
    total_tool_calls = sum(tool_counts.values())

    # ── Cost estimate ──────────────────────────────────────────
    total_cost = 0.0
    for model in set(list(model_turns.keys())):
        rates = MODEL_COST.get(model, MODEL_COST["default"])
        mi = model_input.get(model, 0)
        mo = model_output.get(model, 0)
        # cache costs: approx proportional
        mcr = total_cache_read * (mi / total_input) if total_input else 0
        mcc = total_cache_create * (mi / total_input) if total_input else 0
        cost = (
            (mi / 1_000_000) * rates["input"]
            + (mo / 1_000_000) * rates["output"]
            + (mcr / 1_000_000) * rates["cache_read"]
            + (mcc / 1_000_000) * rates["cache_create"]
        )
        total_cost += cost

    # ── Tool call line ─────────────────────────────────────────
    tool_detail = ", ".join(
        f"{tn}={n}" for tn, n in sorted(tool_counts.items(), key=lambda x: -x[1])[:5]
    )
    if len(tool_counts) > 5:
        tool_detail += f", +{len(tool_counts) - 5} more"

    # ── Model detail lines ─────────────────────────────────────
    model_lines: list[str] = []
    for model in sorted(model_turns.keys()):
        mt = model_turns[model]
        mi = model_input[model]
        mo = model_output[model]
        short = model.replace("claude-", "").replace("-4-6", "").replace("-4-5", "")
        model_lines.append(f"  {short}: {mt} turns ({mi:,} in / {mo:,} out)")

    # ── Build report ───────────────────────────────────────────
    lines = [
        "── Session Metrics ──────────────────────────────",
        f"  Tokens: {total_input:,} in / {total_output:,} out",
    ]
    if total_cache_read > 0 or total_cache_create > 0:
        lines.append(f"  Cache:  {total_cache_read:,} read / {total_cache_create:,} created")
    lines.append(f"  Tool calls: {total_tool_calls:,} total ({tool_detail})")
    lines.append("  Model usage:")
    lines.extend(model_lines)
    if total_cost > 0:
        lines.append(f"  Est. cost: ${total_cost:.4f}")
    lines.append("──────────────────────────────────────────────")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        stage = "unknown"
    else:
        stage = sys.argv[1]

    project_dir = _project_dir()
    if not project_dir:
        print("Session Metrics: unable to determine project directory")
        return

    session_start_ms = _read_session_start(project_dir)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    metrics_path = (
        Path(project_dir)
        / "notes"
        / "metrics"
        / "by-stage"
        / f"{stage}-{date_str}.jsonl"
    )

    records = _read_metrics(metrics_path, session_start_ms)
    if not records:
        print("Session Metrics: no data recorded yet.")
        return

    print(_summarize(records))


if __name__ == "__main__":
    main()
