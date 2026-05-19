from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from codex_usage_tool.core.models import Summary


class TrendChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            import pyqtgraph as pg
        except ImportError:
            self._plot_widget = None
            layout.addWidget(QLabel("缺少 pyqtgraph，无法显示趋势图"))
            return

        self._pg = pg
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground(None)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.22)
        self._plot_widget.setLabel("left", "Tokens")
        self._plot_widget.setLabel("bottom", "Day")
        layout.addWidget(self._plot_widget)

    def update_summary(self, summary: Summary) -> None:
        if self._plot_widget is None:
            return

        self._plot_widget.clear()
        values = [stat.total_tokens for stat in summary.daily_stats]
        if not values:
            self._plot_widget.setYRange(0, 1)
            return

        x_values = list(range(len(values)))
        axis = self._plot_widget.getAxis("bottom")
        axis.setTicks([[(index, stat.date[5:]) for index, stat in enumerate(summary.daily_stats)]])
        pen = self._pg.mkPen(color="#3b82f6", width=3)
        brush = self._pg.mkBrush("#60a5fa")
        self._plot_widget.plot(
            x_values,
            values,
            pen=pen,
            symbol="o",
            symbolSize=8,
            symbolBrush=brush,
        )
        self._plot_widget.setYRange(0, max(values) * 1.15 if max(values) else 1)


class EmptyState(QWidget):
    def __init__(self, text: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel(text)
        label.setObjectName("mutedText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)


class ModelPieChart(FigureCanvas):
    def __init__(self) -> None:
        self.figure = Figure(figsize=(4, 3), dpi=100)
        super().__init__(self.figure)
        self.setMinimumHeight(260)

    def update_summary(self, summary: Summary, is_dark: bool) -> None:
        self.figure.clear()
        axis = self.figure.add_subplot(111)
        self.figure.patch.set_alpha(0)
        axis.set_facecolor("none")

        labels = list(summary.model_totals.keys())
        values = list(summary.model_totals.values())
        if not values:
            axis.text(
                0.5,
                0.5,
                "暂无数据",
                ha="center",
                va="center",
                color="#e5e7eb" if is_dark else "#1f2937",
            )
            axis.axis("off")
            self.draw_idle()
            return

        colors = ["#3b82f6", "#14b8a6", "#f59e0b", "#ef4444", "#8b5cf6", "#64748b"]
        wedges, texts, autotexts = axis.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            colors=colors[: len(values)],
            startangle=90,
            textprops={"color": "#e5e7eb" if is_dark else "#1f2937", "fontsize": 9},
        )
        for text in autotexts:
            text.set_color("#ffffff")
            text.set_fontweight("bold")
        axis.axis("equal")
        self.figure.tight_layout()
        self.draw_idle()
