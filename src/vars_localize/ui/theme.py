"""Centralized UI palette and stylesheet for VARS Localize."""

from PyQt6.QtGui import QColor

PALETTE = {
    "bg_app": "#11161c",
    "bg_panel": "#18212b",
    "bg_input": "#10161d",
    "bg_subtle": "#0d1218",
    "fg_primary": "#e6edf3",
    "fg_muted": "#9cb0c3",
    "border": "#2b3b4c",
    "accent": "#35b3ff",
    "accent_alt": "#57d18f",
    "warning": "#f3b44b",
    "danger": "#e95f5f",
    "success": "#58c58a",
}

STATUS_COLORS = {
    "unknown": PALETTE["fg_muted"],
    "empty": PALETTE["fg_muted"],
    "unlocalized": PALETTE["danger"],
    "partial": PALETTE["warning"],
    "localized": PALETTE["success"],
    "editable": PALETTE["accent"],
}


def status_brush(role: str) -> QColor:
    return QColor(STATUS_COLORS.get(role, STATUS_COLORS["unknown"]))


def app_stylesheet() -> str:
    p = PALETTE
    return f"""
QMainWindow, QWidget {{
    background-color: {p["bg_app"]};
    color: {p["fg_primary"]};
}}

QDockWidget::title {{
    background: {p["bg_subtle"]};
    color: {p["fg_muted"]};
    padding: 6px 8px;
    border: 1px solid {p["border"]};
}}

QFrame#controlsCard {{
    background-color: {p["bg_panel"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
}}

QLabel#sectionHeader {{
    color: {p["fg_muted"]};
    font-weight: 600;
    letter-spacing: 0.3px;
}}

QLabel#secondaryText {{
    color: {p["fg_muted"]};
}}

QLineEdit, QComboBox, QAbstractSpinBox {{
    background-color: {p["bg_input"]};
    border: 1px solid {p["border"]};
    border-radius: 5px;
    padding: 5px 8px;
    color: {p["fg_primary"]};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {p["accent"]};
}}

QPushButton {{
    background-color: {p["bg_panel"]};
    border: 1px solid {p["border"]};
    border-radius: 5px;
    padding: 5px 10px;
    color: {p["fg_primary"]};
}}

QPushButton:hover {{
    border: 1px solid {p["accent"]};
}}

QPushButton:disabled {{
    color: {p["fg_muted"]};
    border-color: {p["border"]};
}}

QPushButton#primaryButton {{
    background-color: {p["accent"]};
    color: {p["bg_subtle"]};
    border: 1px solid {p["accent"]};
    font-weight: 600;
}}

QPushButton#dangerButton {{
    background-color: {p["danger"]};
    color: {p["fg_primary"]};
    border: 1px solid {p["danger"]};
    font-weight: 600;
}}

QStatusBar {{
    background-color: {p["bg_subtle"]};
    border-top: 1px solid {p["border"]};
}}

QTableWidget, QScrollArea {{
    background-color: {p["bg_panel"]};
    border: 1px solid {p["border"]};
}}

QHeaderView::section {{
    background-color: {p["bg_subtle"]};
    color: {p["fg_muted"]};
    border: 0;
    border-right: 1px solid {p["border"]};
    padding: 4px 6px;
    font-weight: 600;
}}

QTableWidget::item {{
    padding: 2px 4px;
}}

QTableWidget::item:selected {{
    background-color: {p["accent"]};
    color: {p["bg_subtle"]};
}}

QWidget#paginatorBar {{
    background-color: {p["bg_subtle"]};
    border: 1px solid {p["border"]};
    border-radius: 6px;
    padding: 2px;
}}

QProgressBar {{
    border: 1px solid {p["border"]};
    border-radius: 4px;
    background-color: {p["bg_input"]};
}}

QProgressBar::chunk {{
    background-color: {p["accent_alt"]};
}}

QToolTip {{
    background-color: {p["bg_subtle"]};
    color: {p["fg_primary"]};
    border: 1px solid {p["border"]};
}}
"""
