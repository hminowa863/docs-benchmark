from __future__ import annotations

import argparse
from pathlib import Path

from .agents import CodexAdapter, MockAdapter
from .config import DocsVariant, load_target
from .reporting import build_summary, render_review, render_summary
from .runner import BenchmarkRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="docsbench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run a target benchmark")
    run.add_argument("target")
    run.add_argument("--targets-dir", type=Path, default=Path("targets"))
    run.add_argument("--results-dir", type=Path, default=Path("results"))
    run.add_argument("--variant", action="append", dest="variants")
    run.add_argument("--question", action="append", dest="questions")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--agent", choices=("codex", "mock"), default="codex")
    run.add_argument("--model")
    run.add_argument("--rubric-agent", choices=("codex",), help="independent agent used only for rubric grading")
    run.add_argument("--rubric-model")
    run.add_argument("--code", help="override fixed code ref")
    run.add_argument("--docs", nargs="+", help="documentation refs; creates git variants")
    run.add_argument("--keep-workspaces", action="store_true")
    report = subparsers.add_parser("report", help="aggregate saved benchmark results")
    report.add_argument("target")
    report.add_argument("--results-dir", type=Path, default=Path("results"))
    review = subparsers.add_parser("review", help="show saved answers for manual evaluation")
    review.add_argument("target")
    review.add_argument("--results-dir", type=Path, default=Path("results"))
    review.add_argument("--variant", action="append", dest="variants")
    review.add_argument("--question", action="append", dest="questions")
    args = parser.parse_args(argv)
    if args.command == "report":
        print(render_summary(args.target, build_summary(args.results_dir, args.target)))
        return 0
    if args.command == "review":
        print(render_review(args.results_dir, args.target, set(args.variants or []), set(args.questions or [])))
        return 0
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    target_path = args.targets_dir / args.target / "target.yaml"
    target = load_target(target_path)
    variants = _select_variants(target.variants, args.variants, args.docs)
    def progress(message: str) -> None:
        print(message, flush=True)

    agent = MockAdapter() if args.agent == "mock" else CodexAdapter(model=args.model, on_progress=progress)
    rubric_judge = CodexAdapter(model=args.rubric_model, on_progress=progress) if args.rubric_agent == "codex" else None
    runner = BenchmarkRunner(target, target_path.with_name("questions.yaml"), args.results_dir, agent,
                             keep_workspaces=args.keep_workspaces, rubric_judge=rubric_judge, on_progress=progress)
    paths = runner.run(variants, set(args.questions or []), args.repeat, args.code)
    print(f"Completed {len(paths)} run(s); results: {args.results_dir / target.name / 'runs'}")
    return 0


def _select_variants(available: tuple[DocsVariant, ...], names: list[str] | None,
                     docs_refs: list[str] | None) -> tuple[DocsVariant, ...]:
    if docs_refs:
        return tuple(DocsVariant(name=f"docs-{ref}", type="git", ref=ref) for ref in docs_refs)
    if not names:
        return available
    chosen = tuple(variant for variant in available if variant.name in names)
    missing = set(names) - {variant.name for variant in chosen}
    if missing:
        raise ValueError(f"unknown variants: {', '.join(sorted(missing))}")
    return chosen


if __name__ == "__main__":
    raise SystemExit(main())
