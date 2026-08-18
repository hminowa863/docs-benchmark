from __future__ import annotations

from docsbench.agents.base import AgentAdapter
from docsbench.config import Grading
from .base import Grade
from .exact import ExactGrader
from .rubric import RubricGrader
from .structured import StructuredGrader


def grade_answer(answer: str, grading: Grading | None, rubric_judge: AgentAdapter | None = None) -> Grade | None:
    if grading is None:
        return None
    graders = {"exact": ExactGrader(), "structured": StructuredGrader(), "rubric": RubricGrader(rubric_judge)}
    try:
        return graders[grading.type].grade(answer, grading)
    except KeyError as exc:
        raise ValueError(f"unsupported grading type: {grading.type}") from exc


__all__ = ["Grade", "grade_answer"]
