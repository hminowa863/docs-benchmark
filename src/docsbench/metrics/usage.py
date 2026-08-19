from __future__ import annotations

from dataclasses import dataclass


CACHED_INPUT_WEIGHT = 0.1


@dataclass(frozen=True)
class UsageMetrics:
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None or self.output_tokens is None:
            return None
        return self.input_tokens + self.output_tokens

    @property
    def input_token_equivalent(self) -> float | None:
        """Input usage with cached input weighted at one tenth."""
        if self.input_tokens is None:
            return None
        cached = self.cached_input_tokens or 0
        return self.input_tokens - cached + cached * CACHED_INPUT_WEIGHT

    def as_dict(self) -> dict[str, int | float | None]:
        return {"input_tokens": self.input_tokens, "cached_input_tokens": self.cached_input_tokens,
                "input_token_equivalent": self.input_token_equivalent, "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens}
