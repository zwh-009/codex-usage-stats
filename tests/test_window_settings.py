from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_usage_tool import window_settings


class WindowSettingsTests(unittest.TestCase):
    def test_settings_are_sanitized_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "window_settings.json"

            with patch.object(window_settings, "WINDOW_SETTINGS_PATH", settings_path):
                saved = window_settings.write_window_settings(
                    {
                        "mode": "widget",
                        "widget_period": "7d",
                        "widget_opacity": 1.7,
                        "widget_theme": "dark",
                        "widget_compact": True,
                        "widget_show_items": {"cost": False},
                        "widget_geometry": {"x": 10, "y": 20, "width": 390, "height": 300},
                        "widget_geometry_version": window_settings.CURRENT_WIDGET_GEOMETRY_VERSION,
                    }
                )
                loaded = window_settings.read_window_settings()

            self.assertEqual(saved["mode"], "widget")
            self.assertEqual(loaded["widget_period"], "7d")
            self.assertEqual(loaded["widget_opacity"], 1.0)
            self.assertEqual(loaded["widget_theme"], "dark")
            self.assertTrue(loaded["widget_compact"])
            self.assertFalse(loaded["widget_show_items"]["cost"])
            self.assertTrue(loaded["widget_show_items"]["tokens"])
            self.assertEqual(loaded["widget_geometry"]["width"], 390)
            self.assertEqual(loaded["widget_geometry_version"], window_settings.CURRENT_WIDGET_GEOMETRY_VERSION)

    def test_invalid_settings_fall_back_to_defaults(self) -> None:
        sanitized = window_settings.sanitize_window_settings(
            {
                "mode": "other",
                "widget_period": "date",
                "widget_opacity": 0.1,
                "widget_theme": "neon",
                "widget_geometry": {"x": 0, "y": 0, "width": 10, "height": 10},
            }
        )

        self.assertEqual(sanitized["mode"], "main")
        self.assertEqual(sanitized["widget_period"], "today")
        self.assertEqual(sanitized["widget_opacity"], 0.2)
        self.assertEqual(sanitized["widget_theme"], "glass")
        self.assertIsNone(sanitized["widget_geometry"])
        self.assertEqual(sanitized["widget_geometry_version"], 0)

    def test_widget_geometry_version_is_clamped(self) -> None:
        sanitized = window_settings.sanitize_window_settings(
            {
                "widget_geometry": {"x": 10, "y": 20, "width": 390, "height": 300},
                "widget_geometry_version": 999,
            }
        )

        self.assertEqual(sanitized["widget_geometry"]["width"], 390)
        self.assertEqual(sanitized["widget_geometry_version"], window_settings.CURRENT_WIDGET_GEOMETRY_VERSION)


if __name__ == "__main__":
    unittest.main()
