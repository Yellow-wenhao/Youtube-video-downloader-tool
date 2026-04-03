#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Literal

SummaryTone = Literal["neutral", "info", "success", "warning", "danger"]


TOKENS = {
    "bg_base": "#0F0F0F",
    "bg_elev1": "#181818",
    "bg_elev2": "#212121",
    "border_default": "#303030",
    "text_primary": "#F1F1F1",
    "text_secondary": "#AAAAAA",
    "accent_red": "#FF3B30",
    "state_success": "#22C55E",
    "state_info": "#3B82F6",
    "state_warning": "#F59E0B",
    "state_error": "#EF4444",
}


def build_main_stylesheet() -> str:
    t = TOKENS
    return f"""
    QWidget {{
        font-family: "Microsoft YaHei UI", "Source Han Sans SC", "Segoe UI";
        font-size: 13px;
        color: {t["text_primary"]};
    }}
    QMainWindow, QWidget#root {{
        background: {t["bg_base"]};
    }}
    QGroupBox {{
        border: 1px solid {t["border_default"]};
        border-radius: 14px;
        margin-top: 14px;
        padding-top: 14px;
        padding-left: 10px;
        padding-right: 10px;
        padding-bottom: 10px;
        background: {t["bg_elev1"]};
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px 0 8px;
        color: {t["text_secondary"]};
        background: {t["bg_base"]};
        border-radius: 6px;
    }}
    QGroupBox#mini {{
        margin-top: 10px;
        border-radius: 10px;
        padding-top: 10px;
        background: {t["bg_elev2"]};
    }}
    QGroupBox#mini::title {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QTabWidget::pane {{
        border: 1px solid {t["border_default"]};
        border-radius: 14px;
        background: {t["bg_elev1"]};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {t["bg_elev2"]};
        border: 1px solid {t["border_default"]};
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        padding: 9px 18px;
        margin-right: 6px;
        color: {t["text_secondary"]};
    }}
    QTabBar::tab:selected {{
        background: {t["bg_elev1"]};
        color: {t["text_primary"]};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        background: #2A2A2A;
    }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTableView, QListWidget {{
        border: 1px solid {t["border_default"]};
        border-radius: 9px;
        padding: 7px 9px;
        background: {t["bg_elev2"]};
        selection-background-color: #2F3F59;
    }}
    QSplitter::handle {{
        background: {t["border_default"]};
        border-radius: 3px;
    }}
    QSplitter::handle:horizontal {{
        width: 6px;
    }}
    QSplitter::handle:horizontal:hover {{
        background: #3D3D3D;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {t["state_info"]};
    }}
    QPushButton, QToolButton {{
        border: 1px solid {t["border_default"]};
        border-radius: 9px;
        padding: 8px 13px;
        background: {t["bg_elev2"]};
        color: {t["text_primary"]};
    }}
    QPushButton:hover, QToolButton:hover {{
        background: #2B2B2B;
    }}
    QPushButton#primary {{
        background: {t["accent_red"]};
        color: #ffffff;
        border: 1px solid #D73027;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background: #E3372D;
    }}
    QPushButton#secondary, QToolButton#secondary {{
        background: {t["bg_elev2"]};
        color: {t["text_primary"]};
        border: 1px solid {t["border_default"]};
        font-weight: 500;
    }}
    QPushButton#secondary:hover, QToolButton#secondary:hover {{
        background: #2B2B2B;
    }}
    QPushButton#danger {{
        background: {t["state_error"]};
        color: #ffffff;
        border: 1px solid #D73B35;
        font-weight: 600;
    }}
    QPushButton#danger:hover {{
        background: #DC423C;
    }}
    QProgressBar {{
        border: 1px solid {t["border_default"]};
        border-radius: 7px;
        text-align: center;
        background: {t["bg_elev2"]};
        min-height: 14px;
    }}
    QProgressBar::chunk {{
        border-radius: 6px;
        background-color: {t["state_info"]};
    }}
    QHeaderView::section {{
        background: {t["bg_elev2"]};
        border: 0px;
        border-right: 1px solid {t["border_default"]};
        border-bottom: 1px solid {t["border_default"]};
        padding: 6px 8px;
        color: {t["text_primary"]};
        font-weight: 600;
    }}
    QTableView {{
        gridline-color: {t["border_default"]};
    }}
    QStatusBar {{
        background: {t["bg_elev1"]};
        border-top: 1px solid {t["border_default"]};
    }}
    QLabel#hint {{
        color: {t["text_secondary"]};
    }}
    QListWidget#videoFeed {{
        border: none;
        background: transparent;
    }}
    QWidget#configTabPage, QWidget#configScrollContent {{
        background: transparent;
    }}
    QScrollArea#configScroll {{
        border: none;
        background: transparent;
    }}
    QScrollArea#configScroll > QWidget > QWidget {{
        background: transparent;
    }}
    QListWidget#sideNav {{
        border: 1px solid {t["border_default"]};
        border-radius: 10px;
        background: {t["bg_elev1"]};
        padding: 6px;
    }}
    QListWidget#sideNav::item {{
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 8px 10px;
        margin: 2px 0;
        color: {t["text_secondary"]};
    }}
    QListWidget#sideNav::item:hover {{
        background: {t["bg_elev2"]};
        color: {t["text_primary"]};
    }}
    QListWidget#sideNav::item:selected {{
        background: #2A1A1A;
        color: {t["text_primary"]};
        border: 1px solid {t["accent_red"]};
    }}
    QLabel#appTitle {{
        font-size: 24px;
        font-weight: 700;
        color: {t["text_primary"]};
        letter-spacing: 0.3px;
    }}
    QLabel#statusBadge {{
        font-size: 12px;
        font-weight: 600;
        color: {t["text_primary"]};
        background: #232323;
        border: 1px solid {t["border_default"]};
        padding: 4px 10px;
        border-radius: 12px;
    }}
    QLabel#sectionTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {t["text_primary"]};
    }}
    """


def tools_summary_style(tone: SummaryTone = "neutral") -> str:
    color_map = {
        "neutral": TOKENS["text_secondary"],
        "info": TOKENS["state_info"],
        "success": TOKENS["state_success"],
        "warning": TOKENS["state_warning"],
        "danger": TOKENS["state_error"],
    }
    return f"font-weight:600; color:{color_map.get(tone, TOKENS['text_secondary'])};"


def muted_text_style() -> str:
    return f"color:{TOKENS['text_secondary']};"


def active_task_card_style() -> str:
    return f"QFrame{{background:{TOKENS['bg_elev2']};border:1px solid {TOKENS['border_default']};border-radius:8px;}}"


def active_task_title_style() -> str:
    return f"font-size:12px;font-weight:600;color:{TOKENS['text_primary']};"


def video_card_style() -> str:
    return (
        f"QFrame{{background:{TOKENS['bg_elev1']};border:1px solid {TOKENS['border_default']};border-radius:12px;}}"
    )


def video_title_style() -> str:
    return f"font-size:15px; font-weight:600; color:{TOKENS['text_primary']};"


def video_meta_style() -> str:
    return f"color:{TOKENS['text_secondary']}; font-size:12px;"


def video_url_style() -> str:
    return f"color:#9FC3FF; font-size:12px;"
