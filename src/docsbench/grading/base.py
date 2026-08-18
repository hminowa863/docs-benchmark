from __future__ import annotations

from dataclasses import dataclass

from docsbench.config import Grading


@dataclass(frozen=True)
class Grade:
    score: float | None
    max_score: float | None
    normalized: float | None
    detail: str = ""


class Grader:
    def grade(self, answer: str, grading: Grading) -> Grade:
        raise NotImplementedError
