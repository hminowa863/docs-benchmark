from __future__ import annotations

import json
from pathlib import Path

from docsbench.config import Criterion, Grading
from docsbench.config import DocsVariant, Question, Target
from docsbench.agents.mock import MockAdapter
from docsbench.agents.base import AgentResult
from docsbench.grading import grade_answer
from docsbench.reporting import build_summary, render_review
from docsbench.runner.benchmark import BenchmarkRunner


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
    record = {"docs_variant": "current", "usage": {"input_tokens": 100, "total_tokens": 140},
              "retrieval": {"files_read": 2, "search_calls": 1, "tool_calls": 3},
              "grading": {"normalized": 1.0}}
    (runs / "one.json").write_text(json.dumps(record), encoding="utf-8")
    rows = build_summary(tmp_path / "results", "Example")
    assert rows[0]["accuracy"] == 1.0
    assert (tmp_path / "results" / "Example" / "summary.csv").exists()


def test_review_renders_ungraded_answers(tmp_path: Path) -> None:
    runs = tmp_path / "results" / "Example" / "runs"
    runs.mkdir(parents=True)
    (runs / "one.json").write_text(json.dumps({
        "timestamp": "2026-01-01T00:00:00+00:00", "docs_variant": "no-docs",
        "question_id": "Q1", "repeat": 1, "answer": "candidate answer",
    }), encoding="utf-8")
    assert "candidate answer" in render_review(tmp_path / "results", "Example")


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
