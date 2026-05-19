from __future__ import annotations

import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

import uvicorn
from PySide6.QtCore import QObject, QRect, QRectF, QStandardPaths, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainterPath, QRegion
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from codex_usage_tool.app_paths import app_asset_path, runtime_log_path
from codex_usage_tool.web_server import create_app
from codex_usage_tool.window_settings import CURRENT_WIDGET_GEOMETRY_VERSION, read_window_settings, update_window_settings


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_SCAN_LIMIT = 40
MIN_WIDGET_WIDTH = 300
MIN_WIDGET_HEIGHT = 220
MIN_MAIN_WIDTH = 1080
MIN_MAIN_HEIGHT = 600
DEFAULT_MAIN_WIDTH = 1280
DEFAULT_MAIN_HEIGHT = 920
MAIN_WINDOW_MARGIN = 40
MAIN_WINDOW_COMPACT_MARGIN = 24
DEFAULT_WIDGET_WIDTH = 392
DEFAULT_WIDGET_HEIGHT = 340
DEFAULT_WIDGET_MARGIN = 24
MAX_WIDGET_SIZE = 16_777_215


def _app_icon() -> QIcon:
    icon_path = app_asset_path("app_icon.ico")
    if icon_path.exists():
        return QIcon(str(icon_path))
    png_path = app_asset_path("app_icon.png")
    if png_path.exists():
        return QIcon(str(png_path))
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)


def _widget_window_flags() -> Qt.WindowType:
    return Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint


def _widget_base_window_flags() -> Qt.WindowType:
    return _widget_window_flags()


def _main_window_flags() -> Qt.WindowType:
    return (
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowMaximizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
    )


def _main_window_margin(available: QRect) -> int:
    if available.height() < 820 or available.width() < 1100:
        return MAIN_WINDOW_COMPACT_MARGIN
    return MAIN_WINDOW_MARGIN


def _inset_rect(rect: QRect, margin: int) -> QRect:
    if margin <= 0 or rect.width() <= margin * 2 or rect.height() <= margin * 2:
        return QRect(rect)
    return rect.adjusted(margin, margin, -margin, -margin)


def _fit_rect_to_bounds(requested: QRect, bounds: QRect, min_width: int, min_height: int) -> QRect:
    if bounds.width() <= 0 or bounds.height() <= 0:
        return QRect(requested)

    effective_min_width = max(1, min(min_width, bounds.width()))
    effective_min_height = max(1, min(min_height, bounds.height()))
    width = min(max(requested.width(), effective_min_width), bounds.width())
    height = min(max(requested.height(), effective_min_height), bounds.height())
    max_x = bounds.right() - width + 1
    max_y = bounds.bottom() - height + 1
    x = min(max(requested.x(), bounds.left()), max_x)
    y = min(max(requested.y(), bounds.top()), max_y)
    return QRect(x, y, width, height)


def _has_current_widget_geometry(settings: dict[str, object]) -> bool:
    try:
        return int(settings.get("widget_geometry_version", 0)) >= CURRENT_WIDGET_GEOMETRY_VERSION
    except (TypeError, ValueError):
        return False


class WindowCommandBridge(QObject):
    command = Signal(str, object)


class UsageWebView(QWebEngineView):
    def __init__(self, window: "UsageWindow") -> None:
        super().__init__()
        self._window = window


class DesktopBridge(QObject):
    def __init__(self, window: "UsageWindow") -> None:
        super().__init__()
        self._window = window

    @Slot(int, int)
    def moveBy(self, dx: int, dy: int) -> None:
        if self._window.is_widget_mode:
            self._window.move(self._window.x() + dx, self._window.y() + dy)

    @Slot(str, int, int)
    def resizeBy(self, edge: str, dx: int, dy: int) -> None:
        if self._window.is_widget_mode:
            self._window.resize_widget_by(edge, dx, dy)

    @Slot(int)
    def setContentHeight(self, height: int) -> None:
        if self._window.is_widget_mode:
            self._window.resize_widget_to_content_height(height)

    @Slot()
    def finishDrag(self) -> None:
        if self._window.is_widget_mode:
            self._window.save_widget_geometry()


