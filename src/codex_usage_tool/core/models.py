from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RequestRecord:
    timestamp: datetime
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    cached_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class DailyStat:
    date: str
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class Summary:
    total_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_requests: int
    cached_tokens: int
    total_cost_usd: float
    daily_stats: list[DailyStat]
    model_totals: dict[str, int]
