from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from codex_usage_tool.core.models import RequestRecord
from codex_usage_tool import web_server


class WebServerPriceConfigTests(unittest.TestCase):
    def test_price_config_is_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "model_prices.json"

            with patch.object(web_server, "PRICE_CONFIG_PATH", config_path):
                web_server._write_price_config(
                    web_server._sanitize_price_config(
                        {"gpt-5.5": {"input": 1.25, "cached": 0.125, "output": 10}}
                    )
                )
                loaded = web_server._read_price_config()

            self.assertEqual(loaded["gpt-5.5"]["input"], 1.25)
            self.assertEqual(loaded["gpt-5.5"]["cached"], 0.125)
            self.assertEqual(loaded["gpt-5.5"]["output"], 10.0)

    def test_records_to_csv_includes_chinese_headers_and_cost(self) -> None:
        record = RequestRecord(
            timestamp=datetime(2026, 5, 18, 10, 0, 0),
            model="gpt-5.5",
            prompt_tokens=1000,
            completion_tokens=100,
            cached=True,
            cached_tokens=400,
        )

        csv_text = web_server._records_to_csv(
            [record],
            {"gpt-5.5": {"input": 1.0, "cached": 0.1, "output": 2.0}},
        )

        self.assertIn("时间,模型,输入,输出,总量,缓存 Tokens,花费 USD", csv_text)
        self.assertIn("gpt-5.5,1000,100,1100,400,0.000840", csv_text)

    def test_records_to_xlsx_contains_sheet_data(self) -> None:
        record = RequestRecord(
            timestamp=datetime(2026, 5, 18, 10, 0, 0),
            model="gpt-5.5",
            prompt_tokens=1000,
            completion_tokens=100,
            cached=True,
            cached_tokens=400,
        )

        workbook_bytes = web_server._records_to_xlsx_bytes(
            [record],
            {"gpt-5.5": {"input": 1.0, "cached": 0.1, "output": 2.0}},
        )

        with ZipFile(BytesIO(workbook_bytes)) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("时间", sheet)
            self.assertIn("gpt-5.5", sheet)
            self.assertIn("<v>1000</v>", sheet)
            self.assertIn("<v>0.00084</v>", sheet)

    def test_desktop_dir_falls_back_to_project_exports(self) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            self.assertEqual(web_server._desktop_dir(), web_server.app_data_dir() / "exports")


if __name__ == "__main__":
    unittest.main()
