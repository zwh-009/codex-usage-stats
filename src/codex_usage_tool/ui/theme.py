from __future__ import annotations


LIGHT_THEME = """
QWidget {
    background: #ffffff;
    color: #111827;
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 14px;
}
QFrame#metricCard, QFrame#panel {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
}
QWidget[interactiveCard="true"]:hover {
    background: #f8fbff;
    border: 1px solid #bfdbfe;
}
QLabel#heroMetric {
    color: #030712;
    font-size: 56px;
    font-weight: 800;
}
QLabel#sideMetric {
    color: #111827;
    font-size: 16px;
    font-weight: 700;
}
QLabel#tileValue {
    color: #111827;
    font-size: 20px;
    font-weight: 700;
}
QLabel#metricTitle {
    color: #6b7280;
    font-size: 13px;
    font-weight: 600;
}
QLabel#metricTitleLarge {
    color: #6b7280;
    font-size: 15px;
    font-weight: 700;
}
QLabel#metricIcon {
    background: #e0f2fe;
    color: #0284c7;
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    qproperty-alignment: AlignCenter;
}
QLabel#sectionTitle {
    color: #111827;
    font-size: 20px;
    font-weight: 800;
}
QLabel#mutedText {
    color: #6b7280;
}
QLabel#successText {
    color: #10b981;
    font-weight: 700;
}
QLabel#sourceBadge {
    background: #e8f2ff;
    color: #1683f8;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 700;
}
QPushButton {
    border-radius: 10px;
    padding: 9px 14px;
}
QPushButton:checked {
    background: #1683f8;
    color: #ffffff;
    border: 1px solid #1683f8;
}
QPushButton:hover {
    background: #eef6ff;
}
QTableWidget {
    background: #ffffff;
    border: none;
    gridline-color: #eef2f7;
    selection-background-color: #e0f2fe;
    selection-color: #111827;
}
QHeaderView::section {
    background: #ffffff;
    border: none;
    padding: 10px;
    font-weight: 700;
}
QProgressBar {
    background: #f3f4f6;
    border: none;
    border-radius: 5px;
}
QProgressBar::chunk {
    background: #10b981;
    border-radius: 5px;
}
"""


DARK_THEME = """
QWidget {
    background: #0f172a;
    color: #e5e7eb;
    font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 14px;
}
QFrame#metricCard, QFrame#panel {
    background: #182235;
    border: 1px solid #2b364b;
    border-radius: 14px;
}
QWidget[interactiveCard="true"]:hover {
    background: #1f2a44;
    border: 1px solid #3b82f6;
}
QLabel#heroMetric {
    color: #ffffff;
    font-size: 56px;
    font-weight: 800;
}
QLabel#sideMetric {
    color: #f8fafc;
    font-size: 16px;
    font-weight: 700;
}
QLabel#tileValue {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 700;
}
QLabel#metricTitle {
    color: #94a3b8;
    font-size: 13px;
    font-weight: 600;
}
QLabel#metricTitleLarge {
    color: #a5b4fc;
    font-size: 15px;
    font-weight: 700;
}
QLabel#metricIcon {
    background: #1e3a8a;
    color: #bfdbfe;
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    qproperty-alignment: AlignCenter;
}
QLabel#sectionTitle {
    color: #f8fafc;
    font-size: 20px;
    font-weight: 800;
}
QLabel#mutedText {
    color: #94a3b8;
}
QLabel#successText {
    color: #34d399;
    font-weight: 700;
}
QLabel#sourceBadge {
    background: #1e3a8a;
    color: #dbeafe;
    border-radius: 10px;
    padding: 8px 14px;
    font-weight: 700;
}
QPushButton {
    border-radius: 10px;
    padding: 9px 14px;
}
QPushButton:checked {
    background: #3b82f6;
    color: #ffffff;
    border: 1px solid #3b82f6;
}
QPushButton:hover {
    background: #1f2a44;
}
QTableWidget {
    background: #182235;
    border: none;
    gridline-color: #2b364b;
    selection-background-color: #1d4ed8;
}
QHeaderView::section {
    background: #182235;
    border: none;
    padding: 10px;
    font-weight: 700;
}
QProgressBar {
    background: #111827;
    border: none;
    border-radius: 5px;
}
QProgressBar::chunk {
    background: #34d399;
    border-radius: 5px;
}
"""


def theme_stylesheet(is_dark: bool) -> str:
    return DARK_THEME if is_dark else LIGHT_THEME
