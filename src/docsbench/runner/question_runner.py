from __future__ import annotations

import json
from pathlib import Path

from docsbench.agents.base import AgentAdapter
from docsbench.config import Question, Target
from docsbench.grading import grade_answer
from docsbench.metrics import UsageMetrics, calculate_retrieval

PROMPT_VERSION = "v1"


def build_prompt(question: Question) -> str:
    prompt = """You are investigating the repository in the current working directory.

Answer the following question based only on information available in the repository.

Investigate the repository as needed before answering.

Question:

""" + question.question.strip()
    if question.grading and question.grading.type == "structured" and isinstance(question.grading.expected, dict):
        schema = {key: _type_name(value) for key, value in question.grading.expected.items()}
        prompt += "\n\nReturn only a JSON object with this shape:\n" + json.dumps(schema, ensure_ascii=False)
    elif question.grading and question.grading.type == "exact":
        prompt += "\n\nReturn only the exact requested value, with no explanation."
    return prompt


def execute_question(agent: AgentAdapter, workspace: Path, target: Target, question: Question,
                     run_metadata: dict[str, object], relevant_files: tuple[str, ...] = (),
                     rubric_judge: AgentAdapter | None = None) -> dict[str, object]:
    result = agent.run(workspace, build_prompt(question))
    grade = grade_answer(result.answer, question.grading, rubric_judge)
    retrieval = calculate_retrieval(result.tool_calls, relevant_files)
    payload: dict[str, object] = {
        **run_metadata,
        "target": target.name,
        "question_id": question.id,
        "category": question.category,
        "agent": {"name": agent.name, "model": result.model, "version": result.agent_version},
        "usage": UsageMetrics(result.input_tokens, result.output_tokens).as_dict(),
        "retrieval": retrieval.as_dict(), "answer": result.answer,
        "grading": None if grade is None else {"score": grade.score, "max_score": grade.max_score,
                    "normalized": grade.normalized, "detail": grade.detail},
        "elapsed_seconds": result.elapsed_seconds,
        "prompt_version": PROMPT_VERSION,
    }
    payload["raw_log"] = result.raw_log
    return payload


def _type_name(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"
