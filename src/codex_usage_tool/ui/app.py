from __future__ import annotations

from PySide6.QtWidgets import QApplication

from codex_usage_tool.ui.main_window import MainWindow


def run_app(argv: list[str]) -> int:
    app = QApplication(argv)
    window = MainWindow()
    window.show()
    return app.exec()
