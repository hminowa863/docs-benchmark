from __future__ import annotations

import json
from pathlib import Path

from docsbench.config import Criterion, Grading
from docsbench.config import DocsVariant, Question, Target, load_target
from docsbench.agents.mock import MockAdapter
from docsbench.agents.base import AgentResult
from docsbench.agents.codex import CodexAdapter
from docsbench.grading import grade_answer
from docsbench.reporting import build_summary, render_review, render_trace
from docsbench.reporting.records import format_run_title
from docsbench.runner.benchmark import BenchmarkRunner
from docsbench.runner.question_runner import PROMPT_VERSION, build_prompt
from docsbench.runner.workspace import Workspace


def test_structured_grader_accepts_fenced_json() -> None:
    grade = grade_answer("```json\n{\"owner\": \"Adventurer\"}\n```", Grading("structured", {"owner": "Adventurer"}))
    assert grade and grade.normalized == 1.0


def test_rubric_grader_uses_independent_judge(tmp_path: Path) -> None:
    class Judge(MockAdapter):
        def run(self, workspace: Path, prompt: str) -> AgentResult:
            assert "Candidate answer" in prompt
            return AgentResult('{"criteria": {"autonomy": true}, "reason": "present"}', 0, 0)
    grading = Grading("rubric", criteria=(Criterion("autonomy", "mentions autonomy", 2),))
    grade = grade_answer("candidate", grading, Judge())
    assert grade and grade.normalized == 1.0


def test_summary_writes_csv(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    record = {"docs_variant": "current", "usage": {"input_tokens": 100, "cached_input_tokens": 80,
              "input_token_equivalent": 28, "total_tokens": 140},
              "retrieval": {"retrieved_chars": 2500, "files_read": 2, "search_calls": 1, "tool_calls": 3},
              "grading": {"normalized": 1.0}}
    (runs / "one.json").write_text(json.dumps(record), encoding="utf-8")
    rows = build_summary(tmp_path / "results", "Example")
    assert rows[0]["accuracy"] == 1.0
    assert rows[0]["avg_input_token_equivalent"] == 28
    assert rows[0]["avg_retrieved_chars"] == 2500
    assert (tmp_path / "results" / "Example" / "summary.csv").exists()


def test_review_renders_ungraded_answers(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    (runs / "one.json").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00", "docs_variant": "no-docs",
        "question_id": "Q1", "repeat": 1, "answer": "candidate answer",
        "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20, "total_tokens": 120},
    }), encoding="utf-8")
    review = render_review(tmp_path / "results", "Example")
    assert "candidate answer" in review
    assert "in=20, cached=80, out=20, total=120" in review


def test_codex_parser_counts_powershell_file_reads() -> None:
    raw_log = '{"type":"item.completed","item":{"type":"command_execution","command":"pwsh -Command \'Get-Content docs/guide.md; Get-Content README.md\'","aggregated_output":"contents"}}\n'
    _, _, calls = CodexAdapter._parse_jsonl(raw_log)
    assert calls[0].type == "read"
    assert calls[0].files == ("docs/guide.md", "README.md")
    assert calls[0].output_chars == 8


def test_question_prompt_requests_economical_targeted_investigation() -> None:
    prompt = build_prompt(Question("Q1", "fact", "Where is the protocol defined?"))
    assert PROMPT_VERSION == "v2"
    assert "Do not run `git status`" in prompt
    assert "Combine related reads into one command" in prompt


def test_usage_metrics_discount_cached_input() -> None:
    from docsbench.metrics import UsageMetrics
    assert UsageMetrics(100, 20, 80).input_token_equivalent == 28


def test_trace_renders_saved_retrieval_order(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    (runs / "one.json").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00", "docs_variant": "after-docs",
        "question_id": "Q1", "repeat": 1,
        "usage": {"input_tokens": 100, "cached_input_tokens": 80, "output_tokens": 20, "total_tokens": 120},
        "retrieval": {"trace": [
            {"type": "search", "command": "rg protocol", "files": []},
            {"type": "read", "command": "Get-Content", "files": ["docs/protocol.md"]},
        ]},
    }), encoding="utf-8")
    route = render_trace(tmp_path / "results", "Example")
    assert "SEARCH: rg protocol" in route
    assert "READ: docs/protocol.md" in route
    assert "in=20, cached=80, out=20, total=120" in route
    assert "] @one" in route


