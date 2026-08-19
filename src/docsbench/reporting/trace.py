from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from docsbench.metrics import calculate_retrieval
from .records import format_run_title, load_run_record


def render_trace(results_root: Path, target: str, variants: set[str] | None = None,
                 question_ids: set[str] | None = None, average: bool = False) -> str:
    """Render the ordered retrieval route for each selected run."""
    runs_dir = results_root / target / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"no results found for target {target}: {runs_dir}")
    records = [_load_trace_record(path) for path in runs_dir.glob("*.json")]
    records.sort(key=lambda record: str(record.get("timestamp", "")))
    records = [record for record in records
               if (not variants or record.get("docs_variant") in variants)
               and (not question_ids or record.get("question_id") in question_ids)]
    if not records:
        return "No matching runs."
    if average:
        return _render_averages(records)
    return "\n\n".join(_render_record(record) for record in records)


def _load_trace_record(path: Path) -> dict[str, Any]:
    record, calls = load_run_record(path)
    trace = record.get("retrieval", {}).get("trace")
    if isinstance(trace, list):
        return record
    if calls:
        record.setdefault("retrieval", {}).update(calculate_retrieval(tuple(calls), ()).as_dict())
    return record


def _render_record(record: dict[str, Any]) -> str:
    title = format_run_title(record)
    trace = record.get("retrieval", {}).get("trace", [])
    if not trace:
        return title + "\n  No observable retrieval calls."
    lines = [title]
    for index, step in enumerate(trace, start=1):
        kind = str(step.get("type", "command")).upper()
        files = [str(file) for file in step.get("files", [])]
        raw_command = str(step.get("command") or "")
        search_details = _search_details(raw_command) if kind == "SEARCH" else None
        if files:
            lines.append(f"  {index}. {kind}: {', '.join(files)}")
        elif search_details:
            lines.append(f"  {index}. SEARCH: {search_details[0]}")
            lines.extend(f"     {detail}" for detail in search_details[1:])
        else:
            lines.append(f"  {index}. {kind}: {_describe_command(raw_command, kind)}")
    return "\n".join(lines)


def _shorten(value: str, limit: int = 160) -> str:
    return value if len(value) <= limit else value[:limit - 3] + "..."


def _describe_command(command: str, kind: str) -> str:
    """Show the repository action, not the PowerShell invocation boilerplate."""
    script = _unwrap_powershell(command)
    if "Test-Path -LiteralPath .codegraph" in script and "git status --short" in script:
        return "check .codegraph; git status --short"
    return _shorten(script)


def _search_details(command: str) -> tuple[str, ...] | None:
    script = _unwrap_powershell(command)
    paths = _match(r"Get-ChildItem\s+-Path\s+(.+?)(?=\s+-Recurse|\s+\||$)", script)
    pattern = _match(r"Select-String\s+-Pattern\s+(.+?)(?=\s+-[A-Za-z]|\s+\||$)", script)
    if not paths or not pattern:
        return None
    details = [_clean_argument(paths), f"pattern: {_clean_argument(pattern)}"]
    context = _match(r"-Context\s+(\d+\s*,\s*\d+)", script)
    if context:
        before, after = context.split(",")
        details.append(f"context: {before} lines before / {after} lines after")
    limit = _match(r"Select-Object\s+-First\s+(\d+)", script)
    if limit:
        details.append(f"limit: first {limit} results")
    return tuple(details)


def _unwrap_powershell(command: str) -> str:
    import re
    match = re.search(r"\s-Command\s+(.+)$", command, flags=re.IGNORECASE)
    if not match:
        return command
    return match.group(1).strip().strip("'\"")


def _match(pattern: str, value: str) -> str | None:
    import re
    match = re.search(pattern, value, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _clean_argument(value: str) -> str:
    value = value.strip().strip("'\"")
    value = value.replace("'\"'", "").replace("\"'", "")
    return value.replace(",", ", ")


def _render_averages(records: list[dict[str, Any]]) -> str:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[(str(record["docs_variant"]), str(record["question_id"]))].append(record)
    sections = []
    for (variant, question_id), group in sorted(grouped.items()):
        count = len(group)
        avg_in = _average(group, "usage", "input_tokens")
        avg_cached = _average(group, "usage", "cached_input_tokens")
        avg_out = _average(group, "usage", "output_tokens")
        avg_total = _average(group, "usage", "total_tokens")
        avg_time = _average(group, "", "elapsed_seconds")
        avg_retrieved = _average(group, "retrieval", "retrieved_chars")
        avg_files = _average(group, "retrieval", "files_read")
        avg_searches = _average(group, "retrieval", "search_calls")
        sections.append(
            f"[{variant} | {question_id} | average of {count} runs | "
            f"in={_format_average(_uncached_input(avg_in, avg_cached))}, "
            f"cached={_format_average(avg_cached)}, out={_format_average(avg_out)}, "
            f"total={_format_average(avg_total)}]\n"
            f"  time={_format_average(avg_time)}s, retrieved={_format_k(avg_retrieved)}, "
            f"files={_format_average(avg_files)}, searches={_format_average(avg_searches)}\n"
            + _file_frequency(group)
        )
    return "\n\n".join(sections)


def _average(records: list[dict[str, Any]], section: str, key: str) -> float | None:
    values = []
    for record in records:
        source = record if not section else record.get(section, {})
        value = source.get(key) if isinstance(source, dict) else None
        if value is not None:
            values.append(float(value))
    return statistics.mean(values) if values else None


def _format_average(value: float | None) -> str:
    return "-" if value is None else f"{value:,.1f}".rstrip("0").rstrip(".")


def _uncached_input(input_tokens: float | None, cached_tokens: float | None) -> float | None:
    if input_tokens is None:
        return None
    return input_tokens - (cached_tokens or 0)


def _format_k(value: float | None) -> str:
    return "-" if value is None else f"{value / 1_000:.1f}k"


def _file_frequency(records: list[dict[str, Any]]) -> str:
    frequency: Counter[str] = Counter()
    for record in records:
        files = record.get("retrieval", {}).get("unique_files_read", [])
        if isinstance(files, (list, tuple)):
            frequency.update(str(file) for file in files)
    if not frequency:
        return "  read files: -"
    count = len(records)
    files = ", ".join(f"{path} ({hits}/{count})" for path, hits in frequency.most_common())
    return "  read files: " + files
