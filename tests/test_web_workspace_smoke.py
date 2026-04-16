from __future__ import annotations

import json
import os
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --headless --no-sandbox")

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineCore import QWebEnginePage


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "web" / "static"
WORKDIR = "D:/YTBDLP/video_info/web_agent"
DOWNLOAD_DIR = f"{WORKDIR}/downloads"
SESSION_DIR = f"{DOWNLOAD_DIR}/task-1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ScenarioState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.phase = "awaiting_confirmation"
        self.poll_count = 0
        self.resume_calls = 0

    def mark_resume(self) -> None:
        with self.lock:
            self.resume_calls += 1
            self.phase = "preparing_download"

    def set_phase(self, phase: str) -> None:
        with self.lock:
            self.phase = phase

    def current_phase(self) -> str:
        with self.lock:
            return self.phase

    def next_poll_payload(self) -> dict:
        with self.lock:
            if self.phase == "preparing_download":
                self.poll_count += 1
                if self.poll_count >= 1:
                    self.phase = "downloading"
            return self._poll_payload(self.phase)

    def lifecycle_payload(self) -> dict:
        with self.lock:
            return self._lifecycle_payload(self.phase)

    def task_list_payload(self) -> dict:
        phase = self.current_phase()
        status = "awaiting_confirmation" if phase == "awaiting_confirmation" else ("succeeded" if phase == "completed" else "running")
        status_label = {
            "awaiting_confirmation": "等待确认",
            "running": "运行中",
            "succeeded": "已完成",
        }[status]
        return {
            "items": [
                {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": status,
                    "status_label": status_label,
                    "status_tone": "warn" if status == "awaiting_confirmation" else ("success" if status == "succeeded" else "info"),
                    "updated_at": _now(),
                    "created_at": _now(),
                    "last_message": "smoke test task",
                    "needs_confirmation": phase == "awaiting_confirmation",
                    "current_step_title": "下载视频",
                    "current_step_status": "awaiting_confirmation" if phase == "awaiting_confirmation" else "running",
                    "progress_text": "已完成 0/1，等待确认" if phase == "awaiting_confirmation" else "已完成 0/1",
                    "badge_text": "需确认" if phase == "awaiting_confirmation" else "0/1 步",
                    "metrics": {
                        "total_steps": 1,
                        "completed_steps": 0,
                        "failed_steps": 0,
                        "pending_steps": 0,
                        "awaiting_confirmation_steps": 1 if phase == "awaiting_confirmation" else 0,
                        "event_count": 0,
                    },
                }
            ],
            "queue": {
                "total": 1,
                "planned": 0,
                "running": 0 if phase == "awaiting_confirmation" else 1,
                "awaiting_confirmation": 1 if phase == "awaiting_confirmation" else 0,
                "succeeded": 1 if phase == "completed" else 0,
                "failed": 0,
                "cancelled": 0,
                "needs_attention": 1 if phase == "awaiting_confirmation" else 0,
            },
            "workdir": WORKDIR,
            "count": 1,
        }

    def _base_task(self, *, status: str, status_label: str, current_step_status: str) -> dict:
        return {
            "task_id": "task-1",
            "title": "Smoke Test Task",
            "user_request": "download sample videos",
            "intent": "download",
            "status": status,
            "status_label": status_label,
            "status_tone": "warn" if status == "awaiting_confirmation" else ("success" if status == "succeeded" else "info"),
            "workdir": WORKDIR,
            "created_at": _now(),
            "updated_at": _now(),
            "current_step_index": 0,
            "needs_confirmation": status == "awaiting_confirmation",
            "current_step_title": "下载视频",
            "current_step_status": current_step_status,
            "progress_text": "已完成 0/1，等待确认继续" if status == "awaiting_confirmation" else ("已完成 1/1" if status == "succeeded" else "已完成 0/1"),
            "active_elapsed_seconds": 2.0,
            "metrics": {
                "total_steps": 1,
                "completed_steps": 1 if status == "succeeded" else 0,
                "failed_steps": 0,
                "pending_steps": 0,
                "awaiting_confirmation_steps": 1 if status == "awaiting_confirmation" else 0,
                "event_count": 0,
            },
            "steps": [
                {
                    "step_id": "download_step",
                    "title": "下载视频",
                    "tool_name": "start_download",
                    "status": current_step_status,
                    "requires_confirmation": True,
                    "message": "",
                    "has_result": status == "succeeded",
                }
            ],
            "params": {},
            "task_paths": {
                "task_dir": f"{WORKDIR}/.agent/tasks/task-1",
                "spec": f"{WORKDIR}/.agent/tasks/task-1/spec.json",
                "summary": f"{WORKDIR}/.agent/tasks/task-1/summary.json",
                "events": f"{WORKDIR}/.agent/tasks/task-1/events.jsonl",
                "logs": f"{WORKDIR}/.agent/tasks/task-1/logs.jsonl",
                "progress": f"{WORKDIR}/.agent/tasks/task-1/progress.json",
                "result": f"{WORKDIR}/.agent/tasks/task-1/result.json",
            },
            "download_progress": None,
        }

    def _download_progress(self, *, percent: float) -> dict:
        return {
            "phase": "downloading",
            "percent": percent,
            "downloaded_bytes": 2 * 1024 * 1024,
            "total_bytes": 8 * 1024 * 1024,
            "speed_text": "2.1 MiB/s",
            "current_video_id": "vid-001",
            "current_video_label": "Demo Video",
            "updated_at": _now(),
        }

    def _lifecycle_payload(self, phase: str) -> dict:
        if phase == "awaiting_confirmation":
            task = self._base_task(status="awaiting_confirmation", status_label="等待确认", current_step_status="awaiting_confirmation")
            return {
                "task": task,
                "summary": {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": "awaiting_confirmation",
                    "updated_at": _now(),
                    "created_at": _now(),
                    "current_step_index": 0,
                    "needs_confirmation": True,
                    "last_message": "等待确认下载",
                    "details": {},
                },
                "result": {
                    "task_id": "task-1",
                    "status": "awaiting_confirmation",
                    "message": "确认后才能继续执行: 下载视频",
                    "started_at": _now(),
                    "finished_at": _now(),
                    "has_data": True,
                    "data": {"pending_step": "download_step"},
                },
                "focus_summary": None,
                "events_tail": [],
                "events_tail_count": 0,
                "download_progress": None,
                "workspace_stage": "awaiting_confirmation",
                "workspace_stage_label": "等待确认下载",
                "primary_message": "当前任务需要你确认后才能开始下载。确认后将继续执行“下载视频”。",
                "confirmation": {"required": True, "step_title": "下载视频", "cta_label": "确认下载并继续"},
                "download_entry": {"path": DOWNLOAD_DIR, "label": "查看目标目录", "ready": False},
            }
        if phase == "preparing_download":
            task = self._base_task(status="running", status_label="运行中", current_step_status="running")
            return {
                "task": task,
                "summary": {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": "running",
                    "updated_at": _now(),
                    "created_at": _now(),
                    "current_step_index": 0,
                    "needs_confirmation": False,
                    "last_message": "正在准备下载环境",
                    "details": {},
                },
                "result": None,
                "focus_summary": None,
                "events_tail": [],
                "events_tail_count": 0,
                "download_progress": None,
                "workspace_stage": "preparing_download",
                "workspace_stage_label": "准备下载中",
                "primary_message": "已确认，正在准备下载环境并启动下载任务。",
                "confirmation": None,
                "download_entry": {"path": DOWNLOAD_DIR, "label": "查看目标目录", "ready": False},
            }
        if phase == "downloading":
            task = self._base_task(status="running", status_label="运行中", current_step_status="running")
            progress = self._download_progress(percent=42.0)
            task["download_progress"] = progress
            return {
                "task": task,
                "summary": {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": "running",
                    "updated_at": _now(),
                    "created_at": _now(),
                    "current_step_index": 0,
                    "needs_confirmation": False,
                    "last_message": "正在下载 Demo Video",
                    "details": {},
                },
                "result": None,
                "focus_summary": None,
                "events_tail": [],
                "events_tail_count": 0,
                "download_progress": progress,
                "workspace_stage": "downloading",
                "workspace_stage_label": "正在下载",
                "primary_message": "正在下载 Demo Video，当前速度 2.1 MiB/s。",
                "confirmation": None,
                "download_entry": {"path": DOWNLOAD_DIR, "label": "查看目标目录", "ready": False},
            }
        task = self._base_task(status="succeeded", status_label="已完成", current_step_status="completed")
        progress = {
            "phase": "completed",
            "percent": 100.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "speed_text": "",
            "current_video_id": "vid-001",
            "current_video_label": "Demo Video",
            "updated_at": _now(),
        }
        task["download_progress"] = progress
        return {
            "task": task,
            "summary": {
                "task_id": "task-1",
                "title": "Smoke Test Task",
                "status": "succeeded",
                "updated_at": _now(),
                "created_at": _now(),
                "current_step_index": 1,
                "needs_confirmation": False,
                "last_message": "下载完成",
                "details": {},
            },
            "result": {
                "task_id": "task-1",
                "status": "succeeded",
                "message": "Task completed successfully",
                "started_at": _now(),
                "finished_at": _now(),
                "has_data": True,
                "data": {"session_dir": SESSION_DIR},
            },
            "focus_summary": None,
            "events_tail": [],
            "events_tail_count": 0,
            "download_progress": progress,
            "workspace_stage": "completed",
            "workspace_stage_label": "下载已完成",
            "primary_message": "下载已完成，可以直接打开目录查看视频。",
            "confirmation": None,
            "download_entry": {"path": SESSION_DIR, "label": "打开已下载视频", "ready": True},
        }

    def _poll_payload(self, phase: str) -> dict:
        if phase == "preparing_download":
            return {
                "task_id": "task-1",
                "status": "running",
                "status_label": "运行中",
                "status_tone": "info",
                "needs_confirmation": False,
                "progress_text": "已完成 0/1",
                "active_elapsed_seconds": 2.0,
                "current_step_title": "下载视频",
                "current_step_status": "running",
                "summary": {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": "running",
                    "updated_at": _now(),
                    "created_at": _now(),
                    "current_step_index": 0,
                    "needs_confirmation": False,
                    "last_message": "正在准备下载环境",
                    "details": {},
                },
                "focus_summary": None,
                "events_tail": [],
                "events_tail_count": 0,
                "download_progress": None,
                "logs_tail_count": 0,
                "workspace_stage": "preparing_download",
                "workspace_stage_label": "准备下载中",
                "primary_message": "已确认，正在准备下载环境并启动下载任务。",
                "confirmation": None,
                "download_entry": {"path": DOWNLOAD_DIR, "label": "查看目标目录", "ready": False},
            }
        if phase == "downloading":
            progress = self._download_progress(percent=42.0)
            return {
                "task_id": "task-1",
                "status": "running",
                "status_label": "运行中",
                "status_tone": "info",
                "needs_confirmation": False,
                "progress_text": "已完成 0/1",
                "active_elapsed_seconds": 3.0,
                "current_step_title": "下载视频",
                "current_step_status": "running",
                "summary": {
                    "task_id": "task-1",
                    "title": "Smoke Test Task",
                    "status": "running",
                    "updated_at": _now(),
                    "created_at": _now(),
                    "current_step_index": 0,
                    "needs_confirmation": False,
                    "last_message": "正在下载 Demo Video",
                    "details": {},
                },
                "focus_summary": None,
                "events_tail": [],
                "events_tail_count": 0,
                "download_progress": progress,
                "logs_tail_count": 1,
                "workspace_stage": "downloading",
                "workspace_stage_label": "正在下载",
                "primary_message": "正在下载 Demo Video，当前速度 2.1 MiB/s。",
                "confirmation": None,
                "download_entry": {"path": DOWNLOAD_DIR, "label": "查看目标目录", "ready": False},
            }
        return self._poll_payload("preparing_download")


