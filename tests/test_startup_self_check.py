from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.startup_self_check import format_startup_dependency_report, inspect_startup_dependencies


class StartupSelfCheckTests(unittest.TestCase):
    @patch("app.core.startup_self_check.resolve_runtime_binary")
    @patch("app.core.startup_self_check.importlib.util.find_spec")
    def test_inspect_startup_dependencies_reports_missing_entries(self, find_spec_mock, resolve_binary_mock) -> None:
        find_spec_mock.side_effect = lambda name: object() if name in {"langgraph", "fastapi"} else None
        resolve_binary_mock.return_value.found = False
        resolve_binary_mock.return_value.requested = "yt-dlp"
        resolve_binary_mock.return_value.resolved_path = ""

        checks = inspect_startup_dependencies()

        self.assertEqual([check.display_name for check in checks], ["langgraph", "fastapi", "uvicorn", "yt-dlp", "yt-dlp binary"])
        self.assertTrue(checks[0].found)
        self.assertTrue(checks[1].found)
        self.assertFalse(checks[2].found)
        self.assertFalse(checks[3].found)
        self.assertFalse(checks[4].found)

    @patch("app.core.startup_self_check.resolve_runtime_binary")
    @patch("app.core.startup_self_check.importlib.util.find_spec")
    def test_format_report_is_ready_only_when_all_checks_pass(self, find_spec_mock, resolve_binary_mock) -> None:
        find_spec_mock.return_value = object()
        resolve_binary_mock.return_value.found = True
        resolve_binary_mock.return_value.requested = "yt-dlp"
        resolve_binary_mock.return_value.resolved_path = "C:/tools/yt-dlp.exe"

        ready, lines = format_startup_dependency_report()

        self.assertTrue(ready)
        self.assertEqual(lines[0], "Environment self-check:")
        self.assertIn("[OK] langgraph (importable)", lines)
        self.assertIn("[OK] yt-dlp binary (C:/tools/yt-dlp.exe)", lines)


if __name__ == "__main__":
    unittest.main()
