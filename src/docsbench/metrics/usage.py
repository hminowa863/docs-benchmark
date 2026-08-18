from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UsageMetrics:
    input_tokens: int | None
    output_tokens: int | None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, int | None]:
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens}
