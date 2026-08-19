from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docsbench.agents.codex import CodexAdapter
from docsbench.agents.base import ToolCall
from docsbench.metrics import UsageMetrics


def load_run_record(path: Path) -> tuple[dict[str, Any], tuple[ToolCall, ...]]:
    """Load a saved run and enrich its usage from the preserved Codex event log."""
    record = json.loads(path.read_text(encoding="utf-8"))
    # Saved records normally include this value, but derive it from the result
    # filename for older records as well.
    record.setdefault("run_id", path.stem)
    log_path = path.with_suffix(".log")
    if not log_path.exists():
        return record, ()
    _, usage, calls = CodexAdapter._parse_jsonl(log_path.read_text(encoding="utf-8", errors="replace"))
    if usage.get("input_tokens") is not None:
        record["usage"] = UsageMetrics(usage.get("input_tokens"), usage.get("output_tokens"),
                                       usage.get("cached_input_tokens")).as_dict()
    return record, tuple(calls)


def format_run_title(record: dict[str, Any]) -> str:
    elapsed_label = format_elapsed_label(record.get("elapsed_seconds"))
    title = (f"[{record['docs_variant']} | {record['question_id']} | "
             f"run {record.get('repeat', 1)}{format_usage_label(record.get('usage'))}"
             f"{elapsed_label}]")
    run_id = record.get("run_id")
    return f"{title} @{str(run_id)[:7]}" if run_id else title


def format_usage_label(usage: object) -> str:
    """Format token usage consistently in review and trace output."""
    if not isinstance(usage, dict) or usage.get("total_tokens") is None:
        return ""
    input_tokens = _as_int(usage.get("input_tokens"))
    cached_tokens = _as_int(usage.get("cached_input_tokens"))
    output_tokens = _as_int(usage.get("output_tokens"))
    total_tokens = _as_int(usage.get("total_tokens"))
    if total_tokens is None:
        return ""
    parts = []
    if input_tokens is not None:
        uncached = input_tokens - (cached_tokens or 0)
        parts.append(f"in={uncached:,}")
    if cached_tokens is not None:
        parts.append(f"cached={cached_tokens:,}")
    if output_tokens is not None:
        parts.append(f"out={output_tokens:,}")
    parts.append(f"total={total_tokens:,}")
    return " | " + ", ".join(parts)


def format_elapsed_label(value: object) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    return f" | {value:.1f} s"


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
