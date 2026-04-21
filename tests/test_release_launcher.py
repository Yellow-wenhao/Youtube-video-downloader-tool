from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.web.release_launcher import _choose_port, _service_command, main


class ReleaseLauncherTests(unittest.TestCase):
    def test_choose_port_returns_usable_port(self) -> None:
        port = _choose_port(0)
        self.assertIsInstance(port, int)
        self.assertGreater(port, 0)

    def test_service_command_uses_python_module_in_dev_mode(self) -> None:
        with patch("app.web.release_launcher.is_frozen_app", return_value=False):
            command = _service_command(8765, "1.0.0")

        self.assertEqual(command[:3], [sys.executable, "-m", "app.web.service_entry"])
        self.assertIn("--port", command)
        self.assertIn("8765", command)

    def test_main_reuses_existing_runtime_when_alive(self) -> None:
        url = "http://127.0.0.1:8765"
        with patch("app.web.release_launcher._is_existing_runtime_alive", return_value=(True, url)):
            with patch("app.web.release_launcher._open_browser", return_value=True) as open_browser:
                with patch("app.web.release_launcher._launch_service") as launch_service:
                    exit_code = main(["--version", "1.2.3"])

        self.assertEqual(exit_code, 0)
        open_browser.assert_called_once_with(url)
        launch_service.assert_not_called()

    def test_main_launches_service_and_opens_browser_when_runtime_is_not_running(self) -> None:
        url = "http://127.0.0.1:9000"
        command = [sys.executable, "-m", "app.web.service_entry", "--port", "9000"]
        with patch("app.web.release_launcher._is_existing_runtime_alive", return_value=(False, "")):
            with patch("app.web.release_launcher._choose_port", return_value=9000):
                with patch("app.web.release_launcher._service_command", return_value=command) as service_command:
                    with patch("app.web.release_launcher.is_frozen_app", return_value=False):
                        with patch("app.web.release_launcher._launch_service") as launch_service:
                            with patch("app.web.release_launcher._wait_for_runtime", return_value=True) as wait_for_runtime:
                                with patch("app.web.release_launcher._open_browser", return_value=True) as open_browser:
                                    exit_code = main(["--version", "1.2.3"])

        self.assertEqual(exit_code, 0)
        service_command.assert_called_once_with(9000, "1.2.3")
        launch_service.assert_called_once_with(command, version="1.2.3", port=9000)
        wait_for_runtime.assert_called_once_with(url)
        open_browser.assert_called_once_with(url)

    def test_main_returns_error_when_frozen_service_exe_is_missing(self) -> None:
        with patch("app.web.release_launcher._is_existing_runtime_alive", return_value=(False, "")):
            with patch("app.web.release_launcher._choose_port", return_value=9000):
                with patch("app.web.release_launcher._service_command", return_value=[r"C:\missing\youtube-downloader-service.exe"]):
                    with patch("app.web.release_launcher.is_frozen_app", return_value=True):
                        with patch("app.web.release_launcher._show_message") as show_message:
                            exit_code = main(["--version", "1.2.3"])

        self.assertEqual(exit_code, 1)
        show_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
