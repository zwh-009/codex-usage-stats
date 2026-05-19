from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from codex_usage_tool.core.models import RequestRecord
from codex_usage_tool.core.pricing import estimate_cost_usd


DEFAULT_LOG_PATH = Path.home() / ".codex" / "logs" / "session_logs.jsonl"
DEFAULT_SQLITE_LOG_PATH = Path.home() / ".codex" / "logs_2.sqlite"
DEFAULT_SESSIONS_PATH = Path.home() / ".codex" / "sessions"


def default_log_path() -> Path:
    return Path(os.environ.get("CODEX_USAGE_LOG_PATH", DEFAULT_LOG_PATH))


def parse_jsonl_file(path: str | Path) -> list[RequestRecord]:
    log_path = Path(path).expanduser()
    if not log_path.exists():
        return []

    records: list[RequestRecord] = []
    with log_path.open("r", encoding="utf-8") as file:
        for line in file:
            record = parse_jsonl_line(line)
            if record is not None:
                records.append(record)
    return records


def parse_sqlite_log_file(path: str | Path) -> list[RequestRecord]:
    sqlite_path = Path(path).expanduser()
    if not sqlite_path.exists():
        return []

    sse_records: list[RequestRecord] = []
    turn_records: list[RequestRecord] = []
    connection = _connect_sqlite_readonly(sqlite_path)
    try:
        rows = connection.execute(
            """
            SELECT ts, feedback_log_body
            FROM logs
            WHERE target = 'codex_api::sse::responses'
              AND feedback_log_body LIKE 'SSE event:%response.completed%'
              AND feedback_log_body LIKE '%"usage"%'
            ORDER BY ts ASC
            """
        )
        for fallback_ts, body in rows:
            record = _record_from_sse_body(body, fallback_ts)
            if record is not None:
                sse_records.append(record)

        turn_rows = connection.execute(
            """
            SELECT ts, feedback_log_body
            FROM logs
            WHERE target = 'codex_core::session::turn'
              AND feedback_log_body LIKE '%post sampling token usage%'
              AND feedback_log_body LIKE '%total_usage_tokens=%'
            ORDER BY ts ASC
            """
        )
        turn_records = _dedupe_turn_records(turn_rows)
    except sqlite3.DatabaseError:
        return []
    finally:
        connection.close()

    if len(turn_records) > len(sse_records):
        return _attach_known_cache_tokens(turn_records, sse_records)
    return sse_records


def parse_session_rollouts(path: str | Path = DEFAULT_SESSIONS_PATH) -> list[RequestRecord]:
    sessions_path = Path(path).expanduser()
    if not sessions_path.exists():
        return []

    records: list[RequestRecord] = []
    for rollout_path in sorted(sessions_path.rglob("rollout-*.jsonl")):
        previous_total: dict[str, int] | None = None
        current_model = "unknown"

        try:
            lines = rollout_path.open("r", encoding="utf-8", errors="ignore")
        except OSError:
            continue

        with lines:
            for line in lines:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                payload = event.get("payload") if isinstance(event, dict) else None
                if not isinstance(payload, dict):
                    continue

                if isinstance(payload.get("model"), str) and payload["model"].strip():
                    current_model = payload["model"].strip()

                if payload.get("type") != "token_count":
                    continue

                info = payload.get("info")
                if not isinstance(info, dict):
                    continue

                total_usage = info.get("total_token_usage")
                if not isinstance(total_usage, dict):
                    continue

                current_total = _usage_totals(total_usage)
                if previous_total is None:
                    delta = current_total
                else:
                    delta = {
                        key: max(current_total[key] - previous_total.get(key, 0), 0)
                        for key in current_total
                    }
                previous_total = current_total

                if delta["total_tokens"] <= 0:
                    continue

                timestamp = _timestamp_from_event(event)
                records.append(
                    RequestRecord(
                        timestamp=timestamp,
                        model=current_model,
                        prompt_tokens=delta["input_tokens"],
                        completion_tokens=delta["output_tokens"],
                        cached=delta["cached_input_tokens"] > 0,
                        cached_tokens=delta["cached_input_tokens"],
                        cost_usd=estimate_cost_usd(
                            current_model,
                            delta["input_tokens"],
                            delta["output_tokens"],
                        ),
                    )
                )

    return sorted(records, key=lambda record: record.timestamp)


