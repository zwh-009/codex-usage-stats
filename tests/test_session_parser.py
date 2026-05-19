from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_usage_tool.core.parser import parse_session_rollouts


class SessionParserTests(unittest.TestCase):
    def test_parse_session_rollout_dedupes_cumulative_total_usage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sessions = Path(directory)
            rollout = sessions / "rollout-test.jsonl"
            events = [
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "type": "event_msg",
                    "payload": {"turn_id": "turn-a", "model": "gpt-5.5"},
                },
                {
                    "timestamp": "2026-05-18T10:00:01Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 80,
                                "output_tokens": 20,
                                "reasoning_output_tokens": 5,
                                "total_tokens": 120,
                            }
                        },
                    },
                },
                {
                    "timestamp": "2026-05-18T10:00:02Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 80,
                                "output_tokens": 20,
                                "reasoning_output_tokens": 5,
                                "total_tokens": 120,
                            }
                        },
                    },
                },
                {
                    "timestamp": "2026-05-18T10:01:00Z",
                    "type": "event_msg",
                    "payload": {"turn_id": "turn-b", "model": "gpt-5.5"},
                },
                {
                    "timestamp": "2026-05-18T10:01:01Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 150,
                                "cached_input_tokens": 90,
                                "output_tokens": 30,
                                "reasoning_output_tokens": 8,
                                "total_tokens": 180,
                            }
                        },
                    },
                },
            ]
            rollout.write_text(
                "\n".join(json.dumps(event) for event in events),
                encoding="utf-8",
            )

            records = parse_session_rollouts(sessions)

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].prompt_tokens, 100)
            self.assertEqual(records[0].completion_tokens, 20)
            self.assertEqual(records[0].cached_tokens, 80)
            self.assertEqual(records[1].prompt_tokens, 50)
            self.assertEqual(records[1].completion_tokens, 10)
            self.assertEqual(records[1].cached_tokens, 10)

    def test_parse_session_rollout_keeps_each_positive_delta_as_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sessions = Path(directory)
            rollout = sessions / "rollout-test.jsonl"
            events = [
                {
                    "timestamp": "2026-05-18T10:00:00Z",
                    "type": "event_msg",
                    "payload": {"turn_id": "turn-a", "model": "gpt-5.5"},
                },
                {
                    "timestamp": "2026-05-18T10:00:01Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 100,
                                "cached_input_tokens": 80,
                                "output_tokens": 20,
                                "total_tokens": 120,
                            }
                        },
                    },
                },
                {
                    "timestamp": "2026-05-18T10:00:02Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 250,
                                "cached_input_tokens": 170,
                                "output_tokens": 50,
                                "total_tokens": 300,
                            }
                        },
                    },
                },
            ]
            rollout.write_text(
                "\n".join(json.dumps(event) for event in events),
                encoding="utf-8",
            )

            records = parse_session_rollouts(sessions)

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].prompt_tokens, 100)
            self.assertEqual(records[0].completion_tokens, 20)
            self.assertEqual(records[1].prompt_tokens, 150)
            self.assertEqual(records[1].completion_tokens, 30)


if __name__ == "__main__":
    unittest.main()
