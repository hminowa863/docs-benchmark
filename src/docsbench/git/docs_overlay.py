from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath

from docsbench.config import DocsVariant
from .repository import GitRepository


def selected_files(files: tuple[str, ...], patterns: tuple[str, ...]) -> set[str]:
    return {file for file in files if any(_matches(file, pattern) for pattern in patterns)}


def apply_docs_overlay(repository: GitRepository, workspace: Path, code_ref: str,
                       patterns: tuple[str, ...], variant: DocsVariant) -> str | None:
    code_files = selected_files(repository.files_at(code_ref), patterns)
    if variant.type == "baseline":
        return code_ref
    if variant.type == "remove":
        _remove(workspace, code_files)
        return None
    if variant.type == "git":
        if not variant.ref:
            raise ValueError(f"git variant {variant.name} requires ref")
        docs_commit = repository.commit(variant.ref)
        source_files = selected_files(repository.files_at(docs_commit), patterns)
        _remove(workspace, code_files | source_files)
        _restore_from_git(repository, workspace, docs_commit, source_files)
        return docs_commit
    if variant.type == "working_tree":
        source_files = selected_files(_working_tree_files(repository.path), patterns)
        _remove(workspace, code_files | source_files)
        _copy_from_working_tree(repository.path, workspace, source_files)
        return "working-tree"
    raise ValueError(f"unsupported docs variant type: {variant.type}")


def apply_submodule_docs_overlays(repository: GitRepository, source_root: Path, workspace: Path,
                                  code_ref: str, patterns: tuple[str, ...], variant: DocsVariant) -> dict[str, str | None]:
    """Overlay documentation inside recursively initialized submodules.

    Submodule source revisions are resolved from the selected superproject docs
    revision. Only configured paths below each submodule are touched; code and
    submodule pointers remain at the fixed code revision.
    """
    code_submodules = repository.submodule_commits(workspace)
    if variant.type == "baseline":
        return dict(code_submodules)
    if not code_submodules:
        return {}
    applicable = {path: commit for path, commit in code_submodules.items() if _submodule_patterns(path, patterns)}
    if not applicable:
        return {}
    source_resolution_set = {
        path: commit for path, commit in code_submodules.items()
        if any(target == path or target.startswith(path.rstrip("/") + "/") for target in applicable)
    }
    docs_sources = _submodule_docs_sources(repository, workspace, variant, source_resolution_set)
    applied: dict[str, str | None] = {}
    for submodule_path, module_code_commit in sorted(applicable.items(), key=lambda item: item[0].count("/")):
        module_patterns = _submodule_patterns(submodule_path, patterns)
        module_workspace = workspace / submodule_path
        if variant.type == "working_tree":
            source_path = source_root / submodule_path
            source_repository = GitRepository(source_path)
            applied[submodule_path] = apply_docs_overlay(source_repository, module_workspace, module_code_commit,
                                                          module_patterns, variant)
            continue
        module_repository = GitRepository(module_workspace)
        source_commit = docs_sources.get(submodule_path)
        if variant.type == "git" and source_commit is None:
            apply_docs_overlay(module_repository, module_workspace, module_code_commit, module_patterns,
                               DocsVariant(variant.name, "remove"))
            applied[submodule_path] = None
            continue
        module_variant = DocsVariant(variant.name, variant.type, source_commit if variant.type == "git" else variant.ref)
        applied[submodule_path] = apply_docs_overlay(module_repository, module_workspace, module_code_commit,
                                                      module_patterns, module_variant)
    return applied


def _submodule_patterns(submodule_path: str, patterns: tuple[str, ...]) -> tuple[str, ...]:
    prefix = submodule_path.rstrip("/") + "/"
    return tuple(pattern[len(prefix):] for pattern in patterns if pattern.replace("\\", "/").startswith(prefix))


def _submodule_docs_sources(repository: GitRepository, workspace: Path, variant: DocsVariant,
                            submodules: dict[str, str]) -> dict[str, str | None]:
    if variant.type == "remove":
        return {path: None for path in submodules}
    if variant.type == "working_tree":
        return {path: "working-tree" for path in submodules}
    if variant.type != "git" or not variant.ref:
        raise ValueError(f"git variant {variant.name} requires ref")
    top_docs_commit = repository.commit(variant.ref)
    sources: dict[str, str | None] = {}
    for path in sorted(submodules, key=lambda value: value.count("/")):
        parent = _nearest_parent_submodule(path, submodules)
        if parent is None:
            sources[path] = repository.gitlink_commit(top_docs_commit, path)
            continue
        parent_source = sources.get(parent)
        if parent_source is None:
            sources[path] = None
            continue
        child_name = path[len(parent) + 1:]
        parent_repository = GitRepository(workspace / parent)
        sources[path] = parent_repository.gitlink_commit(parent_source, child_name)
    return sources


def _nearest_parent_submodule(path: str, submodules: dict[str, str]) -> str | None:
    parents = [candidate for candidate in submodules if path.startswith(candidate.rstrip("/") + "/")]
    return max(parents, key=len) if parents else None


def _matches(file: str, pattern: str) -> bool:
    path = PurePosixPath(file)
    normalized = pattern.replace("\\", "/").rstrip("/")
    return path.match(normalized) or (normalized.endswith("/**") and file.startswith(normalized[:-3]))


def _safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"unsafe documentation path: {relative}") from None
    else:
        return path


def _remove(workspace: Path, files: set[str]) -> None:
    for file in files:
        path = _safe_path(workspace, file)
        if path.is_file() or path.is_symlink():
            path.unlink()
    for directory in sorted({p.parent for p in (_safe_path(workspace, f) for f in files)}, key=lambda p: len(p.parts), reverse=True):
        if directory != workspace and directory.exists() and not any(directory.iterdir()):
            directory.rmdir()


def _restore_from_git(repository: GitRepository, workspace: Path, ref: str, files: set[str]) -> None:
    for file in files:
        target = _safe_path(workspace, file)
        target.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        result = subprocess.run(["git", "show", f"{ref}:{file}"], cwd=repository.path, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError(f"could not restore {file} from {ref}")
        target.write_bytes(result.stdout)


def _working_tree_files(root: Path) -> tuple[str, ...]:
    files: list[str] = []
    for current, directories, names in os.walk(root):
        directories[:] = [directory for directory in directories if directory != ".git"]
        current_path = Path(current)
        files.extend((current_path / name).relative_to(root).as_posix() for name in names)
    return tuple(files)


def _copy_from_working_tree(source_root: Path, workspace: Path, files: set[str]) -> None:
    for file in files:
        source, target = _safe_path(source_root, file), _safe_path(workspace, file)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
