from __future__ import annotations

import unittest
from datetime import datetime

from codex_usage_tool.core.models import RequestRecord
from codex_usage_tool.core.statistics import build_summary


class StatisticsTests(unittest.TestCase):
    def test_build_summary(self) -> None:
        records = [
            RequestRecord(datetime(2026, 5, 18, 10, 0), "a", 10, 20, True, 8, 0.1),
            RequestRecord(datetime(2026, 5, 18, 11, 0), "b", 5, 5, False, 0, 0.2),
            RequestRecord(datetime(2026, 5, 19, 11, 0), "a", 1, 2, False, 0, 0.3),
        ]

        summary = build_summary(records)

        self.assertEqual(summary.total_requests, 3)
        self.assertEqual(summary.total_tokens, 43)
        self.assertEqual(summary.cached_requests, 1)
        self.assertEqual(summary.cached_tokens, 8)
        self.assertEqual(summary.model_totals, {"a": 33, "b": 10})
        self.assertEqual(len(summary.daily_stats), 2)
        self.assertEqual(summary.daily_stats[0].total_tokens, 40)


if __name__ == "__main__":
    unittest.main()
