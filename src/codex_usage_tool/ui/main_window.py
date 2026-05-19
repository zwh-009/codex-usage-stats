from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon as FIF,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    TableWidget,
    Theme,
    TitleLabel,
    setTheme,
)

from codex_usage_tool.core.models import RequestRecord, Summary
from codex_usage_tool.core.parser import auto_load_records, parse_jsonl_file, parse_sqlite_log_file
from codex_usage_tool.core.statistics import build_summary
from codex_usage_tool.core.storage import DEFAULT_DB_PATH, export_records_csv, save_records
from codex_usage_tool.ui.charts import ModelPieChart, TrendChart
from codex_usage_tool.ui.theme import theme_stylesheet
from codex_usage_tool.ui.widgets import AnimatedNumberLabel, HoverCard


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Codex 用量统计")
        self.resize(1180, 760)

        self._records: list[RequestRecord] = []
        self._visible_records: list[RequestRecord] = []
        self._summary = build_summary([])
        self._log_path: Path | None = None
        self._source_note = "自动读取"
        self._is_dark = False
        self._period_filter = "all"
        self._model_filter = "all"
        self._search_text = ""

        self._metric_labels: dict[str, AnimatedNumberLabel] = {}
        self._hero_total_label = AnimatedNumberLabel("0")
        self._hero_hint_label = CaptionLabel("")
        self._cache_bar = QProgressBar()
        self._cache_animation = QPropertyAnimation(self._cache_bar, b"value", self)
        self._cache_animation.setDuration(420)
        self._cache_rate_label = CaptionLabel("0%")
        self._status_badge = QLabel("自动读取")
        self._source_detail_label = CaptionLabel("")
        self._trend_chart = TrendChart()
        self._pie_chart = ModelPieChart()
        self._table = self._create_table()
        self._period_buttons: dict[str, PushButton] = {}
        self._model_buttons: dict[str, PushButton] = {}
        self._model_button_layout: QHBoxLayout | None = None
        self._search_input = SearchLineEdit()

        self._setup_ui()
        self._apply_theme()
        self.refresh_data()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30_000)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._refresh_timer.start()

    def _setup_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(30, 24, 30, 24)
        root_layout.setSpacing(18)

        root_layout.addLayout(self._build_header())
        root_layout.addWidget(self._build_segments())
        root_layout.addWidget(self._build_usage_card())
        root_layout.addLayout(self._build_main_grid(), 1)
        root_layout.addWidget(self._build_history(), 1)

        self.setCentralWidget(root)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        title_group = QVBoxLayout()
        title_group.setSpacing(4)
        title = TitleLabel("使用统计")
        subtitle = CaptionLabel("查看 Codex 模型的本地用量和缓存情况")
        subtitle.setObjectName("mutedText")
        title_group.addWidget(title)
        title_group.addWidget(subtitle)
        layout.addLayout(title_group)
        layout.addStretch(1)

        refresh_button = PrimaryPushButton()
        refresh_button.setText("刷新")
        refresh_button.setIcon(FIF.SYNC)
        refresh_button.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_button)

        export_button = PushButton()
        export_button.setText("导出")
        export_button.setIcon(FIF.DOWNLOAD)
        export_button.clicked.connect(self.export_csv)
        layout.addWidget(export_button)

        choose_button = PushButton()
        choose_button.setText("更换来源")
        choose_button.setIcon(FIF.FOLDER)
        choose_button.clicked.connect(self.choose_log_file)
        layout.addWidget(choose_button)

        theme_button = PushButton()
        theme_button.setText("主题")
        theme_button.setIcon(FIF.BRIGHTNESS)
        theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(theme_button)
        return layout

    def _build_segments(self) -> QFrame:
        panel = self._panel()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        for key, label in [("today", "今天"), ("7d", "7 天"), ("30d", "30 天"), ("all", "全部")]:
            button = PushButton()
            button.setText(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=key: self._set_period_filter(value))
            self._period_buttons[key] = button
            layout.addWidget(button)
        self._period_buttons[self._period_filter].setChecked(True)

        self._model_button_layout = QHBoxLayout()
        self._model_button_layout.setSpacing(8)
        layout.addLayout(self._model_button_layout)

        layout.addStretch(1)
        self._status_badge.setObjectName("sourceBadge")
        layout.addWidget(self._status_badge)

        self._source_detail_label.setObjectName("mutedText")
        self._source_detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._source_detail_label)

        interval = CaptionLabel("30s")
        interval.setObjectName("mutedText")
        layout.addWidget(interval)
        return panel

    def _build_usage_card(self) -> QFrame:
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 34, 40, 34)
        layout.setSpacing(26)

        top = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(12)
        label_row = QHBoxLayout()
        icon = QLabel("↯")
        icon.setObjectName("metricIcon")
        label = BodyLabel("真实消耗 Tokens")
        label.setObjectName("metricTitleLarge")
        label_row.addWidget(icon)
        label_row.addWidget(label)
        label_row.addStretch(1)
        left.addLayout(label_row)

        self._hero_total_label.setObjectName("heroMetric")
        self._hero_hint_label.setObjectName("mutedText")
        left.addWidget(self._hero_total_label)
        left.addWidget(self._hero_hint_label)
        top.addLayout(left, 1)

        right = QHBoxLayout()
        right.setSpacing(32)
        for key, title in [("requests", "总请求数"), ("cost", "总成本")]:
            group = QVBoxLayout()
            group.setSpacing(4)
            title_label = CaptionLabel(title)
            title_label.setObjectName("mutedText")
            value_label = AnimatedNumberLabel("0")
            value_label.setObjectName("sideMetric")
            self._metric_labels[key] = value_label
            group.addWidget(title_label)
            group.addWidget(value_label)
            right.addLayout(group)
        top.addLayout(right)
        layout.addLayout(top)

        tiles = QHBoxLayout()
        tiles.setSpacing(14)

        for key, title in [
            ("input", "新增输入"),
            ("output", "输出"),
            ("cache_tokens", "缓存 Tokens"),
            ("cached", "缓存请求"),
        ]:
            card = HoverCard()
            card.setObjectName("metricCard")
            card.setToolTip(title)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 14, 16, 14)
            card_layout.setSpacing(8)
            title_label = CaptionLabel(title)
            title_label.setObjectName("metricTitle")
            value_label = AnimatedNumberLabel("0")
            value_label.setObjectName("tileValue")
            card_layout.addWidget(title_label)
            card_layout.addWidget(value_label)
            self._metric_labels[key] = value_label
            tiles.addWidget(card, 1)
        layout.addLayout(tiles)

        cache_row = QVBoxLayout()
        line = QHBoxLayout()
        cache_label = CaptionLabel("缓存命中率")
        cache_label.setObjectName("mutedText")
        self._cache_rate_label.setObjectName("successText")
        line.addWidget(cache_label)
        line.addStretch(1)
        line.addWidget(self._cache_rate_label)
        self._cache_bar.setRange(0, 1000)
        self._cache_bar.setTextVisible(False)
        self._cache_bar.setFixedHeight(10)
        cache_row.addLayout(line)
        cache_row.addWidget(self._cache_bar)
        layout.addLayout(cache_row)
        return panel

    def _build_main_grid(self) -> QGridLayout:
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)
        trend_panel = self._panel()
        trend_layout = QVBoxLayout(trend_panel)
        trend_layout.setContentsMargins(16, 12, 16, 12)
        trend_title = BodyLabel("每日 Token 趋势")
        trend_title.setObjectName("sectionTitle")
        trend_layout.addWidget(trend_title)
        trend_layout.addWidget(self._trend_chart, 1)

        pie_panel = self._panel()
        pie_layout = QVBoxLayout(pie_panel)
        pie_layout.setContentsMargins(16, 12, 16, 12)
        pie_title = BodyLabel("模型占比")
        pie_title.setObjectName("sectionTitle")
        pie_layout.addWidget(pie_title)
        pie_layout.addWidget(self._pie_chart, 1)

        layout.addWidget(trend_panel, 0, 0, 1, 3)
        layout.addWidget(pie_panel, 0, 3, 1, 1)
        return layout

    def _build_history(self) -> QFrame:
        panel = self._panel()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 16)
        header = QHBoxLayout()
        title = BodyLabel("最近请求")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._search_input.setPlaceholderText("搜索模型或时间")
        self._search_input.setFixedWidth(260)
        self._search_input.textChanged.connect(self._set_search_text)
        header.addWidget(self._search_input)
        layout.addLayout(header)
        layout.addWidget(self._table)
        return panel

    def _create_table(self) -> TableWidget:
        table = TableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["时间", "模型", "输入", "输出", "总量", "缓存 Tokens", "花费"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        return table

    def choose_log_file(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "更换数据来源",
            str(Path.home() / ".codex"),
            "Codex Logs (*.sqlite *.sqlite3 *.db *.jsonl);;All Files (*.*)",
        )
        if not selected:
            return
        self._log_path = Path(selected)
        self._source_note = "手动选择"
        self.refresh_data()

    def refresh_data(self) -> None:
        if self._log_path is None:
            self._records, self._log_path, self._source_note = auto_load_records()
        elif self._log_path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            self._records = parse_sqlite_log_file(self._log_path)
        else:
            self._records = parse_jsonl_file(self._log_path)
        save_records(self._records, DEFAULT_DB_PATH)
        self._rebuild_model_filters()
        self._render_data()

    def export_csv(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "导出 CSV",
            str(Path("data") / "codex_usage.csv"),
            "CSV Files (*.csv)",
        )
        if not selected:
            return
        path = export_records_csv(self._records, selected)
        QMessageBox.information(self, "导出完成", f"已导出到：{path}")

    def toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self._apply_theme()
        self._pie_chart.update_summary(self._summary, self._is_dark)

    def _render_data(self) -> None:
        self._visible_records = self._filtered_records()
        self._summary = build_summary(self._visible_records)
        summary = self._summary
        self._status_badge.setText("已读取" if self._records else "无数据")
        source_name = self._log_path.name if self._log_path else "未找到来源"
        self._source_detail_label.setText(f"{source_name} · {self._latest_text()}")
        cache_rate = summary.cached_tokens / summary.prompt_tokens if summary.prompt_tokens else 0.0
        bounded_cache_rate = min(max(cache_rate, 0.0), 1.0)
        self._hero_total_label.set_number(summary.total_tokens, lambda value: f"{int(value):,}")
        self._hero_hint_label.setText(f"约 {_format_compact_tokens(summary.total_tokens)} tokens")
        self._metric_labels["requests"].set_number(summary.total_requests, lambda value: f"{int(value):,}")
        self._metric_labels["input"].set_number(summary.prompt_tokens, lambda value: _format_compact_tokens(int(value)))
        self._metric_labels["output"].set_number(summary.completion_tokens, lambda value: _format_compact_tokens(int(value)))
        self._metric_labels["cache_tokens"].set_number(summary.cached_tokens, lambda value: _format_compact_tokens(int(value)))
        self._metric_labels["cached"].set_number(summary.cached_requests, lambda value: f"{int(value):,}")
        cost_label = self._metric_labels["cost"]
        if summary.total_tokens > 0 and summary.total_cost_usd == 0:
            cost_label.set_static_text("未配置")
        else:
            cost_label.set_number(summary.total_cost_usd, lambda value: f"${value:,.4f}")
        self._cache_animation.stop()
        self._cache_animation.setStartValue(self._cache_bar.value())
        self._cache_animation.setEndValue(int(bounded_cache_rate * 1000))
        self._cache_animation.start()
        self._cache_rate_label.setText(f"{cache_rate * 100:.1f}%")
        self._trend_chart.update_summary(summary)
        self._pie_chart.update_summary(summary, self._is_dark)
        self._render_table()

    def _render_table(self) -> None:
        self._table.setSortingEnabled(False)
        records = sorted(self._visible_records, key=lambda item: item.timestamp, reverse=True)[:200]
        self._table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                record.model,
                str(record.prompt_tokens),
                str(record.completion_tokens),
                str(record.total_tokens),
                str(record.cached_tokens),
                f"{record.cost_usd:.6f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in {2, 3, 4, 5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row, column, item)
        self._table.setSortingEnabled(True)

    def _apply_theme(self) -> None:
        setTheme(Theme.DARK if self._is_dark else Theme.LIGHT)
        QApplication.instance().setStyleSheet(theme_stylesheet(self._is_dark))

    def _panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        return panel

    def _latest_text(self) -> str:
        if not self._visible_records:
            return "没有解析到用量记录"
        latest = max(record.timestamp for record in self._visible_records)
        return f"最新 {latest.strftime('%m-%d %H:%M')}"

    def _set_period_filter(self, value: str) -> None:
        self._period_filter = value
        self._sync_filter_buttons()
        self._render_data()

    def _set_model_filter(self, value: str) -> None:
        self._model_filter = value
        self._sync_filter_buttons()
        self._render_data()

    def _set_search_text(self, value: str) -> None:
        self._search_text = value.strip().lower()
        self._render_data()

    def _filtered_records(self) -> list[RequestRecord]:
        records = list(self._records)
        now = datetime.now().astimezone()
        if self._period_filter == "today":
            records = [_record for _record in records if _as_local(_record.timestamp).date() == now.date()]
        elif self._period_filter == "7d":
            since = now - timedelta(days=7)
            records = [_record for _record in records if _as_local(_record.timestamp) >= since]
        elif self._period_filter == "30d":
            since = now - timedelta(days=30)
            records = [_record for _record in records if _as_local(_record.timestamp) >= since]

        if self._model_filter != "all":
            records = [record for record in records if record.model == self._model_filter]

        if self._search_text:
            records = [
                record
                for record in records
                if self._search_text in record.model.lower()
                or self._search_text in record.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ]
        return records

    def _rebuild_model_filters(self) -> None:
        if self._model_button_layout is None:
            return

        _clear_layout(self._model_button_layout)
        self._model_buttons.clear()

        models = sorted({record.model for record in self._records})
        available = {"all", *models}
        if self._model_filter not in available:
            self._model_filter = "all"

        for value, label in [("all", "全部模型"), *[(model, model) for model in models]]:
            button = PushButton()
            button.setText(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, model=value: self._set_model_filter(model))
            self._model_buttons[value] = button
            self._model_button_layout.addWidget(button)
        self._sync_filter_buttons()

    def _sync_filter_buttons(self) -> None:
        for value, button in self._period_buttons.items():
            button.setChecked(value == self._period_filter)
        for value, button in self._model_buttons.items():
            button.setChecked(value == self._model_filter)


def _format_compact_tokens(value: int) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿"
    if value >= 10_000:
        return f"{value / 10_000:.1f} 万"
    return f"{value:,}"


def _format_cost(summary: Summary) -> str:
    if summary.total_tokens > 0 and summary.total_cost_usd == 0:
        return "未配置"
    return f"${summary.total_cost_usd:,.4f}"


def _clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)


def _as_local(value: datetime) -> datetime:
    return value.astimezone()