class UsageWindow(QMainWindow):
    def __init__(self, url: str, bridge: WindowCommandBridge) -> None:
        super().__init__()
        self.base_url = url
        self.is_widget_mode = False
        self._settings = read_window_settings()
        bridge.command.connect(self._handle_window_command)
        self.setWindowTitle("Codex 用量统计")
        self.resize(DEFAULT_MAIN_WIDTH, DEFAULT_MAIN_HEIGHT)

        self._desktop_bridge = DesktopBridge(self)
        self._web_channel: QWebChannel | None = None
        self._download_profile_connected = False
        self.view = self._create_view(transparent=True)
        self.setCentralWidget(self.view)
        self._restore_initial_mode()

    @Slot(str, object)
    def _handle_window_command(self, action: str, settings: object) -> None:
        if isinstance(settings, dict):
            self._settings = settings
        else:
            self._settings = read_window_settings()
        if action == "mode":
            self.apply_mode(str(self._settings.get("mode", "main")))
        elif action == "settings":
            self._apply_widget_appearance()
        elif action == "reset-widget-position":
            if self.is_widget_mode:
                self._apply_geometry("widget_geometry", self._default_widget_geometry())
                self._apply_widget_appearance()
                self._apply_widget_mask()
                self.show()
                self.raise_()

    def _handle_load_finished(self, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(self, "加载失败", "本地页面加载失败。请运行 debug_app.bat 查看启动日志。")
            return
        if not self.is_widget_mode:
            self._force_view_to_window()

    def _restore_initial_mode(self) -> None:
        mode = str(self._settings.get("mode", "main"))
        self.apply_mode(mode if mode in {"main", "widget"} else "main", initial=True)

    def apply_mode(self, mode: str, initial: bool = False) -> None:
        if mode == "widget":
            self._switch_to_widget(initial=initial)
        else:
            self._switch_to_main(initial=initial)

    def _apply_widget_window_flags(self) -> None:
        flags = _widget_window_flags()
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)

    def _apply_main_window_flags(self) -> None:
        flags = _main_window_flags()
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)

    def _apply_widget_transparent_surface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("QMainWindow, QWidget { background: transparent; }")
        if hasattr(self, "view"):
            self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
            self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
            self.view.setStyleSheet("background: transparent; border: 0px;")

    def _apply_main_surface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setStyleSheet("")
        if hasattr(self, "view"):
            self.view.page().setBackgroundColor(QColor(255, 255, 255, 255))
            self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
            self.view.setStyleSheet("")

    def _switch_to_widget(self, initial: bool = False) -> None:
        if not initial and not self.is_widget_mode:
            self._save_geometry("main_geometry")
        if not initial:
            self.hide()
        self.is_widget_mode = True
        self.setWindowTitle("Codex 用量")
        self._apply_widget_window_flags()
        self.setMinimumSize(MIN_WIDGET_WIDTH, MIN_WIDGET_HEIGHT)
        self.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self._replace_view(transparent=True)
        self._apply_widget_transparent_surface()
        self._apply_geometry("widget_geometry", self._default_widget_geometry())
        self._apply_widget_appearance()
        self._apply_widget_mask()
        self.view.setUrl(QUrl(f"{self.base_url}/widget"))
        self.show()
        self.raise_()
        self.activateWindow()

    def _switch_to_main(self, initial: bool = False) -> None:
        if not initial and self.is_widget_mode:
            self._save_geometry("widget_geometry")
            self.hide()
        self.is_widget_mode = False
        self.setWindowTitle("Codex 用量统计")
        self._apply_main_window_flags()
        self.setMinimumSize(MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT)
        self.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self.clearMask()
        self.setWindowOpacity(1.0)
        self._apply_geometry("main_geometry", self._default_main_geometry(), minimum=QRect(0, 0, MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT))
        self._replace_view(transparent=False)
        self._apply_main_surface()
        self.view.setUrl(QUrl(self.base_url))
        self.show()
        self._settle_main_window()
        QTimer.singleShot(0, self._settle_main_window)
        QTimer.singleShot(120, self._settle_main_window)
        QTimer.singleShot(260, self._settle_main_window)
        self.raise_()
        self.activateWindow()

    def _apply_widget_appearance(self) -> None:
        if not self.is_widget_mode:
            return
        self.setWindowOpacity(1.0)
        self._apply_widget_window_flags()
        self._apply_widget_transparent_surface()
        self.show()
        self._apply_widget_mask()

    def _save_geometry(self, key: str) -> None:
        geometry = self.geometry()
        payload: dict[str, object] = {
            key: {
                "x": geometry.x(),
                "y": geometry.y(),
                "width": geometry.width(),
                "height": geometry.height(),
            }
        }
        if key == "widget_geometry":
            payload["widget_geometry_version"] = CURRENT_WIDGET_GEOMETRY_VERSION
        self._settings = update_window_settings(payload)

    def save_widget_geometry(self) -> None:
        self._save_geometry("widget_geometry")

    def resize_widget_by(self, edge: str, dx: int, dy: int) -> None:
        geometry = QRect(self.geometry())
        if "left" in edge:
            new_width = max(MIN_WIDGET_WIDTH, geometry.width() - dx)
            geometry.setX(geometry.right() - new_width + 1)
        if "right" in edge:
            geometry.setWidth(max(MIN_WIDGET_WIDTH, geometry.width() + dx))
        if "top" in edge:
            new_height = max(MIN_WIDGET_HEIGHT, geometry.height() - dy)
            geometry.setY(geometry.bottom() - new_height + 1)
        if "bottom" in edge:
            geometry.setHeight(max(MIN_WIDGET_HEIGHT, geometry.height() + dy))

        self.setGeometry(self._fit_to_available_screen(geometry))
        self._apply_widget_mask()

    def resize_widget_to_content_height(self, height: int) -> None:
        current = self.geometry()
        next_height = max(MIN_WIDGET_HEIGHT, int(height))
        if abs(current.height() - next_height) <= 2:
            return
        geometry = QRect(current.x(), current.y(), current.width(), next_height)
        visible = self._fit_to_available_screen(geometry)
        self.setGeometry(visible)
        self._apply_widget_mask()
        self.save_widget_geometry()

    def _apply_geometry(self, key: str, fallback: QRect, minimum: QRect | None = None) -> None:
        geometry = self._settings.get(key)
        force_save = False
        if key == "widget_geometry" and not _has_current_widget_geometry(self._settings):
            geometry = None
            force_save = True
        if isinstance(geometry, dict):
            requested = QRect(
                int(geometry.get("x", fallback.x())),
                int(geometry.get("y", fallback.y())),
                int(geometry.get("width", fallback.width())),
                int(geometry.get("height", fallback.height())),
            )
        else:
            requested = fallback
        if minimum and (requested.width() < minimum.width() or requested.height() < minimum.height()):
            requested = QRect(fallback)
        visible = self._fit_main_to_available_screen(requested) if key == "main_geometry" else self._fit_to_available_screen(requested)
        self.setGeometry(visible)
        if visible != requested or force_save:
            self._save_geometry(key)
        if self.is_widget_mode:
            self._apply_widget_mask()

    def _fit_to_available_screen(self, requested: QRect) -> QRect:
        screen = QApplication.screenAt(requested.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return requested

        available = screen.availableGeometry()
        return _fit_rect_to_bounds(requested, available, 260, 180)

    def _fit_main_to_available_screen(self, requested: QRect) -> QRect:
        screen = QApplication.screenAt(requested.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return requested

        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        return _fit_rect_to_bounds(requested, bounds, MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT)

    def _create_view(self, transparent: bool) -> UsageWebView:
        view = UsageWebView(self)
        view.loadFinished.connect(self._handle_load_finished)
        if not self._download_profile_connected:
            view.page().profile().downloadRequested.connect(self._handle_download_requested)
            self._download_profile_connected = True
        view.setMinimumSize(0, 0)
        view.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        view.page().setBackgroundColor(QColor(0, 0, 0, 0) if transparent else QColor(255, 255, 255, 255))
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, transparent)
        view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, transparent)
        view.setStyleSheet("background: transparent; border: 0px;" if transparent else "")
        self._web_channel = QWebChannel(view.page())
        self._web_channel.registerObject("desktopBridge", self._desktop_bridge)
        view.page().setWebChannel(self._web_channel)
        return view

    def _replace_view(self, transparent: bool) -> None:
        old_view = self.takeCentralWidget()
        if old_view:
            old_view.deleteLater()
        self.view = self._create_view(transparent=transparent)
        self.setCentralWidget(self.view)
        self._force_view_to_window()

    def _force_view_to_window(self) -> None:
        if self.layout():
            self.layout().activate()
        rect = self.contentsRect()
        self.view.setGeometry(rect)
        self.view.setMinimumSize(0, 0)
        self.view.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self.view.resize(rect.size())
        self.view.updateGeometry()
        self.view.update()
        if not self.is_widget_mode:
            self.view.page().runJavaScript("window.dispatchEvent(new Event('resize'))")

    def _settle_main_window(self) -> None:
        if self.is_widget_mode:
            return
        self._keep_frame_on_screen()
        self._force_view_to_window()

    def _keep_frame_on_screen(self) -> None:
        frame = self.frameGeometry()
        screen = QApplication.screenAt(frame.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        frame_extra_width = max(frame.width() - self.width(), 0)
        frame_extra_height = max(frame.height() - self.height(), 0)
        max_client_width = max(MIN_MAIN_WIDTH, bounds.width() - frame_extra_width)
        max_client_height = max(MIN_MAIN_HEIGHT, bounds.height() - frame_extra_height)
        if self.width() > max_client_width or self.height() > max_client_height:
            self.resize(min(self.width(), max_client_width), min(self.height(), max_client_height))
            frame = self.frameGeometry()

        dx = 0
        dy = 0
        if frame.left() < bounds.left():
            dx = bounds.left() - frame.left()
        elif frame.right() > bounds.right():
            dx = bounds.right() - frame.right()
        if frame.top() < bounds.top():
            dy = bounds.top() - frame.top()
        elif frame.bottom() > bounds.bottom():
            dy = bounds.bottom() - frame.bottom()
        if dx or dy:
            self.move(self.x() + dx, self.y() + dy)
            self._save_geometry("main_geometry")

    def _default_main_geometry(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return QRect(120, 80, DEFAULT_MAIN_WIDTH, DEFAULT_MAIN_HEIGHT)

        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        width = min(DEFAULT_MAIN_WIDTH, bounds.width())
        height = min(DEFAULT_MAIN_HEIGHT, bounds.height())
        x = bounds.left() + max((bounds.width() - width) // 2, 0)
        y = bounds.top() + max((bounds.height() - height) // 2, 0)
        return QRect(x, y, width, height)

    def _default_widget_geometry(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return QRect(80, 80, DEFAULT_WIDGET_WIDTH, DEFAULT_WIDGET_HEIGHT)

        available = screen.availableGeometry()
        width = min(DEFAULT_WIDGET_WIDTH, available.width())
        height = min(DEFAULT_WIDGET_HEIGHT, available.height())
        x = available.right() - width - DEFAULT_WIDGET_MARGIN + 1
        y = available.top() + max((available.height() - height) // 2, 0)
        return QRect(x, y, width, height)

    def _apply_widget_mask(self) -> None:
        if not self.is_widget_mode:
            self.clearMask()
            return
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self.is_widget_mode:
            self._apply_widget_mask()

    def _handle_download_requested(self, download: object) -> None:
        download_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        if not download_dir:
            from pathlib import Path

            download_dir = str(Path.home() / "Downloads")

        try:
            filename = download.suggestedFileName() or "codex_usage.csv"
            download.setDownloadDirectory(download_dir)
            download.setDownloadFileName(filename)
            download.accept()
            QMessageBox.information(self, "导出已开始", f"CSV 将保存到：{download_dir}\\{filename}")
        except Exception as error:
            QMessageBox.critical(self, "导出失败", f"无法保存 CSV：{error}")


class MainUsageWindow(QMainWindow):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.base_url = url
        self.is_widget_mode = False
        self._allow_close = False
        self._close_to_tray_handler: object | None = None
        self._settings = read_window_settings()
        self.setWindowTitle("Codex 用量统计")
        self.setWindowIcon(_app_icon())
        self.setWindowFlags(_main_window_flags())
        self.setMinimumSize(MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT)
        self.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self.view = self._create_view()
        self.setCentralWidget(self.view)
        self._apply_surface()

    def show_main(self, settings: dict[str, object] | None = None) -> None:
        if settings:
            self._settings = settings
        else:
            self._settings = read_window_settings()
        self.clearMask()
        self.setWindowOpacity(1.0)
        self.setWindowFlags(_main_window_flags())
        self.setMinimumSize(MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT)
        self.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self._apply_geometry()
        self._apply_surface()
        self.view.setUrl(QUrl(self.base_url))
        self.show()
        self._settle()
        QTimer.singleShot(0, self._settle)
        QTimer.singleShot(120, self._settle)
        QTimer.singleShot(260, self._settle)
        self.raise_()
        self.activateWindow()

    def save_geometry(self) -> None:
        geometry = self.geometry()
        self._settings = update_window_settings(
            {
                "main_geometry": {
                    "x": geometry.x(),
                    "y": geometry.y(),
                    "width": geometry.width(),
                    "height": geometry.height(),
                }
            }
        )

    def save_widget_geometry(self) -> None:
        self.save_geometry()

    def set_close_to_tray_handler(self, handler: object) -> None:
        self._close_to_tray_handler = handler

    def allow_close(self) -> None:
        self._allow_close = True

    def _create_view(self) -> UsageWebView:
        view = UsageWebView(self)  # type: ignore[arg-type]
        view.loadFinished.connect(self._handle_load_finished)
        view.setMinimumSize(0, 0)
        view.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        view.page().setBackgroundColor(QColor(255, 255, 255, 255))
        return view

    def _apply_surface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setStyleSheet("")
        self.view.page().setBackgroundColor(QColor(255, 255, 255, 255))
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.view.setStyleSheet("")

    def _apply_geometry(self) -> None:
        fallback = self._default_geometry()
        geometry = self._settings.get("main_geometry")
        if isinstance(geometry, dict):
            requested = QRect(
                int(geometry.get("x", fallback.x())),
                int(geometry.get("y", fallback.y())),
                int(geometry.get("width", fallback.width())),
                int(geometry.get("height", fallback.height())),
            )
        else:
            requested = fallback
        if requested.width() < MIN_MAIN_WIDTH or requested.height() < MIN_MAIN_HEIGHT:
            requested = fallback
        visible = self._fit_to_available_screen(requested)
        self.setGeometry(visible)
        if visible != requested:
            self._settings = update_window_settings(
                {
                    "main_geometry": {
                        "x": visible.x(),
                        "y": visible.y(),
                        "width": visible.width(),
                        "height": visible.height(),
                    }
                }
            )

    def _fit_to_available_screen(self, requested: QRect) -> QRect:
        screen = QApplication.screenAt(requested.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return requested
        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        return _fit_rect_to_bounds(requested, bounds, MIN_MAIN_WIDTH, MIN_MAIN_HEIGHT)

    def _default_geometry(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return QRect(120, 80, DEFAULT_MAIN_WIDTH, DEFAULT_MAIN_HEIGHT)
        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        width = min(DEFAULT_MAIN_WIDTH, bounds.width())
        height = min(DEFAULT_MAIN_HEIGHT, bounds.height())
        x = bounds.left() + max((bounds.width() - width) // 2, 0)
        y = bounds.top() + max((bounds.height() - height) // 2, 0)
        return QRect(x, y, width, height)

    def _settle(self) -> None:
        self.clearMask()
        self._keep_frame_on_screen()
        self._force_view_to_window()

    def _keep_frame_on_screen(self) -> None:
        frame = self.frameGeometry()
        screen = QApplication.screenAt(frame.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        bounds = _inset_rect(available, _main_window_margin(available))
        frame_extra_width = max(frame.width() - self.width(), 0)
        frame_extra_height = max(frame.height() - self.height(), 0)
        max_client_width = max(MIN_MAIN_WIDTH, bounds.width() - frame_extra_width)
        max_client_height = max(MIN_MAIN_HEIGHT, bounds.height() - frame_extra_height)
        if self.width() > max_client_width or self.height() > max_client_height:
            self.resize(min(self.width(), max_client_width), min(self.height(), max_client_height))
            frame = self.frameGeometry()

        dx = 0
        dy = 0
        if frame.left() < bounds.left():
            dx = bounds.left() - frame.left()
        elif frame.right() > bounds.right():
            dx = bounds.right() - frame.right()
        if frame.top() < bounds.top():
            dy = bounds.top() - frame.top()
        elif frame.bottom() > bounds.bottom():
            dy = bounds.bottom() - frame.bottom()
        if dx or dy:
            self.move(self.x() + dx, self.y() + dy)
            self.save_geometry()

    def _force_view_to_window(self) -> None:
        if self.layout():
            self.layout().activate()
        rect = self.contentsRect()
        self.view.setGeometry(rect)
        self.view.resize(rect.size())
        self.view.updateGeometry()
        self.view.update()
        self.view.page().runJavaScript("window.dispatchEvent(new Event('resize'))")

    def _handle_load_finished(self, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(self, "加载失败", "本地页面加载失败。请运行 debug_app.bat 查看启动日志。")
            return
        self._settle()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._force_view_to_window()

    def changeEvent(self, event: object) -> None:
        super().changeEvent(event)
        if not self._allow_close and self.isMinimized():
            QTimer.singleShot(0, self._hide_to_tray)

    def closeEvent(self, event: object) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        event.ignore()
        self._hide_to_tray()

    def _hide_to_tray(self) -> None:
        self.save_geometry()
        self.hide()
        if callable(self._close_to_tray_handler):
            self._close_to_tray_handler("main")


class WidgetUsageWindow(QMainWindow):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.base_url = url
        self.is_widget_mode = True
        self._allow_close = False
        self._close_to_tray_handler: object | None = None
        self._settings = read_window_settings()
        self.setWindowTitle("Codex 用量")
        self.setWindowIcon(_app_icon())
        self._desktop_bridge = DesktopBridge(self)  # type: ignore[arg-type]
        self._web_channel: QWebChannel | None = None
        self.setMinimumSize(MIN_WIDGET_WIDTH, MIN_WIDGET_HEIGHT)
        self.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        self.view = self._create_view()
        self.setCentralWidget(self.view)
        self._apply_window_flags()
        self._apply_surface()

    def show_widget(self, settings: dict[str, object] | None = None) -> None:
        if settings:
            self._settings = settings
        else:
            self._settings = read_window_settings()
        self._apply_window_flags()
        self._apply_surface()
        self._apply_geometry()
        self._apply_mask()
        self.view.setUrl(QUrl(f"{self.base_url}/widget"))
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_appearance(self, settings: dict[str, object] | None = None) -> None:
        if settings:
            self._settings = settings
        else:
            self._settings = read_window_settings()
        if not self.isVisible():
            return
        self.setWindowOpacity(1.0)
        self._apply_window_flags()
        self._apply_surface()
        self.show()
        self._apply_mask()

    def reset_position(self, settings: dict[str, object] | None = None) -> None:
        if settings:
            self._settings = settings
        else:
            self._settings = read_window_settings()
        self._apply_geometry(use_default=True)
        self._apply_mask()
        self.show()
        self.raise_()

    def save_geometry(self) -> None:
        geometry = self.geometry()
        self._settings = update_window_settings(
            {
                "widget_geometry": {
                    "x": geometry.x(),
                    "y": geometry.y(),
                    "width": geometry.width(),
                    "height": geometry.height(),
                },
                "widget_geometry_version": CURRENT_WIDGET_GEOMETRY_VERSION,
            }
        )

    def save_widget_geometry(self) -> None:
        self.save_geometry()

    def set_close_to_tray_handler(self, handler: object) -> None:
        self._close_to_tray_handler = handler

    def allow_close(self) -> None:
        self._allow_close = True

    def resize_widget_by(self, edge: str, dx: int, dy: int) -> None:
        geometry = QRect(self.geometry())
        if "left" in edge:
            new_width = max(MIN_WIDGET_WIDTH, geometry.width() - dx)
            geometry.setX(geometry.right() - new_width + 1)
        if "right" in edge:
            geometry.setWidth(max(MIN_WIDGET_WIDTH, geometry.width() + dx))
        if "top" in edge:
            new_height = max(MIN_WIDGET_HEIGHT, geometry.height() - dy)
            geometry.setY(geometry.bottom() - new_height + 1)
        if "bottom" in edge:
            geometry.setHeight(max(MIN_WIDGET_HEIGHT, geometry.height() + dy))
        self.setGeometry(self._fit_to_available_screen(geometry))
        self._apply_mask()

    def resize_widget_to_content_height(self, height: int) -> None:
        current = self.geometry()
        next_height = max(MIN_WIDGET_HEIGHT, int(height))
        if abs(current.height() - next_height) <= 2:
            return
        geometry = QRect(current.x(), current.y(), current.width(), next_height)
        self.setGeometry(self._fit_to_available_screen(geometry))
        self._apply_mask()
        self.save_geometry()

    def _create_view(self) -> UsageWebView:
        view = UsageWebView(self)  # type: ignore[arg-type]
        view.loadFinished.connect(self._handle_load_finished)
        view.setMinimumSize(0, 0)
        view.setMaximumSize(MAX_WIDGET_SIZE, MAX_WIDGET_SIZE)
        view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        view.setStyleSheet("background: transparent; border: 0px;")
        self._web_channel = QWebChannel(view.page())
        self._web_channel.registerObject("desktopBridge", self._desktop_bridge)
        view.page().setWebChannel(self._web_channel)
        return view

    def _apply_window_flags(self) -> None:
        flags = _widget_base_window_flags()
        if self.windowFlags() != flags:
            self.setWindowFlags(flags)

    def _apply_surface(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("QMainWindow, QWidget { background: transparent; }")
        self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.view.setStyleSheet("background: transparent; border: 0px;")

    def _apply_geometry(self, use_default: bool = False) -> None:
        fallback = self._default_geometry()
        geometry = None if use_default else self._settings.get("widget_geometry")
        force_save = use_default
        if not use_default and not _has_current_widget_geometry(self._settings):
            geometry = None
            force_save = True
        if isinstance(geometry, dict):
            requested = QRect(
                int(geometry.get("x", fallback.x())),
                int(geometry.get("y", fallback.y())),
                int(geometry.get("width", fallback.width())),
                int(geometry.get("height", fallback.height())),
            )
        else:
            requested = fallback
        visible = self._fit_to_available_screen(requested)
        self.setGeometry(visible)
        if visible != requested or force_save:
            self.save_geometry()

    def _fit_to_available_screen(self, requested: QRect) -> QRect:
        screen = QApplication.screenAt(requested.center()) or self.screen() or QApplication.primaryScreen()
        if not screen:
            return requested
        return _fit_rect_to_bounds(requested, screen.availableGeometry(), MIN_WIDGET_WIDTH, MIN_WIDGET_HEIGHT)

    def _default_geometry(self) -> QRect:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return QRect(80, 80, DEFAULT_WIDGET_WIDTH, DEFAULT_WIDGET_HEIGHT)
        available = screen.availableGeometry()
        width = min(DEFAULT_WIDGET_WIDTH, available.width())
        height = min(DEFAULT_WIDGET_HEIGHT, available.height())
        x = available.right() - width - DEFAULT_WIDGET_MARGIN + 1
        y = available.top() + max((available.height() - height) // 2, 0)
        return QRect(x, y, width, height)

    def _apply_mask(self) -> None:
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _handle_load_finished(self, ok: bool) -> None:
        if not ok:
            QMessageBox.critical(self, "加载失败", "本地页面加载失败。请运行 debug_app.bat 查看启动日志。")
            return
        self.view.setGeometry(self.contentsRect())
        self.view.resize(self.contentsRect().size())

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._apply_mask()

    def changeEvent(self, event: object) -> None:
        super().changeEvent(event)
        if not self._allow_close and self.isMinimized():
            QTimer.singleShot(0, self._hide_to_tray)

    def closeEvent(self, event: object) -> None:
        if self._allow_close:
            super().closeEvent(event)
            return
        event.ignore()
        self._hide_to_tray()

    def _hide_to_tray(self) -> None:
        self.save_geometry()
        self.hide()
        if callable(self._close_to_tray_handler):
            self._close_to_tray_handler("widget")


class UsageWindowController(QObject):
    def __init__(self, url: str, bridge: WindowCommandBridge) -> None:
        super().__init__()
        self.base_url = url
        self._settings = read_window_settings()
        self.main_window = MainUsageWindow(url)
        self.widget_window = WidgetUsageWindow(url)
        self.main_window.set_close_to_tray_handler(self._handle_window_hidden_to_tray)
        self.widget_window.set_close_to_tray_handler(self._handle_window_hidden_to_tray)
        self._tray_menu = QMenu()
        self._open_main_action = QAction("打开主窗口", self._tray_menu)
        self._toggle_widget_action = QAction("显示组件", self._tray_menu)
        self._quit_action = QAction("退出", self._tray_menu)
        self._tray_icon: QSystemTrayIcon | None = None
        self._create_tray_icon()
        bridge.command.connect(self._handle_window_command)
        self.apply_mode(str(self._settings.get("mode", "main")), initial=True)

    @Slot(str, object)
    def _handle_window_command(self, action: str, settings: object) -> None:
        if isinstance(settings, dict):
            self._settings = settings
        else:
            self._settings = read_window_settings()
        if action == "mode":
            self.apply_mode(str(self._settings.get("mode", "main")))
        elif action == "settings":
            self.widget_window.apply_appearance(self._settings)
        elif action == "reset-widget-position":
            self.widget_window.reset_position(self._settings)

    def apply_mode(self, mode: str, initial: bool = False) -> None:
        mode = "widget" if mode == "widget" else "main"
        self._settings = update_window_settings({"mode": mode})
        if mode == "widget":
            if not initial and self.main_window.isVisible():
                self.main_window.save_geometry()
            self.main_window.hide()
            self.widget_window.show_widget(self._settings)
        else:
            if not initial and self.widget_window.isVisible():
                self.widget_window.save_geometry()
            self.widget_window.hide()
            self.main_window.show_main(self._settings)
        self._sync_tray_menu()

    def _create_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            _log("System tray is not available")
            return

        icon = _app_icon()
        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip("Codex 用量统计")
        self._open_main_action.triggered.connect(self._open_main_from_tray)
        self._toggle_widget_action.triggered.connect(self._toggle_widget_from_tray)
        self._quit_action.triggered.connect(self._quit_from_tray)
        self._tray_menu.addAction(self._open_main_action)
        self._tray_menu.addAction(self._toggle_widget_action)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction(self._quit_action)
        self._tray_menu.aboutToShow.connect(self._sync_tray_menu)
        self._tray_icon.setContextMenu(self._tray_menu)
        self._tray_icon.activated.connect(self._handle_tray_activated)
        self._tray_icon.show()
        self._sync_tray_menu()

    def _sync_tray_menu(self) -> None:
        self._toggle_widget_action.setText("隐藏组件" if self.widget_window.isVisible() else "显示组件")

    def _handle_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._open_current_from_tray()

    def _handle_window_hidden_to_tray(self, source: str) -> None:
        self._sync_tray_menu()
        if self._tray_icon is None or not self._tray_icon.isVisible():
            self._open_main_from_tray()
            QMessageBox.warning(None, "托盘不可用", "当前系统托盘不可用，已恢复主窗口。")

    def _open_main_from_tray(self) -> None:
        self.apply_mode("main")
        self._raise_main_from_tray()

    def _open_current_from_tray(self) -> None:
        mode = str(self._settings.get("mode", "main"))
        if mode == "widget" or self.widget_window.isVisible():
            if not self.widget_window.isVisible():
                self.apply_mode("widget")
            self._raise_widget_from_tray()
            return
        if not self.main_window.isVisible():
            self.apply_mode("main")
        self._raise_main_from_tray()

    def _raise_main_from_tray(self) -> None:
        self.main_window.setWindowState(
            self.main_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive
        )
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _raise_widget_from_tray(self) -> None:
        self.widget_window.setWindowState(
            self.widget_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive
        )
        self.widget_window.show()
        self.widget_window.raise_()
        self.widget_window.activateWindow()

    def _toggle_widget_from_tray(self) -> None:
        if self.widget_window.isVisible():
            self.widget_window.save_geometry()
            self.widget_window.hide()
            self._sync_tray_menu()
            return
        self.apply_mode("widget")
        self._raise_widget_from_tray()

    def _quit_from_tray(self) -> None:
        self.main_window.allow_close()
        self.widget_window.allow_close()
        if self.main_window.isVisible():
            self.main_window.save_geometry()
        if self.widget_window.isVisible():
            self.widget_window.save_geometry()
        if self._tray_icon is not None:
            self._tray_icon.hide()
        self.main_window.close()
        self.widget_window.close()
        QApplication.quit()

    def show(self) -> None:
        if str(self._settings.get("mode", "main")) == "widget":
            self.widget_window.show()
        else:
            self.main_window.show()

    def raise_(self) -> None:
        self.active_window().raise_()

    def activateWindow(self) -> None:
        self.active_window().activateWindow()

    def setWindowState(self, state: Qt.WindowState) -> None:
        self.active_window().setWindowState(state)

    def windowState(self) -> Qt.WindowState:
        return self.active_window().windowState()

    def active_window(self) -> QMainWindow:
        return self.widget_window if self.widget_window.isVisible() else self.main_window


def main() -> int:
    try:
        return _run()
    except Exception:
        _log("Fatal startup error")
        _log(traceback.format_exc())
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "启动失败", f"启动过程中发生错误，详情见：\n{runtime_log_path()}")
        return 1


def _run() -> int:
    _configure_runtime_environment()
    _log("Starting desktop app")
    app = QApplication(sys.argv)
    app.setWindowIcon(_app_icon())
    app.setQuitOnLastWindowClosed(False)
    port = _find_available_port(DEFAULT_PORT, PORT_SCAN_LIMIT)

    if port is None:
        end_port = DEFAULT_PORT + PORT_SCAN_LIMIT - 1
        QMessageBox.critical(None, "启动失败", f"端口 {DEFAULT_PORT}-{end_port} 都不可用，无法启动 Codex 使用统计。")
        return 1

    _log(f"Using local port {port}")
    bridge = WindowCommandBridge()
    _start_server_thread(port, bridge)
    _log("Waiting for local API")
    if not _wait_ready(port, timeout_seconds=30):
        QMessageBox.critical(
            None,
            "启动失败",
            "本地服务没有在 30 秒内启动完成。请运行 debug_app.bat 查看错误。",
        )
        return 1

    _log(f"Opening embedded window: {_app_url(port)}")
    window = UsageWindowController(_app_url(port), bridge)
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
    window.show()
    window.raise_()
    window.activateWindow()
    _log("Desktop window shown")
    return app.exec()


def _start_server_thread(port: int, bridge: WindowCommandBridge) -> None:
    def command(action: str, settings: object) -> None:
        bridge.command.emit(action, settings)

    config = uvicorn.Config(create_app(command), host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()


def _wait_ready(port: int, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _is_ready(port):
            return True
        time.sleep(0.5)
    return False


def _is_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"{_app_url(port)}/api/health", timeout=2) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def _find_available_port(start_port: int, limit: int) -> int | None:
    for port in range(start_port, start_port + limit):
        if not _port_is_busy(port):
            return port
    return None


def _port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, port)) == 0


def _app_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def _configure_runtime_environment() -> None:
    # Some elevated Windows shells start Qt WebEngine less reliably unless Chromium
    # sandboxing is disabled for this local-only embedded view.
    import os

    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault("CODEX_USAGE_LOG_FILE", str(runtime_log_path()))
    log_file = os.environ.get("CODEX_USAGE_LOG_FILE")
    if log_file:
        from pathlib import Path

        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open("a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
        os.environ["CODEX_USAGE_STDIO_REDIRECTED"] = "1"


def _log(message: str) -> None:
    import os

    line = f"[codex-usage] {message}"
    print(line, flush=True)
    log_file = os.environ.get("CODEX_USAGE_LOG_FILE")
    if not log_file or os.environ.get("CODEX_USAGE_STDIO_REDIRECTED") == "1":
        return
    try:
        from pathlib import Path

        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
