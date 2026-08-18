from __future__ import annotations

from pathlib import Path

from .base import AgentAdapter, AgentResult


class MockAdapter(AgentAdapter):
    """Deterministic adapter for validating setup without an agent CLI."""

    name = "mock"

    def run(self, workspace: Path, prompt: str) -> AgentResult:
        return AgentResult(answer="Mock agent: no answer generated.", input_tokens=0, output_tokens=0)
