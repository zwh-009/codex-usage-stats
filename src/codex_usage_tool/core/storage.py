from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from datetime import datetime

from codex_usage_tool.app_paths import app_data_dir
from codex_usage_tool.core.models import RequestRecord


DEFAULT_DB_PATH = app_data_dir() / "codex_usage.sqlite3"


def initialize_database(path: str | Path = DEFAULT_DB_PATH) -> Path:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                cached INTEGER NOT NULL,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL
            )
            """
        )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(requests)").fetchall()
        }
        if "cached_tokens" not in columns:
            connection.execute(
                "ALTER TABLE requests ADD COLUMN cached_tokens INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_unique
            ON requests(timestamp, model, prompt_tokens, completion_tokens, cached)
            """
        )
        connection.commit()
    finally:
        connection.close()
    return db_path


def save_records(records: list[RequestRecord], path: str | Path = DEFAULT_DB_PATH, replace: bool = False) -> int:
    db_path = initialize_database(path)
    connection = sqlite3.connect(db_path)
    try:
        if replace:
            connection.execute("DELETE FROM requests")
        connection.executemany(
            """
            INSERT OR IGNORE INTO requests (
                timestamp,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cached,
                cached_tokens,
                cost_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record.timestamp.isoformat(),
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    int(record.cached),
                    record.cached_tokens,
                    record.cost_usd,
                )
                for record in records
            ],
        )
        connection.commit()
    finally:
        connection.close()
    return len(records)


def load_records(path: str | Path = DEFAULT_DB_PATH) -> list[RequestRecord]:
    db_path = initialize_database(path)
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                model,
                prompt_tokens,
                completion_tokens,
                cached,
                cached_tokens,
                cost_usd
            FROM requests
            ORDER BY timestamp ASC
            """
        ).fetchall()
    finally:
        connection.close()

    records: list[RequestRecord] = []
    for row in rows:
        try:
            timestamp = datetime.fromisoformat(row[0])
        except (TypeError, ValueError):
            continue
        records.append(
            RequestRecord(
                timestamp=timestamp,
                model=str(row[1]),
                prompt_tokens=int(row[2]),
                completion_tokens=int(row[3]),
                cached=bool(row[4]),
                cached_tokens=int(row[5]),
                cost_usd=float(row[6]),
            )
        )
    return records


def export_records_csv(records: list[RequestRecord], path: str | Path) -> Path:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "时间",
                "模型",
                "输入",
                "输出",
                "总量",
                "缓存 Tokens",
                "花费 USD",
            ]
        )
        for record in records:
            writer.writerow(
                [
                    record.timestamp.isoformat(),
                    record.model,
                    record.prompt_tokens,
                    record.completion_tokens,
                    record.total_tokens,
                    record.cached_tokens,
                    f"{record.cost_usd:.6f}",
                ]
            )
    return csv_path
