from __future__ import annotations

import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, Qt

from codex_usage_tool import web_desktop


class WebDesktopPortTest(unittest.TestCase):
    def test_find_available_port_skips_busy_ports(self) -> None:
        busy_ports = {8765, 8766}

        with patch.object(web_desktop, "_port_is_busy", side_effect=lambda port: port in busy_ports):
            self.assertEqual(web_desktop._find_available_port(8765, 5), 8767)

    def test_find_available_port_returns_none_when_range_is_busy(self) -> None:
        with patch.object(web_desktop, "_port_is_busy", return_value=True):
            self.assertIsNone(web_desktop._find_available_port(8765, 3))

    def test_main_window_flags_restore_native_controls(self) -> None:
        flags = web_desktop._main_window_flags()

        self.assertFalse(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowTitleHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowSystemMenuHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMinimizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowMaximizeButtonHint))
        self.assertTrue(bool(flags & Qt.WindowType.WindowCloseButtonHint))

    def test_widget_window_flags_are_frameless_without_topmost(self) -> None:
        flags = web_desktop._widget_window_flags()

        self.assertTrue(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertFalse(bool(flags & Qt.WindowType.WindowStaysOnTopHint))

    def test_widget_base_window_flags_do_not_include_topmost(self) -> None:
        flags = web_desktop._widget_base_window_flags()

        self.assertTrue(bool(flags & Qt.WindowType.FramelessWindowHint))
        self.assertFalse(bool(flags & Qt.WindowType.WindowStaysOnTopHint))

    def test_fit_rect_to_bounds_keeps_margin_area(self) -> None:
        bounds = QRect(40, 40, 1200, 800)
        requested = QRect(0, 0, 1280, 1040)

        fitted = web_desktop._fit_rect_to_bounds(requested, bounds, 900, 600)

        self.assertEqual(fitted.top(), 40)
        self.assertEqual(fitted.left(), 40)
        self.assertLessEqual(fitted.width(), bounds.width())
        self.assertLessEqual(fitted.height(), bounds.height())

    def test_inset_rect_leaves_vertical_safe_margin(self) -> None:
        rect = QRect(0, 0, 1920, 1040)

        inset = web_desktop._inset_rect(rect, 40)

        self.assertEqual(inset.top(), 40)
        self.assertEqual(inset.bottom(), 999)

    def test_widget_geometry_requires_current_version(self) -> None:
        self.assertFalse(web_desktop._has_current_widget_geometry({}))
        self.assertFalse(web_desktop._has_current_widget_geometry({"widget_geometry_version": 0}))
        self.assertTrue(
            web_desktop._has_current_widget_geometry(
                {"widget_geometry_version": web_desktop.CURRENT_WIDGET_GEOMETRY_VERSION}
            )
        )


if __name__ == "__main__":
    unittest.main()
