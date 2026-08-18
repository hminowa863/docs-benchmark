from __future__ import annotations

import json
import re
from typing import Any

from docsbench.config import Grading
from .base import Grade, Grader


class StructuredGrader(Grader):
    def grade(self, answer: str, grading: Grading) -> Grade:
        expected = grading.expected
        if not isinstance(expected, dict):
            raise ValueError("structured grading expected value must be a mapping")
        actual = _json_object(answer)
        if actual is None:
            return Grade(0.0, 1.0, 0.0, "answer did not contain a JSON object")
        correct = all(actual.get(key) == value for key, value in expected.items())
        return Grade(float(correct), 1.0, float(correct), "structured match" if correct else "structured mismatch")


def _json_object(answer: str) -> dict[str, Any] | None:
    candidates = [answer.strip()]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", answer, flags=re.DOTALL | re.IGNORECASE))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
