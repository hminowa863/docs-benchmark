from __future__ import annotations

from pathlib import Path

from .records import format_run_title, load_run_record


def render_review(results_root: Path, target: str, variants: set[str] | None = None,
                  question_ids: set[str] | None = None) -> str:
    """Render candidate answers for manual evaluation without expected answers."""
    runs_dir = results_root / target / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"no results found for target {target}: {runs_dir}")
    records = [load_run_record(path)[0] for path in runs_dir.glob("*.json")]
    records.sort(key=lambda record: str(record.get("timestamp", "")))
    filtered = [record for record in records
                if (not variants or record.get("docs_variant") in variants)
                and (not question_ids or record.get("question_id") in question_ids)]
    if not filtered:
        return "No matching runs."
    sections = []
    for record in filtered:
        sections.append(
            f"{format_run_title(record)}\n"
            f"{record.get('answer', '')}"
        )
    return "\n\n".join(sections)
