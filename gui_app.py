#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import concurrent.futures
import html
import json
import multiprocessing
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from app.agent.llm_planner import provider_model_suggestions, test_llm_connection
from app.core.download_workspace_service import resolve_download_session_pointers
from app.core.task_service import TaskStore
from app.gui.agent_bridge import AgentBridge
import ui_theme


SETTINGS_FILE = Path(__file__).with_name("gui_settings.local.json")
LEGACY_SETTINGS_FILE = Path(__file__).with_name("gui_settings.json")


@dataclass
class QueueTask:
    args: list[str]
    task_name: str
    workdir: str
    run_id: str
    download_dir: str
    cookies_browser: str = ""
    cookies_file: str = ""
    yt_extra_args: str = ""
    download_mode: str = "video"
    include_audio: bool = True
    video_container: str = "auto"
    max_height: str = "1080"
    audio_format: str = "mp3"
    audio_quality: int = 2
    clean_video: bool = False
    sponsorblock_remove: str = ""
    concurrent_videos: int = 3
    concurrent_fragments: int = 8
    download_session_name: str = ""
    status: str = "pending"
    exit_code: Optional[int] = None
    selected_count: int = 0
    origin: str = "manual"
    agent_task_id: str = ""


class RunConfig(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        if getattr(sys, "frozen", False):
            # 打包后 sys.executable 指向 GUI exe，本身不是 python 解释器。
            self.python_exe = shutil.which("python") or shutil.which("py") or ""
            self.script_path = str(Path(sys.executable).with_name("youtube_batch.py"))
        else:
            self.python_exe = sys.executable or "python"
            self.script_path = str(Path(__file__).with_name("youtube_batch.py"))


class ProcessRunner(QtCore.QObject):
    output_received = QtCore.Signal(str)
    finished = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.proc = QtCore.QProcess(self)
        env = QtCore.QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.proc.setProcessEnvironment(env)
        self.proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._on_ready)
        self.proc.finished.connect(self._on_finished)

    def start(self, program: str, args: list[str], working_dir: Optional[str] = None) -> None:
        if working_dir:
            self.proc.setWorkingDirectory(working_dir)
        self.proc.start(program, args)

    def kill(self) -> None:
        if self.proc.state() != QtCore.QProcess.NotRunning:
            self.proc.kill()

    @QtCore.Slot()
    def _on_ready(self) -> None:
        data = self.proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        if text:
            self.output_received.emit(text)

    @QtCore.Slot(int, QtCore.QProcess.ExitStatus)
    def _on_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        self.finished.emit(code)


class CsvPreviewModel(QtCore.QAbstractTableModel):
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []

    def load_csv(self, path: Path, max_rows: int = 200) -> None:
        self.beginResetModel()
        self.headers = []
        self.rows = []
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                for i, row in enumerate(reader):
                    if i == 0:
                        self.headers = row
                    else:
                        self.rows.append(row)
                    if i >= max_rows:
                        break
        except Exception:
            self.headers = []
            self.rows = []
        finally:
            self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # type: ignore[override]
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole):  # type: ignore[override]
        if not index.isValid():
            return None
        if role == QtCore.Qt.DisplayRole:
            r, c = index.row(), index.column()
            try:
                return self.rows[r][c]
            except Exception:
                return ""
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole):  # type: ignore[override]
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            try:
                return self.headers[section]
            except Exception:
                return ""
        return super().headerData(section, orientation, role)


class NoWheelComboBox(QtWidgets.QComboBox):
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # type: ignore[override]
        event.ignore()


class DownloadToast(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._action: Optional[Callable[[], None]] = None
        self.setObjectName("downloadToast")
        self.setWindowFlags(
            QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            """
            QFrame#downloadToast {
                background: #1F1F1F;
                border: 1px solid #3A3A3A;
                border-radius: 12px;
            }
            QLabel#toastTitle {
                color: #F1F1F1;
                font-weight: 700;
                font-size: 13px;
            }
            QLabel#toastDetail {
                color: #B8B8B8;
                font-size: 12px;
            }
            QPushButton#toastAction {
                background: #FF3B30;
                color: #FFFFFF;
                border: 1px solid #D73027;
                border-radius: 8px;
                padding: 4px 10px;
                font-weight: 600;
            }
            QPushButton#toastAction:hover {
                background: #E3372D;
            }
            """
        )
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        self.lbl_title = QtWidgets.QLabel("")
        self.lbl_title.setObjectName("toastTitle")
        self.lbl_detail = QtWidgets.QLabel("")
        self.lbl_detail.setObjectName("toastDetail")
        self.btn_action = QtWidgets.QPushButton("")
        self.btn_action.setObjectName("toastAction")
        self.btn_action.clicked.connect(self._on_action_clicked)
        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_detail)
        lay.addWidget(self.btn_action, 0, QtCore.Qt.AlignRight)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_toast(
        self,
        title: str,
        detail: str = "",
        action_text: str = "",
        action: Optional[Callable[[], None]] = None,
        duration_ms: int = 4500,
    ) -> None:
        self._action = action
        self.lbl_title.setText(title.strip() or "任务通知")
        self.lbl_detail.setText(detail.strip())
        has_action = bool(action_text.strip() and action is not None)
        self.btn_action.setVisible(has_action)
        if has_action:
            self.btn_action.setText(action_text.strip())
        self.adjustSize()
        self._reposition_to_parent_corner()
        self.show()
        self.raise_()
        self.timer.start(max(1200, int(duration_ms or 4500)))

    def _on_action_clicked(self) -> None:
        self.hide()
        if self._action is not None:
            self._action()

    def _reposition_to_parent_corner(self) -> None:
        p = self.parentWidget()
        if p is None:
            return
        margin = 18
        x = max(margin, p.width() - self.width() - margin)
        y = max(margin, p.height() - self.height() - margin - 28)
        self.move(x, y)

