from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import AgentAdapter, AgentResult, ToolCall


class CodexAdapter(AgentAdapter):
    """Adapter for the Codex CLI JSONL protocol."""

    name = "codex"

    def __init__(self, executable: str = "codex", model: str | None = None) -> None:
        self.executable = executable
        self.model = model

    def run(self, workspace: Path, prompt: str) -> AgentResult:
        if not shutil.which(self.executable):
            raise RuntimeError(f"Codex executable not found: {self.executable}")
        command = [self.executable, "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)
        started = time.monotonic()
        completed = subprocess.run(command, cwd=workspace, text=True, capture_output=True, check=False)
        elapsed = time.monotonic() - started
        raw_log = completed.stdout + ("\nSTDERR:\n" + completed.stderr if completed.stderr else "")
        if completed.returncode:
            raise RuntimeError(f"Codex exited with {completed.returncode}: {completed.stderr.strip()}")
        answer, usage, tool_calls = self._parse_jsonl(completed.stdout)
        return AgentResult(answer=answer, input_tokens=usage.get("input_tokens"),
                           output_tokens=usage.get("output_tokens"), tool_calls=tuple(tool_calls),
                           elapsed_seconds=elapsed, raw_log=raw_log, agent_version=self._version(), model=self.model)

    def _version(self) -> str | None:
        completed = subprocess.run([self.executable, "--version"], text=True, capture_output=True, check=False)
        return completed.stdout.strip() or None

    @staticmethod
    def _parse_jsonl(raw_log: str) -> tuple[str, dict[str, int | None], list[ToolCall]]:
        answer = ""
        usage: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}
        calls: list[ToolCall] = []
        for line in raw_log.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            item = event.get("item", {}) if isinstance(event.get("item"), dict) else {}
            if event_type == "item.completed" and item.get("type") == "agent_message":
                answer = str(item.get("text", ""))
            elif event_type == "item.completed" and item.get("type") == "command_execution":
                command = str(item.get("command", ""))
                calls.append(ToolCall(type=_command_type(command), command=command, files=_paths_from_command(command)))
            elif event_type == "turn.completed":
                raw_usage: Any = event.get("usage", {})
                if isinstance(raw_usage, dict):
                    usage["input_tokens"] = _as_int(raw_usage.get("input_tokens"))
                    usage["output_tokens"] = _as_int(raw_usage.get("output_tokens"))
        return answer, usage, calls


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _paths_from_command(command: str) -> tuple[str, ...]:
    """Extract arguments for explicit file-reading commands only."""
    import re
    if _command_type(command) != "read":
        return ()
    paths = re.findall(r"(?:[\w.-]+/)*[\w.-]+\.(?:md|py|ts|tsx|js|jsx|json|ya?ml|toml|cs|java|go|rs|rb|php|c|h|cpp|hpp|sh)|\b(?:README|AGENTS)\.md\b", command, re.IGNORECASE)
    return tuple(dict.fromkeys(path.lstrip("./").replace("\\", "/") for path in paths))


def _command_type(command: str) -> str:
    executable = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
    return "read" if executable in {"cat", "sed", "head", "tail", "bat", "type", "get-content"} else "command"
