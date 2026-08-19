from __future__ import annotations

import os
import json
import shutil
import subprocess
from pathlib import Path

from docsbench.agents.base import AgentAdapter, AgentResult
from docsbench.config import DocsVariant, Target
from docsbench.git.docs_overlay import apply_docs_overlay, apply_submodule_docs_overlays
from docsbench.git.repository import GitRepository
from docsbench.runner.benchmark import BenchmarkRunner
from docsbench.runner.workspace import Workspace
import docsbench.runner.workspace as workspace_module


def git(path: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    executable = shutil.which("git")
    if executable and os.name == "nt":
        helpers = Path(executable).resolve().parent.parent / "usr" / "bin"
        environment["PATH"] += os.pathsep + str(helpers)
    return subprocess.run(["git", *arguments], cwd=path, text=True, capture_output=True, check=True,
                          env=environment).stdout.strip()


def commit(path: Path, message: str) -> str:
    git(path, "add", ".")
    git(path, "-c", "user.name=DocsBench", "-c", "user.email=docsbench@example.test", "commit", "-m", message)
    return git(path, "rev-parse", "HEAD")


def test_git_overlay_replaces_only_documentation(tmp_path: Path) -> None:
    repo_path = tmp_path / "target"
    repo_path.mkdir()
    git(repo_path, "init")
    (repo_path / "README.md").write_text("old docs", encoding="utf-8")
    (repo_path / "docs").mkdir()
    (repo_path / "docs" / "guide.md").write_text("old guide", encoding="utf-8")
    (repo_path / "app.py").write_text("version = 'fixed'", encoding="utf-8")
    code_ref = commit(repo_path, "code")
    (repo_path / "README.md").write_text("new docs", encoding="utf-8")
    (repo_path / "docs" / "guide.md").unlink()
    (repo_path / "docs" / "new.md").write_text("new guide", encoding="utf-8")
    docs_ref = commit(repo_path, "docs")
    repository = GitRepository(repo_path)
    workspace = Workspace.create(repository, code_ref)
    try:
        resolved = apply_docs_overlay(repository, workspace.repo, code_ref, ("README.md", "docs/**"),
                                      DocsVariant("new", "git", docs_ref))
        assert resolved == docs_ref
        assert (workspace.repo / "README.md").read_text(encoding="utf-8") == "new docs"
        assert not (workspace.repo / "docs" / "guide.md").exists()
        assert (workspace.repo / "docs" / "new.md").read_text(encoding="utf-8") == "new guide"
        assert (workspace.repo / "app.py").read_text(encoding="utf-8") == "version = 'fixed'"
    finally:
        workspace.close()


def test_remove_overlay_removes_selected_docs(tmp_path: Path) -> None:
    repo_path = tmp_path / "target"
    repo_path.mkdir()
    git(repo_path, "init")
    (repo_path / "README.md").write_text("docs", encoding="utf-8")
    (repo_path / "app.py").write_text("code", encoding="utf-8")
    ref = commit(repo_path, "initial")
    repository = GitRepository(repo_path)
    workspace = Workspace.create(repository, ref)
    try:
        assert apply_docs_overlay(repository, workspace.repo, ref, ("README.md",), DocsVariant("none", "remove")) is None
        assert not (workspace.repo / "README.md").exists()
        assert (workspace.repo / "app.py").exists()
    finally:
        workspace.close()


def test_repository_scope_uses_the_requested_commit_for_the_whole_worktree(tmp_path: Path) -> None:
    repo_path = tmp_path / "target"
    repo_path.mkdir()
    git(repo_path, "init")
    (repo_path / "README.md").write_text("old docs", encoding="utf-8")
    (repo_path / "app.py").write_text("version = 'old'", encoding="utf-8")
    old_ref = commit(repo_path, "old")
    (repo_path / "README.md").write_text("new docs", encoding="utf-8")
    (repo_path / "app.py").write_text("version = 'new'", encoding="utf-8")
    new_ref = commit(repo_path, "new")

    class InspectingAgent(AgentAdapter):
        name = "inspect"

        def run(self, workspace: Path, prompt: str) -> AgentResult:
            assert (workspace / "README.md").read_text(encoding="utf-8") == "old docs"
            assert (workspace / "app.py").read_text(encoding="utf-8") == "version = 'old'"
            return AgentResult(answer="ok", input_tokens=0, output_tokens=0)

    questions_path = tmp_path / "questions.yaml"
    questions_path.write_text("questions:\n  - id: Q-1\n    question: Which version?\n", encoding="utf-8")
    target = Target("Example", repo_path, new_ref, ("README.md",), (), tmp_path / "target.yaml")
    runner = BenchmarkRunner(target, questions_path, tmp_path / "results", InspectingAgent())

    paths = runner.run((DocsVariant("old-repository", "git", old_ref, scope="repository"),))

    result = json.loads(paths[0].read_text(encoding="utf-8"))
    assert result["code_commit"] == old_ref
    assert result["docs_commit"] == old_ref


def test_submodule_docs_are_initialized_and_overlaid(tmp_path: Path) -> None:
    module_path = tmp_path / "module"
    module_path.mkdir()
    git(module_path, "init")
    (module_path / "docs").mkdir()
    (module_path / "docs" / "guide.md").write_text("old docs", encoding="utf-8")
    (module_path / "core.txt").write_text("fixed code", encoding="utf-8")
    old_module_ref = commit(module_path, "initial module")

    parent_path = tmp_path / "parent"
    parent_path.mkdir()
    git(parent_path, "init")
    git(parent_path, "config", "protocol.file.allow", "always")
    git(parent_path, "-c", "protocol.file.allow=always", "submodule", "add", str(module_path), "vendor/module")
    code_ref = commit(parent_path, "add module")

    (module_path / "docs" / "guide.md").write_text("new docs", encoding="utf-8")
    new_module_ref = commit(module_path, "new module docs")
    git(parent_path / "vendor" / "module", "fetch")
    git(parent_path / "vendor" / "module", "checkout", "--detach", new_module_ref)
    docs_ref = commit(parent_path, "update module docs")

    repository = GitRepository(parent_path)
    workspace = Workspace.create(repository, code_ref)
    try:
        assert repository.submodule_commits(workspace.repo)["vendor/module"] == old_module_ref
        apply_submodule_docs_overlays(repository, parent_path, workspace.repo, code_ref,
                                      ("vendor/module/docs/**",), DocsVariant("new", "git", docs_ref))
        module_workspace = workspace.repo / "vendor" / "module"
        assert (module_workspace / "docs" / "guide.md").read_text(encoding="utf-8") == "new docs"
        assert (module_workspace / "core.txt").read_text(encoding="utf-8") == "fixed code"
    finally:
        workspace.close()


def test_workspace_initializes_codegraph_in_the_worktree(tmp_path: Path, monkeypatch) -> None:
    commands: list[tuple[list[str], Path]] = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def run(command, *, cwd, **kwargs):
        commands.append((command, cwd))
        assert kwargs["capture_output"] is True
        return Completed()

    monkeypatch.setattr(workspace_module.shutil, "which", lambda name: "codegraph.exe")
    monkeypatch.setattr(workspace_module.subprocess, "run", run)
    workspace = Workspace(repository=None, root=tmp_path, repo=tmp_path)

    workspace.initialize_codegraph()

    assert commands == [(["codegraph.exe", "init"], tmp_path)]
