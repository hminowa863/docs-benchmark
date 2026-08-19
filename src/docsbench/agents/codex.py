from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .base import AgentAdapter, AgentResult, ToolCall


class CodexAdapter(AgentAdapter):
    """Adapter for the Codex CLI JSONL protocol."""

    name = "codex"

    def __init__(self, executable: str = "codex", model: str | None = None,
                 on_progress: Callable[[str], None] | None = None) -> None:
        self.executable = executable
        self.model = model
        self.on_progress = on_progress

    def run(self, workspace: Path, prompt: str) -> AgentResult:
        if not shutil.which(self.executable):
            raise RuntimeError(f"Codex executable not found: {self.executable}")
        command = [self.executable, "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)
        started = time.monotonic()
        process = subprocess.Popen(
            command, cwd=workspace, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        lines: list[str] = []
        assert process.stdout is not None
        try:
            for line in process.stdout:
                lines.append(line)
                self._report_event(line)
            return_code = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
        elapsed = time.monotonic() - started
        raw_log = "".join(lines)
        if return_code:
            raise RuntimeError(f"Codex exited with {return_code}. See the run log for details.\n{raw_log[-2000:]}")
        answer, usage, tool_calls = self._parse_jsonl(raw_log)
        return AgentResult(answer=answer, input_tokens=usage.get("input_tokens"),
                           output_tokens=usage.get("output_tokens"),
                           cached_input_tokens=usage.get("cached_input_tokens"), tool_calls=tuple(tool_calls),
                           elapsed_seconds=elapsed, raw_log=raw_log, agent_version=self._version(), model=self.model)

    def _version(self) -> str | None:
        completed = subprocess.run([self.executable, "--version"], text=True, capture_output=True,
                                   encoding="utf-8", errors="replace", check=False)
        return completed.stdout.strip() or None

    def _report_event(self, line: str) -> None:
        if self.on_progress is None:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        item = event.get("item", {}) if isinstance(event.get("item"), dict) else {}
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            self.on_progress(f"  Agent command: {item.get('command', '')}")
        elif event.get("type") == "turn.started":
            self.on_progress("  Agent is investigating…")

    @staticmethod
    def _parse_jsonl(raw_log: str) -> tuple[str, dict[str, int | None], list[ToolCall]]:
        answer = ""
        usage: dict[str, int | None] = {
            "input_tokens": None, "cached_input_tokens": None, "output_tokens": None,
        }
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
                if item.get("exit_code", 0) == 0:
                    output = str(item.get("aggregated_output", ""))
                    calls.append(ToolCall(type=_command_type(command), command=command,
                                          files=_paths_from_command(command), output_chars=len(output)))
            elif event_type == "item.completed" and item.get("type") == "mcp_tool_call":
                call = _mcp_read_call(item)
                if call is not None:
                    calls.append(call)
            elif event_type == "turn.completed":
                raw_usage: Any = event.get("usage", {})
                if isinstance(raw_usage, dict):
                    usage["input_tokens"] = _as_int(raw_usage.get("input_tokens"))
                    usage["cached_input_tokens"] = _as_int(raw_usage.get("cached_input_tokens"))
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
    # Codex on Windows often invokes PowerShell as an outer executable, with
    # Get-Content or Select-String inside its -Command script.
    import re
    return "read" if re.search(r"\b(?:cat|sed|head|tail|bat|type|get-content)\b", command,
                                re.IGNORECASE) else "command"


def _mcp_read_call(item: dict[str, Any]) -> ToolCall | None:
    """Record file reads made via Codex's Node REPL fallback tool."""
    if item.get("server") != "node_repl" or item.get("tool") != "js":
        return None
    arguments = item.get("arguments", {})
    code = arguments.get("code", "") if isinstance(arguments, dict) else ""
    if "readFile" not in str(code):
        return None
    result = item.get("result", {})
    content = result.get("content", []) if isinstance(result, dict) else []
    text = "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
    import re
    files = re.findall(r"^###\s+([^\r\n]+)$", text, flags=re.MULTILINE)
    title = arguments.get("title", "Node REPL file read") if isinstance(arguments, dict) else "Node REPL file read"
    return ToolCall(type="read", command=f"node_repl: {title}",
                    files=tuple(dict.fromkeys(_normalise_path(path) for path in files)), output_chars=len(text))


def _normalise_path(path: str) -> str:
    return path.strip().replace("\\", "/").lstrip("./")
