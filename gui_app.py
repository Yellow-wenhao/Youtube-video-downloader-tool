#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import concurrent.futures
import json
import multiprocessing
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets
import ui_theme


SETTINGS_FILE = Path(__file__).with_name("gui_settings.json")


@dataclass
class QueueTask:
    args: list[str]
    vehicle: str
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


class RunConfig(QtCore.QObject):
    def __init__(self) -> None:
        super().__init__()
        if getattr(sys, "frozen", False):
            # 打包后 sys.executable 指向 GUI exe，本身不是 python 解释器。
            self.python_exe = shutil.which("python") or shutil.which("py") or ""
            self.script_path = str(Path(sys.executable).with_name("myvi_yt_batch.py"))
        else:
            self.python_exe = sys.executable or "python"
            self.script_path = str(Path(__file__).with_name("myvi_yt_batch.py"))


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


class MainWindow(QtWidgets.QMainWindow):
    thumb_ready = QtCore.Signal(str, bytes)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YouTube 视频下载工具 (yt-dlp)")
        self.resize(1360, 900)
        self.setMinimumSize(1160, 760)
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

        self._init_ui()
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
        title = QtWidgets.QLabel("YouTube 视频下载工具")
        title.setObjectName("appTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self.lbl_progress_status = QtWidgets.QLabel("就绪")
        self.lbl_progress_status.setObjectName("statusBadge")
        self.lbl_progress_status.setMaximumWidth(520)
        title_row.addWidget(self.lbl_progress_status, 0, QtCore.Qt.AlignVCenter)
        layout.addLayout(title_row)

        progress_box = QtWidgets.QGroupBox("实时进度")
        progress_layout = QtWidgets.QVBoxLayout(progress_box)
        progress_layout.setContentsMargins(10, 8, 10, 8)
        progress_layout.setSpacing(6)
        row_meta = QtWidgets.QHBoxLayout()
        row_meta.addWidget(QtWidgets.QLabel("元数据抓取"))
        self.progress_stage = QtWidgets.QProgressBar()
        self.progress_stage.setRange(0, 100)
        self.progress_stage.setValue(0)
        self.progress_stage.setFormat("待开始")
        row_meta.addWidget(self.progress_stage, 1)
        progress_layout.addLayout(row_meta)
        row_queue = QtWidgets.QHBoxLayout()
        row_queue.addWidget(QtWidgets.QLabel("队列进度"))
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
        row_current.addWidget(QtWidgets.QLabel("当前视频"))
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
        layout.addWidget(progress_box)

        body_row = QtWidgets.QHBoxLayout()
        body_row.setSpacing(10)
        layout.addLayout(body_row, 1)

        nav_box = QtWidgets.QGroupBox("导航")
        nav_box.setObjectName("mini")
        nav_box.setMaximumWidth(210)
        nav_layout = QtWidgets.QVBoxLayout(nav_box)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(8)
        self.side_nav = QtWidgets.QListWidget()
        self.side_nav.setObjectName("sideNav")
        self.side_nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.side_nav.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.side_nav.addItems(["任务配置", "队列执行", "日志结果"])
        self.side_nav.currentRowChanged.connect(self._on_side_nav_changed)
        nav_layout.addWidget(self.side_nav)
        body_row.addWidget(nav_box, 0)

        tabs = QtWidgets.QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().hide()
        self.tabs = tabs
        body_row.addWidget(tabs, 1)

        tab_config = QtWidgets.QWidget()
        tab_config_outer = QtWidgets.QVBoxLayout(tab_config)
        tab_config_outer.setContentsMargins(8, 8, 8, 8)
        cfg_scroll = QtWidgets.QScrollArea()
        cfg_scroll.setWidgetResizable(True)
        cfg_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        tab_config_outer.addWidget(cfg_scroll)
        cfg_content = QtWidgets.QWidget()
        cfg_scroll.setWidget(cfg_content)
        tab_config_layout = QtWidgets.QVBoxLayout(cfg_content)
        tab_config_layout.setContentsMargins(4, 4, 4, 8)
        tab_config_layout.setSpacing(10)

        wf_banner = QtWidgets.QLabel("推荐流程: A. 设置筛选条件并加入队列  ->  B. 执行筛选获取可下载 URL  ->  C. 按下载策略执行下载")
        wf_banner.setObjectName("hint")
        tab_config_layout.addWidget(wf_banner)

        box_filter = QtWidgets.QGroupBox("步骤 A · 筛选条件")
        form_filter = QtWidgets.QFormLayout(box_filter)
        form_filter.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_filter.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_filter.setHorizontalSpacing(14)
        form_filter.setVerticalSpacing(9)

        box_download = QtWidgets.QGroupBox("步骤 B · 下载策略")
        form_download = QtWidgets.QFormLayout(box_download)
        form_download.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_download.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_download.setHorizontalSpacing(14)
        form_download.setVerticalSpacing(9)

        box_queue = QtWidgets.QGroupBox("步骤 C · 加入队列")
        form_queue = QtWidgets.QFormLayout(box_queue)
        form_queue.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        form_queue.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        form_queue.setHorizontalSpacing(14)
        form_queue.setVerticalSpacing(9)

        self.le_query_text = QtWidgets.QLineEdit()
        self.le_query_text.setPlaceholderText("例如：Perodua Myvi review")
        form_filter.addRow("查询内容:", self.le_query_text)

        self.cb_workdir = NoWheelComboBox()
        self.cb_workdir.setEditable(True)
        self.cb_workdir.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_workdir.setToolTip("用于保存筛选阶段 01~05 的中间结果文件。")
        btn_w = QtWidgets.QPushButton("选择...")
        btn_w.clicked.connect(lambda: self._pick_dir_combo(self.cb_workdir))
        hw = QtWidgets.QHBoxLayout()
        hw.addWidget(self.cb_workdir)
        hw.addWidget(btn_w)
        form_filter.addRow("视频信息目录(信息存放):", self._wrap(hw))
        lbl_work_help = QtWidgets.QLabel("用途: 每次任务会创建独立 run 子目录，保存候选清单、筛选结果和可下载 URL，不直接存放视频媒体文件。")
        lbl_work_help.setWordWrap(True)
        lbl_work_help.setObjectName("hint")
        form_filter.addRow("", lbl_work_help)

        self.cb_downloaddir = NoWheelComboBox()
        self.cb_downloaddir.setEditable(True)
        self.cb_downloaddir.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.cb_downloaddir.setToolTip("用于保存最终下载的视频/音频文件。")
        btn_d = QtWidgets.QPushButton("选择...")
        btn_d.clicked.connect(lambda: self._pick_dir_combo(self.cb_downloaddir))
        hd = QtWidgets.QHBoxLayout()
        hd.addWidget(self.cb_downloaddir)
        hd.addWidget(btn_d)
        form_filter.addRow("下载目录(视频存放):", self._wrap(hd))

        self.spin_search_limit = QtWidgets.QSpinBox()
        self.spin_search_limit.setRange(1, 200)
        self.spin_search_limit.setValue(50)
        form_filter.addRow("视频收集条数:", self.spin_search_limit)
        self.spin_metadata_workers = QtWidgets.QSpinBox()
        self.spin_metadata_workers.setRange(1, 16)
        self.spin_metadata_workers.setValue(4)
        form_filter.addRow("视频信息抓取并发数:", self.spin_metadata_workers)

        self.spin_min_duration = QtWidgets.QSpinBox()
        self.spin_min_duration.setRange(0, 7200)
        self.spin_min_duration.setValue(120)
        form_filter.addRow("最短时长(秒):", self.spin_min_duration)

        self.spin_year_from = QtWidgets.QSpinBox()
        self.spin_year_from.setRange(1990, 2100)
        self.spin_year_from.setValue(2020)
        self.chk_year_from = QtWidgets.QCheckBox("启用")
        hyf = QtWidgets.QHBoxLayout()
        hyf.addWidget(self.spin_year_from)
        hyf.addWidget(self.chk_year_from)
        form_filter.addRow("上传年 >=", self._wrap(hyf))

        self.spin_year_to = QtWidgets.QSpinBox()
        self.spin_year_to.setRange(1990, 2100)
        self.spin_year_to.setValue(2026)
        self.chk_year_to = QtWidgets.QCheckBox("启用")
        hyt = QtWidgets.QHBoxLayout()
        hyt.addWidget(self.spin_year_to)
        hyt.addWidget(self.chk_year_to)
        form_filter.addRow("上传年 <=", self._wrap(hyt))

        self.combo_cookies_browser = NoWheelComboBox()
        self.combo_cookies_browser.setEditable(True)
        self.combo_cookies_browser.addItems(["", "chrome", "edge", "firefox"])
        form_filter.addRow("cookies-from-browser:", self.combo_cookies_browser)

        self.le_cookies_file = QtWidgets.QLineEdit()
        btn_c = QtWidgets.QPushButton("选择...")
        btn_c.clicked.connect(lambda: self._pick_file(self.le_cookies_file, "选择 cookies 文件 (*.*)"))
        hc = QtWidgets.QHBoxLayout()
        hc.addWidget(self.le_cookies_file)
        hc.addWidget(btn_c)
        form_filter.addRow("cookies 文件:", self._wrap(hc))

        self.le_yt_extra_args = QtWidgets.QLineEdit()
        self.le_yt_extra_args.setPlaceholderText("--proxy http://127.0.0.1:7890 --retries 20")
        form_filter.addRow("高级 yt-dlp 参数:", self.le_yt_extra_args)

        self.chk_full_csv = QtWidgets.QCheckBox("导出 04_all_scored.csv（全量评分）")
        form_filter.addRow("", self.chk_full_csv)

        self.combo_download_mode = NoWheelComboBox()
        self.combo_download_mode.addItems(["video", "audio"])
        form_download.addRow("下载模式:", self.combo_download_mode)

        self.chk_include_audio = QtWidgets.QCheckBox("视频模式同时下载并合并音频")
        self.chk_include_audio.setChecked(True)
        form_download.addRow("", self.chk_include_audio)

        self.combo_video_container = NoWheelComboBox()
        self.combo_video_container.addItems(["auto", "mp4", "mkv", "webm"])
        form_download.addRow("视频封装格式:", self.combo_video_container)

        self.combo_max_height = NoWheelComboBox()
        self.combo_max_height.addItems(["144", "240", "360", "480", "720", "1080", "1440", "2160", "4320"])
        self.combo_max_height.setCurrentText("1080")
        self.combo_max_height.setToolTip("固定下载分辨率（按所选分辨率下载）。")
        form_download.addRow("下载分辨率:", self.combo_max_height)

        self.combo_audio_format = NoWheelComboBox()
        self.combo_audio_format.addItems(["best", "mp3", "m4a", "opus", "wav", "flac"])
        form_download.addRow("音频格式(audio):", self.combo_audio_format)

        self.spin_audio_quality = QtWidgets.QSpinBox()
        self.spin_audio_quality.setRange(0, 10)
        self.spin_audio_quality.setValue(2)
        form_download.addRow("音频质量 0-10:", self.spin_audio_quality)
        self.spin_concurrent_videos = QtWidgets.QSpinBox()
        self.spin_concurrent_videos.setRange(1, 8)
        self.spin_concurrent_videos.setValue(3)
        form_download.addRow("并发视频数:", self.spin_concurrent_videos)
        self.spin_concurrent_fragments = QtWidgets.QSpinBox()
        self.spin_concurrent_fragments.setRange(1, 16)
        self.spin_concurrent_fragments.setValue(8)
        form_download.addRow("单视频分片并发:", self.spin_concurrent_fragments)

        self.chk_clean_video = QtWidgets.QCheckBox("纯净模式（移除广告/赞助片段）")
        self.chk_clean_video.setToolTip("仅对 YouTube 生效：通过 SponsorBlock 移除指定片段。")
        form_download.addRow("", self.chk_clean_video)
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
        form_download.addRow("移除类别:", sb_widget)
        self.chk_clean_video.toggled.connect(sb_widget.setEnabled)

        qv = QtWidgets.QVBoxLayout()
        qv.setContentsMargins(14, 12, 14, 12)
        qv.setSpacing(10)
        lbl_queue_help = QtWidgets.QLabel("确认步骤 A/B 设置后，启动筛选任务并在队列页执行下载。")
        lbl_queue_help.setObjectName("hint")
        lbl_queue_help.setWordWrap(True)
        qv.addWidget(lbl_queue_help)
        self.btn_enqueue = QtWidgets.QPushButton("启动筛选队列")
        self.btn_enqueue.setObjectName("primary")
        self.btn_enqueue.setToolTip("创建新筛选任务并立即启动。")
        self.btn_enqueue.clicked.connect(self._enqueue_and_start)
        qv.addWidget(self.btn_enqueue)
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

        self._tune_form_labels(form_filter, 176)
        self._tune_form_labels(form_download, 176)
        self._tune_form_labels(form_queue, 176)

        maint_box = QtWidgets.QGroupBox("工具维护 (yt-dlp / ffmpeg)")
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
        tab_config_layout.addLayout(row_cfg_top)
        row_cfg_bottom = QtWidgets.QHBoxLayout()
        row_cfg_bottom.setSpacing(10)
        row_cfg_bottom.addWidget(box_queue, 1)
        row_cfg_bottom.addWidget(maint_box, 1)
        tab_config_layout.addLayout(row_cfg_bottom)
        self.combo_download_mode.currentTextChanged.connect(self._on_download_mode_changed)
        self._on_download_mode_changed(self.combo_download_mode.currentText())
        tab_config_layout.addStretch()
        tabs.addTab(tab_config, "1. 任务配置")

        tab_queue = QtWidgets.QWidget()
        tab_queue_layout = QtWidgets.QVBoxLayout(tab_queue)
        tab_queue_layout.setContentsMargins(0, 0, 0, 0)
        tab_queue_layout.setSpacing(8)
        self.queue_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.queue_splitter.setChildrenCollapsible(False)
        tab_queue_layout.addWidget(self.queue_splitter, 1)

        left_box = QtWidgets.QGroupBox("任务中心")
        left_box.setMinimumWidth(320)
        left_layout = QtWidgets.QVBoxLayout(left_box)
        left_layout.setSpacing(8)
        self.lbl_queue_stats = QtWidgets.QLabel("队列任务: 0")
        self.lbl_queue_stats.setObjectName("sectionTitle")
        self.lbl_queue_focus = QtWidgets.QLabel("当前选中: 无")
        self.lbl_queue_focus.setObjectName("hint")
        self.lbl_queue_focus.setWordWrap(True)
        left_layout.addWidget(self.lbl_queue_stats)
        left_layout.addWidget(self.lbl_queue_focus)

        self.btn_start_queue = QtWidgets.QPushButton("启动筛选队列")
        self.btn_start_queue.setObjectName("primary")
        self.btn_start_queue.clicked.connect(self.start_queue)

        self.btn_download_selected = QtWidgets.QPushButton("下载选中任务")
        self.btn_download_selected.setObjectName("primary")
        self.btn_download_selected.clicked.connect(self.download_selected_task)

        self.btn_stop = QtWidgets.QPushButton("停止当前任务")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.on_stop_clicked)

        self.btn_more_ops = QtWidgets.QToolButton()
        self.btn_more_ops.setText("更多操作")
        self.btn_more_ops.setObjectName("secondary")
        self.btn_more_ops.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        menu_more = QtWidgets.QMenu(self.btn_more_ops)
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
        ops_layout.addWidget(self.btn_start_queue)
        ops_layout.addWidget(self.btn_download_selected)
        row_ctrl = QtWidgets.QHBoxLayout()
        row_ctrl.setSpacing(8)
        row_ctrl.addWidget(self.btn_stop, 1)
        row_ctrl.addWidget(self.btn_more_ops, 1)
        ops_layout.addLayout(row_ctrl)
        left_layout.addWidget(ops_box)

        self.queue_list = QtWidgets.QListWidget()
        self.queue_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.queue_list.currentRowChanged.connect(self._update_queue_focus_summary)
        self.queue_list.itemDoubleClicked.connect(self._on_queue_item_double_clicked)
        left_layout.addWidget(self.queue_list, 1)

        right_box = QtWidgets.QGroupBox("视频列表")
        right_layout = QtWidgets.QVBoxLayout(right_box)
        right_layout.setSpacing(8)
        row_ops = QtWidgets.QHBoxLayout()
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
        self.le_video_filter.setMinimumWidth(180)
        self.combo_video_sort = NoWheelComboBox()
        self.combo_video_sort.addItems(["默认排序", "上传日期(新->旧)", "时长(长->短)", "标题(A-Z)"])
        self.combo_video_sort.currentTextChanged.connect(self._apply_video_view)
        self.combo_video_sort.setMaximumWidth(140)
        self.btn_download_checked = QtWidgets.QPushButton("下载勾选视频")
        self.btn_download_checked.setObjectName("primary")
        self.btn_download_checked.clicked.connect(self.download_checked_videos)
        row_ops.addWidget(self.btn_load_task_videos)
        row_ops.addWidget(self.btn_check_all_page)
        row_ops.addWidget(self.btn_uncheck_all_page)
        row_ops.addWidget(self.le_video_filter)
        row_ops.addWidget(self.combo_video_sort)
        row_ops.addStretch()
        row_ops.addWidget(self.btn_download_checked)
        right_layout.addLayout(row_ops)
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
        self.combo_page_size.setMaximumWidth(110)
        pager.addWidget(self.btn_prev_page)
        pager.addWidget(self.btn_next_page)
        pager.addWidget(self.lbl_video_page)
        pager.addWidget(self.combo_page_size)
        pager.addStretch()
        right_layout.addLayout(pager)
        self.video_list_widget = QtWidgets.QListWidget()
        self.video_list_widget.setObjectName("videoFeed")
        self.video_list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.video_list_widget.setSpacing(10)
        self.video_list_widget.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.video_list_widget.verticalScrollBar().valueChanged.connect(lambda *_: self._schedule_visible_thumb_load())
        right_layout.addWidget(self.video_list_widget, 1)

        self.queue_splitter.addWidget(left_box)
        self.queue_splitter.addWidget(right_box)
        self.queue_splitter.setStretchFactor(0, 0)
        self.queue_splitter.setStretchFactor(1, 1)
        self.queue_splitter.setSizes([360, 980])
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
        tabs.currentChanged.connect(self._on_main_tab_changed)
        self.side_nav.setCurrentRow(0)

        self._normalize_ui_sizes()
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
        ]
        combos_wide = [
            self.cb_workdir,
            self.cb_downloaddir,
            self.combo_cookies_browser,
            self.combo_download_mode,
            self.combo_video_container,
            self.combo_max_height,
            self.combo_audio_format,
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

        for w in line_edits:
            w.setMinimumWidth(460)
            w.setMinimumHeight(34)
        for w in combos_wide:
            w.setMinimumWidth(240)
            w.setMinimumHeight(34)
        for w in spins:
            w.setMinimumWidth(150)
            w.setMinimumHeight(34)
            w.setMaximumWidth(220)

        for b in self.findChildren(QtWidgets.QPushButton):
            b.setMinimumHeight(34)
            if b.text().strip() == "选择...":
                b.setMinimumWidth(86)

        for b in [
            self.btn_start_queue,
            self.btn_download_selected,
            self.btn_stop,
        ]:
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_more_ops.setMinimumHeight(34)
        self.btn_more_ops.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_more_ops.setMinimumWidth(96)

    def _wrap(self, inner_layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        w.setLayout(inner_layout)
        return w

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
                3: "阶段 3/4: 本地规则筛选",
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

    def _read_download_summary(self, workdir: Path) -> tuple[int, int, int, str, str]:
        report = workdir / "07_download_report.csv"
        downloaded = failed = unknown = 0
        session_path = ""
        session_file = workdir / "08_last_download_session.txt"
        if session_file.exists():
            try:
                session_path = session_file.read_text(encoding="utf-8").strip()
            except Exception:
                session_path = ""
        if session_path:
            p = Path(session_path)
            report2 = p / "07_download_report.csv"
            if report2.exists():
                report = report2
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
            vehicle=query[:48],
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
            session_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", task.vehicle).strip("._-")
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
        row = self.queue_list.currentRow()
        if row < 0 or row >= len(self.task_queue):
            return None
        return self.task_queue[row]

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
        if not csv_path.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"未找到筛选结果: {csv_path}")
            return
        rows: list[dict] = []
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for r in reader:
                    rows.append(
                        {
                            "selected": False,
                            "title": (r.get("title") or "").strip(),
                            "channel": (r.get("channel") or "").strip(),
                            "upload_date": (r.get("upload_date") or "").strip(),
                            "duration": (r.get("duration") or "").strip(),
                            "watch_url": (r.get("watch_url") or "").strip(),
                            "video_id": (r.get("video_id") or "").strip(),
                        }
                    )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "读取失败", f"读取 CSV 失败:\n{exc}")
            return
        self.video_rows = rows
        self.video_view_indices = list(range(len(self.video_rows)))
        self.video_page = 1
        self._apply_video_view()

    def _apply_video_view(self, *_args) -> None:
        indices = list(range(len(self.video_rows)))
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
        if sort_mode == "上传日期(新->旧)":
            indices.sort(key=lambda i: int(re.sub(r"\D", "", str(self.video_rows[i].get("upload_date", ""))) or 0), reverse=True)
        elif sort_mode == "时长(长->短)":
            indices.sort(key=lambda i: int(str(self.video_rows[i].get("duration", "0")) if str(self.video_rows[i].get("duration", "0")).isdigit() else 0), reverse=True)
        elif sort_mode == "标题(A-Z)":
            indices.sort(key=lambda i: str(self.video_rows[i].get("title", "")).lower())

        self.video_view_indices = indices
        self.video_page = 1
        self._render_video_page()

    def _render_video_page(self) -> None:
        total = len(self.video_view_indices)
        pages = max(1, (total + self.video_page_size - 1) // self.video_page_size) if total else 0
        if pages and self.video_page > pages:
            self.video_page = pages
        start = (self.video_page - 1) * self.video_page_size if pages else 0
        end = min(total, start + self.video_page_size)
        self.lbl_video_page.setText(f"第 {self.video_page if pages else 0}/{pages} 页 · 共 {total} 条")
        self.btn_prev_page.setEnabled(pages > 0 and self.video_page > 1)
        self.btn_next_page.setEnabled(pages > 0 and self.video_page < pages)
        self.video_list_widget.clear()
        if total == 0:
            return
        for pos in range(start, end):
            i = self.video_view_indices[pos]
            row = self.video_rows[i]
            item = QtWidgets.QListWidgetItem()
            item.setSizeHint(QtCore.QSize(920, 146))
            self.video_list_widget.addItem(item)
            widget = self._make_video_card(i, row)
            self.video_list_widget.setItemWidget(item, widget)
        self._schedule_visible_thumb_load()

    def _make_video_card(self, idx: int, row: dict) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        card.setStyleSheet(ui_theme.video_card_style())
        card.setProperty("video_id", row.get("video_id", ""))
        h = QtWidgets.QHBoxLayout(card)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(12)
        chk = QtWidgets.QCheckBox()
        chk.setChecked(bool(row.get("selected")))
        chk.toggled.connect(lambda state, k=idx: self._set_video_checked(k, state))
        h.addWidget(chk, 0, QtCore.Qt.AlignTop)
        lbl_thumb = QtWidgets.QLabel()
        lbl_thumb.setObjectName("thumb")
        lbl_thumb.setFixedSize(176, 99)
        lbl_thumb.setPixmap(self._video_thumb(row.get("video_id", "")))
        h.addWidget(lbl_thumb, 0, QtCore.Qt.AlignTop)
        v = QtWidgets.QVBoxLayout()
        v.setSpacing(5)
        title = QtWidgets.QLabel(row.get("title", "(无标题)"))
        title.setStyleSheet(ui_theme.video_title_style())
        title.setWordWrap(True)
        title.setMaximumHeight(44)
        meta = QtWidgets.QLabel(
            f"作者 {row.get('channel', '-')}  ·  上传 {row.get('upload_date', '-')}  ·  时长 {self._format_duration(str(row.get('duration', '-')))}"
        )
        meta.setStyleSheet(ui_theme.video_meta_style())
        url = QtWidgets.QLabel(row.get("watch_url", ""))
        url.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        url.setStyleSheet(ui_theme.video_url_style())
        v.addWidget(title)
        v.addWidget(meta)
        v.addWidget(url)
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
        rows = sorted({idx.row() for idx in self.queue_list.selectedIndexes()})
        return [r for r in rows if 0 <= r < len(self.task_queue)]

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
        failed_file = Path(task.workdir) / "06_failed_urls.txt"
        if not failed_file.exists():
            QtWidgets.QMessageBox.information(self, "提示", f"未找到失败清单: {failed_file}")
            return
        urls = [ln.strip() for ln in failed_file.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("http")]
        if not urls:
            QtWidgets.QMessageBox.information(self, "提示", "失败清单为空，无需重试。")
            return
        task.status = "downloading"
        self.active_queue_index = self.queue_list.currentRow()
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
        self.active_queue_index = self.queue_list.currentRow()
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
        sess_file = latest / "08_last_download_session.txt"
        if sess_file.exists():
            try:
                p = Path(sess_file.read_text(encoding="utf-8").strip())
                if p.name:
                    sess_name = p.name
            except Exception:
                sess_name = ""
        if not sess_name:
            sess_name = (re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", latest.name).strip("._-")[:72] or run_id)
        task = QueueTask(
            args=[],
            vehicle=f"恢复任务 {latest.name[:48]}",
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
        resolved = Path(workdir or self._combo_text(self.cb_workdir) or "./myvi_dataset").resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        self.active_workdir = str(resolved)
        self.runner.start(self.cfg.python_exe, args, working_dir=str(Path(self.cfg.script_path).parent))
        self.status.showMessage("任务执行中...", 5000)

    def remove_selected_tasks(self) -> None:
        if self.active_queue_index is not None:
            running_rows = {self.active_queue_index}
        else:
            running_rows = set()
        rows = sorted({idx.row() for idx in self.queue_list.selectedIndexes()}, reverse=True)
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
        self.download_all_mode = False
        self.lbl_progress_status.setText("正在停止任务...")
        self.runner.kill()

    def _queue_item_color(self, status: str) -> QtGui.QColor:
        s = (status or "").strip()
        if s in {"running", "downloading"}:
            return QtGui.QColor(ui_theme.TOKENS["state_info"])
        if s in {"failed", "download_failed"}:
            return QtGui.QColor(ui_theme.TOKENS["state_error"])
        if s in {"done", "ready_download", "downloaded", "filtered_empty"}:
            return QtGui.QColor(ui_theme.TOKENS["state_success"])
        return QtGui.QColor(ui_theme.TOKENS["text_secondary"])

    def _refresh_queue_list(self) -> None:
        self.queue_list.clear()
        pending_count = 0
        ready_count = 0
        for i, task in enumerate(self.task_queue):
            prefix = {
                "pending": "待运行",
                "running": "运行中",
                "ready_download": "已筛选·待下载",
                "filtered_empty": "已筛选·无结果",
                "downloading": "下载中",
                "downloaded": "下载完成",
                "download_failed": "下载失败",
                "done": "已完成",
                "failed": "失败",
                "stopped": "已停止",
            }.get(task.status, task.status)
            if task.status == "pending":
                pending_count += 1
            if task.status in {"ready_download", "download_failed", "downloaded"}:
                ready_count += 1
            short_query = (task.vehicle or "").strip() or "未命名查询"
            if len(short_query) > 24:
                short_query = short_query[:24] + "..."
            text = f"[{i + 1:02d}] {prefix} | {short_query} | URL {task.selected_count}"
            item = QtWidgets.QListWidgetItem(text)
            item.setToolTip(
                f"状态: {prefix}\n查询: {task.vehicle}\nrun_id: {task.run_id}\n模式: {task.download_mode}\n"
                f"可下载URL: {task.selected_count}\n信息目录: {task.workdir}"
            )
            item.setForeground(self._queue_item_color(task.status))
            self.queue_list.addItem(item)
        self.lbl_queue_stats.setText(
            f"队列任务: {len(self.task_queue)} | 待筛选: {pending_count} | 可下载任务: {ready_count}"
        )
        self._update_queue_focus_summary(self.queue_list.currentRow())

    def _update_queue_focus_summary(self, row: int) -> None:
        if row < 0 or row >= len(self.task_queue):
            self.lbl_queue_focus.setText("当前选中: 无")
            return
        task = self.task_queue[row]
        self.lbl_queue_focus.setText(
            f"当前选中: {task.vehicle} | 状态 {task.status} | URL {task.selected_count}"
        )
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
            if self.user_stopped:
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

        if code == 0:
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

        if finished_task is not None and self.active_run_kind == "download_queue":
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
                    detail=f"{finished_task.vehicle}，请查看日志排查。",
                    action_text="查看日志",
                    action=lambda: self.tabs.setCurrentIndex(2),
                    duration_ms=6500,
                )
            if not self.download_all_mode:
                QtWidgets.QMessageBox.information(self, "下载摘要", msg)

        finished_kind = self.active_run_kind
        was_queue_mode = self.active_queue_index is not None and self.active_run_kind == "filter_queue"
        self._refresh_queue_list()
        self.active_queue_index = None
        self.active_workdir = None
        self.active_run_kind = "adhoc"
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
        self._set_combo_text(self.cb_workdir, str(Path("./myvi_dataset").resolve()))
        self._set_combo_text(self.cb_downloaddir, str(Path("./myvi_downloads").resolve()))
        if not SETTINGS_FILE.exists():
            return
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
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




