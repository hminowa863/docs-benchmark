from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from .csv import write_summary_csv


def build_summary(results_root: Path, target: str) -> list[dict[str, object]]:
    runs_dir = results_root / target / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"no results found for target {target}: {runs_dir}")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in runs_dir.glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        grouped[str(record["docs_variant"])].append(record)
    rows = [_summarize_variant(name, records) for name, records in sorted(grouped.items())]
    write_summary_csv(results_root / target / "summary.csv", rows)
    return rows


def render_summary(target: str, rows: list[dict[str, object]]) -> str:
    headers = ["Variant", "Accuracy", "Median input", "Files", "Searches", "Cost/correct"]
    table = [headers]
    for row in rows:
        table.append([
            str(row["variant"]), _format_percent(row["accuracy"]), _format_number(row["median_input_tokens"]),
            _format_number(row["avg_files_read"]), _format_number(row["avg_search_calls"]),
            _format_number(row["tokens_per_correct"]),
        ])
    widths = [max(len(line[index]) for line in table) for index in range(len(headers))]
    lines = [f"DocsBench — {target}", "", "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(table[0]))]
    lines.extend("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)) for line in table[1:])
    return "\n".join(lines)


def _summarize_variant(name: str, records: list[dict[str, Any]]) -> dict[str, object]:
    normalized = [record.get("grading", {}).get("normalized") for record in records if record.get("grading")]
    graded = [float(value) for value in normalized if value is not None]
    input_tokens = _values(records, "usage", "input_tokens")
    total_tokens = _values(records, "usage", "total_tokens")
    files = _values(records, "retrieval", "files_read")
    searches = _values(records, "retrieval", "search_calls")
    calls = _values(records, "retrieval", "tool_calls")
    correct = sum(1 for value in graded if value == 1.0)
    return {
        "variant": name, "runs": len(records), "accuracy": _mean(graded),
        "median_input_tokens": _median(input_tokens), "median_total_tokens": _median(total_tokens),
        "avg_files_read": _mean(files), "avg_search_calls": _mean(searches), "avg_tool_calls": _mean(calls),
        "tokens_per_correct": sum(total_tokens) / correct if correct else None,
    }


def _values(records: list[dict[str, Any]], section: str, key: str) -> list[float]:
    return [float(record[section][key]) for record in records if record.get(section, {}).get(key) is not None]


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _format_percent(value: object) -> str:
    return "—" if value is None else f"{float(value):.0%}"


def _format_number(value: object) -> str:
    return "—" if value is None else f"{float(value):,.1f}".rstrip("0").rstrip(".")