def test_review_and_trace_share_the_same_run_title_format() -> None:
    record = {"run_id": "asdfasf123", "docs_variant": "after-docs", "question_id": "Q1", "repeat": 1,
              "elapsed_seconds": 42.34,
              "usage": {"input_tokens": 100, "cached_input_tokens": 80,
                        "output_tokens": 20, "total_tokens": 120}}
    assert format_run_title(record) == "[after-docs | Q1 | run 1 | in=20, cached=80, out=20, total=120 | 42.3 s] @asdfasf"


def test_average_trace_splits_cached_input(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    (runs / "one.json").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00", "docs_variant": "after-docs",
        "question_id": "Q1", "usage": {"input_tokens": 100, "cached_input_tokens": 80,
        "output_tokens": 20, "total_tokens": 120}, "retrieval": {"trace": []},
    }), encoding="utf-8")
    assert "in=20, cached=80, out=20, total=120" in render_trace(tmp_path / "results", "Example", average=True)


def test_trace_hides_powershell_wrapper(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    command = ('"C:\\\\Program Files\\\\PowerShell\\\\7\\\\pwsh.exe" -Command '
               '"Get-ChildItem -Path docs,README.md -Recurse -File | '
               "Select-String -Pattern 'emergency stop' -Context 3,4")
    (runs / "one.json").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00", "docs_variant": "after-docs",
        "question_id": "Q1", "retrieval": {"trace": [{"type": "search", "command": command, "files": []}]},
    }), encoding="utf-8")
    route = render_trace(tmp_path / "results", "Example")
    assert "SEARCH: docs, README.md" in route
    assert "pattern: emergency stop" in route
    assert "context: 3 lines before / 4 lines after" in route
    assert "PowerShell" not in route


def test_benchmark_writes_a_run_record(tmp_path: Path) -> None:
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "app.py").write_text("pass", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.test", "commit", "-m", "initial"],
                   cwd=repo, check=True, capture_output=True)
    questions_path = tmp_path / "questions.yaml"
    questions_path.write_text("questions:\n  - id: Q1\n    category: fact\n    question: What is this?\n", encoding="utf-8")
    target = Target("Example", repo, "HEAD", (), (DocsVariant("none", "remove"),), tmp_path / "target.yaml")
    paths = BenchmarkRunner(target, questions_path, tmp_path / "results", MockAdapter()).run(target.variants)
    record = json.loads(paths[0].read_text(encoding="utf-8"))
    assert record["question_id"] == "Q1"
    assert record["raw_log_path"].endswith(".log")


def test_target_reads_codegraph_initialization_setting(tmp_path: Path) -> None:
    target_path = tmp_path / "target.yaml"
    target_path.write_text(
        "name: Example\nrepository: .\ncode_ref: main\ndocs: {paths: []}\n"
        "variants: [{name: codegraph, codegraph: {init: true}}]\n",
        encoding="utf-8",
    )

    variant = load_target(target_path).variants[0]
    assert variant.type == "baseline"
    assert variant.codegraph_init is True


def test_benchmark_yaml_option_initializes_codegraph_and_records_it(tmp_path: Path, monkeypatch) -> None:
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    (repo / "app.py").write_text("pass", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.test", "commit", "-m", "initial"],
                   cwd=repo, check=True, capture_output=True)
    questions_path = tmp_path / "questions.yaml"
    questions_path.write_text("questions:\n  - id: Q1\n    category: fact\n    question: What is this?\n", encoding="utf-8")
    target = Target("Example", repo, "HEAD", (), (DocsVariant("codegraph", codegraph_init=True),),
                    tmp_path / "target.yaml")
    initialized: list[Path] = []
    monkeypatch.setattr(Workspace, "initialize_codegraph", lambda workspace: initialized.append(workspace.repo))

    paths = BenchmarkRunner(target, questions_path, tmp_path / "results", MockAdapter()).run(target.variants)

    record = json.loads(paths[0].read_text(encoding="utf-8"))
    assert len(initialized) == 1
    assert record["codegraph_initialized"] is True
