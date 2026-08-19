from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


def write_summary_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    records = list(rows)
    fields = ["variant", "runs", "accuracy", "median_input_tokens", "median_input_token_equivalent",
              "median_total_tokens", "median_elapsed_seconds", "avg_input_tokens", "avg_input_token_equivalent",
              "avg_total_tokens", "avg_elapsed_seconds",
              "avg_retrieved_chars", "avg_files_read", "avg_search_calls", "avg_tool_calls", "tokens_per_correct"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
