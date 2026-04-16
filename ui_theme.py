#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Literal

SummaryTone = Literal["neutral", "info", "success", "warning", "danger"]


TOKENS = {
    "bg_base": "#F4F7FA",
    "bg_elev1": "#FFFFFF",
    "bg_elev2": "#F8FAFC",
    "bg_elev3": "#EEF3F8",
    "bg_page": "#F4F7FA",
    "bg_card": "#FFFFFF",
    "bg_interactive": "#F8FAFC",
    "bg_interactive_hover": "#EEF3F8",
    "border_default": "#D6DEE8",
    "border_strong": "#B7C4D3",
    "text_primary": "#18212B",
    "text_secondary": "#536273",
    "text_muted": "#708095",
    "accent_red": "#E45A50",
    "accent_red_deep": "#C9453C",
    "accent_blue": "#2F6FE4",
    "accent_gold": "#A56A00",
    "state_success": "#22C55E",
    "state_info": "#3B82F6",
    "state_warning": "#F59E0B",
    "state_error": "#EF4444",
    "surface_info_bg": "#EAF2FF",
    "surface_info_fg": "#255CC4",
    "surface_info_border": "#BDD0F5",
    "surface_success_bg": "#EAF8EF",
    "surface_success_fg": "#216A39",
    "surface_success_border": "#B9DABD",
    "surface_warning_bg": "#FFF5E5",
    "surface_warning_fg": "#9A6100",
    "surface_warning_border": "#F0D6A2",
    "surface_danger_bg": "#FDEDEC",
    "surface_danger_fg": "#B93830",
    "surface_danger_border": "#F2B8B3",
    "surface_muted_bg": "#EEF3F8",
    "surface_muted_fg": "#536273",
    "surface_muted_border": "#D6DEE8",
    "focus_ring": "#BFD5FF",
    "card_shell": "#F8FBFE",
    "card_shell_border": "#D7E2EE",
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
        background: {t["bg_page"]};
    }}
    QGroupBox {{
        border: 1px solid {t["border_default"]};
        border-radius: 16px;
        margin-top: 14px;
        padding-top: 16px;
        padding-left: 12px;
        padding-right: 12px;
        padding-bottom: 12px;
        background: {t["bg_card"]};
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px 0 8px;
        color: {t["text_secondary"]};
        background: {t["bg_page"]};
        border-radius: 8px;
    }}
    QGroupBox#mini {{
        margin-top: 10px;
        border-radius: 12px;
        padding-top: 12px;
        background: {t["bg_interactive"]};
    }}
    QGroupBox#mini::title {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QGroupBox#surfacePanel {{
        background: {t["bg_card"]};
        border: 1px solid {t["border_default"]};
    }}
    QGroupBox#surfacePanel::title {{
        color: {t["text_primary"]};
        font-size: 13px;
        font-weight: 700;
        background: {t["bg_page"]};
        border-radius: 8px;
    }}
    QTabWidget::pane {{
        border: 1px solid {t["border_default"]};
        border-radius: 12px;
        background: {t["bg_card"]};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {t["bg_interactive"]};
        border: 1px solid {t["border_default"]};
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        padding: 9px 18px;
        margin-right: 6px;
        color: {t["text_secondary"]};
    }}
    QTabBar::tab:selected {{
        background: {t["bg_card"]};
        color: {t["text_primary"]};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        background: {t["bg_interactive_hover"]};
    }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTableView, QListWidget {{
        border: 1px solid {t["border_default"]};
        border-radius: 11px;
        padding: 9px 12px;
        background: {t["bg_interactive"]};
        selection-background-color: #DCE7F8;
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QPlainTextEdit:hover {{
        border: 1px solid {t["border_strong"]};
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
        background: #FFFFFF;
    }}
    QPushButton, QToolButton {{
        border: 1px solid {t["border_default"]};
        border-radius: 11px;
        padding: 9px 15px;
        background: {t["bg_interactive"]};
        color: {t["text_primary"]};
        font-weight: 600;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {t["bg_interactive_hover"]};
        border: 1px solid {t["border_strong"]};
    }}
    QPushButton:focus, QToolButton:focus, QListWidget:focus {{
        border: 1px solid {t["state_info"]};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        background: #F1F5F9;
        color: #8A98A8;
        border: 1px solid #D8E0E8;
    }}
    QPushButton#primary {{
        background: {t["accent_blue"]};
        color: #ffffff;
        border: 1px solid #255CC4;
        font-weight: 700;
    }}
    QPushButton#primary:hover {{
        background: #3D7AF0;
        border: 1px solid #255CC4;
    }}
    QPushButton#secondary, QToolButton#secondary {{
        background: #FBFDFF;
        color: {t["text_primary"]};
        border: 1px solid #D5E0EB;
        font-weight: 600;
    }}
    QPushButton#secondary:hover, QToolButton#secondary:hover {{
        background: #EEF5FB;
        border: 1px solid #BFD1E2;
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
    QMenu {{
        background: {t["bg_card"]};
        color: {t["text_primary"]};
        border: 1px solid {t["border_default"]};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 12px;
        margin: 2px 0;
        border-radius: 8px;
        color: {t["text_primary"]};
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {t["bg_interactive"]};
        color: {t["text_primary"]};
    }}
    QMenu::item:disabled {{
        color: #6F6F6F;
        background: transparent;
    }}
    QMenu::separator {{
        height: 1px;
        margin: 6px 4px;
        background: {t["border_default"]};
    }}
    QProgressBar {{
        border: 1px solid {t["border_default"]};
        border-radius: 7px;
        text-align: center;
        background: {t["bg_interactive"]};
        min-height: 14px;
    }}
    QProgressBar::chunk {{
        border-radius: 6px;
        background-color: {t["state_info"]};
    }}
    QHeaderView::section {{
        background: {t["bg_interactive"]};
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
        background: {t["bg_card"]};
        border-top: 1px solid {t["border_default"]};
    }}
    QLabel#hint {{
        color: {t["text_secondary"]};
    }}
    QLabel#appSubtitle {{
        font-size: 12px;
        color: {t["text_secondary"]};
        letter-spacing: 0.2px;
    }}
    QFrame#heroBanner {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #F6F9FF,
            stop:0.55 #FFF9F4,
            stop:1 #F8F1EE);
        border: 1px solid {t["border_default"]};
        border-radius: 16px;
    }}
    QLabel#heroEyebrow {{
        color: {t["accent_gold"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#heroTitle {{
        color: {t["text_primary"]};
        font-size: 20px;
        font-weight: 800;
    }}
    QLabel#heroDescription {{
        color: {t["text_secondary"]};
        font-size: 12px;
        line-height: 1.5;
    }}
    QListWidget#videoFeed {{
        border: none;
        background: transparent;
    }}
    QListWidget#queueCards {{
        border: none;
        background: transparent;
        padding: 0;
    }}
    QListWidget#queueCards::item {{
        border: none;
        margin: 0 0 8px 0;
    }}
    QFrame#queueTaskCardManual, QFrame#queueTaskCardAgent {{
        background: {t["bg_card"]};
        border: 1px solid {t["card_shell_border"]};
        border-radius: 15px;
    }}
    QFrame#queueTaskCardManual:hover, QFrame#queueTaskCardAgent:hover {{
        border: 1px solid {t["border_strong"]};
    }}
    QFrame#queueTaskCardAgent {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F4FBF6,
            stop:1 #EEF8F2);
        border: 1px solid #BFD8C7;
    }}
    QFrame#queueTaskCardManual {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F9FBFD,
            stop:1 #F2F6FA);
    }}
    QLabel#queueCardTitle {{
        font-size: 13px;
        font-weight: 700;
        color: {t["text_primary"]};
    }}
    QLabel#agentBadge, QLabel#manualBadge {{
        font-size: 11px;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 9px;
    }}
    QLabel#agentBadge {{
        background: #EAF8EF;
        color: #216A39;
        border: 1px solid #B9DABD;
    }}
    QLabel#manualBadge {{
        background: #EEF3F8;
        color: {t["text_secondary"]};
        border: 1px solid {t["border_default"]};
    }}
    QLabel#queueNextAction {{
        color: {t["text_secondary"]};
        background: #F8FBFE;
        border: 1px solid #D8E2EC;
        border-radius: 10px;
        padding: 8px 10px;
        font-size: 12px;
    }}
    QLabel#statusPillInfo, QLabel#statusPillSuccess, QLabel#statusPillWarning,
    QLabel#statusPillDanger, QLabel#statusPillMuted {{
        border-radius: 9px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#statusPillInfo {{
        background: {t["surface_info_bg"]};
        color: {t["surface_info_fg"]};
        border: 1px solid {t["surface_info_border"]};
    }}
    QLabel#statusPillSuccess {{
        background: {t["surface_success_bg"]};
        color: {t["surface_success_fg"]};
        border: 1px solid {t["surface_success_border"]};
    }}
    QLabel#statusPillWarning {{
        background: {t["surface_warning_bg"]};
        color: {t["surface_warning_fg"]};
        border: 1px solid {t["surface_warning_border"]};
    }}
    QLabel#statusPillDanger {{
        background: {t["surface_danger_bg"]};
        color: {t["surface_danger_fg"]};
        border: 1px solid {t["surface_danger_border"]};
    }}
    QLabel#statusPillMuted {{
        background: {t["surface_muted_bg"]};
        color: {t["surface_muted_fg"]};
        border: 1px solid {t["surface_muted_border"]};
    }}
    QLabel#metricCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FFFFFF,
            stop:1 #F8FBFE);
        border: 1px solid {t["card_shell_border"]};
        border-radius: 14px;
        padding: 13px 14px;
    }}
    QLabel#semanticBadge {{
        color: #255CC4;
        background: #EAF2FF;
        border: 1px solid #BDD0F5;
        border-radius: 9px;
        padding: 4px 8px;
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#videoStatusOk, QLabel#videoStatusWarn, QLabel#videoStatusMuted {{
        border-radius: 9px;
        padding: 4px 8px;
        font-size: 12px;
        font-weight: 700;
    }}
    QLabel#videoStatusOk {{
        color: {t["state_success"]};
        background: {t["surface_success_bg"]};
        border: 1px solid {t["surface_success_border"]};
    }}
    QLabel#videoStatusWarn {{
        color: {t["state_warning"]};
        background: {t["surface_warning_bg"]};
        border: 1px solid {t["surface_warning_border"]};
    }}
    QLabel#videoStatusMuted {{
        color: {t["text_secondary"]};
        background: {t["surface_muted_bg"]};
        border: 1px solid {t["surface_muted_border"]};
    }}
    QLabel#videoReason {{
        color: {t["text_secondary"]};
        background: #F8FBFE;
        border: 1px solid #D9E4EE;
        border-radius: 10px;
        padding: 7px 9px;
        font-size: 12px;
    }}
    QFrame#decisionCardReady, QFrame#decisionCardReview, QFrame#decisionCardRisk, QFrame#decisionCardMuted {{
        border-radius: 12px;
        border: 1px solid #D9E2EC;
    }}
    QFrame#decisionCardReady {{
        background: #F4FBF6;
        border: 1px solid #C8E3CF;
    }}
    QFrame#decisionCardReview {{
        background: #FFF9EF;
        border: 1px solid #F0D9AF;
    }}
    QFrame#decisionCardRisk {{
        background: #FFF4F3;
        border: 1px solid #EDC6C1;
    }}
    QFrame#decisionCardMuted {{
        background: #F8FBFE;
        border: 1px solid #D9E2EC;
    }}
    QLabel#videoDecisionTitle {{
        color: {t["text_primary"]};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#videoDecisionDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QLabel#videoNextAction {{
        color: {t["text_secondary"]};
        background: #FBFDFF;
        border: 1px dashed #D7E2EE;
        border-radius: 10px;
        padding: 8px 10px;
        font-size: 12px;
    }}
    QFrame#currentTaskSummary {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FFFFFF,
            stop:1 #F4F8FC);
        border: 1px solid {t["card_shell_border"]};
        border-radius: 16px;
    }}
    QFrame#configSummaryCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F8FBFF,
            stop:1 #F3F8FF);
        border: 1px solid #CADBF6;
        border-radius: 16px;
    }}
    QFrame#toolbarGroup {{
        background: #FBFDFF;
        border: 1px solid #D9E2EC;
        border-radius: 14px;
    }}
    QFrame#toolbarGroupStrong {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F8FBFF,
            stop:1 #F3F8FF);
        border: 1px solid #CADBF6;
        border-radius: 14px;
    }}
    QFrame#agentCommandPanel {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FFFFFF,
            stop:1 #FBFDFF);
        border: 1px solid #D7E2EE;
        border-radius: 16px;
    }}
    QFrame#agentWorkspaceCard {{
        background: {t["bg_card"]};
        border: 1px solid #D7E2EE;
        border-radius: 16px;
    }}
    QFrame#agentActionStrip {{
        background: #F8FBFE;
        border: 1px solid #D7E2EE;
        border-radius: 14px;
    }}
    QFrame#agentOverviewCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #F8FBFF,
            stop:1 #F4F8FC);
        border: 1px solid {t["card_shell_border"]};
        border-radius: 16px;
    }}
    QLabel#agentNoticeInfo, QLabel#agentNoticeWarn, QLabel#agentNoticeDanger, QLabel#agentNoticeSuccess {{
        border-radius: 12px;
        padding: 9px 11px;
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#agentNoticeInfo {{
        background: #EAF2FF;
        color: #255CC4;
        border: 1px solid #BDD0F5;
    }}
    QLabel#agentNoticeWarn {{
        background: #FFF5E5;
        color: #9A6100;
        border: 1px solid #F0D6A2;
    }}
    QLabel#agentNoticeDanger {{
        background: #FDEDEC;
        color: #B93830;
        border: 1px solid #F2B8B3;
    }}
    QLabel#agentNoticeSuccess {{
        background: #EAF8EF;
        color: #216A39;
        border: 1px solid #B9DABD;
    }}
    QListWidget#agentStepsList, QListWidget#agentEventsList, QListWidget#agentConfirmList {{
        background: #FBFDFF;
        border: 1px solid #D9E2EC;
        border-radius: 12px;
        padding: 8px;
    }}
    QListWidget#agentPlanPreview {{
        background: #FBFDFF;
        border: 1px solid #D9E2EC;
        border-radius: 12px;
        padding: 8px;
    }}
    QListWidget#agentPlanPreview::item, QListWidget#agentConfirmList::item {{
        padding: 8px 6px;
        border-bottom: none;
    }}
    QFrame#agentEmptyState {{
        background: #F8FBFE;
        border: 1px dashed #D7E2EE;
        border-radius: 12px;
    }}
    QFrame#listEmptyState {{
        background: #F8FBFE;
        border: 1px dashed #D7E2EE;
        border-radius: 12px;
    }}
    QLabel#agentEmptyTitle {{
        color: {t["text_primary"]};
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#agentEmptyDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
        line-height: 1.5;
    }}
    QLabel#listEmptyTitle {{
        color: {t["text_primary"]};
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#listEmptyDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
        line-height: 1.5;
    }}
    QFrame#agentStepCardMuted, QFrame#agentStepCardInfo, QFrame#agentStepCardSuccess,
    QFrame#agentStepCardWarning, QFrame#agentStepCardDanger, QFrame#agentStepCardConfirm {{
        border-radius: 12px;
        border: 1px solid #D9E2EC;
        background: #FBFDFF;
    }}
    QFrame#agentStepCardInfo {{
        background: #F5F9FF;
        border: 1px solid #C9DAF7;
    }}
    QFrame#agentStepCardSuccess {{
        background: #F4FBF6;
        border: 1px solid #C8E3CF;
    }}
    QFrame#agentStepCardWarning, QFrame#agentStepCardConfirm {{
        background: #FFF9EF;
        border: 1px solid #F0D9AF;
    }}
    QFrame#agentStepCardDanger {{
        background: #FFF4F3;
        border: 1px solid #EDC6C1;
    }}
    QLabel#agentStepIndex {{
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        border-radius: 14px;
        background: #EEF4FA;
        border: 1px solid #D2DDEA;
        color: #52667F;
        font-size: 11px;
        font-weight: 700;
        qproperty-alignment: AlignCenter;
    }}
    QLabel#agentStepTitle {{
        color: {t["text_primary"]};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#agentStepDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QLabel#agentStepBadgeMuted, QLabel#agentStepBadgeInfo, QLabel#agentStepBadgeSuccess,
    QLabel#agentStepBadgeWarning, QLabel#agentStepBadgeDanger, QLabel#agentStepBadgeConfirm {{
        border-radius: 9px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#agentStepBadgeMuted {{
        background: {t["surface_muted_bg"]};
        color: {t["surface_muted_fg"]};
        border: 1px solid {t["surface_muted_border"]};
    }}
    QLabel#agentStepBadgeInfo {{
        background: {t["surface_info_bg"]};
        color: {t["surface_info_fg"]};
        border: 1px solid {t["surface_info_border"]};
    }}
    QLabel#agentStepBadgeSuccess {{
        background: {t["surface_success_bg"]};
        color: {t["surface_success_fg"]};
        border: 1px solid {t["surface_success_border"]};
    }}
    QLabel#agentStepBadgeWarning, QLabel#agentStepBadgeConfirm {{
        background: {t["surface_warning_bg"]};
        color: {t["surface_warning_fg"]};
        border: 1px solid {t["surface_warning_border"]};
    }}
    QLabel#agentStepBadgeDanger {{
        background: {t["surface_danger_bg"]};
        color: {t["surface_danger_fg"]};
        border: 1px solid {t["surface_danger_border"]};
    }}
    QFrame#agentConfirmDecisionCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FFF9EF,
            stop:1 #FFFDF8);
        border: 1px solid #F0D9AF;
        border-radius: 14px;
    }}
    QLabel#agentConfirmPill {{
        background: #FFF1CC;
        color: #9A6100;
        border: 1px solid #F0D6A2;
        border-radius: 10px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#agentConfirmState {{
        background: #FDEDEC;
        color: #B93830;
        border: 1px solid #F2B8B3;
        border-radius: 10px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#agentConfirmTitle {{
        color: {t["text_primary"]};
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#agentConfirmDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QFrame#agentConfirmImpact {{
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid #F0D9AF;
        border-radius: 11px;
    }}
    QLabel#agentConfirmImpactTitle {{
        color: #9A6100;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }}
    QLabel#agentConfirmImpactDetail {{
        color: {t["text_primary"]};
        font-size: 12px;
    }}
    QFrame#agentEventCardMuted, QFrame#agentEventCardInfo, QFrame#agentEventCardWarning, QFrame#agentEventCardDanger {{
        border-radius: 12px;
        border: 1px solid #D9E2EC;
        background: #FBFDFF;
    }}
    QFrame#agentEventCardInfo {{
        background: #F5F9FF;
        border: 1px solid #C9DAF7;
    }}
    QFrame#agentEventCardWarning {{
        background: #FFF9EF;
        border: 1px solid #F0D9AF;
    }}
    QFrame#agentEventCardDanger {{
        background: #FFF4F3;
        border: 1px solid #EDC6C1;
    }}
    QLabel#agentEventTitle {{
        color: {t["text_primary"]};
        font-size: 13px;
        font-weight: 700;
    }}
    QLabel#agentEventTime {{
        color: {t["text_muted"]};
        font-size: 11px;
    }}
    QLabel#agentEventDetail {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QLabel#agentEventBadgeMuted, QLabel#agentEventBadgeInfo, QLabel#agentEventBadgeWarning, QLabel#agentEventBadgeDanger {{
        border-radius: 9px;
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QLabel#agentEventBadgeMuted {{
        background: {t["surface_muted_bg"]};
        color: {t["surface_muted_fg"]};
        border: 1px solid {t["surface_muted_border"]};
    }}
    QLabel#agentEventBadgeInfo {{
        background: {t["surface_info_bg"]};
        color: {t["surface_info_fg"]};
        border: 1px solid {t["surface_info_border"]};
    }}
    QLabel#agentEventBadgeWarning {{
        background: {t["surface_warning_bg"]};
        color: {t["surface_warning_fg"]};
        border: 1px solid {t["surface_warning_border"]};
    }}
    QLabel#agentEventBadgeDanger {{
        background: {t["surface_danger_bg"]};
        color: {t["surface_danger_fg"]};
        border: 1px solid {t["surface_danger_border"]};
    }}
    QTextBrowser#agentResultSummary {{
        background: #FBFDFF;
        border: 1px solid #D9E2EC;
        border-radius: 12px;
        padding: 8px;
    }}
    QPlainTextEdit#agentTimeline {{
        background: #FBFDFF;
        border: 1px solid #D9E2EC;
        border-radius: 12px;
        padding: 10px;
    }}
    QFrame#videoAuditCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #FFFFFF,
            stop:1 #F5F9FD);
        border: 1px solid {t["card_shell_border"]};
        border-radius: 16px;
    }}
    QFrame#videoAuditCard:hover {{
        border: 1px solid {t["border_strong"]};
    }}
    QLabel#videoAuditTitle {{
        font-size: 15px;
        font-weight: 700;
        color: {t["text_primary"]};
    }}
    QLabel#videoAuditMeta {{
        color: {t["text_secondary"]};
        font-size: 12px;
    }}
    QLabel#videoAuditSection {{
        color: {t["text_muted"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }}
    QLabel#videoAuditUrl {{
        color: #9FC3FF;
        font-size: 12px;
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
        border: 1px solid #D7E2EE;
        border-radius: 16px;
        background: #F8FBFE;
        padding: 8px 10px;
        outline: 0;
    }}
    QListWidget#sideNav::item {{
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 7px 14px;
        margin: 0 2px;
        color: {t["text_secondary"]};
        min-height: 22px;
        text-align: center;
    }}
    QListWidget#sideNav::item:hover {{
        background: #EEF5FB;
        color: {t["text_primary"]};
    }}
    QListWidget#sideNav::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #EDF4FF,
            stop:1 #F6FAFF);
        color: #255CC4;
        border: 1px solid #BDD0F5;
        font-weight: 700;
    }}
    QListWidget#sideNav::item:selected:active, QListWidget#sideNav::item:selected:!active {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #EDF4FF,
            stop:1 #F6FAFF);
        color: #255CC4;
        border: 1px solid #BDD0F5;
    }}
    QLabel#appTitle {{
        font-size: 26px;
        font-weight: 800;
        color: {t["text_primary"]};
        letter-spacing: 0.4px;
    }}
    QLabel#statusBadge {{
        font-size: 12px;
        font-weight: 700;
        color: #35506E;
        background: #EEF4FA;
        border: 1px solid #D0DDEA;
        padding: 6px 12px;
        border-radius: 14px;
    }}
    QLabel#sectionTitle {{
        font-size: 16px;
        font-weight: 800;
        color: {t["text_primary"]};
    }}
    QPushButton[role="agentTemplate"] {{
        background: #F7FAFD;
        color: #334E68;
        border: 1px solid #D5E0EB;
        border-radius: 11px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton[role="agentTemplate"]:hover {{
        background: #EEF5FB;
        border: 1px solid #BFD1E2;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {t["border_default"]};
        min-height: 32px;
        border-radius: 6px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t["border_strong"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        border: none;
        height: 0px;
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
