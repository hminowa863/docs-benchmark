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

## Comparing retrieval routes

`trace` displays observed searches and file reads in execution order for each
run. Filter variants and questions to compare the documentation or source paths
an agent reached for the same question.

```powershell
docsbench trace ts-piper-wireless --question TSPW-007
docsbench trace ts-piper-wireless --variant before-docs --variant after-docs --question TSPW-007
```

Use `report --average` to display mean token and elapsed-time values rather
than medians.

```powershell
docsbench report ts-piper-wireless --average
```

## Initializing CodeGraph

Enable it for an individual variant. `codegraph init` then runs in the relevant
benchmark worktree before the agent starts, so the resulting index includes
that variant's documentation. The CodeGraph CLI must be available on `PATH`.

```yaml
variants:
  - name: codegraph
    codegraph:
      init: true
```

A variant without `type`, as above, keeps the documentation from the fixed
`code_ref`. To combine CodeGraph with an existing docs variant, add
`codegraph.init` alongside its `type` and `ref`.

For a one-off run across every variant, you can also pass `--codegraph-init`.

```powershell
docsbench run ts-piper-wireless --variant after-docs --codegraph-init
```

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

`variants[].type` accepts the following values. By default, code remains fixed
at `code_ref`, and only files matching `docs.paths` are affected.

| `type` | `ref` | Documentation behavior |
| --- | --- | --- |
| `remove` | Not needed | Removes the selected documentation from the worktree. |
| `git` | Required | Overlays documentation from the specified Git ref. |
| `working_tree` | Not needed | Copies documentation from the target repository's currently checked-out working directory, including uncommitted README or `docs/` edits. |
| `baseline` | Not needed | Applies no overlay and uses documentation at `code_ref`. This is the default when `type` is omitted. |

`scope` controls what the variant applies to. The default, `scope: docs`,
affects only files matching `docs.paths`. You may specify it explicitly when a
`git` variant should overlay documentation only from its `ref`.

```yaml
variants:
  - name: before-docs
    type: git
    ref: 69791c3ac62f12691fd6fbac120a4fb567591816
    scope: docs
```

To compare an entire repository revision—including code, documentation, and
submodule revisions—set `scope: repository` on a `git` variant. Its `ref` is
checked out as the whole worktree, and the run JSON records that commit as
`code_commit`.

```yaml
variants:
  - name: before-change
    type: git
    ref: 69791c3ac62f12691fd6fbac120a4fb567591816
    scope: repository
```

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
