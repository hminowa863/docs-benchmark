from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from docsbench.agents.base import AgentAdapter
from docsbench.config import DocsVariant, Target, load_questions
from docsbench.git import GitRepository, apply_docs_overlay, apply_submodule_docs_overlays
from docsbench.git.docs_overlay import selected_files
from .question_runner import execute_question
from .workspace import Workspace


class BenchmarkRunner:
    def __init__(self, target: Target, questions_path: Path, output_root: Path, agent: AgentAdapter,
                 keep_workspaces: bool = False, rubric_judge: AgentAdapter | None = None,
                 on_progress: Callable[[str], None] | None = None,
                 codegraph_init: bool = False) -> None:
        self.target = target
        self.questions_path = questions_path
        self.output_root = output_root / target.name
        self.agent = agent
        self.keep_workspaces = keep_workspaces
        self.codegraph_init = codegraph_init
        self.rubric_judge = rubric_judge
        self.on_progress = on_progress
        self.repository = GitRepository(target.repository)

    def run(self, variants: tuple[DocsVariant, ...], question_ids: set[str] | None = None,
            repeats: int = 1, code_ref: str | None = None) -> list[Path]:
        questions = load_questions(self.questions_path)
        if question_ids:
            questions = tuple(question for question in questions if question.id in question_ids)
            missing = question_ids - {question.id for question in questions}
            if missing:
                raise ValueError(f"unknown question ids: {', '.join(sorted(missing))}")
        baseline_code_commit = self.repository.commit(code_ref or self.target.code_ref)
        questions_hash = "sha256:" + hashlib.sha256(self.questions_path.read_bytes()).hexdigest()
        destination = self.output_root / "runs"
        destination.mkdir(parents=True, exist_ok=True)
        output_paths: list[Path] = []
        for variant in variants:
            code_commit = self._workspace_commit(baseline_code_commit, variant)
            code_files = self.repository.files_at(code_commit)
            for repeat_index in range(repeats):
                for question in questions:
                    if self.on_progress:
                        self.on_progress(f"Running [{variant.name}] {question.id} (repeat {repeat_index + 1}/{repeats})…")
                    workspace = Workspace.create(self.repository, code_commit, self.keep_workspaces)
                    try:
                        submodule_code_commits = self.repository.submodule_commits(workspace.repo)
                        if variant.scope == "repository":
                            # The worktree itself is checked out at the selected ref, so
                            # its files and submodule revisions already come from it.
                            docs_commit = code_commit
                            submodule_docs_commits = dict(submodule_code_commits)
                        else:
                            docs_commit = apply_docs_overlay(self.repository, workspace.repo, code_commit,
                                                             self.target.docs_paths, variant)
                            submodule_docs_commits = apply_submodule_docs_overlays(
                                self.repository, self.target.repository, workspace.repo, code_commit,
                                self.target.docs_paths, variant,
                            )
                        should_initialize_codegraph = self.codegraph_init or variant.codegraph_init
                        if should_initialize_codegraph:
                            if self.on_progress:
                                self.on_progress("  Initializing CodeGraph…")
                            workspace.initialize_codegraph()
                        metadata: dict[str, object] = {
                            "run_id": uuid.uuid4().hex,
                            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
                            "code_commit": code_commit,
                            "docs_variant": variant.name,
                            "docs_commit": docs_commit,
                            "submodules": {
                                path: {"code_commit": commit,
                                       "docs_commit": submodule_docs_commits.get(path)}
                                for path, commit in submodule_code_commits.items()
                            },
                            "repeat": repeat_index + 1,
                            "questions_hash": questions_hash,
                            "benchmark_version": "0.1.0",
                            "codegraph_initialized": should_initialize_codegraph,
                        }
                        relevant_files = tuple(sorted(selected_files(code_files, question.relevant_context)))
                        result = execute_question(self.agent, workspace.repo, self.target, question, metadata,
                                                  relevant_files, self.rubric_judge)
                    finally:
                        workspace.close()
                    run_id = str(result["run_id"])
                    result["raw_log_path"] = f"{run_id}.log"
                    raw_log = str(result.pop("raw_log", ""))
                    json_path = destination / f"{run_id}.json"
                    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    (destination / f"{run_id}.log").write_text(raw_log, encoding="utf-8")
                    output_paths.append(json_path)
                    if self.on_progress:
                        self.on_progress(f"  Saved: {json_path}")
        return output_paths

    def _workspace_commit(self, baseline_code_commit: str, variant: DocsVariant) -> str:
        if variant.scope != "repository":
            return baseline_code_commit
        if not variant.ref:
            raise ValueError(f"git variant {variant.name} requires ref")
        return self.repository.commit(variant.ref)
