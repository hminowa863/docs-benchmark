# DocsBench

DocsBench measures how document variants affect a coding agent's correctness,
context use, and retrieval behavior. It checks out a fixed code revision in an
isolated Git worktree, overlays only the selected documentation, and starts a
fresh agent process for every question.

## Quick start

```powershell
python -m pip install -e .
docsbench run SampleRepository --variant no-docs --variant current-docs
docsbench report SampleRepository
```

Targets live in `targets/<name>/target.yaml`; questions live alongside them in
`questions.yaml`. Results are written as one JSON record per run under
`results/<name>/runs/`, plus `summary.csv`.

The built-in `codex` adapter invokes `codex exec --json` and extracts answers,
token usage, and command executions from its JSONL event stream. Use
`--agent mock` for a safe dry run. Rubric questions are saved as ungraded by
default; add `--rubric-agent codex` to score them with a fresh, separate Codex
process that receives only the candidate answer and rubric.

## Manual evaluation without expected answers

Omit `grading` from a question in `questions.yaml` to run it without preparing
an expected answer or rubric. Each candidate answer is saved in its run JSON;
review them in the terminal with:

```powershell
docsbench review SampleRepository
docsbench review SampleRepository --variant no-docs --question EXAMPLE-001
```

Accuracy is shown as `—` in the report for ungraded runs. After reviewing the
answers, you can add `grading` and rerun the same question set for automatic
scoring.

## Target configuration

```yaml
name: SampleRepository
repository: ../SampleRepository
code_ref: main
docs:
  paths: [AGENTS.md, README.md, docs/**]
variants:
  - name: no-docs
    type: remove
  - name: current-docs
    type: git
    ref: main
```

`working_tree` copies just the configured documentation from the target's
current working tree, so uncommitted document experiments can be benchmarked.

## Submodules

Submodules are initialized recursively with `git submodule update --init
--recursive` after the worktree is created. Include paths below a submodule in
`docs.paths` to apply an overlay to documentation inside it.

```yaml
docs:
  paths:
    - README.md
    - vendor/library/docs/**
```

Each run JSON records the fixed code commit and selected docs source commit for
every submodule in `submodules`. For a `working_tree` variant, initialize the
relevant submodules in the target repository as well.
