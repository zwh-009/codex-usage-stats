from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from codex_usage_tool.core.models import RequestRecord
from codex_usage_tool.core.storage import export_records_csv, load_records, save_records


class StorageTests(unittest.TestCase):
    def test_save_records_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "usage.sqlite3"
            record = RequestRecord(datetime(2026, 5, 18, 10, 0), "model", 1, 2, False, 0, 0.0)

            save_records([record], db_path)
            save_records([record], db_path)

            connection = sqlite3.connect(db_path)
            try:
                count = connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(count, 1)

    def test_load_records_reads_saved_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "usage.sqlite3"
            record = RequestRecord(datetime(2026, 5, 18, 10, 0), "model", 1, 2, True, 1, 0.1)

            save_records([record], db_path)
            loaded = load_records(db_path)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].model, "model")
            self.assertEqual(loaded[0].cached_tokens, 1)

    def test_save_records_can_replace_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "usage.sqlite3"
            old_record = RequestRecord(datetime(2026, 5, 18, 10, 0), "old", 1, 2, False, 0, 0.0)
            new_record = RequestRecord(datetime(2026, 5, 19, 10, 0), "new", 3, 4, False, 0, 0.0)

            save_records([old_record], db_path)
            save_records([new_record], db_path, replace=True)
            loaded = load_records(db_path)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].model, "new")

    def test_export_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "usage.csv"
            record = RequestRecord(datetime(2026, 5, 18, 10, 0), "model", 1, 2, True, 1, 0.1)

            export_records_csv([record], csv_path)

            with csv_path.open("r", encoding="utf-8", newline="") as file:
                rows = list(csv.reader(file))

            self.assertEqual(rows[0][0], "时间")
            self.assertEqual(rows[1][1], "model")
            self.assertEqual(rows[1][5], "1")


if __name__ == "__main__":
    unittest.main()
