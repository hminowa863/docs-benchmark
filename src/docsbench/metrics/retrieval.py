from __future__ import annotations

from dataclasses import dataclass
from docsbench.agents.base import ToolCall


@dataclass(frozen=True)
class RetrievalMetrics:
    tool_calls: int
    search_calls: int
    retrieved_chars: int
    files_read: int
    unique_files_read: tuple[str, ...]
    docs_files_read: int
    source_files_read: int
    relevant_files_read: int | None
    relevant_files_total: int | None
    relevant_context_recall: float | None
    relevant_context_precision: float | None
    trace: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def calculate_retrieval(calls: tuple[ToolCall, ...], relevant_paths: tuple[str, ...]) -> RetrievalMetrics:
    files = tuple(dict.fromkeys(file for call in calls for file in call.files))
    search = sum(_is_search(call.command or "") for call in calls)
    retrieved_chars = sum(call.output_chars for call in calls)
    docs = sum(file == "README.md" or file == "AGENTS.md" or file.startswith("docs/") for file in files)
    if not relevant_paths:
        relevant_read = relevant_total = None
        recall = precision = None
    else:
        relevant = [file for file in files if file in relevant_paths]
        relevant_read, relevant_total = len(relevant), len(relevant_paths)
        recall = relevant_read / relevant_total if relevant_total else None
        precision = relevant_read / len(files) if files else 0.0
    trace = tuple({"type": _trace_type(call), "command": call.command, "files": list(call.files)} for call in calls)
    return RetrievalMetrics(len(calls), search, retrieved_chars, len(files), files, docs, len(files) - docs,
                            relevant_read, relevant_total, recall, precision, trace)


def _is_search(command: str) -> bool:
    return any(token in command.lower().split() for token in ("rg", "grep", "find", "select-string"))


def _trace_type(call: ToolCall) -> str:
    if _is_search(call.command or ""):
        return "search"
    return call.type
