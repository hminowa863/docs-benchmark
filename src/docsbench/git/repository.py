from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class GitRepository:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._run("rev-parse", "--is-inside-work-tree")

    def _run(self, *args: str, cwd: Path | None = None) -> str:
        command = ["git", *args]
        result = subprocess.run(command, cwd=cwd or self.path, text=True, capture_output=True, check=False,
                                env=_git_environment())
        if result.returncode:
            raise RuntimeError(f"{' '.join(command)} failed: {result.stderr.strip()}")
        return result.stdout

    def commit(self, ref: str) -> str:
        return self._run("rev-parse", "--verify", f"{ref}^{{commit}}").strip()

    def files_at(self, ref: str) -> tuple[str, ...]:
        return tuple(line for line in self._run("ls-tree", "-r", "--name-only", ref).splitlines() if line)

    def add_worktree(self, destination: Path, ref: str) -> None:
        self._run("worktree", "add", "--detach", str(destination), ref)

    def init_submodules(self, worktree: Path) -> None:
        # Git disallows local-path submodules by default in recursive commands.
        # Allowing the file transport here supports repositories that vendor a
        # sibling checkout while leaving the permission scoped to this command.
        self._run("-c", "protocol.file.allow=always", "submodule", "update", "--init", "--recursive", cwd=worktree)

    def submodule_commits(self, worktree: Path) -> dict[str, str]:
        """Return recursively initialized submodule paths and checked-out commits."""
        output = self._run("submodule", "status", "--recursive", cwd=worktree)
        commits: dict[str, str] = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            fields = line[1:].split(maxsplit=2)
            if len(fields) < 2:
                raise RuntimeError(f"could not parse submodule status: {line}")
            commits[fields[1]] = fields[0]
        return commits

    def gitlink_commit(self, ref: str, path: str) -> str | None:
        output = self._run("ls-tree", ref, "--", path).strip()
        if not output:
            return None
        metadata, _, listed_path = output.partition("\t")
        fields = metadata.split()
        if len(fields) != 3 or fields[0] != "160000" or listed_path != path:
            return None
        return fields[2]

    def remove_worktree(self, destination: Path) -> None:
        self._run("worktree", "remove", "--force", str(destination))


def _git_environment() -> dict[str, str]:
    """Make Git for Windows' POSIX helpers available to submodule commands."""
    environment = os.environ.copy()
    if os.name != "nt":
        return environment
    git = shutil.which("git")
    if not git:
        return environment
    candidate = Path(git).resolve().parent.parent / "usr" / "bin"
    if candidate.is_dir() and str(candidate) not in environment.get("PATH", "").split(os.pathsep):
        environment["PATH"] = environment.get("PATH", "") + os.pathsep + str(candidate)
    return environment
