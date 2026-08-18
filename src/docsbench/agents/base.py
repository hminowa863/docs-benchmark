from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ToolCall:
    type: str
    command: str | None = None
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentResult:
    answer: str
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: tuple[ToolCall, ...] = ()
    elapsed_seconds: float = 0.0
    raw_log: str = ""
    agent_version: str | None = None
    model: str | None = None


class AgentAdapter:
    name: str

    def run(self, workspace: Path, prompt: str) -> AgentResult:
        raise NotImplementedError