class _AgentConnectionTestWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)
    error = QtCore.Signal(str)

    def __init__(self, defaults: dict[str, Any]) -> None:
        super().__init__()
        self.defaults = defaults

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.finished.emit(test_llm_connection(self.defaults))
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QtWidgets.QMainWindow):
    thumb_ready = QtCore.Signal(str, bytes)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YouTube 视频下载工具 (yt-dlp)")
        self.resize(1560, 980)
        self.setMinimumSize(1380, 860)
        self.cfg = RunConfig()
        self.runner = ProcessRunner(self)
        self.runner.output_received.connect(self.append_log)
        self.runner.finished.connect(self.on_finished)
        self.maint_proc = QtCore.QProcess(self)
        self.maint_proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.maint_proc.readyReadStandardOutput.connect(self._on_maint_ready)
        self.maint_proc.finished.connect(self._on_maint_finished)
        self.maint_action_name: str = ""
        self.tool_check_proc = QtCore.QProcess(self)
        self.tool_check_proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.tool_check_proc.readyReadStandardOutput.connect(self._on_tool_check_ready)
        self.tool_check_proc.finished.connect(self._on_tool_check_finished)
        self._tool_check_output = ""

        self.task_queue: list[QueueTask] = []
        self.active_queue_index: Optional[int] = None
        self.active_workdir: Optional[str] = None
        self.active_run_kind: str = "adhoc"  # adhoc | filter_queue | download_queue
        self.download_all_mode: bool = False
        self.user_stopped = False
        self.pause_requested = False
        self._log_line_buffer = ""
        self._stage_step = 0
        self._active_has_download = False
        self._queue_total = 0
        self._queue_done = 0
        self._current_video_label = "-"
        self._active_task_widgets: dict[str, dict[str, QtWidgets.QWidget]] = {}
        self._active_task_order: list[str] = []
        self._taskno_to_vid: dict[int, str] = {}
        self._vid_to_label: dict[str, str] = {}
        self.video_rows: list[dict] = []
        self.video_view_indices: list[int] = []
        self.video_page = 1
        self.video_page_size = 10
        self._thumb_cache: dict[str, QtGui.QPixmap] = {}
        self._thumb_fetching: set[str] = set()
        self._thumb_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self._thumb_lazy_enabled = False
        self._thumb_lazy_timer = QtCore.QTimer(self)
        self._thumb_lazy_timer.setSingleShot(True)
        self._thumb_lazy_timer.setInterval(120)
        self._thumb_lazy_timer.timeout.connect(self._load_visible_thumbs)
        self.thumb_ready.connect(self._on_thumb_ready)
        self._toast = DownloadToast(self)
        self._last_download_output_dir = ""
        self.downloaded_records: list[dict] = []
        self.agent_bridge = AgentBridge(self)
        self._agent_task_state: dict[str, dict] = {}
        self._agent_last_task_id: str = ""
        self._agent_last_task_workdir: str = ""
        self._agent_pending_confirmation = False
        self._agent_result_link_targets: dict[str, str] = {}
        self._queue_visible_indices: list[int] = []
        self._agent_test_thread: Optional[QtCore.QThread] = None
        self._agent_test_worker: Optional[_AgentConnectionTestWorker] = None

        self._init_ui()
        self._connect_agent_bridge()
        self._apply_ui_theme()
        self._load_settings()
        self.le_query_text.clear()
        QtCore.QTimer.singleShot(1200, self._check_tools_after_maint)

    def _apply_ui_theme(self) -> None:
        self.setStyleSheet(ui_theme.build_main_stylesheet())

    def _init_ui(self) -> None:
        w = QtWidgets.QWidget()
        w.setObjectName("root")
        self.setCentralWidget(w)
        layout = QtWidgets.QVBoxLayout(w)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(12)

        title_row = QtWidgets.QHBoxLayout()
        title_col = QtWidgets.QVBoxLayout()
        title_col.setSpacing(2)
        title = QtWidgets.QLabel("YouTube 下载控制台")
        title.setObjectName("appTitle")
        subtitle = QtWidgets.QLabel("面向批量筛选、下载与 Agent 编排的桌面工作台")
        subtitle.setObjectName("appSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        title_row.addLayout(title_col)
        title_row.addStretch()
        self.lbl_progress_status = QtWidgets.QLabel("就绪")
        self.lbl_progress_status.setObjectName("statusBadge")
        self.lbl_progress_status.setMaximumWidth(680)
        title_row.addWidget(self.lbl_progress_status, 0, QtCore.Qt.AlignVCenter)
        layout.addLayout(title_row)

        progress_box = QtWidgets.QGroupBox("实时进度")
        progress_box.setObjectName("mini")
        progress_box.setCheckable(True)
        progress_box.setChecked(False)
        progress_box.toggled.connect(self._set_progress_panel_expanded)
        self.progress_box = progress_box
        progress_layout = QtWidgets.QVBoxLayout(progress_box)
        progress_layout.setContentsMargins(10, 8, 10, 8)
        progress_layout.setSpacing(6)
        row_meta = QtWidgets.QHBoxLayout()
        self.lbl_progress_stage_title = QtWidgets.QLabel("元数据抓取")
        row_meta.addWidget(self.lbl_progress_stage_title)
        self.progress_stage = QtWidgets.QProgressBar()
        self.progress_stage.setRange(0, 100)
        self.progress_stage.setValue(0)
        self.progress_stage.setFormat("待开始")
        row_meta.addWidget(self.progress_stage, 1)
        progress_layout.addLayout(row_meta)
        row_queue = QtWidgets.QHBoxLayout()
        self.lbl_progress_queue_title = QtWidgets.QLabel("队列进度")
        row_queue.addWidget(self.lbl_progress_queue_title)
        self.progress_queue = QtWidgets.QProgressBar()
        self.progress_queue.setRange(0, 100)
        self.progress_queue.setValue(0)
        self.progress_queue.setFormat("待开始")
        row_queue.addWidget(self.progress_queue, 1)
        progress_layout.addLayout(row_queue)
        self.lbl_queue_metrics = QtWidgets.QLabel("队列: 0/0")
        self.lbl_queue_metrics.setObjectName("hint")
        progress_layout.addWidget(self.lbl_queue_metrics)
        row_current = QtWidgets.QHBoxLayout()
        self.lbl_progress_current_title = QtWidgets.QLabel("当前视频")
        row_current.addWidget(self.lbl_progress_current_title)
        self.progress_current = QtWidgets.QProgressBar()
        self.progress_current.setRange(0, 100)
        self.progress_current.setValue(0)
        self.progress_current.setFormat("待开始")
        row_current.addWidget(self.progress_current, 1)
        progress_layout.addLayout(row_current)
        self.lbl_download_metrics = QtWidgets.QLabel("当前视频: - | 已下载: - / - | 速度: -")
        self.lbl_download_metrics.setObjectName("hint")
        progress_layout.addWidget(self.lbl_download_metrics)
        self.box_active_tasks = QtWidgets.QGroupBox("并发任务进度")
        self.box_active_tasks.setObjectName("mini")
        active_layout = QtWidgets.QGridLayout(self.box_active_tasks)
        active_layout.setContentsMargins(8, 8, 8, 8)
        active_layout.setHorizontalSpacing(10)
        active_layout.setVerticalSpacing(8)
        self.grid_active_tasks = active_layout
        progress_layout.addWidget(self.box_active_tasks)
        self._progress_detail_widgets = [
            self.lbl_progress_stage_title,
            self.progress_stage,
            self.lbl_progress_queue_title,
            self.progress_queue,
            self.lbl_queue_metrics,
            self.lbl_progress_current_title,
            self.progress_current,
            self.lbl_download_metrics,
            self.box_active_tasks,
        ]
        layout.addWidget(progress_box)
        self._set_progress_panel_expanded(False)

        body_row = QtWidgets.QVBoxLayout()
        body_row.setSpacing(10)
        layout.addLayout(body_row, 1)

        nav_box = QtWidgets.QGroupBox("工作区")
        nav_box.setObjectName("mini")
        nav_box.setMaximumHeight(110)
        nav_layout = QtWidgets.QHBoxLayout(nav_box)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(6)
        self.side_nav = QtWidgets.QListWidget()
        self.side_nav.setObjectName("sideNav")
        self.side_nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.side_nav.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.side_nav.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.side_nav.setFlow(QtWidgets.QListView.LeftToRight)
        self.side_nav.setMovement(QtWidgets.QListView.Static)
        self.side_nav.setResizeMode(QtWidgets.QListView.Adjust)
        self.side_nav.setSelectionRectVisible(False)
        self.side_nav.setSpacing(6)
        self.side_nav.setWrapping(False)
        self.side_nav.setMaximumHeight(64)
        self.side_nav.addItems(["配置", "队列", "日志", "已下载", "Agent"])
        nav_metrics = self.side_nav.fontMetrics()
        for idx in range(self.side_nav.count()):
            item = self.side_nav.item(idx)
            item_width = max(116, nav_metrics.horizontalAdvance(item.text()) + 32)
            item.setSizeHint(QtCore.QSize(item_width, 42))
        self.side_nav.currentRowChanged.connect(self._on_side_nav_changed)
        nav_layout.addWidget(self.side_nav, 1)
        body_row.addWidget(nav_box)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().hide()
        self.tabs = tabs
        body_row.addWidget(tabs, 1)

        tab_config = QtWidgets.QWidget()
        tab_config.setObjectName("configTabPage")
        tab_config_outer = QtWidgets.QVBoxLayout(tab_config)
        tab_config_outer.setContentsMargins(8, 8, 8, 8)
        cfg_scroll = QtWidgets.QScrollArea()
        cfg_scroll.setObjectName("configScroll")
        cfg_scroll.setWidgetResizable(True)
        cfg_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        tab_config_outer.addWidget(cfg_scroll)
        cfg_content = QtWidgets.QWidget()
        cfg_content.setObjectName("configScrollContent")
        cfg_scroll.setWidget(cfg_content)
        tab_config_layout = QtWidgets.QVBoxLayout(cfg_content)
        tab_config_layout.setContentsMargins(4, 4, 4, 8)
        tab_config_layout.setSpacing(10)

        hero_banner = QtWidgets.QFrame()
        hero_banner.setObjectName("heroBanner")
        hero_layout = QtWidgets.QVBoxLayout(hero_banner)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(6)
        hero_eyebrow = QtWidgets.QLabel("WORKFLOW")
        hero_eyebrow.setObjectName("heroEyebrow")
        hero_title = QtWidgets.QLabel("先筛选，再确认，再下载")
        hero_title.setObjectName("heroTitle")
        hero_desc = QtWidgets.QLabel(
            "把任务拆成信息收集、下载策略、队列执行三段，能更清楚地看到候选视频、可下载结果和 Agent 决策过程。"
        )
        hero_desc.setObjectName("heroDescription")
        hero_desc.setWordWrap(True)
        hero_layout.addWidget(hero_eyebrow)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_desc)
        tab_config_layout.addWidget(hero_banner)

        box_filter = QtWidgets.QGroupBox("步骤 A · 筛选条件")
        box_filter.setObjectName("surfacePanel")
        box_filter_layout = QtWidgets.QVBoxLayout(box_filter)
        box_filter_layout.setContentsMargins(6, 6, 6, 6)
        box_filter_layout.setSpacing(10)

        filter_common_box = QtWidgets.QGroupBox("常用设置")
        filter_common_box.setObjectName("mini")
        filter_common_layout = QtWidgets.QFormLayout(filter_common_box)
        filter_common_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        filter_common_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        filter_common_layout.setHorizontalSpacing(14)
        filter_common_layout.setVerticalSpacing(9)

        filter_adv_box = QtWidgets.QGroupBox("高级设置")
        filter_adv_box.setObjectName("mini")
        filter_adv_box.setCheckable(True)
        filter_adv_box.setChecked(False)
        filter_adv_outer = QtWidgets.QVBoxLayout(filter_adv_box)
        filter_adv_outer.setContentsMargins(8, 8, 8, 8)
        filter_adv_outer.setSpacing(8)
        self.filter_adv_body = QtWidgets.QWidget()
        filter_adv_layout = QtWidgets.QFormLayout(self.filter_adv_body)
        filter_adv_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        filter_adv_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        filter_adv_layout.setHorizontalSpacing(14)
        filter_adv_layout.setVerticalSpacing(9)
        filter_adv_outer.addWidget(self.filter_adv_body)
        filter_adv_box.toggled.connect(self.filter_adv_body.setVisible)
        self.filter_adv_body.setVisible(False)

        agent_adv_box = QtWidgets.QGroupBox("Agent / LLM 设置")
        agent_adv_box.setObjectName("mini")
        agent_adv_box.setCheckable(True)
        agent_adv_box.setChecked(False)
        agent_adv_outer = QtWidgets.QVBoxLayout(agent_adv_box)
        agent_adv_outer.setContentsMargins(8, 8, 8, 8)
        agent_adv_outer.setSpacing(8)
        self.agent_adv_body = QtWidgets.QWidget()
        agent_adv_layout = QtWidgets.QFormLayout(self.agent_adv_body)
        agent_adv_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        agent_adv_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        agent_adv_layout.setHorizontalSpacing(14)
        agent_adv_layout.setVerticalSpacing(9)
        agent_adv_outer.addWidget(self.agent_adv_body)
        agent_adv_box.toggled.connect(self.agent_adv_body.setVisible)
        self.agent_adv_body.setVisible(False)

        box_download = QtWidgets.QGroupBox("步骤 B · 下载策略")
        box_download.setObjectName("surfacePanel")
        box_download_layout = QtWidgets.QVBoxLayout(box_download)
        box_download_layout.setContentsMargins(6, 6, 6, 6)
        box_download_layout.setSpacing(10)

        download_common_box = QtWidgets.QGroupBox("常用设置")
        download_common_box.setObjectName("mini")
        download_common_layout = QtWidgets.QFormLayout(download_common_box)
        download_common_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        download_common_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        download_common_layout.setHorizontalSpacing(14)
        download_common_layout.setVerticalSpacing(9)

        download_adv_box = QtWidgets.QGroupBox("高级设置")
        download_adv_box.setObjectName("mini")
        download_adv_box.setCheckable(True)
        download_adv_box.setChecked(False)
        download_adv_outer = QtWidgets.QVBoxLayout(download_adv_box)
        download_adv_outer.setContentsMargins(8, 8, 8, 8)
        download_adv_outer.setSpacing(8)
        self.download_adv_body = QtWidgets.QWidget()
        download_adv_layout = QtWidgets.QFormLayout(self.download_adv_body)
        download_adv_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        download_adv_layout.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        download_adv_layout.setHorizontalSpacing(14)
        download_adv_layout.setVerticalSpacing(9)
        download_adv_outer.addWidget(self.download_adv_body)
        download_adv_box.toggled.connect(self.download_adv_body.setVisible)
        self.download_adv_body.setVisible(False)

        box_queue = QtWidgets.QGroupBox("步骤 C · 加入队列")
        box_queue.setObjectName("surfacePanel")
        form_queue = QtWidgets.QFormLayout(box_queue)
        form_queue.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_queue.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_queue.setHorizontalSpacing(14)
        form_queue.setVerticalSpacing(9)

        self.le_query_text = QtWidgets.QLineEdit()
        self.le_query_text.setPlaceholderText("例如：Python async tutorial / music live performance")
        filter_common_layout.addRow("查询内容:", self.le_query_text)

        self.cb_workdir = NoWheelComboBox()
        self.cb_workdir.setEditable(True)
        self.cb_workdir.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_workdir.setToolTip("用于保存筛选阶段 01~05 的中间结果文件。")
        btn_w = QtWidgets.QPushButton("选择...")
        btn_w.clicked.connect(lambda: self._pick_dir_combo(self.cb_workdir))
        hw = QtWidgets.QHBoxLayout()
        hw.addWidget(self.cb_workdir)
        hw.addWidget(btn_w)
        filter_common_layout.addRow("视频信息目录:", self._wrap(hw))
        lbl_work_help = QtWidgets.QLabel("用途: 每次任务会创建独立 run 子目录，保存候选清单、筛选结果和可下载 URL，不直接存放视频媒体文件。")
        lbl_work_help.setWordWrap(True)
        lbl_work_help.setObjectName("hint")
        filter_common_layout.addRow("", lbl_work_help)

        self.cb_downloaddir = NoWheelComboBox()
        self.cb_downloaddir.setEditable(True)
        self.cb_downloaddir.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_downloaddir.setToolTip("用于保存最终下载的视频/音频文件。")
        btn_d = QtWidgets.QPushButton("选择...")
        btn_d.clicked.connect(lambda: self._pick_dir_combo(self.cb_downloaddir))
        hd = QtWidgets.QHBoxLayout()
        hd.addWidget(self.cb_downloaddir)
        hd.addWidget(btn_d)
        filter_common_layout.addRow("下载目录:", self._wrap(hd))

        self.spin_search_limit = QtWidgets.QSpinBox()
        self.spin_search_limit.setRange(1, 200)
        self.spin_search_limit.setValue(50)
        filter_common_layout.addRow("视频收集条数:", self.spin_search_limit)
        self.spin_metadata_workers = QtWidgets.QSpinBox()
        self.spin_metadata_workers.setRange(1, 16)
        self.spin_metadata_workers.setValue(4)
        filter_adv_layout.addRow("信息抓取并发:", self.spin_metadata_workers)

        self.spin_min_duration = QtWidgets.QSpinBox()
        self.spin_min_duration.setRange(0, 7200)
        self.spin_min_duration.setValue(120)
        filter_common_layout.addRow("最短时长(秒):", self.spin_min_duration)

        self.spin_year_from = QtWidgets.QSpinBox()
        self.spin_year_from.setRange(1990, 2100)
        self.spin_year_from.setValue(2020)
        self.chk_year_from = QtWidgets.QCheckBox("启用")
        hyf = QtWidgets.QHBoxLayout()
        hyf.addWidget(self.spin_year_from)
        hyf.addWidget(self.chk_year_from)
        filter_common_layout.addRow("上传年 >=", self._wrap(hyf))

        self.spin_year_to = QtWidgets.QSpinBox()
        self.spin_year_to.setRange(1990, 2100)
        self.spin_year_to.setValue(2026)
        self.chk_year_to = QtWidgets.QCheckBox("启用")
        hyt = QtWidgets.QHBoxLayout()
        hyt.addWidget(self.spin_year_to)
        hyt.addWidget(self.chk_year_to)
        filter_common_layout.addRow("上传年 <=", self._wrap(hyt))

        self.combo_cookies_browser = NoWheelComboBox()
        self.combo_cookies_browser.setEditable(True)
        self.combo_cookies_browser.addItems(["", "chrome", "edge", "firefox"])
        filter_adv_layout.addRow("cookies 浏览器:", self.combo_cookies_browser)

        self.le_cookies_file = QtWidgets.QLineEdit()
        btn_c = QtWidgets.QPushButton("选择...")
        btn_c.clicked.connect(lambda: self._pick_file(self.le_cookies_file, "选择 cookies 文件 (*.*)"))
        hc = QtWidgets.QHBoxLayout()
        hc.addWidget(self.le_cookies_file)
        hc.addWidget(btn_c)
        filter_adv_layout.addRow("cookies 文件:", self._wrap(hc))

        self.le_yt_extra_args = QtWidgets.QLineEdit()
        self.le_yt_extra_args.setPlaceholderText("--proxy http://127.0.0.1:7890 --retries 20")
        filter_adv_layout.addRow("高级 yt-dlp 参数:", self.le_yt_extra_args)

        self.chk_full_csv = QtWidgets.QCheckBox("导出 04_all_scored.csv（全量评分）")
        filter_adv_layout.addRow("", self.chk_full_csv)

        self.combo_agent_provider = NoWheelComboBox()
        self.combo_agent_provider.setEditable(True)
        self.combo_agent_provider.addItems(["openai", "openrouter", "deepseek", "moonshot", "aliyun_bailian", "custom"])
        self.combo_agent_provider.currentTextChanged.connect(self._on_agent_provider_changed)
        agent_adv_layout.addRow("Agent Provider:", self.combo_agent_provider)

        self.le_agent_base_url = QtWidgets.QLineEdit()
        self.le_agent_base_url.setPlaceholderText("例如: https://api.openai.com/v1")
        agent_adv_layout.addRow("Base URL:", self.le_agent_base_url)

        self.le_agent_model = QtWidgets.QLineEdit()
        self.le_agent_model.setPlaceholderText("例如: gpt-5.4 / deepseek-chat / kimi-k2")
        agent_adv_layout.addRow("Model:", self.le_agent_model)
        self.lbl_agent_model_suggestion = QtWidgets.QLabel("建议模型: -")
        self.lbl_agent_model_suggestion.setObjectName("hint")
        self.lbl_agent_model_suggestion.setWordWrap(True)
        agent_adv_layout.addRow("", self.lbl_agent_model_suggestion)

        self.le_agent_api_key = QtWidgets.QLineEdit()
        self.le_agent_api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self.le_agent_api_key.setPlaceholderText("输入 Agent API Key")
        self.le_agent_api_key.setClearButtonEnabled(True)
        agent_adv_layout.addRow("API Key:", self.le_agent_api_key)

        self.chk_agent_show_api_key = QtWidgets.QCheckBox("显示 API Key")
        self.chk_agent_show_api_key.toggled.connect(self._toggle_agent_api_key_visibility)
        agent_adv_layout.addRow("", self.chk_agent_show_api_key)

        lbl_agent_runtime_help = QtWidgets.QLabel(
            "Agent 使用 OpenAI-compatible 接口规划任务。provider、Base URL、model、API Key 均由用户指定。"
        )
        lbl_agent_runtime_help.setWordWrap(True)
        lbl_agent_runtime_help.setObjectName("hint")
        agent_adv_layout.addRow("", lbl_agent_runtime_help)
        self.combo_agent_provider.setCurrentText("openai")
        self._on_agent_provider_changed(self.combo_agent_provider.currentText())
        self._update_agent_runtime_hint()

        self.combo_download_mode = NoWheelComboBox()
        self.combo_download_mode.addItems(["video", "audio"])
        download_common_layout.addRow("下载模式:", self.combo_download_mode)

        self.chk_include_audio = QtWidgets.QCheckBox("视频模式同时下载并合并音频")
        self.chk_include_audio.setChecked(True)
        download_common_layout.addRow("", self.chk_include_audio)

        self.combo_video_container = NoWheelComboBox()
        self.combo_video_container.addItems(["auto", "mp4", "mkv", "webm"])
        download_common_layout.addRow("视频封装格式:", self.combo_video_container)

        self.combo_max_height = NoWheelComboBox()
        self.combo_max_height.addItems(["144", "240", "360", "480", "720", "1080", "1440", "2160", "4320"])
        self.combo_max_height.setCurrentText("1080")
        self.combo_max_height.setToolTip("固定下载分辨率（按所选分辨率下载）。")
        download_common_layout.addRow("下载分辨率:", self.combo_max_height)

        self.combo_audio_format = NoWheelComboBox()
        self.combo_audio_format.addItems(["best", "mp3", "m4a", "opus", "wav", "flac"])
        download_common_layout.addRow("音频格式(audio):", self.combo_audio_format)

        self.spin_audio_quality = QtWidgets.QSpinBox()
        self.spin_audio_quality.setRange(0, 10)
        self.spin_audio_quality.setValue(2)
        download_common_layout.addRow("音频质量 0-10:", self.spin_audio_quality)
        self.spin_concurrent_videos = QtWidgets.QSpinBox()
        self.spin_concurrent_videos.setRange(1, 8)
        self.spin_concurrent_videos.setValue(3)
        download_adv_layout.addRow("并发视频数:", self.spin_concurrent_videos)
        self.spin_concurrent_fragments = QtWidgets.QSpinBox()
        self.spin_concurrent_fragments.setRange(1, 16)
        self.spin_concurrent_fragments.setValue(8)
        download_adv_layout.addRow("单视频分片并发:", self.spin_concurrent_fragments)

        self.chk_clean_video = QtWidgets.QCheckBox("纯净模式（移除广告/赞助片段）")
        self.chk_clean_video.setToolTip("仅对 YouTube 生效：通过 SponsorBlock 移除指定片段。")
        download_adv_layout.addRow("", self.chk_clean_video)
        self.sb_checks: dict[str, QtWidgets.QCheckBox] = {}
        sb_widget = QtWidgets.QWidget()
        sb_layout = QtWidgets.QGridLayout(sb_widget)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setHorizontalSpacing(10)
        sb_layout.setVerticalSpacing(6)
        sb_items = [
            ("sponsor", "赞助"),
            ("selfpromo", "自我推广"),
            ("intro", "片头"),
            ("outro", "片尾"),
            ("interaction", "互动提醒"),
            ("music_offtopic", "非主题音乐"),
        ]
        for i, (key, text) in enumerate(sb_items):
            chk = QtWidgets.QCheckBox(text)
            chk.setChecked(key in {"sponsor", "selfpromo", "intro", "outro", "interaction"})
            self.sb_checks[key] = chk
            sb_layout.addWidget(chk, i // 3, i % 3)
        download_adv_layout.addRow("移除类别:", sb_widget)
        self.chk_clean_video.toggled.connect(sb_widget.setEnabled)
        sb_widget.setEnabled(False)

        box_filter_layout.addWidget(filter_common_box)
        box_filter_layout.addWidget(filter_adv_box)
        box_filter_layout.addWidget(agent_adv_box)
        box_filter_layout.addStretch(1)

        box_download_layout.addWidget(download_common_box)
        box_download_layout.addWidget(download_adv_box)
        box_download_layout.addStretch(1)

        qv = QtWidgets.QVBoxLayout()
        qv.setContentsMargins(14, 12, 14, 12)
        qv.setSpacing(10)
        lbl_queue_help = QtWidgets.QLabel("确认步骤 A/B 设置后，启动筛选任务并在队列页执行下载。")
        lbl_queue_help.setObjectName("hint")
        lbl_queue_help.setWordWrap(True)
        qv.addWidget(lbl_queue_help)
        config_summary = QtWidgets.QFrame()
        config_summary.setObjectName("configSummaryCard")
        config_summary_layout = QtWidgets.QVBoxLayout(config_summary)
        config_summary_layout.setContentsMargins(12, 12, 12, 12)
        config_summary_layout.setSpacing(6)
        lbl_config_summary_title = QtWidgets.QLabel("当前任务摘要")
        lbl_config_summary_title.setObjectName("sectionTitle")
        self.lbl_config_summary_query = QtWidgets.QLabel("查询: -")
        self.lbl_config_summary_query.setObjectName("hint")
        self.lbl_config_summary_paths = QtWidgets.QLabel("信息目录 / 下载目录: -")
        self.lbl_config_summary_paths.setObjectName("hint")
        self.lbl_config_summary_download = QtWidgets.QLabel("下载策略: -")
        self.lbl_config_summary_download.setObjectName("hint")
        self.lbl_config_summary_flags = QtWidgets.QLabel("执行边界: -")
        self.lbl_config_summary_flags.setObjectName("hint")
        config_summary_layout.addWidget(lbl_config_summary_title)
        for summary_label in [
            self.lbl_config_summary_query,
            self.lbl_config_summary_paths,
            self.lbl_config_summary_download,
            self.lbl_config_summary_flags,
        ]:
            summary_label.setWordWrap(True)
            summary_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            config_summary_layout.addWidget(summary_label)
        qv.addWidget(config_summary)
        self.btn_enqueue = QtWidgets.QPushButton("创建并启动筛选任务")
        self.btn_enqueue.setObjectName("primary")
        self.btn_enqueue.setToolTip("创建新筛选任务并立即启动。")
        self.btn_enqueue.clicked.connect(self._enqueue_and_start)
        qv.addWidget(self.btn_enqueue)
        self.btn_enqueue_only = QtWidgets.QPushButton("仅加入队列，稍后执行")
        self.btn_enqueue_only.setObjectName("secondary")
        self.btn_enqueue_only.setToolTip("只创建任务，不立即启动。")
        self.btn_enqueue_only.clicked.connect(self._enqueue)
        qv.addWidget(self.btn_enqueue_only)
        row_open = QtWidgets.QHBoxLayout()
        self.btn_open_work = QtWidgets.QPushButton("打开信息目录")
        self.btn_open_work.setObjectName("secondary")
        self.btn_open_work.clicked.connect(lambda: self._open_dir(self._combo_text(self.cb_workdir)))
        self.btn_open_down = QtWidgets.QPushButton("打开下载目录")
        self.btn_open_down.setObjectName("secondary")
        self.btn_open_down.clicked.connect(lambda: self._open_dir(self._combo_text(self.cb_downloaddir)))
        row_open.addWidget(self.btn_open_work)
        row_open.addWidget(self.btn_open_down)
        qv.addLayout(row_open)
        qv.addStretch(1)
        queue_panel = QtWidgets.QWidget()
        queue_panel.setLayout(qv)
        form_queue.addRow("", queue_panel)

        self._tune_form_labels(filter_common_layout, 176)
        self._tune_form_labels(filter_adv_layout, 176)
        self._tune_form_labels(agent_adv_layout, 176)
        self._tune_form_labels(download_common_layout, 176)
        self._tune_form_labels(download_adv_layout, 176)
        self._tune_form_labels(form_queue, 176)

        maint_box = QtWidgets.QGroupBox("工具维护 (yt-dlp / ffmpeg)")
        maint_box.setObjectName("surfacePanel")
        maint_layout = QtWidgets.QGridLayout(maint_box)
        self.lbl_tools_summary = QtWidgets.QLabel("状态: 未检查")
        self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("neutral"))
        self.lbl_ytdlp_ver = QtWidgets.QLabel("yt-dlp 当前: - | 最新: - | 更新状态: 未检查")
        self.lbl_ffmpeg_ver = QtWidgets.QLabel("ffmpeg 当前: - | 最新: - | 更新状态: 未检查")
        self.lbl_tools_checked_at = QtWidgets.QLabel("最后检查: -")
        self.lbl_tools_checked_at.setStyleSheet(ui_theme.muted_text_style())
        self.btn_check_tools = QtWidgets.QPushButton("检查版本")
        self.btn_check_tools.clicked.connect(self.on_check_tools)
        self.btn_update_ytdlp = QtWidgets.QPushButton("更新 yt-dlp")
        self.btn_update_ytdlp.clicked.connect(self.on_update_ytdlp)
        self.btn_update_ffmpeg = QtWidgets.QPushButton("更新 ffmpeg")
        self.btn_update_ffmpeg.clicked.connect(self.on_update_ffmpeg)
        maint_layout.addWidget(self.lbl_tools_summary, 0, 0, 1, 3)
        maint_layout.addWidget(self.lbl_ytdlp_ver, 1, 0, 1, 3)
        maint_layout.addWidget(self.lbl_ffmpeg_ver, 2, 0, 1, 3)
        maint_layout.addWidget(self.lbl_tools_checked_at, 3, 0, 1, 2)
        maint_layout.addWidget(self.btn_check_tools, 1, 3)
        maint_layout.addWidget(self.btn_update_ytdlp, 2, 3)
        maint_layout.addWidget(self.btn_update_ffmpeg, 3, 3)

        row_cfg_top = QtWidgets.QHBoxLayout()
        row_cfg_top.setSpacing(10)
        row_cfg_top.addWidget(box_filter, 1)
        row_cfg_top.addWidget(box_download, 1)
        self.cfg_row_top = row_cfg_top
        tab_config_layout.addLayout(row_cfg_top)
        row_cfg_bottom = QtWidgets.QHBoxLayout()
        row_cfg_bottom.setSpacing(10)
        row_cfg_bottom.addWidget(box_queue, 1)
        row_cfg_bottom.addWidget(maint_box, 1)
        self.cfg_row_bottom = row_cfg_bottom
        tab_config_layout.addLayout(row_cfg_bottom)
        self.combo_download_mode.currentTextChanged.connect(self._on_download_mode_changed)
        self._on_download_mode_changed(self.combo_download_mode.currentText())
        self._connect_config_summary_signals()
        self._update_config_summary()
        tab_config_layout.addStretch()
        tabs.addTab(tab_config, "1. 任务配置")

        tab_queue = QtWidgets.QWidget()
        tab_queue_layout = QtWidgets.QVBoxLayout(tab_queue)
        tab_queue_layout.setContentsMargins(0, 0, 0, 0)
        tab_queue_layout.setSpacing(8)
        queue_hero = QtWidgets.QFrame()
        queue_hero.setObjectName("heroBanner")
        queue_hero_layout = QtWidgets.QVBoxLayout(queue_hero)
        queue_hero_layout.setContentsMargins(16, 14, 16, 14)
        queue_hero_layout.setSpacing(6)
        queue_eyebrow = QtWidgets.QLabel("QUEUE WORKSPACE")
        queue_eyebrow.setObjectName("heroEyebrow")
        queue_title = QtWidgets.QLabel("任务调度、审核诊断与下载执行")
        queue_title.setObjectName("heroTitle")
        queue_desc = QtWidgets.QLabel("左侧处理任务队列，右侧查看当前任务的审核结果、Agent 诊断和执行事件，让下载前判断更明确。")
        queue_desc.setObjectName("heroDescription")
        queue_desc.setWordWrap(True)
        queue_hero_layout.addWidget(queue_eyebrow)
        queue_hero_layout.addWidget(queue_title)
        queue_hero_layout.addWidget(queue_desc)
        tab_queue_layout.addWidget(queue_hero)
        self.queue_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.queue_splitter.setChildrenCollapsible(False)
        tab_queue_layout.addWidget(self.queue_splitter, 1)

        left_box = QtWidgets.QGroupBox("任务栏")
        left_box.setObjectName("surfacePanel")
        left_box.setMinimumWidth(360)
        left_box.setMaximumWidth(500)
        left_layout = QtWidgets.QVBoxLayout(left_box)
        left_layout.setSpacing(8)
        self.lbl_queue_stats = QtWidgets.QLabel("队列任务: 0")
        self.lbl_queue_stats.setObjectName("sectionTitle")
        self.lbl_queue_focus = QtWidgets.QLabel("当前选中: 无")
        self.lbl_queue_focus.setObjectName("hint")
        self.lbl_queue_focus.setWordWrap(True)
        left_layout.addWidget(self.lbl_queue_stats)
        left_layout.addWidget(self.lbl_queue_focus)
        self.queue_metric_pending = self._make_metric_label("待筛选", "0")
        self.queue_metric_ready = self._make_metric_label("可下载", "0")
        self.queue_metric_attention = self._make_metric_label("异常/暂停", "0")
        queue_metric_row = QtWidgets.QGridLayout()
        queue_metric_row.setHorizontalSpacing(8)
        queue_metric_row.setVerticalSpacing(8)
        queue_metric_row.addWidget(self.queue_metric_pending, 0, 0)
        queue_metric_row.addWidget(self.queue_metric_ready, 0, 1)
        queue_metric_row.addWidget(self.queue_metric_attention, 1, 0, 1, 2)
        self.queue_metric_row = queue_metric_row
        left_layout.addLayout(queue_metric_row)
        queue_filter_row = QtWidgets.QHBoxLayout()
        queue_filter_row.setSpacing(8)
        self.combo_queue_scope = NoWheelComboBox()
        self.combo_queue_scope.addItems(["全部任务", "待筛选", "可下载", "异常/暂停", "Agent 任务"])
        self.combo_queue_scope.currentTextChanged.connect(self._refresh_queue_list)
        self.combo_queue_scope.setMaximumWidth(140)
        self.le_queue_filter = QtWidgets.QLineEdit()
        self.le_queue_filter.setPlaceholderText("筛选任务名 / run_id")
        self.le_queue_filter.setClearButtonEnabled(True)
        self.le_queue_filter.textChanged.connect(self._refresh_queue_list)
        queue_filter_row.addWidget(self.combo_queue_scope)
        queue_filter_row.addWidget(self.le_queue_filter, 1)
        self.queue_filter_row = queue_filter_row
        left_layout.addLayout(queue_filter_row)

        self.btn_start_queue = QtWidgets.QPushButton("继续执行待筛选任务")
        self.btn_start_queue.setObjectName("primary")
        self.btn_start_queue.clicked.connect(self.start_queue)

        self.btn_download_selected = QtWidgets.QPushButton("下载选中任务")
        self.btn_download_selected.setObjectName("secondary")
        self.btn_download_selected.clicked.connect(self.download_selected_task)

        self.btn_pause = QtWidgets.QPushButton("暂停当前任务")
        self.btn_pause.setObjectName("secondary")
        self.btn_pause.clicked.connect(self.pause_current_task)

        self.btn_resume = QtWidgets.QPushButton("继续选中任务")
        self.btn_resume.setObjectName("secondary")
        self.btn_resume.clicked.connect(self.resume_selected_task)

        self.btn_stop = QtWidgets.QPushButton("停止当前任务")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.on_stop_clicked)

        self.btn_more_ops = QtWidgets.QToolButton()
        self.btn_more_ops.setText("选中 / 更多操作")
        self.btn_more_ops.setObjectName("secondary")
        self.btn_more_ops.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu_more = QtWidgets.QMenu(self.btn_more_ops)
        act_download_selected = menu_more.addAction("下载选中任务")
        act_download_selected.triggered.connect(self.download_selected_task)
        act_resume_selected = menu_more.addAction("继续选中任务")
        act_resume_selected.triggered.connect(self.resume_selected_task)
        act_pause_current = menu_more.addAction("暂停当前任务")
        act_pause_current.triggered.connect(self.pause_current_task)
        act_stop_current = menu_more.addAction("停止当前任务")
        act_stop_current.triggered.connect(self.on_stop_clicked)
        menu_more.addSeparator()
        act_dl_all = menu_more.addAction("下载全部可下载任务")
        act_dl_all.triggered.connect(self.download_all_ready_tasks)
        act_resume = menu_more.addAction("恢复上次未完成下载")
        act_resume.triggered.connect(self.resume_last_download_task)
        act_retry_failed = menu_more.addAction("重试失败URL(当前任务)")
        act_retry_failed.triggered.connect(self.retry_failed_urls_for_selected_task)
        act_retry_failed_tasks = menu_more.addAction("重试选中失败任务")
        act_retry_failed_tasks.triggered.connect(self.retry_selected_failed_tasks)
        act_promote = menu_more.addAction("选中任务置顶")
        act_promote.triggered.connect(self.promote_selected_tasks)
        act_open_task_dir = menu_more.addAction("打开选中任务目录")
        act_open_task_dir.triggered.connect(self.open_selected_task_workdir)
        menu_more.addSeparator()
        act_remove = menu_more.addAction("删除选中任务")
        act_remove.triggered.connect(self.remove_selected_tasks)
        act_clear = menu_more.addAction("清空队列")
        act_clear.triggered.connect(self.clear_queue)
        self.btn_more_ops.setMenu(menu_more)

        ops_box = QtWidgets.QGroupBox("快捷操作")
        ops_box.setObjectName("mini")
        ops_layout = QtWidgets.QVBoxLayout(ops_box)
        ops_layout.setContentsMargins(8, 8, 8, 8)
        ops_layout.setSpacing(8)
        lbl_queue_ops_hint = QtWidgets.QLabel("先继续筛选队列，再对已筛好的任务执行下载或恢复。")
        lbl_queue_ops_hint.setObjectName("hint")
        lbl_queue_ops_hint.setWordWrap(True)
        ops_layout.addWidget(lbl_queue_ops_hint)
        ops_layout.addWidget(self.btn_start_queue)
        ops_layout.addWidget(self.btn_more_ops)
        left_layout.addWidget(ops_box)

        self.queue_list = QtWidgets.QListWidget()
        self.queue_list.setObjectName("queueCards")
        self.queue_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.queue_list.currentRowChanged.connect(self._update_queue_focus_summary)
        self.queue_list.itemDoubleClicked.connect(self._on_queue_item_double_clicked)
        left_layout.addWidget(self.queue_list, 1)

        right_box = QtWidgets.QGroupBox("队列详情")
        right_box.setObjectName("surfacePanel")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        right_layout.setSpacing(8)
        self.current_task_summary = QtWidgets.QFrame()
        self.current_task_summary.setObjectName("currentTaskSummary")
        summary_layout = QtWidgets.QVBoxLayout(self.current_task_summary)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(8)
        summary_top = QtWidgets.QHBoxLayout()
        self.lbl_current_task_title = QtWidgets.QLabel("选择一个任务开始查看结果")
        self.lbl_current_task_title.setObjectName("queueCardTitle")
        self.lbl_current_task_title.setWordWrap(True)
        self.lbl_current_task_status = QtWidgets.QLabel("未选中")
        self.lbl_current_task_status.setObjectName("manualBadge")
        summary_top.addWidget(self.lbl_current_task_title, 1)
        summary_top.addWidget(self.lbl_current_task_status)
        summary_layout.addLayout(summary_top)
        summary_metrics = QtWidgets.QHBoxLayout()
        self.lbl_summary_urls = self._make_metric_label("可下载", "-")
        self.lbl_summary_metadata = self._make_metric_label("视频信息", "-")
        self.lbl_summary_semantic = self._make_metric_label("语义最高", "-")
        summary_metrics.addWidget(self.lbl_summary_urls)
        summary_metrics.addWidget(self.lbl_summary_metadata)
        summary_metrics.addWidget(self.lbl_summary_semantic)
        self.summary_metrics = summary_metrics
        summary_layout.addLayout(summary_metrics)
        right_layout.addWidget(self.current_task_summary)
        self.queue_detail_tabs = QtWidgets.QTabWidget()
        self.queue_detail_tabs.setObjectName("queueDetailTabs")
        right_layout.addWidget(self.queue_detail_tabs, 1)

        diag_box = QtWidgets.QGroupBox("Agent 筛选诊断")
        diag_box.setObjectName("surfacePanel")
        diag_layout = QtWidgets.QVBoxLayout(diag_box)
        diag_layout.setContentsMargins(10, 10, 10, 10)
        diag_layout.setSpacing(6)
        self.lbl_agent_diag_counts = QtWidgets.QLabel("搜到: - | 元数据成功: - | 被筛掉: -")
        self.lbl_agent_diag_counts.setObjectName("sectionTitle")
        self.lbl_agent_diag_counts.setWordWrap(True)
        self.lbl_agent_diag_counts.setVisible(False)
        self.lbl_agent_diag_hint = QtWidgets.QLabel("选中 Agent 任务后，会显示搜索、元数据和筛选诊断。")
        self.lbl_agent_diag_hint.setObjectName("hint")
        self.lbl_agent_diag_hint.setWordWrap(True)
        diag_metrics = QtWidgets.QGridLayout()
        diag_metrics.setHorizontalSpacing(8)
        diag_metrics.setVerticalSpacing(8)
        self.lbl_diag_metric_search = self._make_metric_label("搜索", "-")
        self.lbl_diag_metric_metadata = self._make_metric_label("元数据", "-")
        self.lbl_diag_metric_selected = self._make_metric_label("结果", "-")
        self.lbl_diag_metric_semantic = self._make_metric_label("语义", "-")
        diag_metrics.addWidget(self.lbl_diag_metric_search, 0, 0)
        diag_metrics.addWidget(self.lbl_diag_metric_metadata, 0, 1)
        diag_metrics.addWidget(self.lbl_diag_metric_selected, 1, 0)
        diag_metrics.addWidget(self.lbl_diag_metric_semantic, 1, 1)
        self.agent_diag_reasons = QtWidgets.QListWidget()
        self.agent_diag_reasons.setMinimumHeight(180)
        self.agent_diag_reasons.setFrameShape(QtWidgets.QFrame.NoFrame)
        diag_layout.addWidget(self.lbl_agent_diag_counts)
        diag_layout.addLayout(diag_metrics)
        diag_layout.addWidget(self.lbl_agent_diag_hint)
        diag_layout.addWidget(self.agent_diag_reasons)
        self.queue_detail_tabs.addTab(diag_box, "诊断")

        agent_box = QtWidgets.QGroupBox("Agent 控制中心")
        agent_box.setObjectName("surfacePanel")
        agent_box.setCheckable(False)
        self.agent_detail_box = agent_box
        agent_layout = QtWidgets.QVBoxLayout(agent_box)
        agent_layout.setContentsMargins(10, 10, 10, 10)
        agent_layout.setSpacing(8)
        self.agent_overview_card = QtWidgets.QFrame()
        self.agent_overview_card.setObjectName("agentOverviewCard")
        agent_overview_layout = QtWidgets.QVBoxLayout(self.agent_overview_card)
        agent_overview_layout.setContentsMargins(12, 12, 12, 12)
        agent_overview_layout.setSpacing(8)
        self.lbl_agent_queue_title = QtWidgets.QLabel("当前队列项不是 Agent 任务。")
        self.lbl_agent_queue_title.setObjectName("sectionTitle")
        self.lbl_agent_queue_title.setWordWrap(True)
        self.lbl_agent_queue_status = QtWidgets.QLabel("状态: -")
        self.lbl_agent_queue_status.setObjectName("hint")
        self.lbl_agent_queue_status.setWordWrap(True)
        self.lbl_agent_control_notice = QtWidgets.QLabel("选中 Agent 任务后，这里会显示计划、确认边界、结果摘要和事件时间线。")
        self.lbl_agent_control_notice.setObjectName("agentNoticeInfo")
        self.lbl_agent_control_notice.setWordWrap(True)
        agent_metric_row = QtWidgets.QHBoxLayout()
        self.lbl_agent_metric_steps = self._make_metric_label("计划步骤", "-")
        self.lbl_agent_metric_confirm = self._make_metric_label("待确认", "-")
        self.lbl_agent_metric_events = self._make_metric_label("最近事件", "-")
        agent_metric_row.addWidget(self.lbl_agent_metric_steps)
        agent_metric_row.addWidget(self.lbl_agent_metric_confirm)
        agent_metric_row.addWidget(self.lbl_agent_metric_events)
        self.agent_metric_row = agent_metric_row
        agent_overview_layout.addWidget(self.lbl_agent_queue_title)
        agent_overview_layout.addWidget(self.lbl_agent_queue_status)
        agent_overview_layout.addWidget(self.lbl_agent_control_notice)
        agent_overview_layout.addLayout(agent_metric_row)
        self.agent_paths_box = QtWidgets.QGroupBox("任务路径与输出")
        self.agent_paths_box.setObjectName("mini")
        self.agent_paths_box.setCheckable(True)
        self.agent_paths_box.setChecked(False)
        agent_paths_layout = QtWidgets.QVBoxLayout(self.agent_paths_box)
        agent_paths_layout.setContentsMargins(8, 8, 8, 8)
        agent_paths_layout.setSpacing(8)
        self.lbl_agent_queue_paths = QtWidgets.QLabel("任务目录: -")
        self.lbl_agent_queue_paths.setObjectName("hint")
        self.lbl_agent_queue_paths.setWordWrap(True)
        self.lbl_agent_queue_paths.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        agent_paths_layout.addWidget(self.lbl_agent_queue_paths)
        row_agent_open = QtWidgets.QGridLayout()
        row_agent_open.setHorizontalSpacing(8)
        row_agent_open.setVerticalSpacing(8)
        self.btn_agent_open_workdir = QtWidgets.QPushButton("打开 workdir")
        self.btn_agent_open_workdir.setObjectName("secondary")
        self.btn_agent_open_workdir.clicked.connect(self.open_selected_agent_workdir)
        self.btn_agent_open_selected_urls = QtWidgets.QPushButton("打开 05_selected_urls")
        self.btn_agent_open_selected_urls.setObjectName("secondary")
        self.btn_agent_open_selected_urls.clicked.connect(self.open_selected_agent_selected_urls)
        self.btn_agent_open_task_dir = QtWidgets.QPushButton("打开任务持久化目录")
        self.btn_agent_open_task_dir.setObjectName("secondary")
        self.btn_agent_open_task_dir.clicked.connect(self.open_selected_agent_task_dir)
        row_agent_open.addWidget(self.btn_agent_open_workdir, 0, 0)
        row_agent_open.addWidget(self.btn_agent_open_selected_urls, 0, 1)
        row_agent_open.addWidget(self.btn_agent_open_task_dir, 1, 0, 1, 2)
        self.row_agent_open = row_agent_open
        row_agent_files = QtWidgets.QHBoxLayout()
        self.btn_agent_open_artifacts = QtWidgets.QToolButton()
        self.btn_agent_open_artifacts.setText("打开任务文件")
        self.btn_agent_open_artifacts.setObjectName("secondary")
        self.btn_agent_open_artifacts.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        agent_files_menu = QtWidgets.QMenu(self.btn_agent_open_artifacts)
        self.act_agent_open_spec = agent_files_menu.addAction("打开 spec.json")
        self.act_agent_open_spec.triggered.connect(self.open_selected_agent_spec_file)
        self.act_agent_open_summary = agent_files_menu.addAction("打开 summary.json")
        self.act_agent_open_summary.triggered.connect(self.open_selected_agent_summary_file)
        self.act_agent_open_events = agent_files_menu.addAction("打开 events.jsonl")
        self.act_agent_open_events.triggered.connect(self.open_selected_agent_events_file)
        self.act_agent_open_result = agent_files_menu.addAction("打开 result.json")
        self.act_agent_open_result.triggered.connect(self.open_selected_agent_result_file)
        self.btn_agent_open_artifacts.setMenu(agent_files_menu)
        row_agent_files.addWidget(self.btn_agent_open_artifacts)
        row_agent_files.addStretch(1)
        self.row_agent_files = row_agent_files
        agent_paths_layout.addLayout(row_agent_open)
        agent_paths_layout.addLayout(row_agent_files)
        self.agent_paths_box.toggled.connect(self.lbl_agent_queue_paths.setVisible)
        self.agent_paths_box.toggled.connect(self.btn_agent_open_workdir.setVisible)
        self.agent_paths_box.toggled.connect(self.btn_agent_open_selected_urls.setVisible)
        self.agent_paths_box.toggled.connect(self.btn_agent_open_task_dir.setVisible)
        self.agent_paths_box.toggled.connect(self.btn_agent_open_artifacts.setVisible)
        self.lbl_agent_queue_paths.setVisible(False)
        self.btn_agent_open_workdir.setVisible(False)
        self.btn_agent_open_selected_urls.setVisible(False)
        self.btn_agent_open_task_dir.setVisible(False)
        self.btn_agent_open_artifacts.setVisible(False)
        self.agent_steps_list = QtWidgets.QListWidget()
        self.agent_steps_list.setObjectName("agentStepsList")
        self.agent_steps_list.setMinimumHeight(180)
        self.agent_steps_list.setSpacing(8)
        self.agent_steps_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.agent_steps_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.agent_confirm_list = QtWidgets.QListWidget()
        self.agent_confirm_list.setObjectName("agentConfirmList")
        self.agent_confirm_list.setMinimumHeight(140)
        self.agent_confirm_list.setSpacing(8)
        self.agent_confirm_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.agent_confirm_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self.agent_result_summary = QtWidgets.QTextBrowser()
        self.agent_result_summary.setObjectName("agentResultSummary")
        self.agent_result_summary.setOpenLinks(False)
        self.agent_result_summary.setOpenExternalLinks(False)
        self.agent_result_summary.setPlaceholderText("结果摘要会显示在这里。")
        self.agent_result_summary.setMinimumHeight(220)
        self.agent_result_summary.anchorClicked.connect(self._on_agent_result_link_clicked)
        self.agent_result_summary.highlighted.connect(self._on_agent_result_link_hovered)
        self.agent_result_summary.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.agent_result_summary.customContextMenuRequested.connect(self._show_agent_result_context_menu)
        self.agent_events_list = QtWidgets.QListWidget()
        self.agent_events_list.setObjectName("agentEventsList")
        self.agent_events_list.setMinimumHeight(220)
        self.agent_events_list.setSpacing(8)
        row_agent_events_tools = QtWidgets.QVBoxLayout()
        row_agent_events_tools.setSpacing(8)
        row_agent_events_top = QtWidgets.QHBoxLayout()
        row_agent_events_top.setSpacing(8)
        row_agent_events_bottom = QtWidgets.QHBoxLayout()
        row_agent_events_bottom.setSpacing(8)
        self.combo_agent_event_level = NoWheelComboBox()
        self.combo_agent_event_level.addItems(["全部级别", "Info", "Warning", "Error"])
        self.combo_agent_event_level.setMinimumWidth(130)
        self.combo_agent_event_level.currentTextChanged.connect(self._on_agent_event_filter_changed)
        self.combo_agent_event_type = NoWheelComboBox()
        self.combo_agent_event_type.addItems(["全部类型"])
        self.combo_agent_event_type.setMinimumWidth(150)
        self.combo_agent_event_type.currentTextChanged.connect(self._on_agent_event_filter_changed)
        self.le_agent_event_keyword = QtWidgets.QLineEdit()
        self.le_agent_event_keyword.setPlaceholderText("关键词过滤")
        self.le_agent_event_keyword.setClearButtonEnabled(True)
        self.le_agent_event_keyword.setMinimumWidth(220)
        self.le_agent_event_keyword.textChanged.connect(self._on_agent_event_filter_changed)
        self.btn_agent_clear_event_filters = QtWidgets.QPushButton("清空全部筛选")
        self.btn_agent_clear_event_filters.setObjectName("secondary")
        self.btn_agent_clear_event_filters.clicked.connect(self._clear_agent_event_filters)
        self.btn_agent_copy_events = QtWidgets.QPushButton("复制可见事件")
        self.btn_agent_copy_events.setObjectName("secondary")
        self.btn_agent_copy_events.clicked.connect(self._copy_visible_agent_events)
        self.btn_agent_copy_selected_event = QtWidgets.QPushButton("复制选中事件")
        self.btn_agent_copy_selected_event.setObjectName("secondary")
        self.btn_agent_copy_selected_event.clicked.connect(self._copy_selected_agent_event)
        row_agent_events_top.addWidget(self.combo_agent_event_level)
        row_agent_events_top.addWidget(self.combo_agent_event_type)
        row_agent_events_top.addWidget(self.le_agent_event_keyword, 1)
        row_agent_events_bottom.addWidget(self.btn_agent_clear_event_filters)
        row_agent_events_bottom.addWidget(self.btn_agent_copy_selected_event)
        row_agent_events_bottom.addWidget(self.btn_agent_copy_events)
        row_agent_events_bottom.addStretch(1)
        row_agent_events_tools.addLayout(row_agent_events_top)
        row_agent_events_tools.addLayout(row_agent_events_bottom)
        agent_layout.addWidget(self.agent_overview_card)
        agent_layout.addWidget(self.agent_paths_box)
        self.lbl_agent_steps_header = QtWidgets.QLabel("计划与执行步骤")
        agent_layout.addWidget(self.lbl_agent_steps_header)
        agent_layout.addWidget(self.agent_steps_list)
        self.lbl_agent_confirm_header = QtWidgets.QLabel("确认边界")
        agent_layout.addWidget(self.lbl_agent_confirm_header)
        agent_layout.addWidget(self.agent_confirm_list)
        self.lbl_agent_result_header = QtWidgets.QLabel("结果摘要")
        agent_layout.addWidget(self.lbl_agent_result_header)
        agent_layout.addWidget(self.agent_result_summary)
        self.lbl_agent_events_header = QtWidgets.QLabel("最近事件")
        agent_layout.addWidget(self.lbl_agent_events_header)
        agent_layout.addLayout(row_agent_events_tools)
        agent_layout.addWidget(self.agent_events_list)
        self.queue_detail_tabs.addTab(agent_box, "Agent 详情")
        self._agent_detail_toggle_widgets = [
            self.agent_paths_box,
            self.lbl_agent_steps_header,
            self.agent_steps_list,
            self.lbl_agent_confirm_header,
            self.agent_confirm_list,
            self.lbl_agent_result_header,
            self.agent_result_summary,
            self.lbl_agent_events_header,
            self.combo_agent_event_level,
            self.combo_agent_event_type,
            self.le_agent_event_keyword,
            self.btn_agent_clear_event_filters,
            self.btn_agent_copy_selected_event,
            self.btn_agent_copy_events,
            self.agent_events_list,
        ]
        self.agent_detail_box.setCheckable(True)
        self.agent_detail_box.toggled.connect(self._set_agent_detail_expanded)
        self._set_agent_detail_expanded(False)
        self.btn_agent_open_workdir.setEnabled(False)
        self.btn_agent_open_selected_urls.setEnabled(False)
        self.btn_agent_open_task_dir.setEnabled(False)
        self.btn_agent_open_artifacts.setEnabled(False)
        self.act_agent_open_spec.setEnabled(False)
        self.act_agent_open_summary.setEnabled(False)
        self.act_agent_open_events.setEnabled(False)
        self.act_agent_open_result.setEnabled(False)
        self.btn_agent_clear_event_filters.setEnabled(False)
        self.btn_agent_copy_selected_event.setEnabled(False)
        self.btn_agent_copy_events.setEnabled(False)

        video_box = QtWidgets.QGroupBox("视频列表与下载操作")
        video_box.setObjectName("surfacePanel")
        video_layout = QtWidgets.QVBoxLayout(video_box)
        video_layout.setContentsMargins(10, 10, 10, 10)
        video_layout.setSpacing(8)
        lbl_video_intro = QtWidgets.QLabel("按缩略图、语义分和审核提醒快速复核候选视频，勾选后即可进入下载。")
        lbl_video_intro.setObjectName("hint")
        lbl_video_intro.setWordWrap(True)
        video_layout.addWidget(lbl_video_intro)
        video_summary_row = QtWidgets.QHBoxLayout()
        video_summary_row.setSpacing(8)
        self.lbl_video_stat_ready = self._make_metric_label("本页可下载", "-")
        self.lbl_video_stat_low = self._make_metric_label("低相似", "-")
        self.lbl_video_stat_review = self._make_metric_label("需复核", "-")
        self.lbl_video_stat_checked = self._make_metric_label("已勾选", "-")
        video_summary_row.addWidget(self.lbl_video_stat_ready)
        video_summary_row.addWidget(self.lbl_video_stat_low)
        video_summary_row.addWidget(self.lbl_video_stat_review)
        video_summary_row.addWidget(self.lbl_video_stat_checked)
        video_layout.addLayout(video_summary_row)
        toolbar_hint = QtWidgets.QLabel("把审核操作拆成三组：先选择，再筛选，最后执行下载。")
        toolbar_hint.setObjectName("hint")
        toolbar_hint.setWordWrap(True)
        video_layout.addWidget(toolbar_hint)
        row_ops = QtWidgets.QVBoxLayout()
        row_ops.setSpacing(8)
        row_ops_top = QtWidgets.QHBoxLayout()
        row_ops_top.setSpacing(10)
        row_ops_bottom = QtWidgets.QHBoxLayout()
        row_ops_bottom.setSpacing(10)
        self.btn_load_task_videos = QtWidgets.QPushButton("加载当前任务视频")
        self.btn_load_task_videos.setObjectName("secondary")
        self.btn_load_task_videos.clicked.connect(self.load_selected_task_videos)
        self.btn_check_all_page = QtWidgets.QPushButton("本页全选")
        self.btn_check_all_page.setObjectName("secondary")
        self.btn_check_all_page.clicked.connect(self.select_all_videos_on_page)
        self.btn_uncheck_all_page = QtWidgets.QPushButton("本页清空")
        self.btn_uncheck_all_page.setObjectName("secondary")
        self.btn_uncheck_all_page.clicked.connect(self.unselect_all_videos_on_page)
        self.le_video_filter = QtWidgets.QLineEdit()
        self.le_video_filter.setPlaceholderText("筛选标题/作者")
        self.le_video_filter.textChanged.connect(self._apply_video_view)
        self.le_video_filter.setMinimumWidth(200)
        self.combo_video_scope = NoWheelComboBox()
        self.combo_video_scope.addItems(["可下载", "Agent 推荐", "全部候选", "已勾选", "低相似", "需复核"])
        self.combo_video_scope.currentTextChanged.connect(self._apply_video_view)
        self.combo_video_scope.setMinimumWidth(130)
        self.combo_video_sort = NoWheelComboBox()
        self.combo_video_sort.addItems(["默认排序", "语义分数(高->低)", "上传日期(新->旧)", "时长(长->短)", "标题(A-Z)"])
        self.combo_video_sort.currentTextChanged.connect(self._apply_video_view)
        self.combo_video_sort.setMinimumWidth(170)
        self.btn_download_checked = QtWidgets.QPushButton("下载勾选视频")
        self.btn_download_checked.setObjectName("primary")
        self.btn_download_checked.clicked.connect(self.download_checked_videos)
        select_group = QtWidgets.QFrame()
        select_group.setObjectName("toolbarGroup")
        select_layout = QtWidgets.QHBoxLayout(select_group)
        select_layout.setContentsMargins(10, 8, 10, 8)
        select_layout.setSpacing(8)
        select_layout.addWidget(self.btn_load_task_videos)
        select_layout.addWidget(self.btn_check_all_page)
        select_layout.addWidget(self.btn_uncheck_all_page)
        filter_group = QtWidgets.QFrame()
        filter_group.setObjectName("toolbarGroup")
        filter_layout = QtWidgets.QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(10, 8, 10, 8)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(self.le_video_filter, 1)
        filter_layout.addWidget(self.combo_video_scope)
        filter_layout.addWidget(self.combo_video_sort)
        action_group = QtWidgets.QFrame()
        action_group.setObjectName("toolbarGroupStrong")
        action_layout = QtWidgets.QHBoxLayout(action_group)
        action_layout.setContentsMargins(10, 8, 10, 8)
        action_layout.setSpacing(8)
        action_layout.addWidget(self.btn_download_checked)
        row_ops_top.addWidget(select_group, 1)
        row_ops_top.addWidget(action_group, 0)
        row_ops_bottom.addWidget(filter_group, 1)
        row_ops.addLayout(row_ops_top)
        row_ops.addLayout(row_ops_bottom)
        video_layout.addLayout(row_ops)
        pager = QtWidgets.QHBoxLayout()
        self.btn_prev_page = QtWidgets.QPushButton("上一页")
        self.btn_prev_page.setObjectName("secondary")
        self.btn_prev_page.clicked.connect(self.prev_video_page)
        self.btn_next_page = QtWidgets.QPushButton("下一页")
        self.btn_next_page.setObjectName("secondary")
        self.btn_next_page.clicked.connect(self.next_video_page)
        self.lbl_video_page = QtWidgets.QLabel("第 0/0 页")
        self.lbl_video_page.setObjectName("hint")
        self.combo_page_size = NoWheelComboBox()
        self.combo_page_size.addItems(["10 条/页", "20 条/页", "30 条/页"])
        self.combo_page_size.setCurrentIndex(0)
        self.combo_page_size.currentIndexChanged.connect(self._on_page_size_changed)
        self.combo_page_size.setMaximumWidth(130)
        pager.addWidget(self.btn_prev_page)
        pager.addWidget(self.btn_next_page)
        pager.addWidget(self.lbl_video_page)
        pager.addWidget(self.combo_page_size)
        pager.addStretch()
        video_layout.addLayout(pager)
        self.video_list_widget = QtWidgets.QListWidget()
        self.video_list_widget.setObjectName("videoFeed")
        self.video_list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.video_list_widget.setSpacing(10)
        self.video_list_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.video_list_widget.verticalScrollBar().valueChanged.connect(lambda *_: self._schedule_visible_thumb_load())
        video_layout.addWidget(self.video_list_widget, 1)
        self.queue_detail_tabs.insertTab(0, video_box, "视频")
        self.queue_detail_tabs.setCurrentIndex(0)

        self.queue_splitter.addWidget(left_box)
        self.queue_splitter.addWidget(right_box)
        self.queue_splitter.setStretchFactor(0, 0)
        self.queue_splitter.setStretchFactor(1, 1)
        self.queue_splitter.setSizes([420, 1140])
        tabs.addTab(tab_queue, "2. 队列执行")

        tab_output = QtWidgets.QWidget()
        tab_output_layout = QtWidgets.QVBoxLayout(tab_output)
        self.te_log = QtWidgets.QPlainTextEdit()
        self.te_log.setReadOnly(True)
        self.te_log.setFont(QtGui.QFont("Consolas", 10))
        self.te_log.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.te_log.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.te_log.customContextMenuRequested.connect(self.show_log_context_menu)
        tab_output_layout.addWidget(self.te_log, 1)
        self.model = CsvPreviewModel(self)
        tabs.addTab(tab_output, "3. 日志结果")

        tab_downloaded = QtWidgets.QWidget()
        tab_downloaded_layout = QtWidgets.QVBoxLayout(tab_downloaded)
        tab_downloaded_layout.setContentsMargins(0, 0, 0, 0)
        tab_downloaded_layout.setSpacing(8)
        row_dl_ops = QtWidgets.QHBoxLayout()
        self.btn_refresh_downloaded = QtWidgets.QPushButton("刷新已下载")
        self.btn_refresh_downloaded.setObjectName("secondary")
        self.btn_refresh_downloaded.clicked.connect(self.refresh_downloaded_view)
        self.btn_open_downloaded_dir = QtWidgets.QPushButton("打开目录")
        self.btn_open_downloaded_dir.setObjectName("secondary")
        self.btn_open_downloaded_dir.clicked.connect(self.open_selected_downloaded_dir)
        self.btn_open_downloaded_report = QtWidgets.QPushButton("打开报告 CSV")
        self.btn_open_downloaded_report.setObjectName("secondary")
        self.btn_open_downloaded_report.clicked.connect(self.open_selected_downloaded_report)
        row_dl_ops.addWidget(self.btn_refresh_downloaded)
        row_dl_ops.addWidget(self.btn_open_downloaded_dir)
        row_dl_ops.addWidget(self.btn_open_downloaded_report)
        row_dl_ops.addStretch()
        tab_downloaded_layout.addLayout(row_dl_ops)
        self.downloaded_list = QtWidgets.QListWidget()
        self.downloaded_list.currentRowChanged.connect(self._update_downloaded_detail)
        tab_downloaded_layout.addWidget(self.downloaded_list, 1)
        self.lbl_downloaded_detail = QtWidgets.QLabel("暂无下载记录")
        self.lbl_downloaded_detail.setObjectName("hint")
        self.lbl_downloaded_detail.setWordWrap(True)
        tab_downloaded_layout.addWidget(self.lbl_downloaded_detail)
        tabs.addTab(tab_downloaded, "4. 已下载")

        tab_agent = self._build_agent_workspace_tab()
        self.agent_tab_index = tabs.addTab(tab_agent, "5. Agent")

        tabs.currentChanged.connect(self._on_main_tab_changed)
        self.side_nav.setCurrentRow(0)
        self.refresh_downloaded_view()

        self._normalize_ui_sizes()
        self._adjust_config_layout_for_width()
        self.status = self.statusBar()

    def _tune_form_labels(self, form: QtWidgets.QFormLayout, label_width: int) -> None:
        for r in range(form.rowCount()):
            label_item = form.itemAt(r, QtWidgets.QFormLayout.LabelRole)
            if label_item is None:
                continue
            w = label_item.widget()
            if isinstance(w, QtWidgets.QLabel):
                w.setMinimumWidth(label_width)
                w.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

    def _normalize_ui_sizes(self) -> None:
        # 统一输入控件尺寸，改善对齐观感
        line_edits = [
            self.le_query_text,
            self.le_cookies_file,
            self.le_yt_extra_args,
            self.le_queue_filter,
        ]
        combos_wide = [
            self.cb_workdir,
            self.cb_downloaddir,
            self.combo_cookies_browser,
            self.combo_download_mode,
            self.combo_video_container,
            self.combo_max_height,
            self.combo_audio_format,
            self.combo_queue_scope,
        ]
        spins = [
            self.spin_search_limit,
            self.spin_metadata_workers,
            self.spin_min_duration,
            self.spin_year_from,
            self.spin_year_to,
            self.spin_audio_quality,
            self.spin_concurrent_videos,
            self.spin_concurrent_fragments,
        ]

        # 降低最小宽度，避免在 1080p 下双栏布局被挤压。
        for w in line_edits:
            w.setMinimumWidth(220)
            w.setMinimumHeight(34)
        for w in combos_wide:
            w.setMinimumWidth(150)
            w.setMinimumHeight(34)
        for w in spins:
            w.setMinimumWidth(110)
            w.setMinimumHeight(34)
            w.setMaximumWidth(180)

        for b in self.findChildren(QtWidgets.QPushButton):
            b.setMinimumHeight(34)
            if b.text().strip() == "选择...":
                b.setMinimumWidth(86)

        for b in [
            self.btn_start_queue,
            self.btn_download_selected,
            self.btn_pause,
            self.btn_resume,
            self.btn_stop,
            self.btn_enqueue_only,
        ]:
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_more_ops.setMinimumHeight(34)
        self.btn_more_ops.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_more_ops.setMinimumWidth(96)

    def _adjust_config_layout_for_width(self) -> None:
        width = self.width()
        direction = (
            QtWidgets.QBoxLayout.LeftToRight if width >= 1650 else QtWidgets.QBoxLayout.TopToBottom
        )
        for lay in [getattr(self, "cfg_row_top", None), getattr(self, "cfg_row_bottom", None)]:
            if isinstance(lay, QtWidgets.QBoxLayout):
                lay.setDirection(direction)
        self._adjust_queue_layout_for_width(width)

    def _adjust_queue_layout_for_width(self, width: int) -> None:
        queue_narrow = width < 1480
        queue_dense = width < 1640

        if hasattr(self, "queue_splitter"):
            if queue_narrow:
                self.queue_splitter.setSizes([460, max(820, width - 520)])
            else:
                self.queue_splitter.setSizes([520, max(980, width - 580)])

        for lay in [
            getattr(self, "queue_metric_row", None),
            getattr(self, "queue_filter_row", None),
            getattr(self, "row_primary_ops", None),
            getattr(self, "row_support_ops", None),
            getattr(self, "summary_metrics", None),
            getattr(self, "agent_metric_row", None),
            getattr(self, "row_agent_open", None),
            getattr(self, "row_agent_files", None),
        ]:
            if isinstance(lay, QtWidgets.QBoxLayout):
                lay.setDirection(QtWidgets.QBoxLayout.TopToBottom if queue_narrow else QtWidgets.QBoxLayout.LeftToRight)

        if hasattr(self, "combo_queue_scope"):
            self.combo_queue_scope.setMaximumWidth(16777215 if queue_narrow else 160)
        if hasattr(self, "le_queue_filter"):
            self.le_queue_filter.setMinimumWidth(180 if queue_narrow else 220)

        if hasattr(self, "btn_more_ops"):
            self.btn_more_ops.setMinimumWidth(0 if queue_narrow else 96)

        if hasattr(self, "combo_agent_event_level"):
            self.combo_agent_event_level.setMinimumWidth(110 if queue_dense else 130)
        if hasattr(self, "combo_agent_event_type"):
            self.combo_agent_event_type.setMinimumWidth(130 if queue_dense else 150)
        if hasattr(self, "le_agent_event_keyword"):
            self.le_agent_event_keyword.setMinimumWidth(160 if queue_dense else 220)

    def _wrap(self, inner_layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setLayout(inner_layout)
        return w

    def _make_metric_label(self, label: str, value: str) -> QtWidgets.QLabel:
        widget = QtWidgets.QLabel()
        widget.setObjectName("metricCard")
        widget.setWordWrap(True)
        widget.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        widget.setMinimumHeight(82)
        widget.setText(
            f"<span style='color:#9AA6B2; font-size:12px'>{html.escape(label)}</span><br/>"
            f"<span style='font-size:18px; font-weight:700'>{html.escape(value)}</span>"
        )
        return widget

    def _set_metric_label(self, widget: QtWidgets.QLabel, label: str, value: str, detail: str = "") -> None:
        detail_html = f"<br/><span style='color:#74808C; font-size:11px'>{html.escape(detail)}</span>" if detail else ""
        widget.setText(
            f"<span style='color:#9AA6B2; font-size:12px'>{html.escape(label)}</span><br/>"
            f"<span style='font-size:18px; font-weight:700'>{html.escape(value)}</span>{detail_html}"
        )

    def _queue_task_index_from_view_row(self, row: int) -> Optional[int]:
        if row < 0 or row >= len(self._queue_visible_indices):
            return None
        return self._queue_visible_indices[row]

    def _current_task_index(self) -> Optional[int]:
        return self._queue_task_index_from_view_row(self.queue_list.currentRow())

    def _queue_task_matches_filters(self, task: QueueTask) -> bool:
        scope = self.combo_queue_scope.currentText() if hasattr(self, "combo_queue_scope") else "全部任务"
        if scope == "待筛选" and task.status not in {"pending", "running", "paused_filter"}:
            return False
        if scope == "可下载" and task.status not in {"ready", "downloaded", "downloading", "paused_download", "download_failed"} and task.selected_count <= 0:
            return False
        if scope == "异常/暂停" and task.status not in {"paused_filter", "paused_download", "failed", "download_failed", "filtered_empty"}:
            return False
        if scope == "Agent 任务" and task.origin != "agent":
            return False
        keyword = self.le_queue_filter.text().strip().lower() if hasattr(self, "le_queue_filter") else ""
        if keyword:
            haystack = " ".join([task.task_name, task.run_id, task.status, task.workdir]).lower()
            if keyword not in haystack:
                return False
        return True

    def _connect_config_summary_signals(self) -> None:
        for line_edit in [
            self.le_query_text,
            self.le_cookies_file,
            self.le_yt_extra_args,
            self.le_agent_base_url,
            self.le_agent_model,
            self.le_agent_api_key,
        ]:
            line_edit.textChanged.connect(self._update_config_summary)
        for combo in [
            self.cb_workdir,
            self.cb_downloaddir,
            self.combo_cookies_browser,
            self.combo_download_mode,
            self.combo_video_container,
            self.combo_max_height,
            self.combo_audio_format,
            self.combo_agent_provider,
        ]:
            combo.currentTextChanged.connect(self._update_config_summary)
            if combo.isEditable():
                combo.editTextChanged.connect(self._update_config_summary)
        for spin in [
            self.spin_search_limit,
            self.spin_metadata_workers,
            self.spin_min_duration,
            self.spin_year_from,
            self.spin_year_to,
            self.spin_audio_quality,
            self.spin_concurrent_videos,
            self.spin_concurrent_fragments,
        ]:
            spin.valueChanged.connect(self._update_config_summary)
        for check in [
            self.chk_year_from,
            self.chk_year_to,
            self.chk_include_audio,
            self.chk_clean_video,
            self.chk_full_csv,
            self.chk_agent_show_api_key,
        ]:
            check.toggled.connect(self._update_config_summary)
        for chk in self.sb_checks.values():
            chk.toggled.connect(self._update_config_summary)

    def _update_config_summary(self) -> None:
        query = self.le_query_text.text().strip() or "未填写查询内容"
        workdir = self._combo_text(self.cb_workdir) or "-"
        downloaddir = self._combo_text(self.cb_downloaddir) or "-"
        mode = self.combo_download_mode.currentText().strip() or "video"
        if mode == "audio":
            format_text = f"音频 {self.combo_audio_format.currentText()} / 质量 {self.spin_audio_quality.value()}"
        else:
            audio_suffix = "，合并音频" if self.chk_include_audio.isChecked() else ""
            format_text = f"视频 {self.combo_video_container.currentText()} / {self.combo_max_height.currentText()}p{audio_suffix}"
        filters = [
            f"收集 {self.spin_search_limit.value()} 条",
            f"最短 {self.spin_min_duration.value()} 秒",
        ]
        if self.chk_year_from.isChecked():
            filters.append(f"年份 >= {self.spin_year_from.value()}")
        if self.chk_year_to.isChecked():
            filters.append(f"年份 <= {self.spin_year_to.value()}")
        cookie_browser = self.combo_cookies_browser.currentText().strip()
        cookie_file = self.le_cookies_file.text().strip()
        if cookie_browser:
            filters.append(f"cookies:{cookie_browser}")
        elif cookie_file:
            filters.append("使用 cookies 文件")
        boundaries = [
            f"元数据并发 {self.spin_metadata_workers.value()}",
            f"下载并发 {self.spin_concurrent_videos.value()} 视频 / {self.spin_concurrent_fragments.value()} 分片",
        ]
        if self.chk_clean_video.isChecked():
            boundaries.append("纯净模式开启")
        if self.chk_full_csv.isChecked():
            boundaries.append("导出全量评分 CSV")
        agent_provider = self.combo_agent_provider.currentText().strip() or "-"
        agent_model = self.le_agent_model.text().strip() or "-"
        agent_base = self.le_agent_base_url.text().strip() or "自动/未填"
        api_key_state = "已填写" if self.le_agent_api_key.text().strip() else "未填写"
        boundaries.append(f"Agent: {agent_provider} / {agent_model}")
        boundaries.append(f"LLM API: {api_key_state}")
        self.lbl_config_summary_query.setText(f"查询: {query}")
        self.lbl_config_summary_paths.setText(f"信息目录: {workdir}\n下载目录: {downloaddir}")
        self.lbl_config_summary_download.setText(f"下载策略: {format_text}\n筛选条件: {' | '.join(filters)}")
        self.lbl_config_summary_flags.setText(
            f"执行边界: {' | '.join(boundaries)}\nAgent Base URL: {agent_base}"
        )
        self._update_agent_runtime_hint()

    def _combo_text(self, combo: QtWidgets.QComboBox) -> str:
        return combo.currentText().strip()

    def _set_combo_text(self, combo: QtWidgets.QComboBox, value: str) -> None:
        value = value.strip()
        if not value:
            return
        if combo.findText(value) < 0:
            combo.insertItem(0, value)
        combo.setCurrentText(value)

    def _on_download_mode_changed(self, mode: str) -> None:
        is_audio = mode.strip().lower() == "audio"
        self.chk_include_audio.setEnabled(not is_audio)
        self.combo_video_container.setEnabled(not is_audio)
        self.combo_max_height.setEnabled(not is_audio)
        self.combo_audio_format.setEnabled(is_audio)
        self.spin_audio_quality.setEnabled(is_audio)
        for chk in self.sb_checks.values():
            chk.setEnabled(self.chk_clean_video.isChecked())
        if hasattr(self, "lbl_config_summary_query"):
            self._update_config_summary()

    def _toggle_agent_api_key_visibility(self, checked: bool) -> None:
        self.le_agent_api_key.setEchoMode(
            QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        )

    def _on_agent_provider_changed(self, provider: str) -> None:
        provider_key = provider.strip().lower()
        presets = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "deepseek": "https://api.deepseek.com",
            "moonshot": "https://api.moonshot.cn/v1",
            "aliyun_bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
        target = presets.get(provider_key, "")
        current = self.le_agent_base_url.text().strip()
        if target and (not current or current in presets.values()):
            self.le_agent_base_url.setText(target)
        suggestions = provider_model_suggestions(provider_key)
        if suggestions:
            self.lbl_agent_model_suggestion.setText(f"建议模型: {', '.join(suggestions)}")
            self.le_agent_model.setPlaceholderText(f"例如: {suggestions[0]}")
            self.le_agent_model.setToolTip("建议模型: " + ", ".join(suggestions))
        else:
            self.lbl_agent_model_suggestion.setText("建议模型: 请输入 provider 对应的模型名")
            self.le_agent_model.setToolTip("")
        self._update_agent_runtime_hint()

    def _current_agent_runtime_config(self) -> dict[str, Any]:
        extra_args_text = self.le_yt_extra_args.text().strip()
        return {
            "binary": "yt-dlp",
            "search_limit": self.spin_search_limit.value(),
            "metadata_workers": self.spin_metadata_workers.value(),
            "min_duration": self.spin_min_duration.value(),
            "download_dir": self._combo_text(self.cb_downloaddir),
            "download_mode": self.combo_download_mode.currentText().strip(),
            "include_audio": self.chk_include_audio.isChecked(),
            "video_container": self.combo_video_container.currentText().strip(),
            "max_height": self.combo_max_height.currentText().strip(),
            "audio_format": self.combo_audio_format.currentText().strip(),
            "audio_quality": self.spin_audio_quality.value(),
            "cookies_from_browser": self.combo_cookies_browser.currentText().strip(),
            "cookies_file": self.le_cookies_file.text().strip(),
            "extra_args": shlex.split(extra_args_text) if extra_args_text else [],
            "concurrent_videos": self.spin_concurrent_videos.value(),
            "concurrent_fragments": self.spin_concurrent_fragments.value(),
            "sponsorblock_remove": self._selected_sponsorblock_remove() if self.chk_clean_video.isChecked() else "",
            "full_csv": self.chk_full_csv.isChecked(),
            "llm_provider": self.combo_agent_provider.currentText().strip(),
            "llm_base_url": self.le_agent_base_url.text().strip(),
            "llm_model": self.le_agent_model.text().strip(),
            "llm_api_key": self.le_agent_api_key.text().strip(),
        }

    def _update_agent_runtime_hint(self, status_text: str = "") -> None:
        if not hasattr(self, "lbl_agent_runtime_hint"):
            return
        provider = self.combo_agent_provider.currentText().strip() or "-"
        model = self.le_agent_model.text().strip() or "-"
        base_url = self.le_agent_base_url.text().strip() or "自动/未填"
        key_state = "已填写" if self.le_agent_api_key.text().strip() else "未填写"
        suffix = f" | {status_text}" if status_text else ""
        self.lbl_agent_runtime_hint.setText(
            f"当前连接配置: provider={provider} | model={model} | API Key {key_state} | {base_url}{suffix}"
        )

    def _selected_sponsorblock_remove(self) -> str:
        keys = [k for k, c in self.sb_checks.items() if c.isChecked()]
        return ",".join(keys)

    def _set_sponsorblock_checks(self, value: str) -> None:
        selected = {s.strip() for s in (value or "").split(",") if s.strip()}
        if not selected:
            selected = {"sponsor", "selfpromo", "intro", "outro", "interaction"}
        for k, chk in self.sb_checks.items():
            chk.setChecked(k in selected)

    def _pick_file(self, target_line: QtWidgets.QLineEdit, title: str) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, title, "", "All Files (*.*)")
        if path:
            target_line.setText(path)

    def _pick_dir_combo(self, combo: QtWidgets.QComboBox) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择目录", "")
        if path:
            self._set_combo_text(combo, path)

    def _open_dir(self, path_str: str) -> None:
        if not path_str:
            return
        p = Path(path_str)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(p)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(p)])

    def _open_path(self, path_str: str) -> None:
        if not path_str:
            return
        p = Path(path_str)
        if not p.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"路径不存在：{p}")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(p)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(p)])

    def _show_toast(
        self,
        title: str,
        detail: str = "",
        action_text: str = "",
        action: Optional[Callable[[], None]] = None,
        duration_ms: int = 4500,
    ) -> None:
        self._toast.show_toast(
            title=title,
            detail=detail,
            action_text=action_text,
            action=action,
            duration_ms=duration_ms,
        )

    def _open_last_download_output_dir(self) -> None:
        if self._last_download_output_dir:
            self._open_dir(self._last_download_output_dir)

    @QtCore.Slot(int)
    def _on_side_nav_changed(self, row: int) -> None:
        if row < 0 or row >= self.tabs.count():
            return
        if self.tabs.currentIndex() != row:
            self.tabs.setCurrentIndex(row)

    def _set_progress_panel_expanded(self, expanded: bool) -> None:
        if hasattr(self, "progress_box"):
            self.progress_box.setTitle("实时进度（已展开）" if expanded else "实时进度（点击展开）")
        for widget in getattr(self, "_progress_detail_widgets", []):
            widget.setVisible(expanded)

    def _connect_agent_bridge(self) -> None:
        self.agent_bridge.planned.connect(self._on_agent_task_planned)
        self.agent_bridge.task_summary.connect(self._on_agent_task_summary)
        self.agent_bridge.task_event.connect(self._on_agent_task_event)
        self.agent_bridge.confirmation_required.connect(self._on_agent_confirmation_required)
        self.agent_bridge.completed.connect(self._on_agent_completed)
        self.agent_bridge.error.connect(self._on_agent_error)
        self.agent_bridge.busy_changed.connect(self._on_agent_busy_changed)

    def _build_agent_workspace_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        page.setObjectName("agentWorkspacePage")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        hero = QtWidgets.QFrame()
        hero.setObjectName("agentCommandPanel")
        hero_layout = QtWidgets.QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(12)
        hero_eyebrow = QtWidgets.QLabel("AGENT WORKSPACE")
        hero_eyebrow.setObjectName("heroEyebrow")
        title = QtWidgets.QLabel("用自然语言创建下载任务")
        title.setObjectName("heroTitle")
        hint = QtWidgets.QLabel("描述你想找的视频，先让 Agent 规划与筛选，再决定是否继续下载。这个页签现在会显示当前计划、确认边界和执行进展。")
        hint.setObjectName("heroDescription")
        hint.setWordWrap(True)
        self.lbl_agent_runtime_hint = QtWidgets.QLabel("当前连接配置: 未设置")
        self.lbl_agent_runtime_hint.setObjectName("hint")
        self.lbl_agent_runtime_hint.setWordWrap(True)
        hero_layout.addWidget(hero_eyebrow)
        hero_layout.addWidget(title)
        hero_layout.addWidget(hint)
        hero_layout.addWidget(self.lbl_agent_runtime_hint)
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(12)
        self.le_agent_input = QtWidgets.QLineEdit()
        self.le_agent_input.setPlaceholderText("例如：帮我找 Python async 教程，先筛 30 个，不要下载")
        self.le_agent_input.setMinimumHeight(44)
        self.le_agent_input.returnPressed.connect(self._submit_agent_request)
        self.btn_agent_send = QtWidgets.QPushButton("创建任务")
        self.btn_agent_send.setObjectName("primary")
        self.btn_agent_send.setMinimumWidth(112)
        self.btn_agent_send.clicked.connect(self._submit_agent_request)
        input_row.addWidget(self.le_agent_input, 1)
        input_row.addWidget(self.btn_agent_send)
        hero_layout.addLayout(input_row)
        layout.addWidget(hero)

        control_row = QtWidgets.QHBoxLayout()
        control_row.setSpacing(10)

        plan_box = QtWidgets.QFrame()
        plan_box.setObjectName("agentWorkspaceCard")
        plan_box.setMinimumHeight(334)
        plan_layout = QtWidgets.QVBoxLayout(plan_box)
        plan_layout.setContentsMargins(16, 14, 16, 16)
        plan_layout.setSpacing(10)
        plan_title = QtWidgets.QLabel("当前计划预览")
        plan_title.setObjectName("sectionTitle")
        self.lbl_agent_plan_status = QtWidgets.QLabel("还没有创建任务。")
        self.lbl_agent_plan_status.setObjectName("hint")
        self.lbl_agent_plan_status.setWordWrap(True)
        self.agent_plan_preview = QtWidgets.QListWidget()
        self.agent_plan_preview.setObjectName("agentPlanPreview")
        self.agent_plan_preview.setMinimumHeight(240)
        self.agent_plan_preview.setSpacing(8)
        self.agent_plan_preview.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.agent_plan_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        plan_layout.addWidget(plan_title)
        plan_layout.addWidget(self.lbl_agent_plan_status)
        plan_layout.addWidget(self.agent_plan_preview)
        control_row.addWidget(plan_box, 2)

        confirm_box = QtWidgets.QFrame()
        confirm_box.setObjectName("agentWorkspaceCard")
        confirm_box.setMinimumHeight(334)
        confirm_layout = QtWidgets.QVBoxLayout(confirm_box)
        confirm_layout.setContentsMargins(16, 14, 16, 16)
        confirm_layout.setSpacing(10)
        confirm_title = QtWidgets.QLabel("确认继续")
        confirm_title.setObjectName("sectionTitle")
        self.lbl_agent_confirm_summary = QtWidgets.QLabel("下载前需要人工确认的步骤会显示在这里。")
        self.lbl_agent_confirm_summary.setObjectName("hint")
        self.lbl_agent_confirm_summary.setWordWrap(True)
        self.agent_confirm_preview = QtWidgets.QListWidget()
        self.agent_confirm_preview.setObjectName("agentConfirmList")
        self.agent_confirm_preview.setMinimumHeight(240)
        self.agent_confirm_preview.setSpacing(8)
        self.agent_confirm_preview.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.agent_confirm_preview.setFocusPolicy(QtCore.Qt.NoFocus)
        confirm_layout.addWidget(confirm_title)
        confirm_layout.addWidget(self.lbl_agent_confirm_summary)
        confirm_layout.addWidget(self.agent_confirm_preview)
        control_row.addWidget(confirm_box, 1)
        control_row.setStretch(0, 3)
        control_row.setStretch(1, 2)
        layout.addLayout(control_row)

        status_strip = QtWidgets.QFrame()
        status_strip.setObjectName("agentActionStrip")
        status_layout = QtWidgets.QHBoxLayout(status_strip)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(10)
        self.lbl_agent_status = QtWidgets.QLabel("Agent 就绪")
        self.lbl_agent_status.setObjectName("statusBadge")
        status_layout.addWidget(self.lbl_agent_status)
        status_layout.addStretch()
        self.btn_agent_continue = QtWidgets.QPushButton("继续执行")
        self.btn_agent_continue.setObjectName("primary")
        self.btn_agent_continue.setMinimumWidth(118)
        self.btn_agent_continue.setEnabled(False)
        self.btn_agent_continue.clicked.connect(self._continue_agent_task)
        self.btn_agent_refresh = QtWidgets.QPushButton("刷新状态")
        self.btn_agent_refresh.setObjectName("secondary")
        self.btn_agent_refresh.clicked.connect(self._refresh_agent_status)
        self.btn_agent_test_connection = QtWidgets.QPushButton("测试连接")
        self.btn_agent_test_connection.setObjectName("secondary")
        self.btn_agent_test_connection.clicked.connect(self._test_agent_connection)
        status_layout.addWidget(self.btn_agent_continue)
        status_layout.addWidget(self.btn_agent_test_connection)
        status_layout.addWidget(self.btn_agent_refresh)
        layout.addWidget(status_strip)

        timeline_box = QtWidgets.QFrame()
        timeline_box.setObjectName("agentWorkspaceCard")
        timeline_box.setMinimumHeight(360)
        timeline_layout = QtWidgets.QVBoxLayout(timeline_box)
        timeline_layout.setContentsMargins(16, 14, 16, 16)
        timeline_layout.setSpacing(10)
        timeline_title = QtWidgets.QLabel("活动日志")
        timeline_title.setObjectName("sectionTitle")
        timeline_hint = QtWidgets.QLabel("这里会记录用户请求、Agent 计划、等待确认以及最终完成情况。")
        timeline_hint.setObjectName("hint")
        timeline_hint.setWordWrap(True)
        timeline_layout.addWidget(timeline_title)
        timeline_layout.addWidget(timeline_hint)
        self.agent_chat = QtWidgets.QPlainTextEdit()
        self.agent_chat.setObjectName("agentTimeline")
        self.agent_chat.setReadOnly(True)
        self.agent_chat.setPlaceholderText("Agent 对话记录会显示在这里。")
        self.agent_chat.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.agent_chat.setMinimumHeight(276)
        timeline_layout.addWidget(self.agent_chat, 1)
        layout.addWidget(timeline_box, 1)
        return page

    def _toggle_agent_dock(self) -> None:
        self.tabs.setCurrentIndex(getattr(self, "agent_tab_index", self.tabs.count() - 1))
        self.le_agent_input.setFocus()

    def _append_agent_message(self, role: str, text: str) -> None:
        msg = (text or "").strip()
        if not msg:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self.agent_chat.appendPlainText(f"[{stamp}] {role}\n{msg}\n")
        sb = self.agent_chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _agent_request_workdir(self, text: str) -> str:
        base = Path(self._combo_text(self.cb_workdir) or "./video_info").resolve()
        if any(k in text for k in ["查看状态", "任务状态", "进度", "检查环境", "环境检查"]) and self._agent_last_task_workdir:
            return self._agent_last_task_workdir
        if ("重试" in text or "retry" in text.lower()) and self._agent_last_task_workdir:
            return self._agent_last_task_workdir
        slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", text).strip("._-")[:28] or "agent"
        return str((base / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}").resolve())

    def _submit_agent_request(self) -> None:
        text = self.le_agent_input.text().strip()
        if not text:
            return
        workdir = self._agent_request_workdir(text)
        self._append_agent_message("你", text)
        self.le_agent_input.clear()
        self.lbl_agent_status.setText("Agent 规划中...")
        self._refresh_agent_workspace_preview(
            {
                "title": "正在生成任务计划",
                "status": "planning",
                "steps": [],
            }
        )
        try:
            self.agent_bridge.submit_request(
                text,
                workdir,
                auto_confirm=False,
                defaults=self._current_agent_runtime_config(),
            )
        except Exception as exc:
            self._on_agent_error({"message": str(exc), "user_message": str(exc), "details": {}})

    def _continue_agent_task(self) -> None:
        try:
            self._append_agent_message("系统", "继续执行当前 Agent 任务。")
            self.agent_bridge.continue_current()
        except Exception as exc:
            self._on_agent_error({"message": str(exc), "user_message": str(exc), "details": {}})

    def _refresh_agent_status(self) -> None:
        self.agent_bridge.refresh_current()

    def _test_agent_connection(self) -> None:
        if self._agent_test_thread is not None:
            return
        defaults = self._current_agent_runtime_config()
        self.btn_agent_test_connection.setEnabled(False)
        self.lbl_agent_status.setText("正在测试 Agent 连接...")
        self._append_agent_message("系统", "开始测试 Agent provider 连接。")
        thread = QtCore.QThread(self)
        worker = _AgentConnectionTestWorker(defaults)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_agent_connection_test_finished)
        worker.finished.connect(thread.quit)
        worker.error.connect(self._on_agent_connection_test_error)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._cleanup_agent_connection_test)
        self._agent_test_thread = thread
        self._agent_test_worker = worker
        thread.start()

    def _cleanup_agent_connection_test(self) -> None:
        if self._agent_test_worker is not None:
            self._agent_test_worker.deleteLater()
            self._agent_test_worker = None
        if self._agent_test_thread is not None:
            self._agent_test_thread.deleteLater()
            self._agent_test_thread = None
        if hasattr(self, "btn_agent_test_connection"):
            self.btn_agent_test_connection.setEnabled(True)

    @QtCore.Slot(dict)
    def _on_agent_connection_test_finished(self, payload: dict) -> None:
        provider = str(payload.get("provider") or "-")
        model = str(payload.get("model") or "-")
        message = str(payload.get("message") or "connected")
        self.lbl_agent_status.setText(f"连接成功：{provider} / {model}")
        self._update_agent_runtime_hint("最近测试: 成功")
        self._append_agent_message("系统", f"连接测试成功。provider={provider} model={model} message={message}")
        self.status.showMessage(f"Agent 连接成功：{provider} / {model}", 6000)
        self._show_toast("Agent 连接成功", f"{provider} / {model}", duration_ms=3200)

    @QtCore.Slot(str)
    def _on_agent_connection_test_error(self, message: str) -> None:
        self.lbl_agent_status.setText("Agent 连接测试失败")
        self._update_agent_runtime_hint("最近测试: 失败")
        self._append_agent_message("系统", f"连接测试失败：{message}")
        self.status.showMessage("Agent 连接测试失败", 6000)
        QtWidgets.QMessageBox.warning(self, "Agent 连接测试失败", message)

    @QtCore.Slot(bool)
    def _on_agent_busy_changed(self, busy: bool) -> None:
        self.btn_agent_send.setEnabled(not busy)
        self.le_agent_input.setEnabled(not busy)
        self.btn_agent_refresh.setEnabled(not busy)
        self.btn_agent_test_connection.setEnabled((not busy) and self._agent_test_thread is None)
        self.btn_agent_continue.setEnabled((not busy) and self._agent_pending_confirmation)
        if busy:
            self.lbl_agent_status.setText("Agent 执行中...")
            self.btn_agent_continue.setText("执行中")

    @QtCore.Slot(dict)
    def _on_agent_task_planned(self, task: dict) -> None:
        task = self._remember_agent_task(task)
        self._agent_last_task_id = str(task.get("task_id") or "")
        self._agent_last_task_workdir = str(task.get("workdir") or "")
        self._agent_pending_confirmation = False
        self.lbl_agent_status.setText(f"已创建任务：{task.get('title', 'Agent 任务')}")
        self._refresh_agent_workspace_preview(task)
        self._append_agent_message("Agent", self._format_agent_plan(task))
        self.append_log(f"[Agent] 已创建任务 {task.get('task_id', '-')}: {task.get('title', '-')}\n")
        self._sync_agent_task_to_queue(task)
        if task.get("intent") in {"search_pipeline", "retry_failed_downloads"}:
            self.tabs.setCurrentIndex(1)

    @QtCore.Slot(dict)
    def _on_agent_task_summary(self, summary: dict) -> None:
        task_id = str(summary.get("task_id") or "")
        if not task_id:
            return
        state = self._agent_task_state.get(task_id, {}).copy()
        state.update(summary)
        self._agent_task_state[task_id] = state
        self.lbl_agent_status.setText(f"Agent 状态：{summary.get('status', '-')}")
        self._refresh_agent_workspace_preview(state)
        self._sync_agent_task_to_queue(state)
        current = self._current_task()
        if current is not None and current.agent_task_id == task_id:
            self._refresh_agent_detail_panel(current)

    @QtCore.Slot(dict)
    def _on_agent_task_event(self, event: dict) -> None:
        task_id = str(event.get("task_id") or "")
        message = str(event.get("message") or event.get("event_type") or "").strip()
        if message:
            self.append_log(f"[Agent] {message}\n")
        data = event.get("data") or {}
        state = self._agent_task_state.get(task_id)
        if isinstance(state, dict):
            step_id = str(data.get("step_id") or "")
            if step_id:
                for step in state.get("steps") or []:
                    if step.get("step_id") == step_id:
                        if data.get("status"):
                            step["status"] = data.get("status")
                        if message:
                            step["message"] = message
                        break
                self._sync_agent_task_to_queue(state)
        if message and event.get("event_type") in {"task_status", "step_status"}:
            self._append_agent_message("Agent", message)
        current = self._current_task()
        if current is not None and current.agent_task_id == task_id:
            self._refresh_agent_detail_panel(current)

    @QtCore.Slot(dict)
    def _on_agent_confirmation_required(self, result: dict) -> None:
        self._agent_pending_confirmation = True
        self.btn_agent_continue.setEnabled(True)
        self.btn_agent_continue.setText("确认并继续执行")
        data = result.get("data") or {}
        task = data.get("task") or {}
        if isinstance(task, dict):
            task = self._remember_agent_task(task)
            self._sync_agent_task_to_queue(task)
            self._refresh_agent_workspace_preview(task, result)
        self.lbl_agent_status.setText("等待确认后继续执行")
        self._append_agent_message("Agent", result.get("message", "任务已准备好，等待确认继续执行。"))
        self.status.showMessage("Agent 任务等待确认，可在侧栏点击“继续执行”。", 8000)
        self._show_toast(
            title="Agent 等待确认",
            detail="下载步骤已准备好，可继续执行。",
            action_text="打开 Agent 页",
            action=lambda: self.tabs.setCurrentIndex(getattr(self, "agent_tab_index", self.tabs.count() - 1)),
            duration_ms=4500,
        )

    @QtCore.Slot(dict)
    def _on_agent_completed(self, result: dict) -> None:
        self._agent_pending_confirmation = False
        self.btn_agent_continue.setEnabled(False)
        self.btn_agent_continue.setText("继续执行")
        data = result.get("data") or {}
        task = data.get("task") or {}
        if isinstance(task, dict):
            task = self._remember_agent_task(task)
            self._sync_agent_task_to_queue(task)
            self._refresh_agent_workspace_preview(task, result)
            self._agent_last_task_id = str(task.get("task_id") or self._agent_last_task_id)
            self._agent_last_task_workdir = str(task.get("workdir") or self._agent_last_task_workdir)
        self.lbl_agent_status.setText(f"Agent 完成：{result.get('status', '-')}")
        self._append_agent_message("Agent", self._format_agent_result(result))
        self.status.showMessage(str(result.get("message") or "Agent 任务已完成。"), 8000)
        self.refresh_downloaded_view()
        self._refresh_queue_list()
        current = self._current_task()
        if current is not None and current.agent_task_id:
            self._refresh_agent_detail_panel(current)

    @QtCore.Slot(dict)
    def _on_agent_error(self, payload: dict) -> None:
        message = self._format_agent_error_message(payload)
        self._agent_pending_confirmation = False
        self.btn_agent_continue.setEnabled(False)
        self.btn_agent_continue.setText("继续执行")
        self.lbl_agent_status.setText("Agent 执行失败")
        self._update_agent_runtime_hint("最近规划/执行: 失败")
        if hasattr(self, "lbl_agent_confirm_summary"):
            self.lbl_agent_confirm_summary.setText(f"执行失败：{message}")
        if hasattr(self, "lbl_agent_plan_status"):
            self.lbl_agent_plan_status.setText(self._format_agent_error_title(payload))
        self._append_agent_message("Agent", f"执行失败：{message}")
        self.append_log(f"[Agent][ERROR] {message}\n")
        self.status.showMessage(f"Agent 执行失败：{message}", 8000)

    def _format_agent_error_title(self, payload: dict[str, Any]) -> str:
        code = str(payload.get("code") or "")
        mapping = {
            "planner_config_error": "计划生成失败 · 配置缺失",
            "planner_connection_error": "计划生成失败 · Provider 连接异常",
            "planner_response_error": "计划生成失败 · LLM 返回异常",
            "planner_schema_error": "计划生成失败 · 计划结构无效",
        }
        return mapping.get(code, "Agent 执行失败")

    def _format_agent_error_message(self, payload: dict[str, Any]) -> str:
        user_message = str(payload.get("user_message") or "").strip()
        details = payload.get("details") or {}
        parts: list[str] = [user_message or str(payload.get("message") or "Agent 执行失败")]
        provider = str(details.get("provider") or "").strip()
        endpoint = str(details.get("endpoint") or "").strip()
        http_status = str(details.get("http_status") or "").strip()
        if provider:
            parts.append(f"provider={provider}")
        if http_status:
            parts.append(f"HTTP {http_status}")
        if endpoint:
            parts.append(endpoint)
        return " | ".join(parts)

    def _format_agent_plan(self, task: dict) -> str:
        steps = task.get("steps") or []
        lines = [
            f"已创建任务：{task.get('title', 'Agent 任务')}",
            f"意图：{task.get('intent', '-')}",
            "计划步骤：",
        ]
        for idx, step in enumerate(steps, start=1):
            title = step.get("title") or step.get("tool_name") or "-"
            suffix = "（需确认）" if step.get("requires_confirmation") else ""
            lines.append(f"{idx}. {title}{suffix}")
        return "\n".join(lines)

    def _refresh_agent_workspace_preview(self, task: Optional[dict], result: Optional[dict] = None) -> None:
        if not hasattr(self, "agent_plan_preview"):
            return
        self.agent_plan_preview.clear()
        self.agent_confirm_preview.clear()
        if not task:
            self.lbl_agent_plan_status.setText("还没有创建任务。")
            self.lbl_agent_confirm_summary.setText("下载前需要人工确认的步骤会显示在这里。")
            self._add_agent_empty_state(
                self.agent_plan_preview,
                "等待输入请求",
                "输入一句自然语言请求后，Agent 会在这里给出步骤拆解、执行顺序和状态变化。",
            )
            self._add_agent_empty_state(
                self.agent_confirm_preview,
                "暂无确认边界",
                "当任务涉及下载、覆盖目录或其他需要人工确认的动作时，这里会出现确认卡。",
            )
            return

        title = str(task.get("title") or "Agent 任务")
        status = str(task.get("status") or "-")
        steps = task.get("steps") or []
        self.lbl_agent_plan_status.setText(f"{title} · 当前状态 {status}")
        confirm_count = 0
        if isinstance(steps, list) and steps:
            for idx, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                step_title = str(step.get("title") or step.get("tool_name") or f"Step {idx}")
                step_status = str(step.get("status") or "pending")
                if step.get("requires_confirmation"):
                    confirm_count += 1
                    self._add_agent_confirm_card(
                        self.agent_confirm_preview,
                        idx,
                        step_title,
                        "待确认",
                        "这个步骤触发了人工确认边界，当前已暂停，等待人工明确授权后继续。",
                        "确认后 Agent 会继续向下载或结果落地阶段推进，并写入对应任务目录。",
                    )
                detail = self._agent_step_detail(step_status, bool(step.get("requires_confirmation")))
                self._add_agent_step_card(
                    self.agent_plan_preview,
                    idx,
                    step_title,
                    self._step_status_text(step_status),
                    detail,
                    variant=self._step_status_variant(step_status, bool(step.get("requires_confirmation"))),
                )
        else:
            self._add_agent_empty_state(
                self.agent_plan_preview,
                "计划暂未展开",
                "Agent 已经收到任务，但当前还没有返回可展示的步骤清单。",
            )

        if confirm_count == 0:
            self._add_agent_empty_state(
                self.agent_confirm_preview,
                "当前可直接推进",
                "这份计划暂时没有命中需要人工确认的步骤，可以直接让 Agent 继续执行。",
            )
            self.lbl_agent_confirm_summary.setText("这个任务可以直接执行到结果阶段。")
        else:
            self.lbl_agent_confirm_summary.setText(f"当前计划里有 {confirm_count} 个确认步骤。每项卡片都会说明暂停原因和确认后的执行影响。")

        if result and isinstance(result, dict):
            message = str(result.get("message") or "").strip()
            if message:
                self.lbl_agent_confirm_summary.setText(message)
        if status == "awaiting_confirmation":
            self.btn_agent_continue.setText("确认并继续执行")
        elif status in {"planning", "planned", "running"}:
            self.btn_agent_continue.setText("等待可继续")
        else:
            self.btn_agent_continue.setText("继续执行")

    def _step_status_text(self, status: str) -> str:
        s = (status or "").strip().lower()
        if s in {"completed", "succeeded"}:
            return "已完成"
        if s == "running":
            return "执行中"
        if s == "awaiting_confirmation":
            return "待确认"
        if s in {"failed", "error"}:
            return "执行失败"
        return "待开始"

    def _step_status_variant(self, status: str, requires_confirmation: bool = False) -> str:
        if requires_confirmation:
            return "confirm"
        s = (status or "").strip().lower()
        if s in {"completed", "succeeded"}:
            return "success"
        if s == "running":
            return "info"
        if s == "awaiting_confirmation":
            return "warning"
        if s in {"failed", "error"}:
            return "danger"
        return "muted"

    def _agent_step_detail(self, status: str, requires_confirmation: bool = False) -> str:
        if requires_confirmation:
            return "命中确认边界，等待你明确同意后再继续。"
        s = (status or "").strip().lower()
        if s in {"completed", "succeeded"}:
            return "这个步骤已经完成，结果已经进入后续流程。"
        if s == "running":
            return "Agent 正在执行这个步骤，请关注下方活动日志。"
        if s == "awaiting_confirmation":
            return "这个步骤需要你的确认，继续按钮会在可执行时高亮。"
        if s in {"failed", "error"}:
            return "这个步骤执行失败，请结合日志定位原因。"
        return "步骤已排入计划，等待前序步骤完成后执行。"

    def _add_agent_empty_state(self, target: QtWidgets.QListWidget, title: str, detail: str) -> None:
        card = self._build_empty_state_card("agentEmptyState", "agentEmptyTitle", "agentEmptyDetail", title, detail)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setSizeHint(QtCore.QSize(320, 88))
        target.addItem(item)
        target.setItemWidget(item, card)

    def _add_list_empty_state(
        self,
        target: QtWidgets.QListWidget,
        title: str,
        detail: str,
        *,
        width: int = 360,
        height: int = 94,
    ) -> None:
        card = self._build_empty_state_card("listEmptyState", "listEmptyTitle", "listEmptyDetail", title, detail)
        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setSizeHint(QtCore.QSize(width, height))
        target.addItem(item)
        target.setItemWidget(item, card)

    def _build_empty_state_card(
        self,
        frame_name: str,
        title_name: str,
        detail_name: str,
        title: str,
        detail: str,
    ) -> QtWidgets.QFrame:
        card = QtWidgets.QFrame()
        card.setObjectName(frame_name)
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName(title_name)
        detail_label = QtWidgets.QLabel(detail)
        detail_label.setObjectName(detail_name)
        detail_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)
        return card

    def _add_agent_step_card(
        self,
        target: QtWidgets.QListWidget,
        idx: int,
        title: str,
        status_text: str,
        detail: str,
        variant: str = "muted",
    ) -> None:
        card = QtWidgets.QFrame()
        card.setObjectName(f"agentStepCard{variant.capitalize()}")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)
        index_label = QtWidgets.QLabel(f"{idx:02d}")
        index_label.setObjectName("agentStepIndex")
        top.addWidget(index_label, 0, QtCore.Qt.AlignTop)
        text_col = QtWidgets.QVBoxLayout()
        text_col.setSpacing(4)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("agentStepTitle")
        title_label.setWordWrap(True)
        detail_label = QtWidgets.QLabel(detail)
        detail_label.setObjectName("agentStepDetail")
        detail_label.setWordWrap(True)
        text_col.addWidget(title_label)
        text_col.addWidget(detail_label)
        top.addLayout(text_col, 1)
        status_label = QtWidgets.QLabel(status_text)
        status_label.setObjectName(f"agentStepBadge{variant.capitalize()}")
        top.addWidget(status_label, 0, QtCore.Qt.AlignTop)
        layout.addLayout(top)

        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setSizeHint(QtCore.QSize(360, 94))
        target.addItem(item)
        target.setItemWidget(item, card)

    def _add_agent_confirm_card(
        self,
        target: QtWidgets.QListWidget,
        idx: int,
        title: str,
        status_text: str,
        detail: str,
        impact: str,
    ) -> None:
        card = QtWidgets.QFrame()
        card.setObjectName("agentConfirmDecisionCard")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)
        number_label = QtWidgets.QLabel(f"确认 {idx:02d}")
        number_label.setObjectName("agentConfirmPill")
        top.addWidget(number_label, 0, QtCore.Qt.AlignTop)
        top.addStretch(1)
        status_label = QtWidgets.QLabel(status_text)
        status_label.setObjectName("agentConfirmState")
        top.addWidget(status_label, 0, QtCore.Qt.AlignTop)
        layout.addLayout(top)

        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("agentConfirmTitle")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        detail_label = QtWidgets.QLabel(detail)
        detail_label.setObjectName("agentConfirmDetail")
        detail_label.setWordWrap(True)
        layout.addWidget(detail_label)

        impact_card = QtWidgets.QFrame()
        impact_card.setObjectName("agentConfirmImpact")
        impact_layout = QtWidgets.QVBoxLayout(impact_card)
        impact_layout.setContentsMargins(10, 9, 10, 9)
        impact_layout.setSpacing(4)
        impact_head = QtWidgets.QLabel("确认后将执行")
        impact_head.setObjectName("agentConfirmImpactTitle")
        impact_body = QtWidgets.QLabel(impact)
        impact_body.setObjectName("agentConfirmImpactDetail")
        impact_body.setWordWrap(True)
        impact_layout.addWidget(impact_head)
        impact_layout.addWidget(impact_body)
        layout.addWidget(impact_card)

        item = QtWidgets.QListWidgetItem()
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setSizeHint(QtCore.QSize(420, 196))
        target.addItem(item)
        target.setItemWidget(item, card)

    def _format_agent_result(self, result: dict) -> str:
        lines = [str(result.get("message") or "Agent 任务已完成。")]
        data = result.get("data") or {}
        step_results = data.get("step_results") or {}
        if isinstance(step_results, dict) and step_results:
            keys = ", ".join(step_results.keys())
            lines.append(f"已完成步骤：{keys}")
        task_paths = data.get("task_paths") or {}
        if isinstance(task_paths, dict) and task_paths.get("task_dir"):
            lines.append(f"任务目录：{task_paths.get('task_dir')}")
        return "\n".join(lines)

    def _remember_agent_task(self, task: dict) -> dict:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            return task
        merged = dict(self._agent_task_state.get(task_id, {}))
        for key, value in task.items():
            if key == "steps" and not value and merged.get("steps"):
                continue
            merged[key] = value
        self._agent_task_state[task_id] = merged
        return merged

    def _find_queue_task_index_by_run_id(self, run_id: str) -> Optional[int]:
        for idx, task in enumerate(self.task_queue):
            if task.run_id == run_id:
                return idx
        return None

    def _map_agent_task_status(self, task: dict) -> str:
        status = str(task.get("status") or "")
        steps = task.get("steps") or []
        workdir = str(task.get("workdir") or "")
        selected_count = self._count_selected_urls(workdir) if workdir else 0
        if status in {"planned", "draft"}:
            return "pending"
        if status == "running":
            for step in steps:
                if step.get("tool_name") == "start_download" and step.get("status") == "running":
                    return "downloading"
            return "running"
        if status == "awaiting_confirmation":
            return "ready_download" if selected_count > 0 else "running"
        if status == "succeeded":
            has_download = any(step.get("tool_name") == "start_download" for step in steps)
            if has_download:
                return "downloaded"
            return "ready_download" if selected_count > 0 else "filtered_empty"
        if status == "failed":
            for step in steps:
                if step.get("tool_name") == "start_download" and step.get("status") == "failed":
                    return "download_failed"
            return "failed"
        if status == "cancelled":
            return "stopped"
        return "pending"

    def _sync_agent_task_to_queue(self, task: dict) -> None:
        intent = str(task.get("intent") or "")
        if intent not in {"search_pipeline", "retry_failed_downloads"}:
            return
        task_id = str(task.get("task_id") or "")
        if not task_id:
            return
        workdir = str(task.get("workdir") or "")
        params = task.get("params") or {}
        idx = self._find_queue_task_index_by_run_id(task_id)
        selected_count = self._count_selected_urls(workdir) if workdir else 0
        queue_status = self._map_agent_task_status(task)
        task_name = str(params.get("query") or task.get("title") or "Agent 任务")
        max_height = params.get("max_height")
        payload = dict(
            args=[],
            task_name=task_name,
            workdir=workdir,
            run_id=task_id,
            download_dir=str(params.get("download_dir") or (Path(workdir) / "downloads")),
            cookies_browser=str(params.get("cookies_from_browser") or ""),
            cookies_file=str(params.get("cookies_file") or ""),
            yt_extra_args=" ".join(str(x) for x in (params.get("extra_args") or [])),
            download_mode=str(params.get("download_mode") or "video"),
            include_audio=bool(params.get("include_audio", True)),
            video_container=str(params.get("video_container") or "auto"),
            max_height=str(max_height) if max_height else "1080",
            audio_format=str(params.get("audio_format") or "best"),
            audio_quality=int(params.get("audio_quality") or 2),
            clean_video=bool(params.get("sponsorblock_remove")),
            sponsorblock_remove=str(params.get("sponsorblock_remove") or ""),
            concurrent_videos=int(params.get("concurrent_videos") or 1),
            concurrent_fragments=int(params.get("concurrent_fragments") or 4),
            download_session_name=str(params.get("download_session_name") or ""),
            status=queue_status,
            selected_count=selected_count,
            origin="agent",
            agent_task_id=task_id,
        )
        if idx is None:
            self.task_queue.append(QueueTask(**payload))
        else:
            qt = self.task_queue[idx]
            for key, value in payload.items():
                setattr(qt, key, value)
        self._refresh_queue_list()

    def show_log_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        act_copy = menu.addAction("复制")
        act_select_all = menu.addAction("全选")
        menu.addSeparator()
        act_clear = menu.addAction("清空日志")
        chosen = menu.exec(self.te_log.mapToGlobal(pos))
        if chosen == act_copy:
            self.te_log.copy()
        elif chosen == act_select_all:
            self.te_log.selectAll()
        elif chosen == act_clear:
            self.te_log.clear()

    def _set_maint_buttons_enabled(self, enabled: bool) -> None:
        self.btn_check_tools.setEnabled(enabled)
        self.btn_update_ytdlp.setEnabled(enabled)
        self.btn_update_ffmpeg.setEnabled(enabled)

    def _run_maintenance(self, action_name: str, program: str, args: list[str]) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "任务执行中", "请先等待当前筛选/下载任务完成。")
            return
        if self.maint_proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.information(self, "维护进行中", "当前已有维护任务在执行，请稍后。")
            return
        self.maint_action_name = action_name
        self._set_maint_buttons_enabled(False)
        self.append_log(f"\n[维护] 开始: {action_name}\n")
        self.maint_proc.setWorkingDirectory(str(Path(__file__).parent))
        self.maint_proc.start(program, args)
        self.status.showMessage(f"维护任务执行中: {action_name}", 5000)

    def _on_maint_ready(self) -> None:
        data = self.maint_proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        if text:
            self.append_log(text)

    def _on_maint_finished(self, code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        self.append_log(f"[维护] 结束: {self.maint_action_name} | 退出码: {code}\n")
        ok = code == 0
        self.status.showMessage(
            f"{'成功' if ok else '失败'}: {self.maint_action_name}",
            6000,
        )
        self._set_maint_buttons_enabled(True)
        if self.maint_action_name in {"检查版本", "妫€鏌ョ増鏈?", "更新 yt-dlp", "更新 ffmpeg"}:
            self._check_tools_after_maint()

    def _check_tools_after_maint(self) -> None:
        # 异步版本检查：避免阻塞主线程导致界面卡顿
        if self.tool_check_proc.state() != QtCore.QProcess.NotRunning:
            return
        if not self.cfg.python_exe:
            self.lbl_tools_summary.setText("状态: 未找到系统 Python，无法检查/更新 yt-dlp")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("warning"))
            self.lbl_ytdlp_ver.setText("yt-dlp 当前: 未知 | 最新: 未知 | 更新状态: 需安装 Python")
            self.lbl_ffmpeg_ver.setText("ffmpeg 当前: 未检查 | 最新: 未检查 | 更新状态: 未检查")
            self.lbl_tools_checked_at.setText(
                f"最后检查: {QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}"
            )
            return
        script = self._build_tool_check_script()
        self._tool_check_output = ""
        self.lbl_tools_summary.setText("状态: 正在后台检查版本...")
        self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("info"))
        self.tool_check_proc.setWorkingDirectory(str(Path(__file__).parent))
        self.tool_check_proc.start(self.cfg.python_exe, ["-c", script])

    def _build_tool_check_script(self) -> str:
        return (
            "import subprocess,sys,shutil,re\n"
            "def dec(b):\n"
            "  for enc in ('utf-8','gbk','utf-16-le','utf-16'):\n"
            "    try:\n"
            "      return b.decode(enc)\n"
            "    except Exception:\n"
            "      pass\n"
            "  return b.decode('utf-8','replace')\n"
            "def run(cmd):\n"
            "  try:\n"
            "    p=subprocess.run(cmd,capture_output=True,text=False)\n"
            "    txt=(dec(p.stdout or b'') + '\\n' + dec(p.stderr or b'')).strip()\n"
            "    return p.returncode, txt\n"
            "  except Exception:\n"
            "    return 1, ''\n"
            "def strip_ansi(s):\n"
            "  return re.sub(r'\\x1b\\[[0-9;]*[A-Za-z]', '', s)\n"
            "def first_line(s):\n"
            "  return s.splitlines()[0].strip() if s else ''\n"
            "def ver_tuple(v):\n"
            "  nums=re.findall(r'\\d+', v or '')\n"
            "  return tuple(int(x) for x in nums)\n"
            "def need_update(cur, latest):\n"
            "  if not cur or not latest:\n"
            "    return False\n"
            "  c=ver_tuple(cur)\n"
            "  l=ver_tuple(latest)\n"
            "  if not c or not l:\n"
            "    return False\n"
            "  n=max(len(c), len(l))\n"
            "  c=c+(0,)*(n-len(c))\n"
            "  l=l+(0,)*(n-len(l))\n"
            "  return c<l\n"
            "rc, ytxt = run([sys.executable,'-m','yt_dlp','--version'])\n"
            "y_cur = first_line(ytxt) if rc==0 else ''\n"
            "rc2, pipv = run([sys.executable,'-m','pip','index','versions','yt-dlp'])\n"
            "y_latest = ''\n"
            "if rc2==0:\n"
            "  m=re.search(r'Available versions:\\s*(.+)', pipv)\n"
            "  if m:\n"
            "    y_latest=(m.group(1).split(',')[0].strip())\n"
            "ff_path = shutil.which('ffmpeg') or ''\n"
            "f_cur = ''\n"
            "if ff_path:\n"
            "  rc3, fftxt = run(['ffmpeg','-version'])\n"
            "  if rc3==0:\n"
            "    m2=re.search(r'ffmpeg version\\s+([^\\s]+)', first_line(fftxt))\n"
            "    f_cur = m2.group(1) if m2 else first_line(fftxt)\n"
            "    f_cur = re.sub(r'[^0-9A-Za-z._\\-+]+','', f_cur)\n"
            "f_latest = ''\n"
            "rc4, wing = run(['winget','show','--id','Gyan.FFmpeg','-e','--accept-source-agreements'])\n"
            "if rc4==0:\n"
            "  wing=strip_ansi(wing)\n"
            "  m3=re.search(r'(?im)^(?:Version|版本)\\s*:\\s*(\\S+)', wing)\n"
            "  if m3:\n"
            "    cand=m3.group(1).strip()\n"
            "    if re.search(r'\\d', cand):\n"
            "      f_latest=re.sub(r'[^0-9A-Za-z._\\-+]+','', cand)\n"
            "if not f_latest:\n"
            "  rc5, ch = run(['choco','info','ffmpeg'])\n"
            "  if rc5==0:\n"
            "    ch=strip_ansi(ch)\n"
            "    m4=re.search(r'(?im)^Latest Version\\s*:\\s*(\\S+)', ch)\n"
            "    if m4:\n"
            "      cand=m4.group(1).strip()\n"
            "      if re.search(r'\\d', cand):\n"
            "        f_latest=re.sub(r'[^0-9A-Za-z._\\-+]+','', cand)\n"
            "print('YTDLP_OK=' + ('1' if y_cur else '0'))\n"
            "print('YTDLP_CURRENT=' + (y_cur if y_cur else 'UNAVAILABLE'))\n"
            "print('YTDLP_LATEST=' + (y_latest if y_latest else 'UNKNOWN'))\n"
            "print('YTDLP_NEEDS_UPDATE=' + ('1' if need_update(y_cur,y_latest) else '0'))\n"
            "print('YTDLP_PATH=' + sys.executable)\n"
            "print('FFMPEG_OK=' + ('1' if f_cur else '0'))\n"
            "print('FFMPEG_CURRENT=' + (f_cur if f_cur else 'UNAVAILABLE'))\n"
            "print('FFMPEG_LATEST=' + (f_latest if f_latest else 'UNKNOWN'))\n"
            "print('FFMPEG_NEEDS_UPDATE=' + ('1' if need_update(f_cur,f_latest) else '0'))\n"
            "print('FFMPEG_PATH=' + (ff_path if ff_path else 'NOT_FOUND'))\n"
        )

    @QtCore.Slot()
    def _on_tool_check_ready(self) -> None:
        data = self.tool_check_proc.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        if text:
            self._tool_check_output += text

    @QtCore.Slot(int, QtCore.QProcess.ExitStatus)
    def _on_tool_check_finished(self, _code: int, _status: QtCore.QProcess.ExitStatus) -> None:
        self._apply_tool_check_result(self._tool_check_output)
        self.append_log("[维护] 检查完成。\n")

    def _apply_tool_check_result(self, text: str) -> None:
        info: dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()

        y_ok = info.get("YTDLP_OK", "0") == "1"
        f_ok = info.get("FFMPEG_OK", "0") == "1"
        y_cur = info.get("YTDLP_CURRENT", "UNAVAILABLE")
        y_latest = info.get("YTDLP_LATEST", "UNKNOWN")
        y_need = info.get("YTDLP_NEEDS_UPDATE", "0") == "1"
        y_path = info.get("YTDLP_PATH", "UNKNOWN")
        f_cur = info.get("FFMPEG_CURRENT", "UNAVAILABLE")
        f_latest = info.get("FFMPEG_LATEST", "UNKNOWN")
        f_need = info.get("FFMPEG_NEEDS_UPDATE", "0") == "1"
        f_path = info.get("FFMPEG_PATH", "NOT_FOUND")

        y_cur = {"UNAVAILABLE": "不可用"}.get(y_cur, y_cur)
        y_latest = {"UNKNOWN": "未知"}.get(y_latest, y_latest)
        y_path = {"UNKNOWN": "未知"}.get(y_path, y_path)
        f_cur = {"UNAVAILABLE": "不可用"}.get(f_cur, f_cur)
        f_latest = {"UNKNOWN": "未知"}.get(f_latest, f_latest)
        f_path = {"NOT_FOUND": "未找到", "UNKNOWN": "未知"}.get(f_path, f_path)

        # 当在线检查最新版本失败时，至少给出可理解的本地兜底
        if f_latest == "未知" and f_cur not in {"", "不可用"}:
            f_latest = f_cur
            f_need = False

        # UI 兜底：如果“最新版本”不是有效版本号，则显示未知并取消更新提示
        if not re.search(r"\d", y_latest):
            y_latest = "未知"
            y_need = False
        if not re.search(r"\d", f_latest):
            f_latest = "未知"
            f_need = False

        y_status = "需要更新" if y_need else ("已最新" if y_ok and y_latest != "未知" else ("可用" if y_ok else "异常"))
        f_status = "需要更新" if f_need else ("已最新" if f_ok and f_latest != "未知" else ("可用" if f_ok else "异常"))
        self.lbl_ytdlp_ver.setText(
            f"yt-dlp 当前: {y_cur} | 最新: {y_latest} | 更新状态: {y_status} | 解释器: {y_path}"
        )
        self.lbl_ffmpeg_ver.setText(
            f"ffmpeg 当前: {f_cur} | 最新: {f_latest} | 更新状态: {f_status} | 路径: {f_path}"
        )
        now = QtCore.QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")
        self.lbl_tools_checked_at.setText(f"最后检查: {now}")

        if (y_ok and not y_need) and (f_ok and not f_need):
            self.lbl_tools_summary.setText("状态: 两个工具均可用且已是最新")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("success"))
        elif y_ok and f_ok and (y_need or f_need):
            self.lbl_tools_summary.setText("状态: 工具可用，但存在可更新版本")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("warning"))
        elif y_ok and not f_ok:
            self.lbl_tools_summary.setText("状态: yt-dlp 可用，ffmpeg 缺失/异常")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("warning"))
        elif (not y_ok) and f_ok:
            self.lbl_tools_summary.setText("状态: ffmpeg 可用，yt-dlp 异常")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("warning"))
        else:
            self.lbl_tools_summary.setText("状态: yt-dlp 与 ffmpeg 均异常或缺失")
            self.lbl_tools_summary.setStyleSheet(ui_theme.tools_summary_style("danger"))

    def on_check_tools(self) -> None:
        self.append_log("\n[维护] 检查版本...\n")
        self._check_tools_after_maint()

    def on_update_ytdlp(self) -> None:
        if not self.cfg.python_exe:
            QtWidgets.QMessageBox.warning(self, "缺少 Python", "未找到系统 Python，无法更新 yt-dlp。")
            return
        self._run_maintenance(
            "更新 yt-dlp",
            self.cfg.python_exe,
            ["-m", "pip", "install", "-U", "yt-dlp[default]"],
        )

    def on_update_ffmpeg(self) -> None:
        cmd = (
            "$ErrorActionPreference='Continue';"
            "$ok=$false;"
            "if (Get-Command winget -ErrorAction SilentlyContinue) {"
            "  winget upgrade --id Gyan.FFmpeg -e --silent --accept-source-agreements --accept-package-agreements;"
            "  if ($LASTEXITCODE -eq 0) {$ok=$true}"
            "};"
            "if (-not $ok -and (Get-Command choco -ErrorAction SilentlyContinue)) {"
            "  choco upgrade ffmpeg -y;"
            "  if ($LASTEXITCODE -eq 0) {$ok=$true}"
            "};"
            "if (-not $ok) {"
            "  Write-Output '未能自动更新 ffmpeg（未找到 winget/choco 或执行失败）。';"
            "  exit 1"
            "}"
        )
        self._run_maintenance("更新 ffmpeg", "powershell", ["-NoProfile", "-Command", cmd])

    def append_log(self, text: str) -> None:
        self.te_log.moveCursor(QtGui.QTextCursor.End)
        self.te_log.insertPlainText(text)
        self.te_log.moveCursor(QtGui.QTextCursor.End)
        self._consume_log_for_progress(text)

    def _consume_log_for_progress(self, text: str) -> None:
        self._log_line_buffer += text.replace("\r", "\n")
        while "\n" in self._log_line_buffer:
            line, self._log_line_buffer = self._log_line_buffer.split("\n", 1)
            self._parse_progress_line(line.rstrip("\r"))

    def _size_to_bytes(self, size_text: str) -> Optional[float]:
        m = re.match(r"(?i)^([0-9]+(?:\.[0-9]+)?)([kmgti]?i?b)$", size_text.strip())
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2).lower()
        scales = {
            "b": 1,
            "kib": 1024,
            "mib": 1024**2,
            "gib": 1024**3,
            "tib": 1024**4,
            "kb": 1000,
            "mb": 1000**2,
            "gb": 1000**3,
            "tb": 1000**4,
        }
        mul = scales.get(unit)
        if mul is None:
            return None
        return num * mul

    def _bytes_to_mib(self, b: float) -> str:
        return f"{b / (1024**2):.2f}MiB"

    def _format_duration(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return "-"
        if not s.isdigit():
            return s
        sec = int(s)
        if sec < 60:
            return f"{sec}秒"
        m, ss = divmod(sec, 60)
        if m < 60:
            return f"{m}分{ss:02d}秒"
        h, mm = divmod(m, 60)
        return f"{h}小时{mm:02d}分{ss:02d}秒"

    def _format_speed_mibs(self, raw: str) -> str:
        s = (raw or "").strip()
        if not s or s in {"NA", "None", "null", "-"}:
            return "-"
        try:
            # [PROG] 中 speed 是 bytes/s 数值
            v = float(s)
            if v < 0:
                return "-"
            return f"{(v / (1024**2)):.2f}MB/s"
        except Exception:
            m = re.match(r"(?i)^([0-9]+(?:\.[0-9]+)?)\s*([kmg]?i?b)/s$", s)
            if not m:
                return s
            num = float(m.group(1))
            unit = m.group(2).lower()
            scale = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "kib": 1024, "mib": 1024**2, "gib": 1024**3}
            bps = num * scale.get(unit, 1)
            return f"{(bps / (1024**2)):.2f}MB/s"

    def _clear_active_task_cards(self) -> None:
        while self.grid_active_tasks.count():
            it = self.grid_active_tasks.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._active_task_widgets.clear()
        self._active_task_order = []
        self._taskno_to_vid = {}
        self._vid_to_label = {}

    def _ensure_active_task_card(self, vid: str, label: str) -> None:
        key = (vid or "").strip()
        if not key:
            return
        if key in self._active_task_widgets:
            title = self._active_task_widgets[key]["title"]
            if isinstance(title, QtWidgets.QLabel) and label:
                title.setText(label[:42])
                title.setToolTip(label)
            return
        if len(self._active_task_order) >= 8:
            old = self._active_task_order.pop(0)
            old_w = self._active_task_widgets.pop(old, None)
            if old_w and isinstance(old_w.get("card"), QtWidgets.QWidget):
                old_w["card"].deleteLater()
            self._reflow_active_cards()
        card = QtWidgets.QFrame()
        card.setStyleSheet(ui_theme.active_task_card_style())
        v = QtWidgets.QVBoxLayout(card)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        lbl_title = QtWidgets.QLabel((label or f"id={key}")[:42])
        lbl_title.setToolTip(label or f"id={key}")
        lbl_title.setStyleSheet(ui_theme.active_task_title_style())
        bar = QtWidgets.QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat("0%")
        lbl_meta = QtWidgets.QLabel("等待进度...")
        lbl_meta.setObjectName("hint")
        v.addWidget(lbl_title)
        v.addWidget(bar)
        v.addWidget(lbl_meta)
        self._active_task_widgets[key] = {"card": card, "title": lbl_title, "bar": bar, "meta": lbl_meta}
        self._active_task_order.append(key)
        self._reflow_active_cards()

    def _reflow_active_cards(self) -> None:
        while self.grid_active_tasks.count():
            self.grid_active_tasks.takeAt(0)
        for i, vid in enumerate(self._active_task_order):
            w = self._active_task_widgets.get(vid, {}).get("card")
            if isinstance(w, QtWidgets.QWidget):
                self.grid_active_tasks.addWidget(w, i // 4, i % 4)

    def _update_active_task_card(
        self,
        vid: str,
        label: str,
        pct: Optional[int] = None,
        speed: str = "-",
        downloaded: str = "-",
        total: str = "-",
        status: str = "",
    ) -> None:
        key = (vid or "").strip()
        if not key:
            return
        status_text = (status or "").strip()
        if ("成功" in status_text) or ("失败" in status_text):
            refs = self._active_task_widgets.pop(key, None)
            if key in self._active_task_order:
                self._active_task_order.remove(key)
            if refs and isinstance(refs.get("card"), QtWidgets.QWidget):
                refs["card"].deleteLater()
            self._reflow_active_cards()
            if self._active_task_order:
                pv = self._active_task_order[0]
                self._current_video_label = self._vid_to_label.get(pv, f"id={pv}")
            else:
                self._current_video_label = "-"
                self.progress_current.setValue(0)
                self.progress_current.setFormat("待开始")
                self.lbl_download_metrics.setText("当前视频: - | 已下载: - / - | 速度: -")
            return
        self._ensure_active_task_card(key, label or f"id={key}")
        refs = self._active_task_widgets.get(key, {})
        bar = refs.get("bar")
        meta = refs.get("meta")
        if isinstance(bar, QtWidgets.QProgressBar) and pct is not None:
            p = max(0, min(100, int(pct)))
            bar.setValue(p)
            bar.setFormat(f"{p}%")
        if isinstance(meta, QtWidgets.QLabel):
            st = f" | {status}" if status else ""
            meta.setText(f"{downloaded} / {total} | {self._format_speed_mibs(speed)}{st}")

    def _parse_progress_line(self, line: str) -> None:
        s = line.strip()
        if not s:
            return

        m_q_start = re.search(
            r"\[Q\]\s*开始任务\s+(\d+)/(\d+)(?:\s*\|\s*视频数:\s*\d+)?(?:\s*\|\s*视频:\s*(.*?))?(?:\s*\|\s*id:\s*([^\s|]+))?$",
            s,
        )
        if m_q_start:
            cur = int(m_q_start.group(1))
            total = max(1, int(m_q_start.group(2)))
            video_label = (m_q_start.group(3) or "").strip()
            vid = (m_q_start.group(4) or "").strip()
            if video_label:
                self._current_video_label = video_label
            if vid and vid != "-":
                self._taskno_to_vid[cur] = vid
                if video_label:
                    self._vid_to_label[vid] = video_label
                self._ensure_active_task_card(vid, self._vid_to_label.get(vid, video_label or f"id={vid}"))
                if self._active_task_order and self._active_task_order[0] == vid:
                    self._current_video_label = self._vid_to_label.get(vid, video_label or f"id={vid}")
            self._queue_total = total
            self._queue_done = max(self._queue_done, cur - 1)
            pct = int((self._queue_done / total) * 100)
            self.progress_queue.setValue(max(0, min(100, pct)))
            self.progress_queue.setFormat(f"{pct}%")
            self.lbl_progress_status.setText(f"阶段 4/4: 并发下载队列中 {self._queue_done}/{total}")
            self.lbl_queue_metrics.setText(f"队列: {self._queue_done}/{total}")
            return

        m_q_done = re.search(
            r"\[Q\]\s*完成任务\s+(\d+)/(\d+)\s+\|\s+状态:\s*(.*?)\s*(?:\|\s*视频:\s*(.*?))?(?:\s*\|\s*id:\s*([^\s|]+))?$",
            s,
        )
        if m_q_done:
            cur = int(m_q_done.group(1))
            total = max(1, int(m_q_done.group(2)))
            status = m_q_done.group(3).strip()
            video_label = (m_q_done.group(4) or "").strip()
            vid = (m_q_done.group(5) or "").strip() or self._taskno_to_vid.get(cur, "")
            if vid and video_label:
                self._vid_to_label[vid] = video_label
            self._queue_total = total
            self._queue_done = max(self._queue_done, cur)
            pct = int((self._queue_done / total) * 100)
            self.progress_queue.setValue(max(0, min(100, pct)))
            self.progress_queue.setFormat(f"{pct}%")
            self.lbl_progress_status.setText(f"阶段 4/4: 并发下载队列 {self._queue_done}/{total}")
            self.lbl_queue_metrics.setText(f"队列: {self._queue_done}/{total} | 最新状态: {status}")
            if vid and vid != "-":
                self._update_active_task_card(
                    vid=vid,
                    label=self._vid_to_label.get(vid, video_label or f"id={vid}"),
                    status=status,
                )
            return

        m_prog = re.search(
            r"\[PROG\]\s*([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|(.+)$",
            s,
        )
        if m_prog:
            vid = m_prog.group(1).strip()
            pct_raw = m_prog.group(2).strip()
            downloaded_raw = m_prog.group(3).strip()
            total_raw = m_prog.group(4).strip()
            est_raw = m_prog.group(5).strip()
            speed = m_prog.group(6).strip()
            speed_fmt = self._format_speed_mibs(speed)
            m_pct = re.search(r"(\d{1,3}(?:\.\d+)?)", pct_raw)
            pct = int(float(m_pct.group(1))) if m_pct else 0
            pct = max(0, min(100, pct))

            def _to_num(v: str) -> Optional[float]:
                v = v.strip()
                if not v or v in {"NA", "None", "null"}:
                    return None
                try:
                    return float(v)
                except Exception:
                    return None

            downloaded_b = _to_num(downloaded_raw)
            total_b = _to_num(total_raw) or _to_num(est_raw)
            label = self._vid_to_label.get(vid, self._current_video_label if self._current_video_label != "-" else f"id={vid}")
            is_primary = bool(self._active_task_order) and self._active_task_order[0] == vid
            if downloaded_b is not None and total_b is not None and total_b > 0:
                if is_primary:
                    self.progress_current.setValue(pct)
                    self.progress_current.setFormat(f"{pct}%")
                    self.lbl_progress_status.setText(f"阶段 4/4: 下载中 {pct}%")
                    self.lbl_download_metrics.setText(
                        f"当前视频: {label} | 已下载: {self._bytes_to_mib(downloaded_b)} / {self._bytes_to_mib(total_b)} | 速度: {speed_fmt}"
                    )
                self._update_active_task_card(
                    vid=vid,
                    label=label,
                    pct=pct,
                    speed=speed_fmt,
                    downloaded=self._bytes_to_mib(downloaded_b),
                    total=self._bytes_to_mib(total_b),
                )
            elif total_b is not None and total_b > 0:
                if is_primary:
                    self.progress_current.setValue(pct)
                    self.progress_current.setFormat(f"{pct}%")
                    self.lbl_progress_status.setText(f"阶段 4/4: 下载中 {pct}%")
                    self.lbl_download_metrics.setText(
                        f"当前视频: {label} | 已下载: {pct}% / {self._bytes_to_mib(total_b)} | 速度: {speed_fmt}"
                    )
                self._update_active_task_card(
                    vid=vid,
                    label=label,
                    pct=pct,
                    speed=speed_fmt,
                    downloaded=f"{pct}%",
                    total=self._bytes_to_mib(total_b),
                )
            else:
                if is_primary:
                    self.progress_current.setValue(pct)
                    self.progress_current.setFormat(f"{pct}%")
                    self.lbl_progress_status.setText(f"阶段 4/4: 下载中 {pct}%")
                    self.lbl_download_metrics.setText(f"当前视频: {label} | 下载: {pct}% | 速度: {speed_fmt}")
                self._update_active_task_card(
                    vid=vid,
                    label=label,
                    pct=pct,
                    speed=speed_fmt,
                    downloaded=f"{pct}%",
                    total="-",
                )
            return

        m_meta = re.search(r"元数据进度:\s*(\d+)\s*/\s*(\d+)", s)
        if m_meta:
            done = int(m_meta.group(1))
            total = max(1, int(m_meta.group(2)))
            pct = int((done / total) * 100)
            self.progress_stage.setValue(max(0, min(100, pct)))
            self.progress_stage.setFormat(f"元数据抓取: {pct}% ({done}/{total})")
            self.lbl_progress_status.setText(f"阶段 2/4: 拉取详细元数据 {done}/{total}")
            return

        m_stage = re.search(r"\[(\d)/4\]", s)
        if m_stage:
            self._stage_step = int(m_stage.group(1))
            if self._stage_step == 1:
                self.progress_stage.setValue(0)
                self.progress_stage.setFormat("元数据抓取: 等待阶段 2")
            elif self._stage_step == 2 and self.progress_stage.value() == 0:
                self.progress_stage.setFormat("元数据抓取: 0%")
            elif self._stage_step >= 3:
                self.progress_stage.setValue(100)
                self.progress_stage.setFormat("元数据抓取: 100%")
            stage_text = {
                1: "阶段 1/4: 搜索候选",
                2: "阶段 2/4: 拉取详细元数据",
                3: "阶段 3/4: Agent 语义筛选",
                4: "阶段 4/4: 下载或收尾",
            }.get(self._stage_step, f"阶段 {self._stage_step}/4")
            self.lbl_progress_status.setText(stage_text)

        if "[4/4]" in s and "开始下载" in s:
            self.lbl_progress_status.setText("阶段 4/4: 正在下载视频")
        if s.startswith("[下载模式]"):
            self.progress_stage.setValue(0)
            self.progress_stage.setFormat("元数据抓取: 未执行（下载模式）")
            self.lbl_progress_status.setText("下载模式: 按 URL 队列下载")

        m_download = re.search(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%", s)
        if m_download:
            # 并发模式下以 [PROG] 为准，避免多个线程竞争更新“当前视频”显示。
            if self._active_task_order:
                return
            pct = int(float(m_download.group(1)))
            pct = max(0, min(100, pct))
            self.progress_current.setValue(pct)
            self.progress_current.setFormat(f"{pct}%")
            self.lbl_progress_status.setText(f"阶段 4/4: 下载中 {pct}%")
            m_detail = re.search(
                r"\[download\]\s+\d{1,3}(?:\.\d+)?%\s+of\s+([^\s]+)\s+at\s+([^\s]+)",
                s,
            )
            if m_detail:
                total_size = m_detail.group(1)
                speed = self._format_speed_mibs(m_detail.group(2))
                total_bytes = self._size_to_bytes(total_size.replace("~", ""))
                if total_bytes is not None:
                    downloaded = self._bytes_to_mib(total_bytes * (pct / 100.0))
                    total_fmt = self._bytes_to_mib(total_bytes)
                    self.lbl_download_metrics.setText(f"已下载: {downloaded} / {total_fmt} | 速度: {speed}")
                else:
                    self.lbl_download_metrics.setText(f"已下载: {pct}% / {total_size} | 速度: {speed}")

            m_detail_full = re.search(
                r"\[download\]\s+\d{1,3}(?:\.\d+)?%\s+of\s+([^\s]+)\s+at\s+([^\s]+)\s+ETA",
                s,
            )
            if m_detail_full:
                total_size = m_detail_full.group(1)
                speed = self._format_speed_mibs(m_detail_full.group(2))
                self.lbl_download_metrics.setText(f"已下载: {pct}% / {total_size} | 速度: {speed}")

        if "跳过下载" in s:
            self.progress_current.setValue(0)
            self.progress_current.setFormat("跳过")
            self.lbl_download_metrics.setText("当前视频: - | 已下载: - / - | 速度: -")

        if s.startswith("完成"):
            self.progress_stage.setValue(100)
            self.progress_stage.setFormat("100%")
            if self.progress_current.value() >= 100:
                self.lbl_progress_status.setText("任务完成（已下载）")
            else:
                self.lbl_progress_status.setText("任务完成")

    def build_args(self, task_workdir: Optional[str] = None) -> list[str]:
        args: list[str] = [self.cfg.script_path]
        q = self.le_query_text.text().strip()
        if q:
            args += ["--query-text", q]
        args += ["--workdir", task_workdir or self._combo_text(self.cb_workdir)]
        args += ["--download-dir", self._combo_text(self.cb_downloaddir)]
        args += ["--search-limit", str(self.spin_search_limit.value())]
        args += ["--metadata-workers", str(self.spin_metadata_workers.value())]
        args += ["--min-duration", str(self.spin_min_duration.value())]
        if self.chk_year_from.isChecked():
            args += ["--year-from", str(self.spin_year_from.value())]
        if self.chk_year_to.isChecked():
            args += ["--year-to", str(self.spin_year_to.value())]
        if self.chk_full_csv.isChecked():
            args += ["--full-csv"]
        br = self.combo_cookies_browser.currentText().strip()
        if br:
            args += ["--cookies-from-browser", br]
        cf = self.le_cookies_file.text().strip()
        if cf:
            args += ["--cookies-file", cf]
        yt_extra = self.le_yt_extra_args.text().strip()
        if yt_extra:
            args += ["--yt-extra-args", yt_extra]
        args += ["--concurrent-videos", str(self.spin_concurrent_videos.value())]
        args += ["--concurrent-fragments", str(self.spin_concurrent_fragments.value())]
        return args

    def _current_config(self) -> dict:
        return {
            "query_text": self.le_query_text.text().strip(),
            "workdir": self._combo_text(self.cb_workdir),
            "downloaddir": self._combo_text(self.cb_downloaddir),
            "search_limit": self.spin_search_limit.value(),
            "metadata_workers": self.spin_metadata_workers.value(),
            "min_duration": self.spin_min_duration.value(),
            "year_from_enabled": self.chk_year_from.isChecked(),
            "year_from": self.spin_year_from.value(),
            "year_to_enabled": self.chk_year_to.isChecked(),
            "year_to": self.spin_year_to.value(),
            "cookies_browser": self.combo_cookies_browser.currentText().strip(),
            "cookies_file": self.le_cookies_file.text().strip(),
            "full_csv": self.chk_full_csv.isChecked(),
            "yt_extra_args": self.le_yt_extra_args.text().strip(),
            "download_mode": self.combo_download_mode.currentText(),
            "include_audio": self.chk_include_audio.isChecked(),
            "video_container": self.combo_video_container.currentText(),
            "max_height": self.combo_max_height.currentText(),
            "audio_format": self.combo_audio_format.currentText(),
            "audio_quality": self.spin_audio_quality.value(),
            "concurrent_videos": self.spin_concurrent_videos.value(),
            "concurrent_fragments": self.spin_concurrent_fragments.value(),
            "clean_video": self.chk_clean_video.isChecked(),
            "sponsorblock_remove": self._selected_sponsorblock_remove(),
            "agent_provider": self.combo_agent_provider.currentText().strip(),
            "agent_base_url": self.le_agent_base_url.text().strip(),
            "agent_model": self.le_agent_model.text().strip(),
            "agent_show_api_key": self.chk_agent_show_api_key.isChecked(),
        }

    def _count_selected_urls(self, workdir: str) -> int:
        try:
            p = Path(workdir) / "05_selected_urls.txt"
            if not p.exists():
                return 0
            return len(
                [
                    ln.strip()
                    for ln in p.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and ln.strip().startswith("http")
                ]
            )
        except Exception:
            return 0

    def _normalize_filter_reason_label(self, reason: str) -> str:
        text = (reason or "").strip()
        if not text:
            return ""
        if "关键词核心匹配: 不通过" in text:
            return "关键词未命中"
        if "主题核心词检查: 未命中" in text:
            return "主题词未命中"
        if "YouTube召回兜底入选" in text:
            return "召回兜底入选"
        if "软评分未入选" in text:
            return "软评分不足"
        if "软评分入选" in text:
            return "软评分入选"
        if "详细元数据提取失败" in text:
            return "元数据提取失败"
        if "时长不足" in text:
            return "时长不足"
        if "上传年 " in text or "无上传日期" in text:
            return "年份不匹配/缺失"
        if "直播/直播回放/待开始" in text:
            return "直播或回放"
        if "可用性受限" in text:
            return "可用性受限"
        return text

    def _summarize_filter_failures(self, workdir: str) -> str:
        try:
            scored_path = Path(workdir) / "03_scored_candidates.jsonl"
            if not scored_path.exists():
                return ""
            total = 0
            selected = 0
            reason_counts: dict[str, int] = {}
            for line in scored_path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                item = json.loads(s)
                total += 1
                if item.get("selected"):
                    selected += 1
                    continue
                reasons_text = str(item.get("reasons") or "")
                for part in [seg.strip() for seg in reasons_text.split(" | ") if seg.strip()]:
                    label = self._normalize_filter_reason_label(part)
                    if not label:
                        continue
                    reason_counts[label] = reason_counts.get(label, 0) + 1
            if total == 0:
                return "没有候选结果。"
            if selected > 0:
                return ""
            top_reasons = sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
            if not top_reasons:
                return f"共 {total} 个候选，未生成可下载 URL。"
            summary = "，".join(f"{label}({count})" for label, count in top_reasons)
            return f"共 {total} 个候选，主要原因：{summary}"
        except Exception:
            return ""

    def _read_download_summary(self, workdir: Path) -> tuple[int, int, int, str, str]:
        downloaded = failed = unknown = 0
        pointers = resolve_download_session_pointers(workdir)
        session_path = pointers.session_dir
        report = Path(pointers.report_csv) if pointers.report_csv else (workdir / "07_download_report.csv")
        if report.exists():
            try:
                with report.open("r", encoding="utf-8-sig", newline="") as fh:
                    for row in csv.DictReader(fh):
                        # 兼容新旧下载报告字段：
                        # 旧版使用 status(downloaded/failed)，新版使用 视频是否下载成功(是/否)。
                        st = (row.get("status") or "").strip().lower()
                        success_flag = (row.get("视频是否下载成功") or "").strip()
                        if success_flag == "是" or st == "downloaded":
                            downloaded += 1
                        elif success_flag == "否" or st == "failed":
                            failed += 1
                        else:
                            unknown += 1
            except Exception:
                pass
        return downloaded, failed, unknown, session_path, str(report)

    def _apply_config(self, cfg: dict) -> None:
        self.le_query_text.setText(str(cfg.get("query_text", "")))
        self._set_combo_text(self.cb_workdir, str(cfg.get("workdir", "")))
        self._set_combo_text(self.cb_downloaddir, str(cfg.get("downloaddir", "")))
        self.spin_search_limit.setValue(int(cfg.get("search_limit", 50)))
        self.spin_metadata_workers.setValue(int(cfg.get("metadata_workers", 4)))
        self.spin_min_duration.setValue(int(cfg.get("min_duration", 120)))
        self.chk_year_from.setChecked(bool(cfg.get("year_from_enabled", False)))
        self.spin_year_from.setValue(int(cfg.get("year_from", 2020)))
        self.chk_year_to.setChecked(bool(cfg.get("year_to_enabled", False)))
        self.spin_year_to.setValue(int(cfg.get("year_to", 2026)))
        self.combo_cookies_browser.setCurrentText(str(cfg.get("cookies_browser", "")))
        self.le_cookies_file.setText(str(cfg.get("cookies_file", "")))
        self.chk_full_csv.setChecked(bool(cfg.get("full_csv", False)))
        self.le_yt_extra_args.setText(str(cfg.get("yt_extra_args", "")))
        dmode = str(cfg.get("download_mode", "video"))
        idx_dm = self.combo_download_mode.findText(dmode)
        self.combo_download_mode.setCurrentIndex(idx_dm if idx_dm >= 0 else 0)
        self.chk_include_audio.setChecked(bool(cfg.get("include_audio", True)))
        vcont = str(cfg.get("video_container", "auto"))
        idx_vc = self.combo_video_container.findText(vcont)
        self.combo_video_container.setCurrentIndex(idx_vc if idx_vc >= 0 else 0)
        mh = str(cfg.get("max_height", "1080"))
        if mh == "auto":
            mh = "1080"
        idx_mh = self.combo_max_height.findText(mh)
        self.combo_max_height.setCurrentIndex(idx_mh if idx_mh >= 0 else self.combo_max_height.findText("1080"))
        af = str(cfg.get("audio_format", "best"))
        idx_af = self.combo_audio_format.findText(af)
        self.combo_audio_format.setCurrentIndex(idx_af if idx_af >= 0 else 0)
        self.spin_audio_quality.setValue(int(cfg.get("audio_quality", 2)))
        self.spin_concurrent_videos.setValue(int(cfg.get("concurrent_videos", 3)))
        self.spin_concurrent_fragments.setValue(int(cfg.get("concurrent_fragments", 8)))
        self.chk_clean_video.setChecked(bool(cfg.get("clean_video", False)))
        self._set_sponsorblock_checks(str(cfg.get("sponsorblock_remove", "sponsor,selfpromo,intro,outro,interaction")))
        self.combo_agent_provider.setCurrentText(str(cfg.get("agent_provider", "openai")))
        self.le_agent_base_url.setText(str(cfg.get("agent_base_url", "")))
        self.le_agent_model.setText(str(cfg.get("agent_model", "")))
        self.chk_agent_show_api_key.setChecked(bool(cfg.get("agent_show_api_key", False)))
        for chk in self.sb_checks.values():
            chk.setEnabled(self.chk_clean_video.isChecked())
        self._on_download_mode_changed(self.combo_download_mode.currentText())

    def _enqueue(self) -> None:
        query = self.le_query_text.text().strip()
        if not query:
            QtWidgets.QMessageBox.information(self, "提示", "请先输入一个查询关键词。")
            return
        root_workdir = self._combo_text(self.cb_workdir).strip()
        if not root_workdir:
            QtWidgets.QMessageBox.information(self, "提示", "请先设置“视频信息目录(信息存放)”。")
            return
        safe_q = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", query)[:24].strip("_") or "query"
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        task_workdir = str((Path(root_workdir) / f"run_{run_id}_{safe_q}").resolve())

        try:
            args = self.build_args(task_workdir=task_workdir)
            if self.le_yt_extra_args.text().strip():
                shlex.split(self.le_yt_extra_args.text().strip())
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "鍙傛暟閿欒", f"高级 yt-dlp 参数解析失败:\n{exc}")
            return

        task = QueueTask(
            args=args,
            task_name=query[:48],
            workdir=task_workdir,
            run_id=run_id,
            download_dir=self._combo_text(self.cb_downloaddir),
            cookies_browser=self.combo_cookies_browser.currentText().strip(),
            cookies_file=self.le_cookies_file.text().strip(),
            yt_extra_args=self.le_yt_extra_args.text().strip(),
            download_mode=self.combo_download_mode.currentText(),
            include_audio=self.chk_include_audio.isChecked(),
            video_container=self.combo_video_container.currentText(),
            max_height=self.combo_max_height.currentText(),
            audio_format=self.combo_audio_format.currentText(),
            audio_quality=self.spin_audio_quality.value(),
            concurrent_videos=self.spin_concurrent_videos.value(),
            concurrent_fragments=self.spin_concurrent_fragments.value(),
            clean_video=self.chk_clean_video.isChecked(),
            sponsorblock_remove=self._selected_sponsorblock_remove(),
            download_session_name=f"{run_id}_{safe_q[:48]}",
        )
        self.task_queue.append(task)
        self._refresh_queue_list()
        self._touch_histories()
        self.status.showMessage(f"已加入筛选队列（任务目录: {task_workdir}）", 5000)

    def start_queue(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            self.status.showMessage("当前有任务在运行，队列会在其完成后继续。", 4000)
            return
        self.download_all_mode = False
        self._start_next_pending()

    def _start_next_pending(self) -> None:
        for idx, task in enumerate(self.task_queue):
            if task.status == "pending":
                self.active_queue_index = idx
                self.active_run_kind = "filter_queue"
                task.status = "running"
                self._refresh_queue_list()
                self._start_process(task.args, task.workdir)
                return
        self.status.showMessage("队列已执行完毕。", 4000)

    def _enqueue_and_start(self) -> None:
        before = len(self.task_queue)
        self._enqueue()
        if len(self.task_queue) > before and self.runner.proc.state() == QtCore.QProcess.NotRunning:
            self.start_queue()

    def _download_args_for_task(self, task: QueueTask) -> list[str]:
        urls_file = str(Path(task.workdir) / "05_selected_urls.txt")
        session_name = (task.download_session_name or "").strip()
        if not session_name:
            session_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", task.task_name).strip("._-")
            if not session_name:
                session_name = "task"
            session_name = f"{task.run_id}_{session_name[:48]}"
        args: list[str] = [
            self.cfg.script_path,
            "--workdir",
            task.workdir,
            "--download-dir",
            task.download_dir,
            "--download-from-urls-file",
            urls_file,
            "--download-session-name",
            session_name,
        ]
        if task.cookies_browser:
            args += ["--cookies-from-browser", task.cookies_browser]
        if task.cookies_file:
            args += ["--cookies-file", task.cookies_file]
        args += ["--download-mode", task.download_mode]
        args += ["--video-container", task.video_container]
        if task.include_audio:
            args += ["--include-audio"]
        else:
            args += ["--no-include-audio"]
        if task.max_height:
            args += ["--max-height", str(task.max_height)]
        args += ["--audio-format", task.audio_format]
        args += ["--audio-quality", str(task.audio_quality)]
        if task.clean_video:
            args += ["--clean-video"]
        if task.sponsorblock_remove:
            args += ["--sponsorblock-remove", task.sponsorblock_remove]
        args += ["--concurrent-videos", str(max(1, int(task.concurrent_videos)))]
        args += ["--concurrent-fragments", str(max(1, int(task.concurrent_fragments)))]
        if task.yt_extra_args:
            args += ["--yt-extra-args", task.yt_extra_args]
        return args

    def _download_args_for_task_with_file(self, task: QueueTask, urls_file: str) -> list[str]:
        args = self._download_args_for_task(task)
        if "--download-from-urls-file" in args:
            i = args.index("--download-from-urls-file")
            if i + 1 < len(args):
                args[i + 1] = urls_file
        return args

    def _current_task(self) -> Optional[QueueTask]:
        task_index = self._current_task_index()
        if task_index is None or task_index < 0 or task_index >= len(self.task_queue):
            return None
        return self.task_queue[task_index]

    def _selected_queue_task(self) -> Optional[QueueTask]:
        rows = self._selected_queue_rows()
        if not rows:
            return self._current_task()
        row = rows[0]
        if row < 0 or row >= len(self.task_queue):
            return None
        return self.task_queue[row]

    def _agent_task_paths_for_queue_task(self, task: QueueTask) -> dict[str, str]:
        if task.origin != "agent" or not task.agent_task_id or not task.workdir:
            return {}
        try:
            store = TaskStore(task.workdir)
            return store.task_paths(task.agent_task_id)
        except Exception:
            return {}

    def _selected_agent_task_and_paths(self) -> tuple[Optional[QueueTask], dict[str, str]]:
        task = self._selected_queue_task()
        if task is None or task.origin != "agent":
            return None, {}
        return task, self._agent_task_paths_for_queue_task(task)

    @QtCore.Slot(bool)
    def _set_agent_detail_expanded(self, expanded: bool) -> None:
        if hasattr(self, "agent_detail_box"):
            if self.agent_detail_box.isCheckable():
                self.agent_detail_box.setChecked(expanded)
                self.agent_detail_box.setTitle("Agent 技术详情（已展开）" if expanded else "Agent 技术详情（点击展开）")
            else:
                self.agent_detail_box.setTitle("Agent 技术详情")
        for widget in getattr(self, "_agent_detail_toggle_widgets", []):
            widget.setVisible(expanded)

    def _count_jsonl_records(self, path: Path, predicate: Optional[Callable[[dict], bool]] = None) -> int:
        if not path.exists():
            return 0
        count = 0
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    item = json.loads(s)
                except Exception:
                    continue
                if predicate is None or predicate(item):
                    count += 1
        except Exception:
            return 0
        return count

    def _agent_filter_failure_counts(self, scored_path: Path) -> tuple[int, int, dict[str, int]]:
        total = 0
        selected = 0
        reason_counts: dict[str, int] = {}
        if not scored_path.exists():
            return total, selected, reason_counts
        try:
            for line in scored_path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    item = json.loads(s)
                except Exception:
                    continue
                total += 1
                if item.get("selected"):
                    selected += 1
                    continue
                reasons_text = str(item.get("reasons") or "")
                for part in [seg.strip() for seg in reasons_text.split(" | ") if seg.strip()]:
                    label = self._normalize_filter_reason_label(part)
                    if label:
                        reason_counts[label] = reason_counts.get(label, 0) + 1
        except Exception:
            return total, selected, reason_counts
        return total, selected, reason_counts

    def _agent_vector_summary(self, vector_path: Path) -> dict[str, object]:
        summary: dict[str, object] = {
            "total": 0,
            "topk": 0,
            "max_score": 0.0,
            "average_score": 0.0,
            "low_similarity": 0,
            "threshold": 0.12,
        }
        if not vector_path.exists():
            return summary
        scores: list[float] = []
        try:
            for line in vector_path.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    item = json.loads(s)
                except Exception:
                    continue
                summary["total"] = int(summary["total"]) + 1
                try:
                    score = float(item.get("vector_score") or 0.0)
                except (TypeError, ValueError):
                    score = 0.0
                try:
                    threshold = float(item.get("vector_threshold") or summary["threshold"])
                except (TypeError, ValueError):
                    threshold = float(summary["threshold"])
                summary["threshold"] = threshold
                if item.get("vector_rank") not in (None, ""):
                    summary["topk"] = int(summary["topk"]) + 1
                    scores.append(score)
                if score < threshold:
                    summary["low_similarity"] = int(summary["low_similarity"]) + 1
            if scores:
                summary["max_score"] = max(scores)
                summary["average_score"] = sum(scores) / len(scores)
        except Exception:
            return summary
        return summary

    def _set_agent_diagnostic_placeholder(self, message: str) -> None:
        self.lbl_agent_diag_counts.setText("搜到: - | 元数据成功: - | 被筛掉: -")
        self._set_metric_label(self.lbl_diag_metric_search, "搜索", "-")
        self._set_metric_label(self.lbl_diag_metric_metadata, "元数据", "-")
        self._set_metric_label(self.lbl_diag_metric_selected, "结果", "-")
        self._set_metric_label(self.lbl_diag_metric_semantic, "语义", "-")
        self.lbl_agent_diag_hint.setText(message)
        self.agent_diag_reasons.clear()
        self.agent_diag_reasons.addItem("暂无诊断数据。")

    def _refresh_agent_diagnostic_card(self, task: Optional[QueueTask]) -> None:
        if task is None or task.origin != "agent" or not task.workdir:
            self._set_agent_diagnostic_placeholder("选中 Agent 任务后，会显示搜索、元数据和筛选诊断。")
            return
        workdir = Path(task.workdir)
        raw_count = self._count_jsonl_records(workdir / "01_search_candidates.jsonl", lambda item: bool(item.get("video_id")))
        deduped_count = self._count_jsonl_records(workdir / "01b_deduped_candidates.jsonl")
        detail_total = self._count_jsonl_records(workdir / "02_detailed_candidates.jsonl")
        detail_ok = self._count_jsonl_records(workdir / "02_detailed_candidates.jsonl", lambda item: not item.get("detail_error"))
        vector_summary = self._agent_vector_summary(workdir / "02b_vector_scored_candidates.jsonl")
        scored_total, selected, reason_counts = self._agent_filter_failure_counts(workdir / "03_scored_candidates.jsonl")
        rejected = max(0, scored_total - selected)

        searched_text = f"{raw_count}"
        if deduped_count and deduped_count != raw_count:
            searched_text = f"{raw_count} / 去重 {deduped_count}"
        detail_text = f"{detail_ok}"
        if detail_total:
            detail_text = f"{detail_ok}/{detail_total}"
        self.lbl_agent_diag_counts.setText(
            f"搜到: {searched_text} | 元数据成功: {detail_text} | 被筛掉: {rejected} | 语义最高: {float(vector_summary['max_score']):.3f}"
        )
        self._set_metric_label(self.lbl_diag_metric_search, "搜索", searched_text, "raw / 去重")
        self._set_metric_label(self.lbl_diag_metric_metadata, "元数据", detail_text, "成功 / 总数")
        self._set_metric_label(self.lbl_diag_metric_selected, "结果", f"{selected} 可下载", f"被筛掉 {rejected}")
        self._set_metric_label(
            self.lbl_diag_metric_semantic,
            "语义",
            f"{float(vector_summary['max_score']):.3f}",
            f"TopK {int(vector_summary['topk'])} | 低相似 {int(vector_summary['low_similarity'])}",
        )

        quality, quality_detail = self._diagnostic_quality(
            raw_count,
            detail_ok,
            selected,
            float(vector_summary["max_score"]),
        )
        suggestions = self._diagnostic_suggestions(raw_count, detail_ok, selected, rejected, vector_summary)

        if scored_total == 0:
            self.lbl_agent_diag_hint.setText("还没有筛选产物，任务可能仍在搜索/拉取元数据阶段。")
        elif selected > 0:
            self.lbl_agent_diag_hint.setText(
                f"筛选质量：{quality}。{quality_detail} 语义 TopK {int(vector_summary['topk'])} 条，"
                f"平均相似度 {float(vector_summary['average_score']):.3f}，"
                f"低相似度 {int(vector_summary['low_similarity'])} 条。"
            )
        else:
            self.lbl_agent_diag_hint.setText(
                f"筛选质量：{quality}。{quality_detail} 语义 TopK {int(vector_summary['topk'])} 条，"
                f"低相似度 {int(vector_summary['low_similarity'])} 条，下面是主要筛选失败原因。"
            )

        self.agent_diag_reasons.clear()
        if scored_total > 0:
            self.agent_diag_reasons.addItem(f"筛选质量: {quality}")
            for suggestion in suggestions:
                self.agent_diag_reasons.addItem(f"建议: {suggestion}")
        if int(vector_summary["total"]) > 0:
            self.agent_diag_reasons.addItem(
                f"语义低相似度淘汰: {int(vector_summary['low_similarity'])} "
                f"(< {float(vector_summary['threshold']):.3f})"
            )
        top_reasons = sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        if not top_reasons:
            if int(vector_summary["total"]) <= 0:
                self.agent_diag_reasons.addItem("暂无失败原因统计。")
            return
        for label, count in top_reasons:
            self.agent_diag_reasons.addItem(f"{label}: {count}")

    def _diagnostic_quality(self, raw_count: int, detail_ok: int, selected: int, max_score: float) -> tuple[str, str]:
        if raw_count <= 0:
            return "失败", "没有搜索召回，建议换更明确的主题词，或补充 YouTube 常见英文描述。"
        if detail_ok <= 0:
            return "失败", "没有成功获取视频信息，优先检查网络、yt-dlp 或 cookies。"
        if selected <= 0:
            if max_score < 0.12:
                return "偏弱", "语义相似度整体偏低，建议缩短需求、加入英文关键词或放宽搜索词。"
            return "偏弱", "有语义候选但未入选，建议降低最短时长或放宽年份限制。"
        if max_score >= 0.28:
            return "好", "语义匹配较明确，可以优先检查可下载列表。"
        if max_score >= 0.16:
            return "中等", "已有可下载结果，但语义分不算高，建议人工复核前几条。"
        return "中等", "结果可用但匹配信号偏弱，建议增加英文关键词再次搜索。"

    def _diagnostic_suggestions(
        self,
        raw_count: int,
        detail_ok: int,
        selected: int,
        rejected: int,
        vector_summary: dict[str, object],
    ) -> list[str]:
        suggestions: list[str] = []
        max_score = float(vector_summary.get("max_score") or 0.0)
        low_similarity = int(vector_summary.get("low_similarity") or 0)
        total = int(vector_summary.get("total") or 0)
        if raw_count <= 0:
            suggestions.append("把核心主题写得更明确，例如 Python async tutorial / Japan travel vlog。")
            suggestions.append("加入 tutorial、review、documentary、interview、comparison 这类 YouTube 常见词。")
        if detail_ok <= 0 and raw_count > 0:
            suggestions.append("检查网络、yt-dlp 或 cookies 设置，当前搜索到了候选但没拿到视频信息。")
        if total > 0 and low_similarity >= max(3, total * 0.6):
            suggestions.append("低相似度较多，可以把需求写得更短更具体，只保留主题 + 内容类型。")
        if selected <= 0 and max_score >= 0.12:
            suggestions.append("语义候选存在但被规则筛掉，尝试降低最短时长或放宽年份范围。")
        if selected > 0 and max_score < 0.18:
            suggestions.append("结果可用但语义分偏弱，建议按语义分排序后人工复核。")
        if rejected > selected and selected > 0:
            suggestions.append("被筛掉的视频较多，可以查看失败原因 Top 5 调整下一次任务。")
        return suggestions[:4] or ["当前诊断没有明显风险，可以继续查看视频结果。"]

    def _set_agent_detail_placeholder(self, message: str) -> None:
        self._refresh_agent_diagnostic_card(None)
        self.lbl_current_task_title.setText("选择一个任务开始查看结果")
        self.lbl_current_task_status.setText("未选中")
        self._set_metric_label(self.lbl_summary_urls, "可下载", "-")
        self._set_metric_label(self.lbl_summary_metadata, "视频信息", "-")
        self._set_metric_label(self.lbl_summary_semantic, "语义最高", "-")
        self.lbl_agent_queue_title.setText(message)
        self.lbl_agent_queue_status.setText("状态: -")
        self.lbl_agent_control_notice.setText("选中 Agent 任务后，这里会显示计划、确认边界、结果摘要和事件时间线。")
        self.lbl_agent_control_notice.setObjectName("agentNoticeInfo")
        self.lbl_agent_control_notice.style().unpolish(self.lbl_agent_control_notice)
        self.lbl_agent_control_notice.style().polish(self.lbl_agent_control_notice)
        self._set_metric_label(self.lbl_agent_metric_steps, "计划步骤", "-")
        self._set_metric_label(self.lbl_agent_metric_confirm, "待确认", "-")
        self._set_metric_label(self.lbl_agent_metric_events, "最近事件", "-")
        self.lbl_agent_queue_paths.setText("任务目录: -")
        self.agent_steps_list.clear()
        self.agent_confirm_list.clear()
        self.agent_result_summary.clear()
        self.agent_events_list.clear()
        self.agent_events_list.setProperty("all_events", [])
        self._add_list_empty_state(
            self.agent_steps_list,
            "计划步骤会显示在这里",
            "选中一个 Agent 任务后，这里会展示计划拆解、当前状态和每一步的执行语义。",
            width=520,
            height=100,
        )
        self._add_list_empty_state(
            self.agent_confirm_list,
            "确认边界暂未出现",
            "需要人工确认的步骤会在这里显示成确认卡，帮助你判断是否继续执行。",
            width=520,
            height=100,
        )
        self._add_list_empty_state(
            self.agent_events_list,
            "事件时间线待加载",
            "选中 Agent 任务后，这里会显示规划、确认、执行和完成事件。",
            width=520,
            height=100,
        )
        self.agent_result_summary.setHtml(
            "<div style='color:#536273; line-height:1.7;'>"
            "<b style='color:#18212B;'>结果摘要会显示在这里</b><br/>"
            "选中 Agent 任务后，这里会汇总关键结果、文件路径和失败步骤。"
            "</div>"
        )
        blocker = QtCore.QSignalBlocker(self.combo_agent_event_type)
        self.combo_agent_event_type.clear()
        self.combo_agent_event_type.addItem("全部类型")
        self.combo_agent_event_level.setCurrentIndex(0)
        self.le_agent_event_keyword.clear()
        self.btn_agent_open_workdir.setEnabled(False)
        self.btn_agent_open_selected_urls.setEnabled(False)
        self.btn_agent_open_task_dir.setEnabled(False)
        self.btn_agent_open_artifacts.setEnabled(False)
        self.act_agent_open_spec.setEnabled(False)
        self.act_agent_open_summary.setEnabled(False)
        self.act_agent_open_events.setEnabled(False)
        self.act_agent_open_result.setEnabled(False)
        self.btn_agent_clear_event_filters.setEnabled(False)
        self.btn_agent_copy_selected_event.setEnabled(False)
        self.btn_agent_copy_events.setEnabled(False)

    def _agent_event_level_filter_value(self) -> str:
        label = self.combo_agent_event_level.currentText().strip().lower()
        return {
            "全部级别": "",
            "info": "info",
            "warning": "warning",
            "error": "error",
        }.get(label, "")

    def _agent_event_type_filter_value(self) -> str:
        label = self.combo_agent_event_type.currentText().strip()
        if not label or label == "全部类型":
            return ""
        return label

    def _agent_event_keyword_filter_value(self) -> str:
        return self.le_agent_event_keyword.text().strip().lower()

    def _format_agent_event_timeline_item(self, event_type: str, message: str, level: str, timestamp: str) -> str:
        stamp = (timestamp or "").replace("T", " ")
        if len(stamp) >= 19:
            stamp = stamp[:19]
        level_text = (level or "info").upper()
        event_label = (event_type or "event").replace("_", " ")
        detail = message or event_label
        return f"[{stamp or '-'}] {level_text} · {event_label}\n{detail}"

    def _queue_status_tone(self, status: str) -> str:
        s = (status or "").strip()
        if s in {"running", "downloading"}:
            return "info"
        if s in {"paused_filter", "paused_download", "filtered_empty"}:
            return "warning"
        if s in {"failed", "download_failed", "stopped"}:
            return "danger"
        if s in {"done", "ready_download", "downloaded"}:
            return "success"
        return "muted"

    def _queue_next_action_text(self, task: QueueTask) -> str:
        if task.origin == "agent" and task.agent_task_id:
            if task.status in {"pending", "running"}:
                return "建议下一步: 查看 Agent 计划与诊断。"
            if task.status == "ready_download":
                return "建议下一步: 检查可下载视频后开始下载。"
            if task.status in {"download_failed", "failed"}:
                return "建议下一步: 打开事件时间线查看失败原因。"
        if task.status == "pending":
            return "建议下一步: 启动筛选任务。"
        if task.status == "ready_download":
            return "建议下一步: 直接下载或先抽查视频列表。"
        if task.status in {"downloading", "running"}:
            return "建议下一步: 观察当前进度与日志。"
        if task.status in {"downloaded", "done"}:
            return "建议下一步: 打开目录检查结果。"
        if task.status == "filtered_empty":
            return "建议下一步: 放宽筛选条件后重试。"
        return "建议下一步: 打开目录或查看详情。"

    def _friendly_task_status(self, status: str) -> str:
        return {
            "pending": "待运行",
            "running": "运行中",
            "paused_filter": "已暂停·筛选",
            "ready_download": "已筛选·待下载",
            "filtered_empty": "已筛选·无结果",
            "downloading": "下载中",
            "paused_download": "已暂停·下载",
            "downloaded": "下载完成",
            "download_failed": "下载失败",
            "done": "已完成",
            "failed": "失败",
            "stopped": "已停止",
        }.get(status, status or "-")

    def _short_agent_path_label(self, path_value: str, task: QueueTask) -> str:
        path = Path(path_value)
        try:
            workdir = Path(task.workdir).resolve()
            resolved = path.resolve()
            rel = resolved.relative_to(workdir)
            parts = list(rel.parts)
            if len(parts) <= 2:
                return "/".join(parts)
            if len(parts) >= 4 and parts[0] == ".agent" and parts[1] == "tasks":
                return "/".join(parts[:2] + [parts[-2], parts[-1]])
            return f".../{parts[-2]}/{parts[-1]}"
        except Exception:
            parts = path.parts
            if len(parts) >= 2:
                return f".../{parts[-2]}/{parts[-1]}"
            return path.name or path_value

    def _make_agent_path_link(self, label: str, path_value: str) -> str:
        url = QtCore.QUrl.fromLocalFile(path_value).toString()
        self._agent_result_link_targets[url] = path_value
        return '<a href="{url}">{label}</a>'.format(url=url, label=html.escape(label))

    def _populate_agent_event_type_filter(self, events: list[Any]) -> None:
        current = self.combo_agent_event_type.currentText().strip()
        types = []
        seen: set[str] = set()
        for event in events:
            event_type = str(getattr(event, "event_type", "") or "").strip()
            if not event_type or event_type in seen:
                continue
            seen.add(event_type)
            types.append(event_type)
        blocker = QtCore.QSignalBlocker(self.combo_agent_event_type)
        self.combo_agent_event_type.clear()
        self.combo_agent_event_type.addItem("全部类型")
        for event_type in sorted(types):
            self.combo_agent_event_type.addItem(event_type)
        if current and self.combo_agent_event_type.findText(current) >= 0:
            self.combo_agent_event_type.setCurrentText(current)
        else:
            self.combo_agent_event_type.setCurrentIndex(0)

    def _summarize_agent_result(self, result_payload: dict[str, Any], task: QueueTask) -> str:
        self._agent_result_link_targets = {}
        if not result_payload:
            return (
                "<div style='background:#F8FBFE; border:1px dashed #D7E2EE; border-radius:12px; padding:14px;'>"
                "<div style='font-size:14px; font-weight:700; color:#18212B;'>暂无结果摘要</div>"
                "<div style='margin-top:6px; font-size:12px; color:#536273; line-height:1.6;'>"
                "当 Agent 完成规划或执行后，这里会显示结果概览、文件产物和失败步骤。"
                "</div></div>"
            )
        status = str(result_payload.get("status") or task.status or "-")
        message = str(result_payload.get("message") or "").strip()
        started_at = str(result_payload.get("started_at") or "")
        finished_at = str(result_payload.get("finished_at") or "")

        data = result_payload.get("data") or {}
        if not isinstance(data, dict):
            data = {}

        def tone_colors(tone: str) -> tuple[str, str, str]:
            mapping = {
                "success": ("#EAF8EF", "#216A39", "#B9DABD"),
                "warning": ("#FFF5E5", "#9A6100", "#F0D6A2"),
                "danger": ("#FDEDEC", "#B93830", "#F2B8B3"),
                "info": ("#EAF2FF", "#255CC4", "#BDD0F5"),
                "muted": ("#EEF3F8", "#536273", "#D6DEE8"),
            }
            return mapping.get(tone, mapping["muted"])

        def badge_html(text: str, tone: str) -> str:
            bg, fg, border = tone_colors(tone)
            return (
                f"<span style='display:inline-block; padding:4px 8px; border-radius:9px; "
                f"background:{bg}; color:{fg}; border:1px solid {border}; font-size:11px; font-weight:700;'>"
                f"{html.escape(text)}</span>"
            )

        def section_card(title: str, body: str) -> str:
            return (
                "<div style='margin-top:10px; background:#FFFFFF; border:1px solid #D9E2EC; "
                "border-radius:12px; padding:12px 14px;'>"
                f"<div style='font-size:14px; font-weight:700; color:#18212B; margin-bottom:8px;'>{html.escape(title)}</div>"
                f"{body}</div>"
            )

        status_tone = self._queue_status_tone(status)
        overview_lines = [
            "<div style='display:flex; justify-content:space-between; gap:12px; align-items:flex-start;'>"
            "<div>"
            "<div style='font-size:18px; font-weight:800; color:#18212B;'>结果概览</div>"
            "<div style='margin-top:6px;'>"
            f"{badge_html(self._friendly_task_status(status), status_tone)}"
            "</div>"
            "</div>"
            f"<div style='font-size:12px; color:#708095;'>{html.escape(task.run_id or '')}</div>"
            "</div>"
        ]
        if message:
            overview_lines.append(
                "<div style='margin-top:10px; font-size:13px; color:#18212B; line-height:1.7;'>"
                f"{html.escape(message)}</div>"
            )
        meta_bits = []
        if started_at:
            meta_bits.append(f"开始时间：{html.escape(started_at)}")
        if finished_at:
            meta_bits.append(f"完成时间：{html.escape(finished_at)}")
        if meta_bits:
            overview_lines.append(
                "<div style='margin-top:10px; font-size:12px; color:#536273; line-height:1.7;'>"
                + "<br/>".join(meta_bits)
                + "</div>"
            )

        step_results = data.get("step_results")
        step_lines: list[str] = []
        if isinstance(step_results, dict) and step_results:
            for step_id, payload in step_results.items():
                if isinstance(payload, dict):
                    keys = ", ".join(sorted(payload.keys())[:8]) or "-"
                    step_lines.append(
                        "<div style='margin-bottom:8px; padding:10px 12px; background:#F8FBFE; "
                        "border:1px solid #D9E2EC; border-radius:10px;'>"
                        f"<div style='font-size:13px; font-weight:700; color:#18212B;'>{html.escape(str(step_id))}</div>"
                        f"<div style='margin-top:4px; font-size:12px; color:#536273;'>结果字段：{html.escape(keys)}</div>"
                    )
                    export_paths = []
                    for key, value in payload.items():
                        key_text = str(key)
                        if "path" in key_text or "file" in key_text or key_text.endswith("_dir"):
                            if isinstance(value, str) and value.strip():
                                export_paths.append((key_text, value))
                    export_lines: list[str] = []
                    for key_text, value in export_paths[:4]:
                        short_label = self._short_agent_path_label(value, task)
                        export_lines.append(
                            "{key} = {link}".format(
                                key=html.escape(key_text),
                                link=self._make_agent_path_link(short_label, value),
                            )
                        )
                    failed_like = []
                    for key, value in payload.items():
                        if "fail" in str(key).lower() or "error" in str(key).lower():
                            if isinstance(value, (str, int, float)) and str(value).strip():
                                failed_like.append(f"{key}={value}")
                            elif isinstance(value, list) and value:
                                failed_like.append(f"{key}: {len(value)}")
                    if export_lines:
                        step_lines.append(
                            "<div style='margin-top:8px; font-size:12px; color:#35506E; line-height:1.7;'>"
                            + "<br/>".join(export_lines)
                            + "</div>"
                        )
                    if failed_like:
                        step_lines.append(
                            "<div style='margin-top:8px; font-size:12px; color:#9A6100; line-height:1.7;'>"
                            + "<br/>".join(html.escape(item) for item in failed_like[:3])
                            + "</div>"
                        )
                    step_lines.append("</div>")
                else:
                    step_lines.append(
                        "<div style='margin-bottom:8px; padding:10px 12px; background:#F8FBFE; border:1px solid #D9E2EC; border-radius:10px;'>"
                        f"<div style='font-size:13px; font-weight:700; color:#18212B;'>{html.escape(str(step_id))}</div>"
                        f"<div style='margin-top:4px; font-size:12px; color:#536273;'>{html.escape(str(payload))}</div>"
                        "</div>"
                    )

        task_paths = data.get("task_paths")
        file_lines: list[str] = []
        if isinstance(task_paths, dict) and task_paths:
            for key in ("task_dir", "spec", "summary", "events", "result"):
                value = task_paths.get(key)
                if value:
                    short_label = self._short_agent_path_label(str(value), task)
                    file_lines.append(
                        "<div style='margin-bottom:8px; padding:10px 12px; background:#F8FBFE; border:1px solid #D9E2EC; border-radius:10px;'>"
                        "<div style='font-size:12px; color:#708095;'>"
                        f"{html.escape(key)}</div>"
                        "<div style='margin-top:4px; font-size:13px; font-weight:700; color:#18212B;'>"
                        "{link}</div></div>".format(
                            key=html.escape(key),
                            link=self._make_agent_path_link(short_label, str(value)),
                        )
                    )

        failed_step = data.get("failed_step")
        failure_bits: list[str] = []
        if failed_step:
            failure_bits.append(f"失败步骤：{html.escape(str(failed_step))}")
        tool_name = data.get("tool_name")
        if tool_name:
            failure_bits.append(f"失败工具：{html.escape(str(tool_name))}")
        resolved_payload = data.get("resolved_payload")
        if isinstance(resolved_payload, dict) and resolved_payload:
            keys = ", ".join(sorted(str(k) for k in resolved_payload.keys())[:10])
            failure_bits.append(f"执行参数 keys：{html.escape(keys)}")

        sections = [
            section_card("结果卡", "".join(overview_lines)),
            section_card(
                "文件产物卡",
                "".join(file_lines)
                if file_lines
                else "<div style='font-size:12px; color:#536273; line-height:1.7;'>当前结果里还没有可展示的任务文件产物。</div>",
            ),
            section_card(
                "失败步骤卡",
                (
                    "<div style='padding:10px 12px; background:#FFF4F3; border:1px solid #EDC6C1; border-radius:10px; "
                    "font-size:12px; color:#8F3A34; line-height:1.7;'>"
                    + "<br/>".join(failure_bits)
                    + "</div>"
                )
                if failure_bits
                else "<div style='font-size:12px; color:#536273; line-height:1.7;'>当前没有失败步骤记录，任务可以继续从上方步骤流和事件流中回看。</div>",
            ),
        ]
        if step_lines:
            sections.insert(
                1,
                section_card("步骤结果卡", "".join(step_lines)),
            )

        return (
            "<div style='background:#FBFDFF; line-height:1.6;'>"
            + "".join(sections)
            + "</div>"
        )

    def _render_agent_events_timeline(self, events: list[Any]) -> None:
        filter_level = self._agent_event_level_filter_value()
        filter_type = self._agent_event_type_filter_value()
        keyword = self._agent_event_keyword_filter_value()
        self.agent_events_list.clear()
        visible_count = 0
        for event in events[-20:]:
            event_level = str(getattr(event, "level", "") or "info").lower()
            event_type = str(getattr(event, "event_type", "") or "")
            if filter_level and event_level != filter_level:
                continue
            if filter_type and event_type != filter_type:
                continue
            if keyword:
                haystack = " ".join(
                    [
                        event_type,
                        str(getattr(event, "message", "") or ""),
                        str(getattr(event, "level", "") or ""),
                        str(getattr(event, "timestamp", "") or ""),
                        json.dumps(getattr(event, "data", {}) or {}, ensure_ascii=False),
                    ]
                ).lower()
                if keyword not in haystack:
                    continue
            timeline_text = self._format_agent_event_timeline_item(
                event_type,
                str(getattr(event, "message", "")),
                str(getattr(event, "level", "")),
                str(getattr(event, "timestamp", "")),
            )
            data = getattr(event, "data", {}) or {}
            payload_text = json.dumps(data, ensure_ascii=False, indent=2) if data else ""
            item = QtWidgets.QListWidgetItem(timeline_text)
            item.setToolTip(payload_text or str(getattr(event, "message", "")))
            item.setData(QtCore.Qt.UserRole, timeline_text)
            self.agent_events_list.addItem(item)
            item.setSizeHint(QtCore.QSize(520, 96))
            self.agent_events_list.setItemWidget(
                item,
                self._build_agent_event_card(
                    event_type=event_type,
                    message=str(getattr(event, "message", "")),
                    level=event_level,
                    timestamp=str(getattr(event, "timestamp", "")),
                    payload_preview=payload_text,
                ),
            )
            visible_count += 1
        if visible_count == 0:
            self._add_list_empty_state(
                self.agent_events_list,
                "当前筛选条件下暂无事件",
                "你可以调整事件级别、类型或关键词筛选，匹配到的 Agent 事件会以时间线卡片显示在这里。",
                width=520,
                height=100,
            )
        self.btn_agent_clear_event_filters.setEnabled(bool(events))
        self.btn_agent_copy_selected_event.setEnabled(visible_count > 0)
        self.btn_agent_copy_events.setEnabled(visible_count > 0)

    def _build_agent_event_card(
        self,
        *,
        event_type: str,
        message: str,
        level: str,
        timestamp: str,
        payload_preview: str = "",
    ) -> QtWidgets.QFrame:
        variant = {
            "error": "Danger",
            "warning": "Warning",
            "info": "Info",
        }.get((level or "").strip().lower(), "Muted")
        card = QtWidgets.QFrame()
        card.setObjectName(f"agentEventCard{variant}")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(8)
        type_label = QtWidgets.QLabel(event_type or "event")
        type_label.setObjectName(f"agentEventBadge{variant}")
        top.addWidget(type_label, 0, QtCore.Qt.AlignTop)
        title_label = QtWidgets.QLabel(message or "事件无描述")
        title_label.setObjectName("agentEventTitle")
        title_label.setWordWrap(True)
        top.addWidget(title_label, 1)
        time_label = QtWidgets.QLabel(timestamp or "-")
        time_label.setObjectName("agentEventTime")
        top.addWidget(time_label, 0, QtCore.Qt.AlignTop)
        layout.addLayout(top)

        if payload_preview:
            lines = [line.strip() for line in payload_preview.splitlines() if line.strip()]
            preview = " | ".join(lines[:2])
            if len(preview) > 180:
                preview = preview[:180] + "..."
            detail_label = QtWidgets.QLabel(preview)
            detail_label.setObjectName("agentEventDetail")
            detail_label.setWordWrap(True)
            layout.addWidget(detail_label)
        return card

    def _on_agent_event_filter_changed(self, _text: str) -> None:
        events = self.agent_events_list.property("all_events") or []
        if isinstance(events, list):
            self._render_agent_events_timeline(events)

    def _clear_agent_event_filters(self) -> None:
        blocker_level = QtCore.QSignalBlocker(self.combo_agent_event_level)
        blocker_type = QtCore.QSignalBlocker(self.combo_agent_event_type)
        blocker_keyword = QtCore.QSignalBlocker(self.le_agent_event_keyword)
        self.combo_agent_event_level.setCurrentIndex(0)
        self.combo_agent_event_type.setCurrentIndex(0)
        self.le_agent_event_keyword.clear()
        del blocker_keyword
        del blocker_type
        del blocker_level
        self._on_agent_event_filter_changed("")

    def _copy_visible_agent_events(self) -> None:
        lines: list[str] = []
        for idx in range(self.agent_events_list.count()):
            text = self.agent_events_list.item(idx).text().strip()
            if text and "暂无事件" not in text:
                lines.append(text)
        if not lines:
            self.status.showMessage("当前没有可复制的事件。", 4000)
            return
        QtWidgets.QApplication.clipboard().setText("\n\n".join(lines))
        self.status.showMessage("已复制当前可见事件。", 4000)

    def _copy_selected_agent_event(self) -> None:
        item = self.agent_events_list.currentItem()
        if item is None:
            self.status.showMessage("请先选中一条事件。", 4000)
            return
        text = str(item.data(QtCore.Qt.UserRole) or item.text()).strip()
        if not text or "暂无事件" in text:
            self.status.showMessage("当前没有可复制的事件。", 4000)
            return
        QtWidgets.QApplication.clipboard().setText(text)
        self.status.showMessage("已复制选中事件。", 4000)

    @QtCore.Slot(QtCore.QUrl)
    def _on_agent_result_link_clicked(self, url: QtCore.QUrl) -> None:
        path = url.toLocalFile() or url.toString()
        if path:
            self._open_path(path)

    @QtCore.Slot(object)
    def _on_agent_result_link_hovered(self, value: object) -> None:
        if isinstance(value, QtCore.QUrl):
            url_text = value.toString()
        else:
            url_text = str(value or "")
        path = self._agent_result_link_targets.get(url_text, "")
        if path:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), path, self.agent_result_summary)
            self.status.showMessage(path, 4000)
        else:
            QtWidgets.QToolTip.hideText()

    @QtCore.Slot(QtCore.QPoint)
    def _show_agent_result_context_menu(self, pos: QtCore.QPoint) -> None:
        menu = self.agent_result_summary.createStandardContextMenu()
        href = self.agent_result_summary.anchorAt(pos)
        path = self._agent_result_link_targets.get(href, "")
        if path:
            menu.addSeparator()
            act_copy_path = menu.addAction("复制完整路径")
            act_open_parent = menu.addAction("打开所在目录")
            chosen = menu.exec(self.agent_result_summary.mapToGlobal(pos))
            if chosen == act_copy_path:
                QtWidgets.QApplication.clipboard().setText(path)
                self.status.showMessage("已复制完整路径。", 4000)
                return
            if chosen == act_open_parent:
                parent = str(Path(path).parent)
                self._open_dir(parent)
                return
            return
        menu.exec(self.agent_result_summary.mapToGlobal(pos))

    def _refresh_agent_detail_panel(self, task: Optional[QueueTask]) -> None:
        if task is None:
            self._set_agent_detail_placeholder("当前未选中任务。")
            return
        if task.origin != "agent" or not task.agent_task_id:
            self._set_agent_detail_placeholder("当前队列项不是 Agent 任务。")
            return
        self._refresh_agent_diagnostic_card(task)
        snapshot: dict[str, object] = {}
        store = TaskStore(task.workdir)
        try:
            persisted = asdict(store.load_task(task.agent_task_id))
            snapshot.update(persisted)
        except Exception:
            pass
        summary_state = self._agent_task_state.get(task.agent_task_id, {})
        if isinstance(summary_state, dict):
            snapshot.update(summary_state)
        try:
            events = store.load_events(task.agent_task_id)
        except Exception:
            events = []
        try:
            result_payload = asdict(store.load_result(task.agent_task_id)) if store.load_result(task.agent_task_id) else {}
        except Exception:
            result_payload = {}
        paths = self._agent_task_paths_for_queue_task(task)
        selected_urls_path = str(Path(task.workdir) / "05_selected_urls.txt")
        self.lbl_agent_queue_title.setText(str(snapshot.get("title") or task.task_name or "Agent 任务"))
        current_status = str(snapshot.get("status") or task.status or "-")
        self.lbl_agent_queue_status.setText(f"状态: {current_status} | task_id: {task.agent_task_id}")
        self.lbl_agent_queue_paths.setText(
            "workdir: {workdir}\nselected_urls: {urls}\ntask_dir: {task_dir}".format(
                workdir=task.workdir or "-",
                urls=selected_urls_path,
                task_dir=paths.get("task_dir", "-"),
            )
        )
        self.agent_steps_list.clear()
        self.agent_confirm_list.clear()
        steps = snapshot.get("steps") or []
        confirm_count = 0
        if isinstance(steps, list) and steps:
            for idx, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                title = str(step.get("title") or step.get("tool_name") or f"Step {idx}")
                status = str(step.get("status") or "-")
                message = str(step.get("message") or "").strip()
                detail = message or self._agent_step_detail(status, bool(step.get("requires_confirmation")))
                self._add_agent_step_card(
                    self.agent_steps_list,
                    idx,
                    title,
                    self._step_status_text(status),
                    detail,
                    variant=self._step_status_variant(status, bool(step.get("requires_confirmation"))),
                )
                if step.get("requires_confirmation"):
                    confirm_count += 1
                    self._add_agent_confirm_card(
                        self.agent_confirm_list,
                        idx,
                        title,
                        "待确认",
                        message or "这个步骤触发了确认边界，建议先检查结果摘要、事件时间线和输出目录，再决定是否继续。",
                        "确认后 Agent 会恢复执行，并继续推进下载、结果写入或目录落地动作。",
                    )
        else:
            self._add_list_empty_state(
                self.agent_steps_list,
                "暂无步骤信息",
                "当前任务还没有写入可展示的计划步骤，可能仍在初始化或只生成了部分状态。",
                width=520,
                height=100,
            )
        if self.agent_confirm_list.count() == 0:
            self._add_list_empty_state(
                self.agent_confirm_list,
                "当前没有待确认步骤",
                "这说明当前任务可以继续自动推进，除非后续步骤再命中新的确认边界。",
                width=520,
                height=100,
            )

        if current_status == "awaiting_confirmation":
            self.lbl_agent_control_notice.setText("当前任务已停在确认边界。先查看确认卡里的暂停原因和执行影响，再决定是否继续执行。")
            self.lbl_agent_control_notice.setObjectName("agentNoticeWarn")
        elif current_status in {"failed", "download_failed"}:
            self.lbl_agent_control_notice.setText("任务执行失败。优先查看最近事件和结果摘要中的失败步骤。")
            self.lbl_agent_control_notice.setObjectName("agentNoticeDanger")
        elif current_status == "succeeded":
            self.lbl_agent_control_notice.setText("任务已完成。可以从结果摘要和任务文件快速回看执行产物。")
            self.lbl_agent_control_notice.setObjectName("agentNoticeSuccess")
        else:
            self.lbl_agent_control_notice.setText("这是当前任务的控制中心，你可以在这里查看计划、确认边界、结果和事件时间线。")
            self.lbl_agent_control_notice.setObjectName("agentNoticeInfo")
        self.lbl_agent_control_notice.style().unpolish(self.lbl_agent_control_notice)
        self.lbl_agent_control_notice.style().polish(self.lbl_agent_control_notice)

        self.agent_result_summary.setHtml(self._summarize_agent_result(result_payload, task))
        self.agent_events_list.setProperty("all_events", list(events))
        self._populate_agent_event_type_filter(events)
        self._render_agent_events_timeline(events)
        self._set_metric_label(self.lbl_agent_metric_steps, "计划步骤", str(len(steps) if isinstance(steps, list) else 0))
        self._set_metric_label(self.lbl_agent_metric_confirm, "待确认", str(confirm_count), current_status)
        self._set_metric_label(self.lbl_agent_metric_events, "最近事件", str(len(events)), "时间线条目")
        self.btn_agent_open_workdir.setEnabled(bool(task.workdir))
        self.btn_agent_open_selected_urls.setEnabled(Path(selected_urls_path).exists())
        self.btn_agent_open_task_dir.setEnabled(bool(paths.get("task_dir")))
        spec_exists = Path(paths.get("spec", "")).exists()
        summary_exists = Path(paths.get("summary", "")).exists()
        events_exists = Path(paths.get("events", "")).exists()
        result_exists = Path(paths.get("result", "")).exists()
        self.act_agent_open_spec.setEnabled(spec_exists)
        self.act_agent_open_summary.setEnabled(summary_exists)
        self.act_agent_open_events.setEnabled(events_exists)
        self.act_agent_open_result.setEnabled(result_exists)
        self.btn_agent_open_artifacts.setEnabled(any([spec_exists, summary_exists, events_exists, result_exists]))

    @QtCore.Slot(int)
    def _on_main_tab_changed(self, idx: int) -> None:
        # 仅在“队列执行”页启用缩略图加载，避免启动阶段占用网络/CPU。
        self._thumb_lazy_enabled = idx == 1
        if self._thumb_lazy_enabled:
            self._schedule_visible_thumb_load()
        if hasattr(self, "side_nav") and self.side_nav.currentRow() != idx:
            blocker = QtCore.QSignalBlocker(self.side_nav)
            self.side_nav.setCurrentRow(idx)

    def _schedule_visible_thumb_load(self) -> None:
        if not self._thumb_lazy_enabled:
            return
        self._thumb_lazy_timer.start()

    def _load_visible_thumbs(self) -> None:
        if not self._thumb_lazy_enabled:
            return
        viewport = self.video_list_widget.viewport().rect()
        for n in range(self.video_list_widget.count()):
            item = self.video_list_widget.item(n)
            rect = self.video_list_widget.visualItemRect(item)
            if not rect.isValid() or not viewport.intersects(rect):
                continue
            widget = self.video_list_widget.itemWidget(item)
            if widget is None:
                continue
            video_id = str(widget.property("video_id") or "").strip()
            if video_id:
                self._ensure_thumb_async(video_id)

    def _video_thumb(self, video_id: str) -> QtGui.QPixmap:
        if video_id in self._thumb_cache:
            return self._thumb_cache[video_id]
        pm = QtGui.QPixmap(176, 99)
        pm.fill(QtGui.QColor("#212121"))
        painter = QtGui.QPainter(pm)
        painter.setPen(QtGui.QColor("#AAAAAA"))
        painter.drawText(pm.rect(), QtCore.Qt.AlignCenter, "加载中")
        painter.end()
        return pm

    def _fetch_thumb_job(self, video_id: str) -> None:
        try:
            url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = resp.read()
        except Exception:
            data = b""
        finally:
            self._thumb_fetching.discard(video_id)
            self.thumb_ready.emit(video_id, data)

    def _ensure_thumb_async(self, video_id: str) -> None:
        if not video_id:
            return
        if video_id in self._thumb_cache or video_id in self._thumb_fetching:
            return
        self._thumb_fetching.add(video_id)
        self._thumb_executor.submit(self._fetch_thumb_job, video_id)

    @QtCore.Slot(str, bytes)
    def _on_thumb_ready(self, video_id: str, data: bytes) -> None:
        if data:
            loaded = QtGui.QPixmap()
            if loaded.loadFromData(data):
                pm = loaded.scaled(176, 99, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
                self._thumb_cache[video_id] = pm
        for n in range(self.video_list_widget.count()):
            item = self.video_list_widget.item(n)
            widget = self.video_list_widget.itemWidget(item)
            if widget is None:
                continue
            if widget.property("video_id") != video_id:
                continue
            lbl_thumb = widget.findChild(QtWidgets.QLabel, "thumb")
            if lbl_thumb is not None:
                lbl_thumb.setPixmap(self._video_thumb(video_id))
            break

    def load_selected_task_videos(self) -> None:
        task = self._current_task()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先在上方任务列表选择一个任务。")
            return
        csv_path = Path(task.workdir) / "04_selected_for_review.csv"
        scored_path = Path(task.workdir) / "03_scored_candidates.jsonl"
        if not csv_path.exists() and not scored_path.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"未找到筛选结果: {csv_path}")
            return
        rows: list[dict] = []
        try:
            if scored_path.exists():
                for line in scored_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    agent_selected = bool(item.get("selected"))
                    rows.append(
                        {
                            "selected": agent_selected,
                            "agent_selected": agent_selected,
                            "title": (item.get("title") or "").strip(),
                            "channel": (item.get("channel") or "").strip(),
                            "upload_date": str(item.get("upload_date") or "").strip(),
                            "duration": str(item.get("duration") or "").strip(),
                            "watch_url": (item.get("watch_url") or "").strip(),
                            "video_id": (item.get("video_id") or "").strip(),
                            "vector_score": item.get("vector_score"),
                            "vector_threshold": item.get("vector_threshold"),
                            "score": item.get("score"),
                            "reasons": item.get("reasons"),
                            "manual_review": item.get("manual_review"),
                        }
                    )
            else:
                with csv_path.open("r", encoding="utf-8", newline="") as fh:
                    reader = csv.DictReader(fh)
                    for r in reader:
                        rows.append(
                            {
                                "selected": False,
                                "agent_selected": True,
                                "title": (r.get("title") or "").strip(),
                                "channel": (r.get("channel") or "").strip(),
                                "upload_date": (r.get("upload_date") or "").strip(),
                                "duration": (r.get("duration") or "").strip(),
                                "watch_url": (r.get("watch_url") or "").strip(),
                                "video_id": (r.get("video_id") or "").strip(),
                            }
                        )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "读取失败", f"读取筛选结果失败:\n{exc}")
            return
        self.video_rows = rows
        self.video_view_indices = list(range(len(self.video_rows)))
        self.video_page = 1
        self._apply_video_view()

    def _apply_video_view(self, *_args) -> None:
        indices = list(range(len(self.video_rows)))
        scope = self.combo_video_scope.currentText() if hasattr(self, "combo_video_scope") else "可下载"
        if scope == "可下载":
            indices = [i for i in indices if str(self.video_rows[i].get("watch_url", "")).strip().startswith("http")]
        elif scope == "Agent 推荐":
            indices = [i for i in indices if bool(self.video_rows[i].get("agent_selected"))]
        elif scope == "已勾选":
            indices = [i for i in indices if bool(self.video_rows[i].get("selected"))]
        elif scope == "低相似":
            indices = [i for i in indices if self._is_low_similarity(self.video_rows[i])]
        elif scope == "需复核":
            indices = [i for i in indices if bool(self.video_rows[i].get("manual_review"))]

        kw = self.le_video_filter.text().strip().lower() if hasattr(self, "le_video_filter") else ""
        if kw:
            def _hit(i: int) -> bool:
                r = self.video_rows[i]
                s = " ".join(
                    [
                        str(r.get("title", "")),
                        str(r.get("channel", "")),
                        str(r.get("watch_url", "")),
                    ]
                ).lower()
                return kw in s
            indices = [i for i in indices if _hit(i)]

        sort_mode = self.combo_video_sort.currentText() if hasattr(self, "combo_video_sort") else "默认排序"
        if sort_mode == "语义分数(高->低)":
            indices.sort(key=lambda i: float(self.video_rows[i].get("vector_score") or 0.0), reverse=True)
        elif sort_mode == "上传日期(新->旧)":
            indices.sort(key=lambda i: int(re.sub(r"\D", "", str(self.video_rows[i].get("upload_date", ""))) or 0), reverse=True)
        elif sort_mode == "时长(长->短)":
            indices.sort(key=lambda i: int(str(self.video_rows[i].get("duration", "0")) if str(self.video_rows[i].get("duration", "0")).isdigit() else 0), reverse=True)
        elif sort_mode == "标题(A-Z)":
            indices.sort(key=lambda i: str(self.video_rows[i].get("title", "")).lower())

        self.video_view_indices = indices
        self.video_page = 1
        self._render_video_page()

    def _safe_float(self, value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _step_status_color(self, status: str) -> QtGui.QColor:
        s = (status or "").strip().lower()
        if s in {"completed", "succeeded"}:
            return QtGui.QColor(ui_theme.TOKENS["state_success"])
        if s == "running":
            return QtGui.QColor(ui_theme.TOKENS["state_info"])
        if s == "awaiting_confirmation":
            return QtGui.QColor(ui_theme.TOKENS["state_warning"])
        if s in {"failed", "error"}:
            return QtGui.QColor(ui_theme.TOKENS["state_error"])
        return QtGui.QColor(ui_theme.TOKENS["text_secondary"])

    def _refresh_video_summary_bar(self) -> None:
        if not hasattr(self, "lbl_video_stat_ready"):
            return
        if not self.video_view_indices:
            self._set_metric_label(self.lbl_video_stat_ready, "本页可下载", "-")
            self._set_metric_label(self.lbl_video_stat_low, "低相似", "-")
            self._set_metric_label(self.lbl_video_stat_review, "需复核", "-")
            self._set_metric_label(self.lbl_video_stat_checked, "已勾选", "-")
            return
        start = (self.video_page - 1) * self.video_page_size
        end = min(len(self.video_view_indices), start + self.video_page_size)
        page_indices = self.video_view_indices[start:end]
        ready_count = sum(1 for i in page_indices if bool(self.video_rows[i].get("agent_selected", self.video_rows[i].get("selected"))))
        low_count = sum(1 for i in page_indices if self._is_low_similarity(self.video_rows[i]))
        review_count = sum(1 for i in page_indices if bool(self.video_rows[i].get("manual_review")))
        checked_count = sum(1 for i in page_indices if bool(self.video_rows[i].get("selected")))
        self._set_metric_label(self.lbl_video_stat_ready, "本页可下载", str(ready_count), f"共 {len(page_indices)} 条")
        self._set_metric_label(self.lbl_video_stat_low, "低相似", str(low_count), "需重点复核")
        self._set_metric_label(self.lbl_video_stat_review, "需复核", str(review_count), "人工判断")
        self._set_metric_label(self.lbl_video_stat_checked, "已勾选", str(checked_count), "待执行")

    def _is_low_similarity(self, row: dict) -> bool:
        if row.get("vector_score") in (None, ""):
            return False
        score = self._safe_float(row.get("vector_score"))
        threshold = self._safe_float(row.get("vector_threshold"), 0.12)
        return score < threshold

    def _render_video_page(self) -> None:
        total = len(self.video_view_indices)
        pages = max(1, (total + self.video_page_size - 1) // self.video_page_size) if total else 0
        if pages and self.video_page > pages:
            self.video_page = pages
        start = (self.video_page - 1) * self.video_page_size if pages else 0
        end = min(total, start + self.video_page_size)
        if total > 0:
            self.lbl_video_page.setText(f"第 {self.video_page if pages else 0}/{pages} 页 · 第 {start + 1}-{end} 条 / 共 {total} 条")
        else:
            self.lbl_video_page.setText("第 0/0 页 · 共 0 条")
        self.btn_prev_page.setEnabled(pages > 0 and self.video_page > 1)
        self.btn_next_page.setEnabled(pages > 0 and self.video_page < pages)
        self.video_list_widget.clear()
        if total == 0:
            self._add_list_empty_state(
                self.video_list_widget,
                "当前没有可展示的视频",
                "先加载任务视频，或调整筛选范围、关键词和排序条件。满足条件的候选视频会以审核卡形式显示在这里。",
                width=920,
                height=118,
            )
            self._refresh_video_summary_bar()
            return
        for pos in range(start, end):
            i = self.video_view_indices[pos]
            row = self.video_rows[i]
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(920, 292))
            self.video_list_widget.addItem(item)
            widget = self._make_video_card(i, row)
            self.video_list_widget.setItemWidget(item, widget)
        self._refresh_video_summary_bar()
        self._schedule_visible_thumb_load()

    def _video_status_text(self, row: dict) -> tuple[str, str]:
        if row.get("manual_review"):
            return "需复核", "videoStatusWarn"
        if bool(row.get("agent_selected")):
            return "可下载", "videoStatusOk"
        if self._is_low_similarity(row):
            return "低相似", "videoStatusMuted"
        return "未入选", "videoStatusMuted"

    def _video_reasons_summary(self, row: dict) -> str:
        raw = row.get("reasons") or row.get("vector_reason") or ""
        if isinstance(raw, list):
            parts = [str(x).strip() for x in raw if str(x).strip()]
        else:
            text = str(raw).replace("\r", "\n")
            parts = [p.strip(" ;；,，") for p in re.split(r"[\n;；]+", text) if p.strip(" ;；,，")]
        if not parts:
            return "暂无筛选原因记录"
        summary = "；".join(parts[:2])
        return summary[:130] + ("..." if len(summary) > 130 else "")

    def _video_score_label(self, row: dict) -> str:
        bits = []
        if row.get("vector_score") not in (None, ""):
            score = self._safe_float(row.get("vector_score"))
            level = "高" if score >= 0.22 else "中" if score >= 0.12 else "低"
            bits.append(f"语义 {score:.3f} · {level}")
        if row.get("score") not in (None, ""):
            bits.append(f"规则 {row.get('score')}")
        return " | ".join(bits) if bits else "未记录语义分"

    def _video_similarity_tone(self, row: dict) -> str:
        if self._is_low_similarity(row):
            return "danger"
        score = self._safe_float(row.get("vector_score"))
        if score >= 0.22:
            return "success"
        if score >= 0.12:
            return "warning"
        return "muted"

    def _video_decision_summary(self, row: dict) -> tuple[str, str, str]:
        if row.get("manual_review"):
            return (
                "需要人工复核",
                "检测到边界结果，建议先人工确认标题、来源和筛选原因，再决定是否下载。",
                "decisionCardReview",
            )
        if self._is_low_similarity(row):
            return (
                "语义相似度偏低",
                "语义分低于当前阈值，建议谨慎处理，优先检查标题与来源是否匹配真实需求。",
                "decisionCardRisk",
            )
        if bool(row.get("agent_selected")):
            return (
                "Agent 推荐通过",
                "该视频已通过当前筛选规则，可以直接加入下载范围，必要时再做人工抽查。",
                "decisionCardReady",
            )
        return (
            "当前未进入下载结果",
            "这条视频没有进入最终推荐集合，可保留观察，也可以忽略。",
            "decisionCardMuted",
        )

    def _video_next_action_text(self, row: dict) -> str:
        if row.get("manual_review"):
            return "建议动作：先打开链接核对内容，再决定是否手动勾选下载。"
        if self._is_low_similarity(row):
            return "建议动作：优先人工核对，必要时降低筛选约束后重试任务。"
        if bool(row.get("agent_selected")):
            return "建议动作：可直接勾选并下载，或抽查来源链接后再批量执行。"
        return "建议动作：保留为候选，不建议优先下载。"

    def _make_video_card(self, idx: int, row: dict) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("videoAuditCard")
        card.setProperty("video_id", row.get("video_id", ""))
        h = QtWidgets.QHBoxLayout(card)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(14)

        rail = QtWidgets.QVBoxLayout()
        rail.setSpacing(8)
        rail.setAlignment(QtCore.Qt.AlignTop)
        chk = QtWidgets.QCheckBox("勾选")
        chk.setChecked(bool(row.get("selected")))
        chk.toggled.connect(lambda state, k=idx: self._set_video_checked(k, state))
        rail.addWidget(chk)
        audit_badge = QtWidgets.QLabel("审核优先" if row.get("manual_review") else "已自动判断")
        audit_badge.setObjectName("statusPillWarning" if row.get("manual_review") else "statusPillInfo")
        rail.addWidget(audit_badge, 0, QtCore.Qt.AlignLeft)
        h.addLayout(rail, 0)

        lbl_thumb = QtWidgets.QLabel()
        lbl_thumb.setObjectName("thumb")
        lbl_thumb.setFixedSize(176, 99)
        lbl_thumb.setPixmap(self._video_thumb(row.get("video_id", "")))
        h.addWidget(lbl_thumb, 0, QtCore.Qt.AlignTop)

        v = QtWidgets.QVBoxLayout()
        v.setSpacing(8)
        title = QtWidgets.QLabel(row.get("title", "(无标题)"))
        title.setObjectName("videoAuditTitle")
        title.setWordWrap(True)
        meta = QtWidgets.QLabel(
            f"作者 {row.get('channel', '-')}  ·  上传 {row.get('upload_date', '-')}  ·  时长 {self._format_duration(str(row.get('duration', '-')))}"
        )
        meta.setObjectName("videoAuditMeta")
        badge_row = QtWidgets.QHBoxLayout()
        badge_row.setSpacing(8)
        status_text, status_name = self._video_status_text(row)
        status_label = QtWidgets.QLabel(status_text)
        status_label.setObjectName(status_name)
        score_label = QtWidgets.QLabel(self._video_score_label(row))
        score_label.setObjectName(f"statusPill{self._video_similarity_tone(row).capitalize()}")
        score_label.setToolTip(str(row.get("reasons") or ""))
        review_label = QtWidgets.QLabel("低相似提醒" if self._is_low_similarity(row) else ("Agent 推荐" if bool(row.get("agent_selected")) else "候选观察"))
        review_label.setObjectName(
            "statusPillDanger"
            if self._is_low_similarity(row)
            else ("statusPillInfo" if bool(row.get("agent_selected")) else "statusPillMuted")
        )
        badge_row.addWidget(status_label, 0, QtCore.Qt.AlignLeft)
        badge_row.addWidget(score_label, 0, QtCore.Qt.AlignLeft)
        badge_row.addWidget(review_label, 0, QtCore.Qt.AlignLeft)
        badge_row.addStretch()

        decision_title, decision_detail, decision_style = self._video_decision_summary(row)
        decision_card = QtWidgets.QFrame()
        decision_card.setObjectName(decision_style)
        decision_layout = QtWidgets.QVBoxLayout(decision_card)
        decision_layout.setContentsMargins(10, 9, 10, 9)
        decision_layout.setSpacing(4)
        decision_head = QtWidgets.QLabel(decision_title)
        decision_head.setObjectName("videoDecisionTitle")
        decision_desc = QtWidgets.QLabel(decision_detail)
        decision_desc.setObjectName("videoDecisionDetail")
        decision_desc.setWordWrap(True)
        decision_layout.addWidget(decision_head)
        decision_layout.addWidget(decision_desc)

        reason_head = QtWidgets.QLabel("审核结论")
        reason_head.setObjectName("videoAuditSection")
        reason = QtWidgets.QLabel(self._video_reasons_summary(row))
        reason.setObjectName("videoReason")
        reason.setWordWrap(True)
        reason.setToolTip(str(row.get("reasons") or row.get("vector_reason") or ""))

        watch_head = QtWidgets.QLabel("来源链接")
        watch_head.setObjectName("videoAuditSection")
        url = QtWidgets.QLabel(row.get("watch_url", ""))
        url.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        url.setObjectName("videoAuditUrl")
        next_action = QtWidgets.QLabel(self._video_next_action_text(row))
        next_action.setObjectName("videoNextAction")
        next_action.setWordWrap(True)

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(8)
        btn_open = QtWidgets.QPushButton("打开链接")
        btn_open.setObjectName("secondary")
        btn_open.clicked.connect(lambda _checked=False, k=idx: self.open_video_url(k))
        btn_single = QtWidgets.QPushButton("下载单条")
        btn_single.setObjectName("secondary")
        btn_single.clicked.connect(lambda _checked=False, k=idx: self.download_single_video(k))
        action_row.addWidget(btn_open)
        action_row.addWidget(btn_single)
        action_row.addStretch()
        v.addWidget(title)
        v.addWidget(meta)
        v.addLayout(badge_row)
        v.addWidget(decision_card)
        v.addWidget(reason_head)
        v.addWidget(reason)
        v.addWidget(watch_head)
        v.addWidget(url)
        v.addWidget(next_action)
        v.addLayout(action_row)
        h.addLayout(v, 1)
        return card

    def _on_page_size_changed(self, _idx: int) -> None:
        text = self.combo_page_size.currentText()
        if text.startswith("20"):
            self.video_page_size = 20
        elif text.startswith("30"):
            self.video_page_size = 30
        else:
            self.video_page_size = 10
        self.video_page = 1
        self._render_video_page()

    def _set_video_checked(self, idx: int, checked: bool) -> None:
        if 0 <= idx < len(self.video_rows):
            self.video_rows[idx]["selected"] = bool(checked)

    def select_all_videos_on_page(self) -> None:
        if not self.video_view_indices:
            return
        start = (self.video_page - 1) * self.video_page_size
        end = min(len(self.video_view_indices), start + self.video_page_size)
        for pos in range(start, end):
            i = self.video_view_indices[pos]
            self.video_rows[i]["selected"] = True
        self._render_video_page()

    def unselect_all_videos_on_page(self) -> None:
        if not self.video_view_indices:
            return
        start = (self.video_page - 1) * self.video_page_size
        end = min(len(self.video_view_indices), start + self.video_page_size)
        for pos in range(start, end):
            i = self.video_view_indices[pos]
            self.video_rows[i]["selected"] = False
        self._render_video_page()

    def prev_video_page(self) -> None:
        if self.video_page > 1:
            self.video_page -= 1
            self._render_video_page()

    def next_video_page(self) -> None:
        total = len(self.video_view_indices)
        pages = max(1, (total + self.video_page_size - 1) // self.video_page_size) if total else 0
        if self.video_page < pages:
            self.video_page += 1
            self._render_video_page()

    def _selected_queue_rows(self) -> list[int]:
        view_rows = sorted({idx.row() for idx in self.queue_list.selectedIndexes()})
        mapped_rows: list[int] = []
        for view_row in view_rows:
            task_index = self._queue_task_index_from_view_row(view_row)
            if task_index is not None and 0 <= task_index < len(self.task_queue):
                mapped_rows.append(task_index)
        return mapped_rows

    def _selected_downloaded_record(self) -> Optional[dict]:
        row = self.downloaded_list.currentRow() if hasattr(self, "downloaded_list") else -1
        if row < 0 or row >= len(self.downloaded_records):
            return None
        return self.downloaded_records[row]

    def _collect_downloaded_records(self) -> list[dict]:
        records: list[dict] = []
        for task in self.task_queue:
            if task.status not in {"downloaded", "download_failed", "downloading", "paused_download"} and task.selected_count <= 0:
                continue
            ok_n, fail_n, unk_n, session_path, report_path = self._read_download_summary(Path(task.workdir))
            out_dir = session_path.strip() if session_path.strip() else task.download_dir
            records.append(
                {
                    "task_name": task.task_name,
                    "status": task.status,
                    "ok": ok_n,
                    "fail": fail_n,
                    "unknown": unk_n,
                    "dir": out_dir,
                    "report": report_path,
                    "run_id": task.run_id,
                }
            )
        records.sort(key=lambda r: str(r.get("run_id", "")), reverse=True)
        return records

    def refresh_downloaded_view(self) -> None:
        self.downloaded_records = self._collect_downloaded_records()
        self.downloaded_list.clear()
        if not self.downloaded_records:
            self.lbl_downloaded_detail.setText("暂无下载记录")
            return
        status_label = {
            "downloaded": "已完成",
            "download_failed": "失败",
            "downloading": "下载中",
            "paused_download": "已暂停",
        }
        for rec in self.downloaded_records:
            st = status_label.get(str(rec.get("status", "")), str(rec.get("status", "")))
            text = (
                f"[{st}] {rec.get('task_name', '-')[:28]} | 成功 {rec.get('ok', 0)} "
                f"失败 {rec.get('fail', 0)} 其他 {rec.get('unknown', 0)}"
            )
            item = QtWidgets.QListWidgetItem(text)
            self.downloaded_list.addItem(item)
        self.downloaded_list.setCurrentRow(0)

    def _update_downloaded_detail(self, row: int) -> None:
        if row < 0 or row >= len(self.downloaded_records):
            self.lbl_downloaded_detail.setText("暂无下载记录")
            return
        rec = self.downloaded_records[row]
        self.lbl_downloaded_detail.setText(
            f"任务: {rec.get('task_name', '-')}\n"
            f"状态: {rec.get('status', '-')}\n"
            f"成功: {rec.get('ok', 0)} | 失败: {rec.get('fail', 0)} | 其他: {rec.get('unknown', 0)}\n"
            f"目录: {rec.get('dir', '-')}\n"
            f"报告: {rec.get('report', '-')}"
        )

    def open_selected_downloaded_dir(self) -> None:
        rec = self._selected_downloaded_record()
        if rec is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一条下载记录。")
            return
        self._open_dir(str(rec.get("dir", "")))

    def open_selected_downloaded_report(self) -> None:
        rec = self._selected_downloaded_record()
        if rec is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一条下载记录。")
            return
        report = Path(str(rec.get("report", "")))
        if not report.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"报告不存在: {report}")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(report))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(report)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(report)])

    def pause_current_task(self) -> None:
        if self.runner.proc.state() == QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.information(self, "提示", "当前没有正在运行的任务。")
            return
        self.pause_requested = True
        self.user_stopped = False
        self.download_all_mode = False
        self.lbl_progress_status.setText("正在暂停任务...")
        self.runner.kill()

    def resume_selected_task(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        rows = self._selected_queue_rows()
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个任务。")
            return
        row = rows[0]
        task = self.task_queue[row]
        if task.status == "paused_filter":
            self.active_queue_index = row
            self.active_run_kind = "filter_queue"
            task.status = "running"
            self._refresh_queue_list()
            self._start_process(task.args, task.workdir)
            return
        if task.status == "paused_download":
            self._start_download_for_row(row)
            return
        QtWidgets.QMessageBox.information(self, "提示", "选中任务不是可继续状态。")

    def _on_queue_item_double_clicked(self, _item: QtWidgets.QListWidgetItem) -> None:
        self.load_selected_task_videos()
        if self.tabs.currentIndex() != 1:
            self.tabs.setCurrentIndex(1)

    def _start_download_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self.task_queue):
            return
        task = self.task_queue[row]
        self.active_queue_index = row
        self.active_run_kind = "download_queue"
        self.download_all_mode = False
        task.status = "downloading"
        self._refresh_queue_list()
        self._start_process(self._download_args_for_task(task), task.workdir)

    def open_selected_task_workdir(self) -> None:
        rows = self._selected_queue_rows()
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个任务。")
            return
        task = self.task_queue[rows[0]]
        self._open_dir(task.workdir)

    def open_selected_agent_workdir(self) -> None:
        task = self._selected_queue_task()
        if task is None or task.origin != "agent":
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        self._open_dir(task.workdir)

    def open_selected_agent_selected_urls(self) -> None:
        task = self._selected_queue_task()
        if task is None or task.origin != "agent":
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        path = Path(task.workdir) / "05_selected_urls.txt"
        self._open_path(str(path))

    def open_selected_agent_task_dir(self) -> None:
        task = self._selected_queue_task()
        if task is None or task.origin != "agent":
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        paths = self._agent_task_paths_for_queue_task(task)
        task_dir = paths.get("task_dir", "")
        if not task_dir:
            QtWidgets.QMessageBox.information(self, "提示", "当前任务还没有可用的持久化目录。")
            return
        self._open_dir(task_dir)

    def open_selected_agent_spec_file(self) -> None:
        task, paths = self._selected_agent_task_and_paths()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        self._open_path(paths.get("spec", ""))

    def open_selected_agent_summary_file(self) -> None:
        task, paths = self._selected_agent_task_and_paths()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        self._open_path(paths.get("summary", ""))

    def open_selected_agent_events_file(self) -> None:
        task, paths = self._selected_agent_task_and_paths()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        self._open_path(paths.get("events", ""))

    def open_selected_agent_result_file(self) -> None:
        task, paths = self._selected_agent_task_and_paths()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个 Agent 任务。")
            return
        self._open_path(paths.get("result", ""))

    def promote_selected_tasks(self) -> None:
        rows = self._selected_queue_rows()
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择要置顶的任务。")
            return
        running_task = None
        if self.active_queue_index is not None and 0 <= self.active_queue_index < len(self.task_queue):
            running_task = self.task_queue[self.active_queue_index]
        selected_set = set(rows)
        selected_tasks = [self.task_queue[i] for i in rows]
        others = [t for i, t in enumerate(self.task_queue) if i not in selected_set]
        self.task_queue = selected_tasks + others
        if running_task is not None:
            try:
                self.active_queue_index = self.task_queue.index(running_task)
            except ValueError:
                self.active_queue_index = None
        self._refresh_queue_list()
        self.queue_list.clearSelection()
        for i in range(len(selected_tasks)):
            item = self.queue_list.item(i)
            if item is not None:
                item.setSelected(True)
        self.status.showMessage(f"已将 {len(selected_tasks)} 个任务置顶。", 4000)

    def retry_selected_failed_tasks(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        rows = self._selected_queue_rows()
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先选择一个或多个任务。")
            return
        retry_filter = 0
        retry_download = 0
        first_download_row: Optional[int] = None
        for row in rows:
            task = self.task_queue[row]
            if task.status in {"failed", "stopped"}:
                task.status = "pending"
                retry_filter += 1
                continue
            if task.status == "download_failed":
                if task.selected_count > 0:
                    task.status = "ready_download"
                    retry_download += 1
                    if first_download_row is None:
                        first_download_row = row
                else:
                    task.status = "filtered_empty"
        if retry_filter == 0 and retry_download == 0:
            QtWidgets.QMessageBox.information(self, "提示", "选中任务中没有可重试的失败项。")
            return
        self._refresh_queue_list()
        if retry_filter > 0:
            self.status.showMessage(f"已重试筛选任务 {retry_filter} 个。", 5000)
            self.start_queue()
            return
        if first_download_row is not None:
            self.status.showMessage(f"已重试下载任务 {retry_download} 个。", 5000)
            self._start_download_for_row(first_download_row)

    def retry_failed_urls_for_selected_task(self) -> None:
        task = self._current_task()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先在任务列表选择一个任务。")
            return
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        failed_ref = resolve_download_session_pointers(task.workdir)
        failed_file = Path(failed_ref.failed_urls_file) if failed_ref.failed_urls_file else Path(task.workdir) / "06_failed_urls.txt"
        if not failed_file.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"未找到失败清单: {failed_file}")
            return
        urls = [ln.strip() for ln in failed_file.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")]
        if not urls:
            QtWidgets.QMessageBox.information(self, "提示", "失败清单为空，无需重试。")
            return
        task.status = "downloading"
        self.active_queue_index = self._current_task_index()
        self.active_run_kind = "download_queue"
        self.download_all_mode = False
        self._refresh_queue_list()
        self._start_process(self._download_args_for_task_with_file(task, str(failed_file)), task.workdir)

    def download_checked_videos(self) -> None:
        task = self._current_task()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先在上方任务列表选择一个任务。")
            return
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        urls = [str(r.get("watch_url", "")).strip() for r in self.video_rows if r.get("selected")]
        urls = [u for u in urls if u.startswith("http")]
        if not urls:
            QtWidgets.QMessageBox.information(self, "提示", "请先勾选要下载的视频。")
            return
        out_file = Path(task.workdir) / "05_selected_urls_manual_page.txt"
        out_file.write_text("\n".join(urls) + "\n", encoding="utf-8")
        task.status = "downloading"
        self.active_queue_index = self._current_task_index()
        self.active_run_kind = "download_queue"
        self.download_all_mode = False
        self._refresh_queue_list()
        self._start_process(self._download_args_for_task_with_file(task, str(out_file)), task.workdir)

    def open_video_url(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.video_rows):
            return
        url = str(self.video_rows[idx].get("watch_url", "")).strip()
        if not url.startswith("http"):
            QtWidgets.QMessageBox.information(self, "提示", "这条视频没有可打开的链接。")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def download_single_video(self, idx: int) -> None:
        task = self._current_task()
        if task is None:
            QtWidgets.QMessageBox.information(self, "提示", "请先在上方任务列表选择一个任务。")
            return
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        if idx < 0 or idx >= len(self.video_rows):
            return
        url = str(self.video_rows[idx].get("watch_url", "")).strip()
        if not url.startswith("http"):
            QtWidgets.QMessageBox.information(self, "提示", "这条视频没有可下载的链接。")
            return
        video_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(self.video_rows[idx].get("video_id") or "single")).strip("_") or "single"
        out_file = Path(task.workdir) / f"05_selected_url_{video_id}.txt"
        out_file.write_text(url + "\n", encoding="utf-8")
        task.status = "downloading"
        self.active_queue_index = self._current_task_index()
        self.active_run_kind = "download_queue"
        self.download_all_mode = False
        self._refresh_queue_list()
        self._start_process(self._download_args_for_task_with_file(task, str(out_file)), task.workdir)

    def _find_latest_resume_workdir(self) -> Optional[Path]:
        root = Path(self._combo_text(self.cb_workdir)).resolve()
        if not root.exists():
            return None
        candidates: list[Path] = []
        for d in root.iterdir():
            if not d.is_dir():
                continue
            if not d.name.startswith("run_"):
                continue
            urls = d / "05_selected_urls.txt"
            if not urls.exists():
                continue
            try:
                count = len([ln.strip() for ln in urls.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")])
            except Exception:
                count = 0
            if count > 0:
                candidates.append(d)
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def resume_last_download_task(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        latest = self._find_latest_resume_workdir()
        if latest is None:
            QtWidgets.QMessageBox.information(self, "提示", "未找到可恢复的历史下载任务。")
            return
        selected_count = self._count_selected_urls(str(latest))
        if selected_count <= 0:
            QtWidgets.QMessageBox.information(self, "提示", "最近任务没有可下载 URL。")
            return
        run_id = latest.name.replace("run_", "", 1)
        sess_name = ""
        session_ref = resolve_download_session_pointers(latest)
        if session_ref.session_dir:
            try:
                p = Path(session_ref.session_dir)
                if p.name:
                    sess_name = p.name
            except Exception:
                sess_name = ""
        if not sess_name:
            sess_name = (re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", latest.name).strip("._-")[:72] or run_id)
        task = QueueTask(
            args=[],
            task_name=f"恢复任务 {latest.name[:48]}",
            workdir=str(latest),
            run_id=run_id,
            download_dir=self._combo_text(self.cb_downloaddir),
            cookies_browser=self.combo_cookies_browser.currentText().strip(),
            cookies_file=self.le_cookies_file.text().strip(),
            yt_extra_args=self.le_yt_extra_args.text().strip(),
            download_mode=self.combo_download_mode.currentText(),
            include_audio=self.chk_include_audio.isChecked(),
            video_container=self.combo_video_container.currentText(),
            max_height=self.combo_max_height.currentText(),
            audio_format=self.combo_audio_format.currentText(),
            audio_quality=self.spin_audio_quality.value(),
            concurrent_videos=self.spin_concurrent_videos.value(),
            concurrent_fragments=self.spin_concurrent_fragments.value(),
            clean_video=self.chk_clean_video.isChecked(),
            sponsorblock_remove=self._selected_sponsorblock_remove(),
            download_session_name=sess_name,
        )
        task.selected_count = selected_count
        task.status = "downloading"
        self.task_queue.append(task)
        row = len(self.task_queue) - 1
        self.active_queue_index = row
        self.active_run_kind = "download_queue"
        self.download_all_mode = False
        self._refresh_queue_list()
        self.status.showMessage(f"已恢复最近任务并开始续传: {latest}", 6000)
        self._start_process(self._download_args_for_task(task), task.workdir)

    def download_selected_task(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        rows = self._selected_queue_rows()
        if not rows:
            QtWidgets.QMessageBox.information(self, "提示", "请先在队列中选中一个任务。")
            return
        row = rows[0]
        task = self.task_queue[row]
        if task.status not in {"ready_download", "download_failed", "downloaded"} and task.selected_count <= 0:
            QtWidgets.QMessageBox.information(self, "提示", "该任务尚未筛选出可下载 URL，请先执行筛选。")
            return
        self._start_download_for_row(row)

    def download_all_ready_tasks(self) -> None:
        if self.runner.proc.state() != QtCore.QProcess.NotRunning:
            QtWidgets.QMessageBox.warning(self, "正在运行", "请先等待当前任务结束。")
            return
        ready = [i for i, t in enumerate(self.task_queue) if t.selected_count > 0 and t.status == "ready_download"]
        if not ready:
            QtWidgets.QMessageBox.information(self, "提示", "没有可下载的已筛选任务。")
            return
        self.download_all_mode = True
        first = ready[0]
        self.active_queue_index = first
        self.active_run_kind = "download_queue"
        task = self.task_queue[first]
        task.status = "downloading"
        self._refresh_queue_list()
        self._start_process(self._download_args_for_task(task), task.workdir)

    def _start_next_ready_download(self) -> bool:
        for idx, task in enumerate(self.task_queue):
            if task.selected_count > 0 and task.status == "ready_download":
                self.active_queue_index = idx
                self.active_run_kind = "download_queue"
                task.status = "downloading"
                self._refresh_queue_list()
                self._start_process(self._download_args_for_task(task), task.workdir)
                return True
        return False

    def _start_process(self, args: list[str], workdir: Optional[str] = None) -> None:
        if not self.cfg.python_exe:
            QtWidgets.QMessageBox.critical(
                self,
                "缺少 Python 解释器",
                "当前为打包版，未找到系统 Python。\n请安装 Python 3.10+ 后重试，或在源码模式运行。",
            )
            return
        if not Path(self.cfg.script_path).exists():
            QtWidgets.QMessageBox.critical(
                self,
                "缺少后端脚本",
                f"未找到后端脚本:\n{self.cfg.script_path}\n\n请重新使用最新打包产物。",
            )
            return
        self.user_stopped = False
        self.pause_requested = False
        self._log_line_buffer = ""
        self._stage_step = 0
        self._active_has_download = ("--download" in args) or ("--download-from-urls-file" in args)
        self._queue_total = 0
        self._queue_done = 0
        self._current_video_label = "-"
        self._clear_active_task_cards()
        self.progress_stage.setValue(0)
        self.progress_stage.setFormat("元数据抓取: 待开始")
        self.progress_queue.setValue(0)
        self.progress_queue.setFormat("0%")
        self.progress_current.setValue(0)
        self.progress_current.setFormat("0%")
        self.lbl_queue_metrics.setText("队列: 0/0")
        self.lbl_download_metrics.setText("当前视频: - | 已下载: - / - | 速度: -")
        self.lbl_progress_status.setText("任务启动中...")
        self.te_log.clear()
        self.append_log(f"$ {self.cfg.python_exe} {Path(self.cfg.script_path).name} " + " ".join(args[1:]) + "\n\n")
        resolved = Path(workdir or self._combo_text(self.cb_workdir) or "./video_info").resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self.active_workdir = str(resolved)
        self.runner.start(self.cfg.python_exe, args, working_dir=str(Path(self.cfg.script_path).parent))
        self.status.showMessage("任务执行中...", 5000)

    def remove_selected_tasks(self) -> None:
        if self.active_queue_index is not None:
            running_rows = {self.active_queue_index}
        else:
            running_rows = set()
        rows = sorted(self._selected_queue_rows(), reverse=True)
        for row in rows:
            if row in running_rows:
                continue
            if 0 <= row < len(self.task_queue):
                self.task_queue.pop(row)
                if self.active_queue_index is not None and row < self.active_queue_index:
                    self.active_queue_index -= 1
        self._refresh_queue_list()

    def clear_queue(self) -> None:
        if self.active_queue_index is None:
            self.task_queue.clear()
        else:
            running = self.task_queue[self.active_queue_index]
            self.task_queue = [running]
            self.active_queue_index = 0
        self._refresh_queue_list()

    def on_stop_clicked(self) -> None:
        self.user_stopped = True
        self.pause_requested = False
        self.download_all_mode = False
        self.lbl_progress_status.setText("正在停止任务...")
        self.runner.kill()

    def _queue_item_color(self, status: str) -> QtGui.QColor:
        s = (status or "").strip()
        if s in {"running", "downloading"}:
            return QtGui.QColor(ui_theme.TOKENS["state_info"])
        if s in {"paused_filter", "paused_download"}:
            return QtGui.QColor(ui_theme.TOKENS["state_warning"])
        if s in {"failed", "download_failed"}:
            return QtGui.QColor(ui_theme.TOKENS["state_error"])
        if s in {"done", "ready_download", "downloaded", "filtered_empty"}:
            return QtGui.QColor(ui_theme.TOKENS["state_success"])
        return QtGui.QColor(ui_theme.TOKENS["text_secondary"])

    def _select_queue_row(self, row: int) -> None:
        if row in self._queue_visible_indices:
            self.queue_list.setCurrentRow(self._queue_visible_indices.index(row))

    def _open_queue_row_workdir(self, row: int) -> None:
        self._select_queue_row(row)
        self.open_selected_task_workdir()

    def _download_queue_row(self, row: int) -> None:
        self._select_queue_row(row)
        self.download_selected_task()

    def _make_queue_task_card(self, row: int, task: QueueTask, status_label: str) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("queueTaskCardAgent" if task.origin == "agent" else "queueTaskCardManual")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 11, 12, 11)
        layout.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel((task.task_name or "未命名查询").strip())
        title.setObjectName("queueCardTitle")
        title.setWordWrap(True)
        top.addWidget(title, 1)
        badge_text = "Agent" if task.origin == "agent" else "手动"
        badge = QtWidgets.QLabel(badge_text)
        badge.setObjectName("agentBadge" if task.origin == "agent" else "manualBadge")
        top.addWidget(badge, 0, QtCore.Qt.AlignTop)
        layout.addLayout(top)

        chip_row = QtWidgets.QHBoxLayout()
        chip_row.setSpacing(6)
        status_chip = QtWidgets.QLabel(status_label)
        status_chip.setObjectName(f"statusPill{self._queue_status_tone(task.status).capitalize()}")
        mode_chip = QtWidgets.QLabel(task.download_mode or "video")
        mode_chip.setObjectName("statusPillMuted")
        chip_row.addWidget(status_chip, 0)
        chip_row.addWidget(mode_chip, 0)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        meta = QtWidgets.QLabel(f"可下载 URL {task.selected_count}  ·  run {task.run_id}")
        meta.setObjectName("hint")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        next_action = QtWidgets.QLabel(self._queue_next_action_text(task))
        next_action.setObjectName("queueNextAction")
        next_action.setWordWrap(True)
        layout.addWidget(next_action)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(6)
        btn_view = QtWidgets.QPushButton("查看")
        btn_view.setObjectName("secondary")
        btn_view.clicked.connect(lambda _checked=False, r=row: self._select_queue_row(r))
        btn_open = QtWidgets.QPushButton("目录")
        btn_open.setObjectName("secondary")
        btn_open.clicked.connect(lambda _checked=False, r=row: self._open_queue_row_workdir(r))
        btn_download = QtWidgets.QPushButton("下载")
        btn_download.setObjectName("secondary")
        btn_download.setEnabled(task.selected_count > 0)
        btn_download.clicked.connect(lambda _checked=False, r=row: self._download_queue_row(r))
        actions.addWidget(btn_view)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        actions.addWidget(btn_download)
        layout.addLayout(actions)
        return card

    def _refresh_queue_list(self) -> None:
        current_row = self.queue_list.currentRow()
        current_run_id = ""
        current_task_index = self._queue_task_index_from_view_row(current_row)
        if current_task_index is not None and 0 <= current_task_index < len(self.task_queue):
            current_run_id = self.task_queue[current_task_index].run_id
        selected_run_ids = {
            self.task_queue[row].run_id
            for row in self._selected_queue_rows()
            if 0 <= row < len(self.task_queue)
        }
        blocker = QtCore.QSignalBlocker(self.queue_list)
        self.queue_list.clear()
        self._queue_visible_indices = []
        pending_count = 0
        ready_count = 0
        run_id_to_view_row: dict[str, int] = {}
        if not self.task_queue:
            self._add_list_empty_state(
                self.queue_list,
                "队列里还没有任务",
                "先在配置页创建筛选任务，或用 Agent 发起请求。任务加入后，这里会显示状态、下一步动作和快捷操作。",
                width=300,
                height=112,
            )
        for i, task in enumerate(self.task_queue):
            prefix = self._friendly_task_status(task.status)
            if task.status == "pending":
                pending_count += 1
            if task.status in {"ready_download", "download_failed", "downloaded", "paused_download"}:
                ready_count += 1
            if not self._queue_task_matches_filters(task):
                continue
            view_row = len(self._queue_visible_indices)
            self._queue_visible_indices.append(i)
            run_id_to_view_row[task.run_id] = view_row
            short_query = (task.task_name or "").strip() or "未命名查询"
            if len(short_query) > 24:
                short_query = short_query[:24] + "..."
            zero_reason_summary = ""
            if task.selected_count <= 0 and task.status == "filtered_empty":
                zero_reason_summary = self._summarize_filter_failures(task.workdir)
            text = f"[{i + 1:02d}] {prefix} | {short_query} | URL {task.selected_count}"
            item = QtWidgets.QListWidgetItem(text)
            item.setSizeHint(QtCore.QSize(250, 118))
            tooltip_lines = [
                f"状态: {prefix}",
                f"查询: {task.task_name}",
                f"run_id: {task.run_id}",
                f"模式: {task.download_mode}",
                f"可下载URL: {task.selected_count}",
                f"信息目录: {task.workdir}",
            ]
            if zero_reason_summary:
                tooltip_lines.append(f"筛选失败原因: {zero_reason_summary}")
            item.setToolTip("\n".join(tooltip_lines))
            item.setForeground(self._queue_item_color(task.status))
            self.queue_list.addItem(item)
            item.setSizeHint(QtCore.QSize(250, 144))
            self.queue_list.setItemWidget(item, self._make_queue_task_card(i, task, prefix))
        if self.task_queue and not self._queue_visible_indices:
            self._add_list_empty_state(
                self.queue_list,
                "当前筛选下没有任务",
                "试试切换队列范围，或清空关键词筛选来查看全部任务。",
                width=300,
                height=112,
            )
        attention_count = sum(1 for task in self.task_queue if task.status in {"paused_filter", "paused_download", "failed", "download_failed"})
        self.lbl_queue_stats.setText(
            f"队列任务: {len(self.task_queue)} | 待筛选: {pending_count} | 可下载任务: {ready_count}"
        )
        self._set_metric_label(self.queue_metric_pending, "待筛选", str(pending_count), "等待执行")
        self._set_metric_label(self.queue_metric_ready, "可下载", str(ready_count), "已完成筛选")
        self._set_metric_label(self.queue_metric_attention, "异常/暂停", str(attention_count), "需要人工处理")
        restored_current_row = -1
        if current_run_id and current_run_id in run_id_to_view_row:
            restored_current_row = run_id_to_view_row[current_run_id]
        elif selected_run_ids:
            restored_current_row = min(
                (run_id_to_view_row[run_id] for run_id in selected_run_ids if run_id in run_id_to_view_row),
                default=-1,
            )
        elif 0 <= current_row < self.queue_list.count():
            restored_current_row = current_row
        if restored_current_row >= 0:
            self.queue_list.setCurrentRow(restored_current_row)
        for run_id in selected_run_ids:
            row = run_id_to_view_row.get(run_id)
            if row is not None:
                item = self.queue_list.item(row)
                if item is not None:
                    item.setSelected(True)
        if restored_current_row >= 0:
            item = self.queue_list.item(restored_current_row)
            if item is not None:
                item.setSelected(True)
        del blocker
        self._update_queue_focus_summary(restored_current_row)

    def _update_queue_focus_summary(self, row: int) -> None:
        task_index = self._queue_task_index_from_view_row(row)
        if task_index is None or task_index < 0 or task_index >= len(self.task_queue):
            self.lbl_queue_focus.setText("当前选中: 无")
            self._refresh_agent_detail_panel(None)
            return
        task = self.task_queue[task_index]
        focus_text = f"当前选中: {task.task_name} | 状态 {task.status} | URL {task.selected_count}"
        workdir = Path(task.workdir)
        detail_total = self._count_jsonl_records(workdir / "02_detailed_candidates.jsonl")
        detail_ok = self._count_jsonl_records(workdir / "02_detailed_candidates.jsonl", lambda item: not item.get("detail_error"))
        vector_summary = self._agent_vector_summary(workdir / "02b_vector_scored_candidates.jsonl")
        self.lbl_current_task_title.setText(task.task_name or "未命名任务")
        self.lbl_current_task_status.setText("Agent" if task.origin == "agent" else task.status)
        self._set_metric_label(self.lbl_summary_urls, "可下载", str(task.selected_count), task.status)
        self._set_metric_label(
            self.lbl_summary_metadata,
            "视频信息",
            f"{detail_ok}/{detail_total}" if detail_total else "-",
            "成功 / 总数",
        )
        self._set_metric_label(
            self.lbl_summary_semantic,
            "语义最高",
            f"{float(vector_summary['max_score']):.3f}" if int(vector_summary["total"]) else "-",
            f"低相似 {int(vector_summary['low_similarity'])}" if int(vector_summary["total"]) else "",
        )
        if task.selected_count <= 0 and task.status == "filtered_empty":
            zero_reason_summary = self._summarize_filter_failures(task.workdir)
            if zero_reason_summary:
                focus_text += f"\n筛选失败原因摘要: {zero_reason_summary}"
        self.lbl_queue_focus.setText(focus_text)
        self._refresh_agent_detail_panel(task)
        self.video_rows = []
        self.video_view_indices = []
        self.video_page = 1
        self._render_video_page()

    def on_finished(self, code: int) -> None:
        self.append_log(f"\n[完成] 退出码: {code}\n")
        finished_task: Optional[QueueTask] = None

        if self.active_queue_index is not None and 0 <= self.active_queue_index < len(self.task_queue):
            task = self.task_queue[self.active_queue_index]
            finished_task = task
            task.exit_code = code
            if self.pause_requested:
                if self.active_run_kind == "filter_queue":
                    task.status = "paused_filter"
                elif self.active_run_kind == "download_queue":
                    task.status = "paused_download"
                else:
                    task.status = "stopped"
            elif self.user_stopped:
                task.status = "stopped"
            else:
                if self.active_run_kind == "filter_queue":
                    if code == 0:
                        urls_path = Path(task.workdir) / "05_selected_urls.txt"
                        count = 0
                        if urls_path.exists():
                            try:
                                count = len(
                                    [
                                        ln.strip()
                                        for ln in urls_path.read_text(encoding="utf-8").splitlines()
                                        if ln.strip() and ln.strip().startswith("http")
                                    ]
                                )
                            except Exception:
                                count = 0
                        task.selected_count = count
                        task.status = "ready_download" if count > 0 else "filtered_empty"
                    else:
                        task.status = "failed"
                elif self.active_run_kind == "download_queue":
                    task.status = "downloaded" if code == 0 else "download_failed"
                else:
                    task.status = "done" if code == 0 else "failed"

        if self.pause_requested:
            self.lbl_progress_status.setText("任务已暂停")
            self.status.showMessage("任务已暂停，可在队列中继续。", 8000)
            self._show_toast(
                title="任务已暂停",
                detail="可在队列页点击“继续选中任务”恢复。",
                action_text="转到队列",
                action=lambda: self.tabs.setCurrentIndex(1),
                duration_ms=4500,
            )
        elif code == 0:
            if not self._active_has_download:
                self.progress_stage.setValue(100)
                self.progress_stage.setFormat("元数据抓取: 100%")
            if self._active_has_download:
                self.progress_current.setValue(max(self.progress_current.value(), 100))
                if self._queue_total > 0:
                    self.progress_queue.setValue(max(self.progress_queue.value(), 100))
                    self.lbl_queue_metrics.setText(f"队列: {self._queue_total}/{self._queue_total}")
                self.lbl_progress_status.setText("任务完成（下载结束）")
            else:
                self.lbl_progress_status.setText("任务完成（仅筛选）")
            workdir = Path(self.active_workdir or self._combo_text(self.cb_workdir))
            csv_selected = workdir / "04_selected_for_review.csv"
            if csv_selected.exists():
                self.model.load_csv(csv_selected)
                self.status.showMessage(f"加载 CSV: {csv_selected}", 8000)
            else:
                self.status.showMessage("未找到 04_selected_for_review.csv", 8000)
            # 对未运行中的队列任务，如果工作目录匹配则刷新可下载 URL 数
            done_workdir = str((Path(self.active_workdir) if self.active_workdir else Path(self._combo_text(self.cb_workdir))).resolve())
            for t in self.task_queue:
                try:
                    if str(Path(t.workdir).resolve()) == done_workdir and t.status in {"pending", "ready_download", "filtered_empty"}:
                        cnt = self._count_selected_urls(t.workdir)
                        t.selected_count = cnt
                        t.status = "ready_download" if cnt > 0 else "filtered_empty"
                except Exception:
                    pass
        else:
            if self.user_stopped:
                self.lbl_progress_status.setText("任务已手动停止")
            else:
                self.lbl_progress_status.setText("任务失败，请查看日志")
            self.status.showMessage("任务失败，请检查日志输出。", 8000)

        if finished_task is not None and self.active_run_kind == "download_queue" and not self.pause_requested:
            wd = Path(finished_task.workdir)
            ok_n, fail_n, unk_n, session_path, report_path = self._read_download_summary(wd)
            msg = f"下载完成摘要：成功 {ok_n} | 失败 {fail_n} | 其他 {unk_n}"
            if session_path:
                msg += f"\n目录：{session_path}"
            msg += f"\n报告：{report_path}"
            self.append_log(f"[摘要] {msg}\n")
            self.status.showMessage(msg.replace("\n", " | "), 10000)
            out_dir = session_path.strip() if session_path else finished_task.download_dir
            self._last_download_output_dir = out_dir
            if code == 0:
                self._show_toast(
                    title="下载完成",
                    detail=f"成功 {ok_n} | 失败 {fail_n} | 其他 {unk_n}",
                    action_text="打开目录",
                    action=self._open_last_download_output_dir,
                    duration_ms=5500,
                )
            else:
                self._show_toast(
                    title="下载失败",
                    detail=f"{finished_task.task_name}，请查看日志排查。",
                    action_text="查看日志",
                    action=lambda: self.tabs.setCurrentIndex(2),
                    duration_ms=6500,
                )
            if not self.download_all_mode:
                QtWidgets.QMessageBox.information(self, "下载摘要", msg)
            self.refresh_downloaded_view()
            if code == 0:
                self.tabs.setCurrentIndex(3)

        finished_kind = self.active_run_kind
        was_queue_mode = (
            self.active_queue_index is not None
            and self.active_run_kind == "filter_queue"
            and not self.pause_requested
        )
        self._refresh_queue_list()
        self.refresh_downloaded_view()
        self.active_queue_index = None
        self.active_workdir = None
        self.active_run_kind = "adhoc"
        self.pause_requested = False
        self._save_settings()
        if was_queue_mode:
            self._start_next_pending()
        elif finished_kind == "download_queue" and self.download_all_mode:
            if not self._start_next_ready_download():
                self.download_all_mode = False

    def _touch_histories(self) -> None:
        self._set_combo_text(self.cb_workdir, self._combo_text(self.cb_workdir))
        self._set_combo_text(self.cb_downloaddir, self._combo_text(self.cb_downloaddir))

    def _load_settings(self) -> None:
        self._set_combo_text(self.cb_workdir, str(Path("./video_info").resolve()))
        self._set_combo_text(self.cb_downloaddir, str(Path("./downloads").resolve()))
        settings_path = SETTINGS_FILE if SETTINGS_FILE.exists() else LEGACY_SETTINGS_FILE
        if not settings_path.exists():
            self._update_config_summary()
            return
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            return
        work_hist = data.get("workdir_history", [])
        down_hist = data.get("downloaddir_history", [])
        for v in work_hist:
            if isinstance(v, str) and v.strip():
                self._set_combo_text(self.cb_workdir, v)
        for v in down_hist:
            if isinstance(v, str) and v.strip():
                self._set_combo_text(self.cb_downloaddir, v)
        last_cfg = data.get("last_config")
        if isinstance(last_cfg, dict):
            self._apply_config(last_cfg)
        self._update_config_summary()

    def _save_settings(self) -> None:
        self._touch_histories()
        data = {
            "workdir_history": [self.cb_workdir.itemText(i) for i in range(self.cb_workdir.count())][:20],
            "downloaddir_history": [self.cb_downloaddir.itemText(i) for i in range(self.cb_downloaddir.count())][:20],
            "last_config": self._current_config(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        self._save_settings()
        return super().closeEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._adjust_config_layout_for_width()
        if self._toast.isVisible():
            self._toast._reposition_to_parent_corner()


def main() -> int:
    multiprocessing.freeze_support()
    QtCore.QCoreApplication.setOrganizationName("ytbdlp")
    QtCore.QCoreApplication.setApplicationName("ytbdlp-car-gui")
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())




