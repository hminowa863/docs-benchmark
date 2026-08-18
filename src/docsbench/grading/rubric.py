from __future__ import annotations

import json
import tempfile
from pathlib import Path

from docsbench.agents.base import AgentAdapter
from docsbench.config import Grading
from .base import Grade, Grader
from .structured import _json_object


class RubricGrader(Grader):
    """Scores with an independently started agent, never the target workspace."""

    def __init__(self, judge: AgentAdapter | None = None) -> None:
        self.judge = judge

    def grade(self, answer: str, grading: Grading) -> Grade:
        maximum = sum(item.points for item in grading.criteria)
        if self.judge is not None:
            return self._judge(answer, grading, maximum)
        return Grade(None, maximum, None, "rubric grading requires an independent judge; answer saved for review")

    def _judge(self, answer: str, grading: Grading, maximum: float) -> Grade:
        criteria = [{"id": item.id, "description": item.description} for item in grading.criteria]
        prompt = """You are an independent benchmark grader. Do not inspect files or use outside information.

Assess only the candidate answer against the rubric. For each criterion, set true only if the answer clearly satisfies it.
Return only JSON in this exact shape:
{"criteria": {"criterion-id": true}, "reason": "brief explanation"}

Rubric:
""" + json.dumps(criteria, ensure_ascii=False) + "\n\nCandidate answer:\n" + answer
        with tempfile.TemporaryDirectory(prefix="docsbench-grader-") as directory:
            result = self.judge.run(Path(directory), prompt)
        parsed = _json_object(result.answer)
        if parsed is None or not isinstance(parsed.get("criteria"), dict):
            return Grade(0.0, maximum, 0.0, "judge did not return the requested JSON")
        satisfied = {str(key) for key, value in parsed["criteria"].items() if value is True}
        score = sum(item.points for item in grading.criteria if item.id in satisfied)
        reason = str(parsed.get("reason", "independent rubric judge"))
        return Grade(score, maximum, score / maximum if maximum else None, reason)
