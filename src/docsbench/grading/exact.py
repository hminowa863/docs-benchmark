from __future__ import annotations

from docsbench.config import Grading
from .base import Grade, Grader


class ExactGrader(Grader):
    def grade(self, answer: str, grading: Grading) -> Grade:
        expected = str(grading.expected).strip()
        actual = answer.strip()
        correct = actual == expected
        return Grade(float(correct), 1.0, float(correct), "exact match" if correct else "exact mismatch")
