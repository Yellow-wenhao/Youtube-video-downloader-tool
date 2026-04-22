from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.planner import (
    PlannerConfigurationError,
    build_planner_from_mode,
    create_default_planner,
)


class PlannerFallbackPolicyTests(unittest.TestCase):
    def test_default_mode_is_llm_only_not_fallback(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            planner = create_default_planner()

        self.assertEqual(planner.planner_name, "llm")

    def test_only_llm_mode_is_supported(self) -> None:
        self.assertEqual(build_planner_from_mode("llm").planner_name, "llm")

    def test_invalid_mode_message_lists_supported_non_silent_options(self) -> None:
        with self.assertRaises(PlannerConfigurationError) as ctx:
            build_planner_from_mode("auto")

        text = str(ctx.exception)
        self.assertIn("YTBDLP_AGENT_PLANNER=llm", text)
        self.assertNotIn("legacy_rule_based", text)
        self.assertNotIn("llm_with_legacy_fallback", text)


if __name__ == "__main__":
    unittest.main()
