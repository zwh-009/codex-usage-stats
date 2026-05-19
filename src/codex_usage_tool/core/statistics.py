from __future__ import annotations

from collections import defaultdict

from codex_usage_tool.core.models import DailyStat, RequestRecord, Summary


def build_summary(records: list[RequestRecord]) -> Summary:
    sorted_records = sorted(records, key=lambda record: record.timestamp)
    daily: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        }
    )
    model_totals: dict[str, int] = defaultdict(int)

    for record in sorted_records:
        day = record.timestamp.date().isoformat()
        daily[day]["requests"] += 1
        daily[day]["prompt_tokens"] += record.prompt_tokens
        daily[day]["completion_tokens"] += record.completion_tokens
        daily[day]["total_tokens"] += record.total_tokens
        daily[day]["cost_usd"] += record.cost_usd
        model_totals[record.model] += record.total_tokens

    daily_stats = [
        DailyStat(
            date=date,
            requests=int(values["requests"]),
            prompt_tokens=int(values["prompt_tokens"]),
            completion_tokens=int(values["completion_tokens"]),
            total_tokens=int(values["total_tokens"]),
            cost_usd=round(float(values["cost_usd"]), 6),
        )
        for date, values in sorted(daily.items())
    ]

    prompt_tokens = sum(record.prompt_tokens for record in sorted_records)
    completion_tokens = sum(record.completion_tokens for record in sorted_records)

    return Summary(
        total_requests=len(sorted_records),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cached_requests=sum(1 for record in sorted_records if record.cached),
        cached_tokens=sum(record.cached_tokens for record in sorted_records),
        total_cost_usd=round(sum(record.cost_usd for record in sorted_records), 6),
        daily_stats=daily_stats,
        model_totals=dict(sorted(model_totals.items())),
    )
