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

from app.core.app_paths import app_data_root, default_download_dir, default_workdir
from app.web.main import app


class AppPathsTests(unittest.TestCase):
    def test_default_paths_follow_local_appdata_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.core.app_paths.os.name", "nt"):
                with patch.dict(os.environ, {"LOCALAPPDATA": tmp}, clear=False):
                    root = app_data_root()
                    workdir = default_workdir()
                    download_dir = default_download_dir()

        self.assertEqual(root, Path(tmp) / "YTBDLP")
        self.assertEqual(workdir, Path(tmp) / "YTBDLP" / "workspace")
        self.assertEqual(download_dir, Path(tmp) / "YTBDLP" / "workspace" / "downloads")

    def test_default_download_dir_appends_downloads_to_given_workdir(self) -> None:
        target = Path("C:/demo/workspace")

        result = default_download_dir(target)

        self.assertEqual(result, target / "downloads")

    def test_web_bootstrap_returns_dynamic_default_paths(self) -> None:
        client = TestClient(app)
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.core.app_paths.os.name", "nt"):
                with patch.dict(os.environ, {"LOCALAPPDATA": tmp}, clear=False):
                    response = client.get("/api/bootstrap")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["product_mode"], "web-first")
        self.assertEqual(payload["workdir"], str(Path(tmp) / "YTBDLP" / "workspace"))
        self.assertEqual(payload["recommended_download_dir"], str(Path(tmp) / "YTBDLP" / "workspace" / "downloads"))
        self.assertEqual(payload["workdir_source"], "system_default")

    def test_static_html_does_not_embed_repo_specific_workdir(self) -> None:
        index_path = ROOT_DIR / "app" / "web" / "static" / "index.html"
        html = index_path.read_text(encoding="utf-8")

        self.assertNotIn('value="D:/YTBDLP/video_info/web_agent"', html)
        self.assertIn('placeholder="首次加载时会自动填入当前系统推荐工作区"', html)


if __name__ == "__main__":
    unittest.main()
