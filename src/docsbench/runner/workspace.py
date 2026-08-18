from __future__ import annotations

import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from docsbench.git.repository import GitRepository


@dataclass
class Workspace:
    repository: GitRepository
    root: Path
    repo: Path
    keep: bool = False

    @classmethod
    def create(cls, repository: GitRepository, code_ref: str, keep: bool = False) -> "Workspace":
        root = Path(tempfile.mkdtemp(prefix=f"docsbench-{uuid.uuid4().hex[:8]}-"))
        repo = root / "repo"
        repository.add_worktree(repo, code_ref)
        try:
            repository.init_submodules(repo)
        except Exception:
            repository.remove_worktree(repo)
            shutil.rmtree(root, ignore_errors=True)
            raise
        return cls(repository, root, repo, keep)

    def close(self) -> None:
        if self.keep:
            return
        try:
            self.repository.remove_worktree(self.repo)
        finally:
            shutil.rmtree(self.root, ignore_errors=True)