class _WorkspaceHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: _ScenarioState | None = None

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        assert self.state is not None
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._serve_static(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if parsed.path == "/static/workspace.css":
            return self._serve_static(STATIC_DIR / "workspace.css", "text/css; charset=utf-8")
        if parsed.path == "/static/workspace.js":
            return self._serve_static(STATIC_DIR / "workspace.js", "application/javascript; charset=utf-8")
        if parsed.path == "/api/settings/download":
            return self._json(
                {
                    "workdir": WORKDIR,
                    "download_dir": DOWNLOAD_DIR,
                    "download_mode": "video",
                    "include_audio": True,
                    "video_container": "auto",
                    "max_height": None,
                    "audio_format": "best",
                    "audio_quality": None,
                    "concurrent_videos": 1,
                    "concurrent_fragments": 4,
                    "sponsorblock_remove": "",
                    "clean_video": False,
                }
            )
        if parsed.path == "/api/tasks":
            return self._json(self.state.task_list_payload())
        if parsed.path == "/api/tasks/task-1/lifecycle":
            return self._json(self.state.lifecycle_payload())
        if parsed.path == "/api/tasks/task-1/poll":
            return self._json(self.state.next_poll_payload())
        if parsed.path == "/api/tasks/task-1/logs":
            return self._json({"task_id": "task-1", "workdir": WORKDIR, "items": [], "count": 0})
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        assert self.state is not None
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings/download":
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            payload.setdefault("workdir", WORKDIR)
            payload.setdefault("download_dir", DOWNLOAD_DIR)
            return self._json(payload)
        if parsed.path == "/api/agent/resume":
            self.state.mark_resume()
            return self._json({"task_id": "task-1", "status": "running", "message": "resumed"})
        if parsed.path == "/api/system/open-path":
            return self._json({"ok": True, "path": SESSION_DIR})
        self.send_error(404)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class WebWorkspaceSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.state = _ScenarioState()
        handler = type("WorkspaceHandler", (_WorkspaceHandler,), {})
        handler.state = self.state
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.page = QWebEnginePage()
        self.addCleanup(self._cleanup_page)
        self.addCleanup(self._cleanup_server)
        self._load_page()

    def _cleanup_page(self) -> None:
        if getattr(self, "page", None) is not None:
            self.page.deleteLater()

    def _cleanup_server(self) -> None:
        if getattr(self, "server", None) is not None:
            self.server.shutdown()
            self.server.server_close()
        if getattr(self, "server_thread", None) is not None:
            self.server_thread.join(timeout=2)

    def _load_page(self) -> None:
        loop = QEventLoop()
        self.page.loadFinished.connect(loop.quit)
        self.page.load(QUrl(f"{self.base_url}/"))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        self._wait_for_js("typeof window.loadTaskLifecycle === 'function'")

    def _run_js(self, script: str, timeout_ms: int = 10000):
        loop = QEventLoop()
        holder: dict[str, object] = {}

        def _done(result):
            holder["result"] = result
            loop.quit()

        self.page.runJavaScript(script, _done)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return holder.get("result")

    def _run_js_json(self, script: str, timeout_ms: int = 10000) -> dict:
        result = self._run_js(f"JSON.stringify({script})", timeout_ms=timeout_ms)
        self.assertIsInstance(result, str)
        return json.loads(result)

    def _wait_for_js(self, script: str, timeout_s: float = 5.0, interval_s: float = 0.05):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            result = self._run_js(script)
            if result:
                return result
            time.sleep(interval_s)
        self.fail(f"Timed out waiting for JS condition: {script}")

    def _load_task(self) -> None:
        self._run_js(f"loadTaskLifecycle('task-1', '{WORKDIR}')")
        self._wait_for_js("document.querySelector('#confirmWrap #btnConfirmNow') !== null")

    def test_confirmation_cta_and_prepare_to_download_transition(self) -> None:
        self._load_task()

        info = self._run_js_json(
            """
            (() => ({
              primaryCount: document.querySelectorAll('#confirmWrap button.btn').length,
              text: document.getElementById('btnConfirmNow') ? document.getElementById('btnConfirmNow').textContent.trim() : '',
              stage: document.getElementById('workspaceStagePill')?.textContent.trim() || ''
            }))()
            """
        )
        self.assertEqual(info["primaryCount"], 1)
        self.assertEqual(info["text"], "确认下载并继续")
        self.assertEqual(info["stage"], "等待确认下载")

        started = time.time()
        self._run_js("document.getElementById('btnConfirmNow').click()")
        self._wait_for_js("document.getElementById('confirmWrap').innerText.includes('已确认，正在进入下载阶段')")
        elapsed = time.time() - started
        self.assertLess(elapsed, 0.5)

        stage = self._run_js("document.getElementById('workspaceStagePill').textContent.trim()")
        self.assertEqual(stage, "准备下载中")

    def test_download_progress_updates_and_completed_view_keeps_single_entry(self) -> None:
        self._load_task()
        self._run_js("document.getElementById('btnConfirmNow').click()")
        self._wait_for_js("document.getElementById('workspaceStagePill').textContent.trim() === '准备下载中'")
        self._run_js(f"pollCurrentTask('task-1', '{WORKDIR}')")
        self._run_js(f"pollCurrentTask('task-1', '{WORKDIR}')")

        self._wait_for_js(
            """
            (() => {
              const box = document.getElementById('downloadBox');
              return box && box.innerText.includes('Demo Video') && box.innerText.includes('2.1 MiB/s');
            })()
            """,
            timeout_s=4.0,
        )

        progress_info = self._run_js_json(
            """
            (() => ({
              phase: document.getElementById('downloadPhase')?.textContent.trim() || '',
              text: document.getElementById('downloadBox')?.innerText || ''
            }))()
            """
        )
        self.assertEqual(progress_info["phase"], "downloading")
        self.assertIn("Demo Video", progress_info["text"])
        self.assertIn("2.1 MiB/s", progress_info["text"])

        self.state.set_phase("completed")
        self._run_js(f"loadTaskLifecycle('task-1', '{WORKDIR}')")
        self._wait_for_js("document.querySelector('#entryBox [data-entry-action=\"open\"]') !== null")

        completed_info = self._run_js_json(
            """
            (() => ({
              bodyText: document.body.innerText,
              entryButton: document.querySelector('#entryBox [data-entry-action="open"]')?.textContent.trim() || '',
              entryState: document.getElementById('entryStatusPill')?.textContent.trim() || '',
              stage: document.getElementById('workspaceStagePill')?.textContent.trim() || ''
            }))()
            """
        )
        self.assertEqual(completed_info["stage"], "下载已完成")
        self.assertEqual(completed_info["entryState"], "已就绪")
        self.assertEqual(completed_info["entryButton"], "打开下载目录")
        self.assertNotIn("结果与产物", completed_info["bodyText"])
        self.assertNotIn("最近状态", completed_info["bodyText"])


if __name__ == "__main__":
    unittest.main()
