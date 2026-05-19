from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_usage_tool import app_paths


class AppPathsTests(unittest.TestCase):
    def test_development_data_dir_uses_project_data(self) -> None:
        with patch.object(app_paths, "is_frozen", return_value=False):
            self.assertEqual(app_paths.app_data_dir(), app_paths.project_root() / "data")

    def test_frozen_data_dir_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(app_paths, "is_frozen", return_value=True):
                with patch.dict("os.environ", {"LOCALAPPDATA": directory}, clear=False):
                    self.assertEqual(app_paths.app_data_dir(), Path(directory) / app_paths.APP_DIR_NAME)

    def test_data_dir_can_be_overridden_for_tests_or_portable_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"CODEX_USAGE_DATA_DIR": directory}, clear=False):
                self.assertEqual(app_paths.app_data_dir(), Path(directory))


if __name__ == "__main__":
    unittest.main()
