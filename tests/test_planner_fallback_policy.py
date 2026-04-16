from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.planner import (
    FallbackPlanner,
    PlanDraft,
    PlannerConfigurationError,
    PlannerConnectionError,
    build_planner_from_mode,
    create_default_planner,
)


class _PrimaryFails:
    planner_name = "llm"

    def build_plan(self, user_request: str, workdir: str | Path, defaults: dict | None = None) -> PlanDraft:
        raise PlannerConnectionError("network down")


class _LegacySucceeds:
    planner_name = "legacy_rule_based"

    def build_plan(self, user_request: str, workdir: str | Path, defaults: dict | None = None) -> PlanDraft:
        return PlanDraft(
            title="Legacy plan",
            intent="search_pipeline",
            params={"query": user_request},
            steps=[],
            planner_name=self.planner_name,
        )


class PlannerFallbackPolicyTests(unittest.TestCase):
    def test_default_mode_is_llm_only_not_fallback(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            planner = create_default_planner()

        self.assertEqual(planner.planner_name, "llm")
        self.assertNotIsInstance(planner, FallbackPlanner)

    def test_explicit_modes_cover_llm_legacy_and_fallback(self) -> None:
        self.assertEqual(build_planner_from_mode("legacy_rule_based").planner_name, "legacy_rule_based")
        self.assertEqual(build_planner_from_mode("llm_with_legacy_fallback").planner_name, "llm_with_legacy_fallback")
        self.assertEqual(build_planner_from_mode("llm").planner_name, "llm")

    def test_explicit_fallback_mode_annotates_reason_when_llm_fails(self) -> None:
        planner = FallbackPlanner(_PrimaryFails(), _LegacySucceeds())

        draft = planner.build_plan("find robots", "D:/YTBDLP/video_info/test")

        self.assertEqual(draft.planner_name, "legacy_rule_based")
        self.assertTrue(draft.planner_notes)
        self.assertIn("explicitly enabled", draft.planner_notes[-1])
        self.assertIn("planner_connection_error", draft.planner_notes[-1])

    def test_invalid_mode_message_lists_supported_non_silent_options(self) -> None:
        with self.assertRaises(PlannerConfigurationError) as ctx:
            build_planner_from_mode("auto")

        text = str(ctx.exception)
        self.assertIn("YTBDLP_AGENT_PLANNER=llm", text)
        self.assertIn("legacy_rule_based", text)
        self.assertIn("llm_with_legacy_fallback", text)


if __name__ == "__main__":
    unittest.main()
