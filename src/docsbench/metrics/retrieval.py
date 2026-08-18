from __future__ import annotations

from dataclasses import dataclass
from docsbench.agents.base import ToolCall


@dataclass(frozen=True)
class RetrievalMetrics:
    tool_calls: int
    search_calls: int
    files_read: int
    unique_files_read: tuple[str, ...]
    docs_files_read: int
    source_files_read: int
    relevant_files_read: int | None
    relevant_files_total: int | None
    relevant_context_recall: float | None
    relevant_context_precision: float | None

    def as_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


def calculate_retrieval(calls: tuple[ToolCall, ...], relevant_paths: tuple[str, ...]) -> RetrievalMetrics:
    files = tuple(dict.fromkeys(file for call in calls for file in call.files))
    search = sum(_is_search(call.command or "") for call in calls)
    docs = sum(file == "README.md" or file == "AGENTS.md" or file.startswith("docs/") for file in files)
    if not relevant_paths:
        relevant_read = relevant_total = None
        recall = precision = None
    else:
        relevant = [file for file in files if file in relevant_paths]
        relevant_read, relevant_total = len(relevant), len(relevant_paths)
        recall = relevant_read / relevant_total if relevant_total else None
        precision = relevant_read / len(files) if files else 0.0
    return RetrievalMetrics(len(calls), search, len(files), files, docs, len(files) - docs,
                            relevant_read, relevant_total, recall, precision)


def _is_search(command: str) -> bool:
    return any(token in command.lower().split() for token in ("rg", "grep", "find", "select-string"))

