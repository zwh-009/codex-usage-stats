from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    prompt_usd_per_1k: float
    completion_usd_per_1k: float


DEFAULT_PRICING: dict[str, ModelPrice] = {
    "codex-davinci-002": ModelPrice(prompt_usd_per_1k=0.02, completion_usd_per_1k=0.02),
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    pricing: dict[str, ModelPrice] | None = None,
) -> float:
    price_table = pricing or DEFAULT_PRICING
    price = price_table.get(model)
    if price is None:
        return 0.0

    prompt_cost = (prompt_tokens / 1000) * price.prompt_usd_per_1k
    completion_cost = (completion_tokens / 1000) * price.completion_usd_per_1k
    return round(prompt_cost + completion_cost, 6)
