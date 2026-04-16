from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.web.release_launcher import _choose_port, _service_command


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


if __name__ == "__main__":
    unittest.main()
