from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DocsVariant:
    name: str
    type: str
    ref: str | None = None


@dataclass(frozen=True)
class Target:
    name: str
    repository: Path
    code_ref: str
    docs_paths: tuple[str, ...]
    variants: tuple[DocsVariant, ...]
    config_path: Path


@dataclass(frozen=True)
class Criterion:
    id: str
    description: str
    points: float


@dataclass(frozen=True)
class Grading:
    type: str
    expected: Any = None
    criteria: tuple[Criterion, ...] = ()


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    question: str
    grading: Grading | None = None
    relevant_context: tuple[str, ...] = ()


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    return value


def load_target(path: Path) -> Target:
    path = path.resolve()
    data = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "target.yaml")
    docs = _mapping(data.get("docs", {}), "docs")
    variants = tuple(
        DocsVariant(name=str(v["name"]), type=str(v["type"]), ref=v.get("ref"))
        for item in data.get("variants", [])
        for v in (_mapping(item, "variant"),)
    )
    if not variants:
        raise ValueError("target must define at least one variant")
    repository = Path(str(data["repository"]))
    if not repository.is_absolute():
        # Target files conventionally live in targets/<target>/; resolve their
        # repository paths from the DocsBench root so ../TargetRepo works.
        targets_dir = next((parent for parent in path.parents if parent.name == "targets"), None)
        base = targets_dir.parent if targets_dir is not None else path.parent
        repository = (base / repository).resolve()
    return Target(
        name=str(data["name"]), repository=repository, code_ref=str(data["code_ref"]),
        docs_paths=tuple(str(p) for p in docs.get("paths", [])), variants=variants,
        config_path=path,
    )


def load_questions(path: Path) -> tuple[Question, ...]:
    data = _mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "questions.yaml")
    questions: list[Question] = []
    for raw in data.get("questions", []):
        item = _mapping(raw, "question")
        grading_data = item.get("grading")
        grading = None
        if grading_data is not None:
            g = _mapping(grading_data, "grading")
            grading = Grading(
                type=str(g["type"]), expected=g.get("expected"),
                criteria=tuple(Criterion(str(c["id"]), str(c["description"]), float(c["points"]))
                                for raw_c in g.get("criteria", [])
                                for c in (_mapping(raw_c, "criterion"),)),
            )
        context = _mapping(item.get("context", {}), "context")
        questions.append(Question(str(item["id"]), str(item.get("category", "")),
                                  str(item["question"]), grading,
                                  tuple(str(p) for p in context.get("relevant", []))))
    if not questions:
        raise ValueError("questions.yaml must define at least one question")
    return tuple(questions)
