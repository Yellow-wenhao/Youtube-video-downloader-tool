from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.subprocess_utils import hidden_process_kwargs


class SubprocessUtilsTests(unittest.TestCase):
    def test_hidden_process_kwargs_returns_windows_flags_on_nt(self) -> None:
        with patch("app.core.subprocess_utils.os.name", "nt"):
            kwargs = hidden_process_kwargs()

        self.assertIn("startupinfo", kwargs)
        self.assertIn("creationflags", kwargs)
        self.assertNotEqual(kwargs["creationflags"], 0)

    def test_hidden_process_kwargs_returns_empty_on_non_windows(self) -> None:
        with patch("app.core.subprocess_utils.os.name", "posix"):
            kwargs = hidden_process_kwargs()

        self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
