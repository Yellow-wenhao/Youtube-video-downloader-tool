from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.app_paths import (
    APP_DIR_NAME,
    PRODUCT_NAME,
    app_data_root,
    default_download_dir,
    default_workdir,
    runtime_metadata_path,
    runtime_mode,
)
from app.web.main import app


class AppPathsTests(unittest.TestCase):
    def test_default_paths_follow_user_safe_windows_directories(self) -> None:
        with tempfile.TemporaryDirectory() as local_app, tempfile.TemporaryDirectory() as profile:
            with patch("app.core.app_paths.os.name", "nt"):
                with patch.dict(os.environ, {"LOCALAPPDATA": local_app, "USERPROFILE": profile}, clear=False):
                    root = app_data_root()
                    workdir = default_workdir()
                    download_dir = default_download_dir()
                    metadata = runtime_metadata_path()

        self.assertEqual(root, Path(local_app) / APP_DIR_NAME)
        self.assertEqual(workdir, Path(local_app) / APP_DIR_NAME / "workspace")
        self.assertEqual(download_dir, Path(profile) / "Downloads" / PRODUCT_NAME)
        self.assertEqual(metadata, Path(local_app) / APP_DIR_NAME / "runtime" / "runtime.json")

    def test_default_download_dir_ignores_custom_workdir_and_uses_downloads_root(self) -> None:
        with tempfile.TemporaryDirectory() as profile:
            with patch("app.core.app_paths.os.name", "nt"):
                with patch.dict(os.environ, {"USERPROFILE": profile}, clear=False):
                    result = default_download_dir(Path("C:/demo/workspace"))

        self.assertEqual(result, Path(profile) / "Downloads" / PRODUCT_NAME)

    def test_runtime_mode_prefers_release_when_env_requests_it(self) -> None:
        with patch.dict(os.environ, {"YTBDLP_RUNTIME_MODE": "release"}, clear=False):
            self.assertEqual(runtime_mode(), "release")

    def test_web_bootstrap_returns_dynamic_default_paths(self) -> None:
        client = TestClient(app)
        with tempfile.TemporaryDirectory() as local_app, tempfile.TemporaryDirectory() as profile:
            with patch("app.core.app_paths.os.name", "nt"):
                with patch.dict(os.environ, {"LOCALAPPDATA": local_app, "USERPROFILE": profile}, clear=False):
                    response = client.get("/api/bootstrap")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["product_mode"], "web-first")
        self.assertEqual(payload["workdir"], str(Path(local_app) / APP_DIR_NAME / "workspace"))
        self.assertEqual(payload["recommended_download_dir"], str(Path(profile) / "Downloads" / PRODUCT_NAME))
        self.assertEqual(payload["workdir_source"], "system_default")

    def test_static_html_does_not_embed_repo_specific_workdir(self) -> None:
        index_path = ROOT_DIR / "app" / "web" / "static" / "index.html"
        html = index_path.read_text(encoding="utf-8")

        self.assertNotIn('value="D:/YTBDLP/video_info/web_agent"', html)
        self.assertIn('placeholder="首次加载时会自动填入当前系统推荐工作区"', html)


if __name__ == "__main__":
    unittest.main()
