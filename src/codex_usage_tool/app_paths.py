from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "CodexUsageTool"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_data_dir() -> Path:
    override = os.environ.get("CODEX_USAGE_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if is_frozen():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / f".{APP_DIR_NAME}"

    return project_root() / "data"


def frontend_dist_dir() -> Path:
    override = os.environ.get("CODEX_USAGE_FRONTEND_DIST")
    if override:
        return Path(override).expanduser()

    if is_frozen():
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        bundled = bundle_root / "frontend" / "dist"
        if bundled.exists():
            return bundled
        return Path(sys.executable).resolve().parent / "frontend" / "dist"

    return project_root() / "frontend" / "dist"


def app_asset_path(name: str) -> Path:
    if is_frozen():
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        bundled = bundle_root / "assets" / name
        if bundled.exists():
            return bundled
        return Path(sys.executable).resolve().parent / "assets" / name

    return project_root() / "assets" / name


def runtime_log_path() -> Path:
    return app_data_dir() / "desktop-run.log"