def auto_load_records() -> tuple[list[RequestRecord], Path | None, str]:
    env_path = os.environ.get("CODEX_USAGE_LOG_PATH")
    if env_path:
        path = Path(env_path).expanduser()
        records = _parse_by_suffix(path)
        return records, path, "环境变量指定日志"

    if DEFAULT_SESSIONS_PATH.exists():
        records = parse_session_rollouts(DEFAULT_SESSIONS_PATH)
        if records:
            return records, DEFAULT_SESSIONS_PATH, "自动读取 Codex session JSONL"

    if DEFAULT_SQLITE_LOG_PATH.exists():
        records = parse_sqlite_log_file(DEFAULT_SQLITE_LOG_PATH)
        if records:
            return records, DEFAULT_SQLITE_LOG_PATH, "自动读取 Codex 本地 SQLite"

    jsonl_candidates = sorted(
        (Path.home() / ".codex").glob("logs/**/*.jsonl"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for candidate in jsonl_candidates:
        records = parse_jsonl_file(candidate)
        if records:
            return records, candidate, "自动读取 Codex JSONL"

    return [], DEFAULT_SQLITE_LOG_PATH if DEFAULT_SQLITE_LOG_PATH.exists() else DEFAULT_LOG_PATH, "未找到可解析的用量日志"


def parse_jsonl_lines(lines: Iterable[str]) -> list[RequestRecord]:
    records: list[RequestRecord] = []
    for line in lines:
        record = parse_jsonl_line(line)
        if record is not None:
            records.append(record)
    return records


def parse_jsonl_line(line: str) -> RequestRecord | None:
    stripped = line.strip()
    if not stripped:
        return None

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return record_from_payload(payload)


def record_from_payload(payload: dict[str, Any]) -> RequestRecord | None:
    timestamp = _extract_timestamp(payload)
    model = _extract_model(payload)
    usage = _extract_usage(payload)

    if timestamp is None or model is None or usage is None:
        return None

    prompt_tokens = _as_int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or payload.get("prompt_tokens")
        or payload.get("input_tokens")
    )
    completion_tokens = _as_int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or payload.get("completion_tokens")
        or payload.get("output_tokens")
    )

    if prompt_tokens is None or completion_tokens is None:
        return None

    cached_tokens = _extract_cached_tokens(usage)
    cached = _extract_cached(payload, usage)
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    return RequestRecord(
        timestamp=timestamp,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached=cached,
        cached_tokens=cached_tokens,
        cost_usd=cost_usd,
    )


def _record_from_sse_body(body: Any, fallback_ts: Any) -> RequestRecord | None:
    if not isinstance(body, str) or not body.startswith("SSE event:"):
        return None

    try:
        event = json.loads(body.removeprefix("SSE event:").strip())
    except json.JSONDecodeError:
        return None

    if not isinstance(event, dict) or event.get("type") != "response.completed":
        return None

    response = event.get("response")
    if not isinstance(response, dict):
        return None

    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None

    model = response.get("model")
    if not isinstance(model, str) or not model.strip():
        return None

    prompt_tokens = _as_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
    completion_tokens = _as_int(usage.get("output_tokens") or usage.get("completion_tokens"))
    if prompt_tokens is None or completion_tokens is None:
        return None

    timestamp = _timestamp_from_response(response, fallback_ts)
    cached_tokens = _extract_cached_tokens(usage)
    cached = _extract_cached(response, usage)
    return RequestRecord(
        timestamp=timestamp,
        model=model.strip(),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached=cached,
        cached_tokens=cached_tokens,
        cost_usd=estimate_cost_usd(model.strip(), prompt_tokens, completion_tokens),
    )


def _dedupe_turn_records(rows: Iterable[tuple[Any, Any]]) -> list[RequestRecord]:
    records_by_turn: dict[str, RequestRecord] = {}
    for fallback_ts, body in rows:
        record = _record_from_turn_body(body, fallback_ts)
        turn_id = _regex_value(body, r"turn_id=([0-9a-f-]+)") if isinstance(body, str) else None
        if record is None or turn_id is None:
            continue

        existing = records_by_turn.get(turn_id)
        if existing is None or record.total_tokens >= existing.total_tokens:
            records_by_turn[turn_id] = record
    return sorted(records_by_turn.values(), key=lambda record: record.timestamp)


