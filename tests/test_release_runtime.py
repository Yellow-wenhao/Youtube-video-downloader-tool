from __future__ import annotations

import json
import logging
import logging.config
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.app_paths import APP_VERSION_ENV, RUNTIME_MODE_ENV, RUNTIME_PORT_ENV
from app.core.environment_service import inspect_runtime_environment, resolve_runtime_binary
from app.core.models import StepStatus, TaskSpec, TaskStatus, TaskStep
from app.web import service_entry
from app.web.main import app
from app.web.runtime_host import LocalWebRuntimeHost
from app.web.service_entry import _release_log_config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


class ReleaseRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_resolve_runtime_binary_prefers_bundled_tool_in_release_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "yt-dlp.exe"
            bundled.write_text("echo", encoding="utf-8")
            with patch("app.core.environment_service.bundled_tool_path", return_value=bundled):
                with patch("app.core.environment_service.runtime_mode", return_value="release"):
                    resolved = resolve_runtime_binary("yt-dlp", fallback_names=("yt-dlp", "yt-dlp.exe"))

        self.assertTrue(resolved.found)
        self.assertEqual(resolved.source, "bundled")
        self.assertEqual(Path(resolved.resolved_path), bundled.resolve())

    def test_inspect_runtime_environment_returns_path_resolution_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yt_dlp = Path(tmp) / "yt-dlp.exe"
            ffmpeg = Path(tmp) / "ffmpeg.exe"
            yt_dlp.write_text("yt", encoding="utf-8")
            ffmpeg.write_text("ff", encoding="utf-8")

            def fake_bundled(name: str):
                mapping = {
                    "yt-dlp": yt_dlp,
                    "yt-dlp.exe": yt_dlp,
                    "ffmpeg": ffmpeg,
                    "ffmpeg.exe": ffmpeg,
                }
                return mapping.get(name)

            with patch("app.core.environment_service.bundled_tool_path", side_effect=fake_bundled):
                with patch("app.core.environment_service.runtime_mode", return_value="release"):
                    status = inspect_runtime_environment()

        self.assertTrue(status.yt_dlp_found)
        self.assertTrue(status.ffmpeg_found)
        self.assertEqual(status.yt_dlp_source, "bundled")
        self.assertEqual(status.ffmpeg_source, "bundled")

    def test_runtime_host_writes_metadata_and_tracks_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            metadata = Path(tmp) / "runtime.json"
            host = LocalWebRuntimeHost(metadata_path=metadata, mode="release", version="1.2.3", port=9876, idle_timeout_seconds=900)
            host.start()
            host.request_started("GET /")
            host.request_finished("GET /")
            with host.background_job("task:demo"):
                pass
            host.shutdown()

            payload = json.loads(metadata.read_text(encoding="utf-8"))

        self.assertEqual(payload["port"], 9876)
        self.assertEqual(payload["version"], "1.2.3")
        self.assertEqual(payload["state"], "stopped")
        self.assertEqual(payload["active_requests"], 0)
        self.assertEqual(payload["background_jobs"], 0)

    def test_release_log_config_rebuilds_file_handlers_without_console_only_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "service.log"
            config = _release_log_config(log_path)

            self.assertNotIn("stream", config["handlers"]["default"])
            self.assertNotIn("stream", config["handlers"]["access"])

            logging.config.dictConfig(config)
            try:
                logger = logging.getLogger("uvicorn.error")
                logger.info("release log smoke")
            finally:
                logging.shutdown()

            self.assertTrue(log_path.exists())

    def test_service_entry_sets_release_env_and_runs_uvicorn_server(self) -> None:
        fd, log_name = tempfile.mkstemp(suffix="-web-service.log")
        os.close(fd)
        log_path = Path(log_name)
        self.addCleanup(lambda: _cleanup_path(log_path))
        with patch("app.web.service_entry.web_service_log_path", return_value=log_path):
            with patch("app.web.service_entry._configure_release_stdio") as configure_stdio:
                with patch("app.web.service_entry.uvicorn.Server") as server_cls:
                    server = server_cls.return_value
                    exit_code = service_entry.main(["--host", "127.0.0.1", "--port", "9123", "--version", "1.2.3"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(os.environ[RUNTIME_MODE_ENV], "release")
        self.assertEqual(os.environ[RUNTIME_PORT_ENV], "9123")
        self.assertEqual(os.environ[APP_VERSION_ENV], "1.2.3")
        configure_stdio.assert_called_once_with(log_path)
        config = server_cls.call_args.args[0]
        self.assertEqual(config.app, "app.web.main:app")
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 9123)
        self.assertFalse(config.reload)
        server.run.assert_called_once_with()

    def test_release_mode_health_endpoint_smoke(self) -> None:
        with patch.dict(os.environ, {RUNTIME_MODE_ENV: "release"}, clear=False):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")

    def test_release_mode_agent_plan_endpoint_smoke(self) -> None:
        task = TaskSpec(
            task_id="release-plan",
            title="Release smoke task",
            user_request="find videos",
            intent="search_pipeline",
            workdir=tempfile.gettempdir(),
            created_at=_now(),
            updated_at=_now(),
            status=TaskStatus.PLANNED,
            params={"search_limit": 3},
            steps=[
                TaskStep(
                    step_id="search",
                    title="Search videos",
                    tool_name="search_videos",
                    status=StepStatus.PENDING,
                )
            ],
            current_step_index=0,
            needs_confirmation=False,
        )
        with patch.dict(os.environ, {RUNTIME_MODE_ENV: "release"}, clear=False):
            with patch("app.web.main.AgentRunner.plan", return_value=task):
                response = self.client.post(
                    "/api/agent/plan",
                    json={"user_request": "find videos", "workdir": tempfile.gettempdir()},
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["task_id"], task.task_id)
        self.assertEqual(payload["status"], TaskStatus.PLANNED.value)


if __name__ == "__main__":
    unittest.main()
