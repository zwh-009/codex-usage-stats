from __future__ import annotations

import unittest

from codex_usage_tool.core.parser import parse_jsonl_line, parse_jsonl_lines


class ParserTests(unittest.TestCase):
    def test_parse_flat_record(self) -> None:
        record = parse_jsonl_line(
            '{"timestamp":"2026-05-18T14:22:33","model":"codex-davinci-002",'
            '"prompt_tokens":45,"completion_tokens":120,"cached":false}'
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.model, "codex-davinci-002")
        self.assertEqual(record.prompt_tokens, 45)
        self.assertEqual(record.completion_tokens, 120)
        self.assertFalse(record.cached)
        self.assertEqual(record.cached_tokens, 0)
        self.assertEqual(record.total_tokens, 165)
        self.assertGreater(record.cost_usd, 0)

    def test_parse_nested_usage_and_cached_tokens(self) -> None:
        record = parse_jsonl_line(
            '{"timestamp":"2026-05-18T14:22:33Z","model":"gpt-example",'
            '"usage":{"input_tokens":45,"output_tokens":120,'
            '"input_tokens_details":{"cached_tokens":20}}}'
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record.cached)
        self.assertEqual(record.cached_tokens, 20)
        self.assertEqual(record.prompt_tokens, 45)
        self.assertEqual(record.completion_tokens, 120)
        self.assertEqual(record.cost_usd, 0.0)

    def test_skip_bad_lines(self) -> None:
        records = parse_jsonl_lines(
            [
                "",
                "not-json",
                '{"timestamp":"2026-05-18T14:22:33","model":"x"}',
                '{"timestamp":"2026-05-18T14:22:33","model":"x","prompt_tokens":1,"completion_tokens":2}',
            ]
        )

        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
