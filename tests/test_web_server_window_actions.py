from __future__ import annotations

import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch

from codex_usage_tool import window_settings
from codex_usage_tool.web_server import create_app


class FakeRequest:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def json(self) -> dict[str, object]:
        return self._payload


class WebServerWindowActionTests(unittest.TestCase):
    def test_reset_widget_position_persists_default_geometry_and_emits_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings_path = Path(directory) / "window_settings.json"
            events: list[tuple[str, dict[str, object]]] = []

            with patch.object(window_settings, "WINDOW_SETTINGS_PATH", settings_path):
                app = create_app(lambda action, settings: events.append((action, settings)))
                endpoint = next(
                    route.endpoint
                    for route in app.routes
                    if getattr(route, "path", "") == "/api/window-action"
                )
                response = asyncio.run(endpoint(FakeRequest({"action": "reset-widget-position"})))
                loaded = window_settings.read_window_settings()

            self.assertEqual(response["settings"]["widget_geometry"], loaded["widget_geometry"])
            self.assertIsNone(loaded["widget_geometry"])
            self.assertEqual(events[0][0], "reset-widget-position")
            self.assertEqual(events[0][1]["widget_geometry"], loaded["widget_geometry"])


if __name__ == "__main__":
    unittest.main()