def _record_from_turn_body(body: Any, fallback_ts: Any) -> RequestRecord | None:
    if not isinstance(body, str):
        return None

    model = _regex_value(body, r"model=([^\s}:]+)")
    total_usage = _regex_int(body, r"total_usage_tokens=(\d+)")
    estimated_input = _regex_int(body, r"estimated_token_count=Some\((\d+)\)")
    if model is None or total_usage is None:
        return None

    prompt_tokens = estimated_input if estimated_input is not None else total_usage
    completion_tokens = max(total_usage - prompt_tokens, 0)
    timestamp = _timestamp_from_response({}, fallback_ts)
    return RequestRecord(
        timestamp=timestamp,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached=False,
        cached_tokens=0,
        cost_usd=estimate_cost_usd(model, prompt_tokens, completion_tokens),
    )


def _attach_known_cache_tokens(
    turn_records: list[RequestRecord],
    sse_records: list[RequestRecord],
) -> list[RequestRecord]:
    if not turn_records or not sse_records:
        return turn_records

    cached_by_index: dict[int, int] = {}
    for sse_record in sse_records:
        if sse_record.cached_tokens <= 0:
            continue
        nearest_index = min(
            range(len(turn_records)),
            key=lambda index: abs(
                (turn_records[index].timestamp - sse_record.timestamp).total_seconds()
            ),
        )
        distance = abs((turn_records[nearest_index].timestamp - sse_record.timestamp).total_seconds())
        if distance <= 300:
            cached_by_index[nearest_index] = cached_by_index.get(nearest_index, 0) + sse_record.cached_tokens

    merged: list[RequestRecord] = []
    for index, record in enumerate(turn_records):
        cached_tokens = cached_by_index.get(index, 0)
        merged.append(
            RequestRecord(
                timestamp=record.timestamp,
                model=record.model,
                prompt_tokens=record.prompt_tokens,
                completion_tokens=record.completion_tokens,
                cached=record.cached or cached_tokens > 0,
                cached_tokens=cached_tokens,
                cost_usd=record.cost_usd,
            )
        )
    return merged


def _timestamp_from_response(response: dict[str, Any], fallback_ts: Any) -> datetime:
    for key in ("completed_at", "created_at"):
        value = response.get(key)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone()

    if isinstance(fallback_ts, (int, float)):
        value = fallback_ts / 1_000_000_000 if fallback_ts > 10_000_000_000 else fallback_ts
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone()

    return datetime.now().astimezone()


def _timestamp_from_event(event: dict[str, Any]) -> datetime:
    timestamp = _extract_timestamp({"timestamp": event.get("timestamp")})
    return timestamp or datetime.now().astimezone()


def _usage_totals(usage: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": _as_int(usage.get("input_tokens")) or 0,
        "cached_input_tokens": _as_int(usage.get("cached_input_tokens")) or 0,
        "output_tokens": _as_int(usage.get("output_tokens")) or 0,
        "reasoning_output_tokens": _as_int(usage.get("reasoning_output_tokens")) or 0,
        "total_tokens": _as_int(usage.get("total_tokens")) or 0,
    }


def _parse_by_suffix(path: Path) -> list[RequestRecord]:
    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return parse_sqlite_log_file(path)
    return parse_jsonl_file(path)


def _connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.OperationalError:
        return sqlite3.connect(path, timeout=5)


def _extract_timestamp(payload: dict[str, Any]) -> datetime | None:
    value = (
        payload.get("timestamp")
        or payload.get("created_at")
        or payload.get("time")
        or payload.get("created")
    )

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_model(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("model"),
        payload.get("model_name"),
        _nested_get(payload, "request", "model"),
        _nested_get(payload, "response", "model"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_usage(payload: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        payload.get("usage"),
        _nested_get(payload, "response", "usage"),
        payload,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            has_prompt = any(key in candidate for key in ("prompt_tokens", "input_tokens"))
            has_completion = any(key in candidate for key in ("completion_tokens", "output_tokens"))
            if has_prompt and has_completion:
                return candidate
    return None


def _extract_cached(payload: dict[str, Any], usage: dict[str, Any]) -> bool:
    for value in (payload.get("cached"), usage.get("cached"), payload.get("cache_hit")):
        if isinstance(value, bool):
            return value

    cached_tokens = _extract_cached_tokens(usage)
    return bool(cached_tokens and cached_tokens > 0)


def _extract_cached_tokens(usage: dict[str, Any]) -> int:
    return _as_int(
        _nested_get(usage, "prompt_tokens_details", "cached_tokens")
        or _nested_get(usage, "input_tokens_details", "cached_tokens")
        or usage.get("cached_tokens")
    ) or 0


def _nested_get(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _regex_value(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _regex_int(text: str, pattern: str) -> int | None:
    value = _regex_value(text, pattern)
    return int(value) if value is not None else None
