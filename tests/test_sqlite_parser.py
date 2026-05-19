from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from codex_usage_tool.core.parser import parse_sqlite_log_file


class SqliteParserTests(unittest.TestCase):
    def test_parse_completed_sse_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "logs.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE logs (
                        id INTEGER,
                        ts INTEGER,
                        target TEXT,
                        feedback_log_body TEXT
                    )
                    """
                )
                event = {
                    "type": "response.completed",
                    "response": {
                        "created_at": 1779091692,
                        "completed_at": 1779091710,
                        "model": "gpt-5.5",
                        "usage": {
                            "input_tokens": 100,
                            "input_tokens_details": {"cached_tokens": 80},
                            "output_tokens": 25,
                            "total_tokens": 125,
                        },
                    },
                }
                connection.execute(
                    "INSERT INTO logs VALUES (?, ?, ?, ?)",
                    (
                        1,
                        1779091710000000000,
                        "codex_api::sse::responses",
                        f"SSE event: {json.dumps(event)}",
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            records = parse_sqlite_log_file(db_path)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].model, "gpt-5.5")
            self.assertEqual(records[0].prompt_tokens, 100)
            self.assertEqual(records[0].completion_tokens, 25)
            self.assertTrue(records[0].cached)
            self.assertEqual(records[0].cached_tokens, 80)

    def test_parse_turn_usage_when_more_complete_than_sse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "logs.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE logs (
                        id INTEGER,
                        ts INTEGER,
                        target TEXT,
                        feedback_log_body TEXT
                    )
                    """
                )
                rows = [
                    (
                        1,
                        1779091710000000000,
                        "codex_core::session::turn",
                        "model=gpt-5.5}:run_turn: post sampling token usage "
                        "turn_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa "
                        "total_usage_tokens=100 estimated_token_count=Some(80)",
                    ),
                    (
                        2,
                        1779091720000000000,
                        "codex_core::session::turn",
                        "model=gpt-5.5}:run_turn: post sampling token usage "
                        "turn_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa "
                        "total_usage_tokens=120 estimated_token_count=Some(90)",
                    ),
                    (
                        3,
                        1779091730000000000,
                        "codex_core::session::turn",
                        "model=gpt-5.5}:run_turn: post sampling token usage "
                        "turn_id=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb "
                        "total_usage_tokens=50 estimated_token_count=Some(40)",
                    ),
                ]
                connection.executemany("INSERT INTO logs VALUES (?, ?, ?, ?)", rows)
                connection.commit()
            finally:
                connection.close()

            records = parse_sqlite_log_file(db_path)

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].total_tokens, 120)
            self.assertEqual(records[0].prompt_tokens, 90)
            self.assertEqual(records[0].completion_tokens, 30)


if __name__ == "__main__":
    unittest.main()
