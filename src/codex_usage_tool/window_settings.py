from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codex_usage_tool.app_paths import app_data_dir

WINDOW_SETTINGS_PATH = app_data_dir() / "window_settings.json"
CURRENT_WIDGET_GEOMETRY_VERSION = 1

DEFAULT_WINDOW_SETTINGS: dict[str, Any] = {
    "mode": "main",
    "widget_period": "today",
    "widget_opacity": 0.86,
    "widget_theme": "glass",
    "widget_compact": False,
    "widget_show_items": {
        "tokens": True,
        "requests": True,
        "cost": True,
        "cache_rate": True,
        "token_split": True,
    },
    "main_geometry": None,
    "widget_geometry": None,
    "widget_geometry_version": 0,
}


def read_window_settings() -> dict[str, Any]:
    try:
        payload = json.loads(WINDOW_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return sanitize_window_settings(payload)


def write_window_settings(settings: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_window_settings(settings)
    WINDOW_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    WINDOW_SETTINGS_PATH.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return sanitized


def update_window_settings(partial: dict[str, Any]) -> dict[str, Any]:
    current = read_window_settings()
    current.update(partial)
    return write_window_settings(current)


def sanitize_window_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = dict(DEFAULT_WINDOW_SETTINGS)

    mode = payload.get("mode")
    if mode in {"main", "widget"}:
        settings["mode"] = mode

    period = payload.get("widget_period")
    if period in {"today", "7d", "30d", "all"}:
        settings["widget_period"] = period

    settings["widget_opacity"] = _clamp_float(payload.get("widget_opacity"), 0.2, 1.0, 0.86)

    theme = payload.get("widget_theme")
    if theme in {"glass", "frosted", "light", "dark"}:
        settings["widget_theme"] = theme

    if isinstance(payload.get("widget_compact"), bool):
        settings["widget_compact"] = payload["widget_compact"]

    show_items = payload.get("widget_show_items")
    if isinstance(show_items, dict):
        merged = dict(settings["widget_show_items"])
        for key in merged:
            if isinstance(show_items.get(key), bool):
                merged[key] = show_items[key]
        settings["widget_show_items"] = merged

    for key in ("main_geometry", "widget_geometry"):
        geometry = payload.get(key)
        if _is_geometry(geometry):
            settings[key] = {
                "x": int(geometry["x"]),
                "y": int(geometry["y"]),
                "width": int(geometry["width"]),
                "height": int(geometry["height"]),
            }

    settings["widget_geometry_version"] = _clamp_int(
        payload.get("widget_geometry_version"),
        0,
        CURRENT_WIDGET_GEOMETRY_VERSION,
        0,
    )

    return settings


def _clamp_float(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(max(parsed, minimum), maximum)


def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(max(parsed, minimum), maximum)


def _is_geometry(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        width = int(value["width"])
        height = int(value["height"])
        int(value["x"])
        int(value["y"])
    except (KeyError, TypeError, ValueError):
        return False
    return width >= 260 and height >= 180
