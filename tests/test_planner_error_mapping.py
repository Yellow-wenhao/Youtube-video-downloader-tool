from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.planner import (
    PlannerConfigurationError,
    PlannerConnectionError,
    PlannerResponseError,
    PlannerSchemaError,
    planner_error_view,
)
from app.agent.runner import AgentRunnerPlanningError
from app.web.main import app


class PlannerErrorMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_planner_error_view_covers_expected_categories(self) -> None:
        self.assertEqual(planner_error_view("planner_config_error")["error_category"], "config")
        self.assertEqual(planner_error_view("planner_connection_error")["error_category"], "connection")
        self.assertEqual(planner_error_view("planner_response_error")["error_category"], "response_structure")
        self.assertEqual(planner_error_view("planner_schema_error")["error_category"], "response_structure")

    def test_planner_error_view_falls_back_to_unknown_mapping(self) -> None:
        payload = planner_error_view("totally_unknown_code")

        self.assertEqual(payload["error_category"], "unknown")
        self.assertEqual(payload["user_title"], "Agent 计划生成失败")
        self.assertTrue(payload["user_message"])
        self.assertTrue(payload["user_recovery"])
        self.assertEqual(payload["user_actions"], ["重试", "检查配置", "更换模型"])

    def test_planner_runtime_errors_emit_user_facing_payload_fields(self) -> None:
        cases = [
            PlannerConfigurationError("missing api key"),
            PlannerConnectionError("network down"),
            PlannerResponseError("invalid json"),
            PlannerSchemaError("missing search_queries"),
        ]

        for exc in cases:
            with self.subTest(code=exc.code):
                payload = exc.to_payload()
                self.assertEqual(payload["kind"], "planner_error")
                self.assertEqual(payload["code"], exc.code)
                self.assertTrue(payload["user_title"])
                self.assertTrue(payload["user_message"])
                self.assertIn("error_category", payload)
                self.assertIsInstance(payload["user_actions"], list)

    def test_agent_runner_planning_error_preserves_planner_mapping_fields(self) -> None:
        exc = PlannerSchemaError("missing required fields")

        mapped = AgentRunnerPlanningError.from_exception(exc).to_payload()

        self.assertEqual(mapped["code"], "planner_schema_error")
        self.assertEqual(mapped["error_category"], "response_structure")
        self.assertTrue(mapped["user_title"])
        self.assertTrue(mapped["user_message"])
        self.assertTrue(mapped["user_recovery"])
        self.assertIsInstance(mapped["user_actions"], list)

    def test_agent_runner_planning_error_uses_unknown_mapping_for_unclassified_exception(self) -> None:
        mapped = AgentRunnerPlanningError.from_exception(RuntimeError("boom")).to_payload()

        self.assertEqual(mapped["code"], "planner_unknown_error")
        self.assertEqual(mapped["phase"], "planning")
        self.assertEqual(mapped["error_category"], "unknown")
        self.assertEqual(mapped["user_title"], "Agent 计划生成失败")
        self.assertEqual(mapped["user_actions"], ["重试", "检查配置", "更换模型"])

    def test_agent_plan_endpoint_returns_planner_error_payload_without_losing_user_fields(self) -> None:
        planner_error = AgentRunnerPlanningError.from_exception(PlannerConnectionError("network down"))
        with patch("app.web.main.AgentRunner.plan", side_effect=planner_error):
            response = self.client.post(
                "/api/agent/plan",
                json={"user_request": "下载最近的评测视频", "workdir": "D:/YTBDLP/video_info/test"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["kind"], "agent_runner_error")
        self.assertEqual(payload["code"], "planner_connection_error")
        self.assertEqual(payload["phase"], "planning")
        self.assertEqual(payload["error_category"], "connection")
        self.assertEqual(payload["user_title"], "Agent 连接失败")
        self.assertEqual(payload["user_message"], "当前无法连接到所选 LLM Provider。")
        self.assertEqual(
            payload["user_recovery"],
            "请先测试连接，并检查网络、Base URL、代理或 API Key 是否有效。",
        )
        self.assertEqual(payload["user_actions"], ["测试连接", "检查网络", "检查 Base URL", "检查 API Key"])

    def test_agent_test_connection_endpoint_returns_planner_runtime_error_payload(self) -> None:
        with patch("app.web.main.test_llm_connection", side_effect=PlannerConfigurationError("missing api key")):
            response = self.client.post(
                "/api/agent/test-connection",
                json={
                    "provider": "openai",
                    "base_url": "https://example.invalid/v1",
                    "model": "gpt-5.4",
                    "api_key": "",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["kind"], "planner_error")
        self.assertEqual(payload["code"], "planner_config_error")
        self.assertEqual(payload["phase"], "planning")
        self.assertEqual(payload["error_category"], "config")
        self.assertEqual(payload["user_title"], "Agent 配置不完整")
        self.assertTrue(payload["user_message"])
        self.assertTrue(payload["user_recovery"])
        self.assertEqual(payload["user_actions"], ["检查 Provider", "检查 Base URL", "检查模型名", "检查 API Key"])


if __name__ == "__main__":
    unittest.main()
