from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.llm_planner import LLMPlanner
from app.agent.prompt_loader import load_prompt_template, render_prompt_template


class AgentPromptLoaderTests(unittest.TestCase):
    def test_system_prompt_template_exists_and_can_be_loaded(self) -> None:
        content = load_prompt_template("system_prompt.md")

        self.assertIn("You are the planning model", content)
        self.assertIn("{{TOOL_DEFAULTS_JSON}}", content)
        self.assertIn("search_pipeline", content)

    def test_render_prompt_template_replaces_runtime_defaults_placeholder(self) -> None:
        rendered = render_prompt_template(
            "system_prompt.md",
            {"TOOL_DEFAULTS_JSON": '{"search_limit": 25, "download_mode": "video"}'},
        )

        self.assertIn('"search_limit": 25', rendered)
        self.assertIn('"download_mode": "video"', rendered)
        self.assertNotIn("{{TOOL_DEFAULTS_JSON}}", rendered)

    def test_llm_planner_build_system_prompt_uses_file_template(self) -> None:
        planner = LLMPlanner()
        prompt = planner._build_system_prompt(
            {
                "search_limit": 42,
                "min_duration": 180,
                "download_mode": "audio",
                "include_audio": False,
                "concurrent_videos": 3,
            }
        )

        self.assertIn("strict JSON only", prompt)
        self.assertIn("retry_failed_downloads", prompt)
        self.assertIn('"search_limit": 42', prompt)
        self.assertIn('"min_duration": 180', prompt)
        self.assertIn('"download_mode": "audio"', prompt)
        self.assertIn('"include_audio": false', prompt.lower())
        self.assertIn('"concurrent_videos": 3', prompt)


if __name__ == "__main__":
    unittest.main()
