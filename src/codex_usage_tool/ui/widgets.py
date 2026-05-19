from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QVariantAnimation
from PySide6.QtWidgets import QLabel
from qfluentwidgets import SimpleCardWidget


class AnimatedNumberLabel(QLabel):
    def __init__(self, text: str = "0") -> None:
        super().__init__(text)
        self._value = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(420)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._apply_value)
        self._format: Callable[[float], str] = lambda value: f"{int(value):,}"

    def set_number(self, value: float, formatter: Callable[[float], str] | None = None) -> None:
        self._format = formatter or self._format
        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(float(value))
        self._animation.start()

    def set_static_text(self, text: str) -> None:
        self._animation.stop()
        self.setText(text)

    def _apply_value(self, value: object) -> None:
        self._value = float(value)
        self.setText(self._format(self._value))


class HoverCard(SimpleCardWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("interactiveCard", True)
