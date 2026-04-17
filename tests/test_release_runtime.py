from __future__ import annotations

import json
import logging
import logging.config
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.environment_service import inspect_runtime_environment, resolve_runtime_binary
from app.web.service_entry import _release_log_config
from app.web.runtime_host import LocalWebRuntimeHost


class ReleaseRuntimeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
