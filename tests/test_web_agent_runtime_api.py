from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.models import StepStatus, TaskResult, TaskSpec, TaskStatus, TaskStep
from app.web.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebAgentRuntimeApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)
        self.client = TestClient(app)

    def _task(self, *, task_id: str = "task-001", status: TaskStatus = TaskStatus.PLANNED) -> TaskSpec:
        return TaskSpec(
            task_id=task_id,
            title="Demo Task",
            user_request="find some videos",
            intent="search_pipeline",
            workdir=str(self.workdir),
            created_at=_now(),
            updated_at=_now(),
            status=status,
            params={"search_limit": 5},
            steps=[
                TaskStep(
                    step_id="search",
                    title="Search videos",
                    tool_name="search_videos",
                    status=StepStatus.PENDING if status == TaskStatus.PLANNED else StepStatus.COMPLETED,
                )
            ],
            current_step_index=0,
            needs_confirmation=False,
        )

    def test_agent_plan_endpoint_returns_task_summary_shape(self) -> None:
        task = self._task()
        with patch("app.web.main.AgentRunner.plan", return_value=task):
            response = self.client.post(
                "/api/agent/plan",
                json={"user_request": "find some videos", "workdir": str(self.workdir)},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["task_id"], task.task_id)
        self.assertEqual(payload["title"], task.title)
        self.assertEqual(payload["intent"], task.intent)
        self.assertEqual(payload["status"], task.status.value)
        self.assertIn("steps", payload)
        self.assertEqual(payload["workdir"], str(self.workdir))

    def test_agent_run_endpoint_returns_result_payload(self) -> None:
        result = TaskResult(
            task_id="task-run",
            status=TaskStatus.SUCCEEDED,
            message="Task completed successfully",
            data={"task": {"task_id": "task-run"}, "step_results": {"search": {"count": 3}}},
            started_at=_now(),
            finished_at=_now(),
        )
        with patch("app.web.main.AgentRunner.run", return_value=result):
            response = self.client.post(
                "/api/agent/run",
                json={
                    "user_request": "run task",
                    "workdir": str(self.workdir),
                    "auto_confirm": True,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["task_id"], result.task_id)
        self.assertEqual(payload["status"], TaskStatus.SUCCEEDED.value)
        self.assertEqual(payload["message"], result.message)
        self.assertEqual(payload["data"]["step_results"]["search"]["count"], 3)

    def test_agent_resume_endpoint_returns_result_payload(self) -> None:
        result = TaskResult(
            task_id="task-resume",
            status=TaskStatus.AWAITING_CONFIRMATION,
            message="确认后才能继续执行: Download videos",
            data={"pending_step": "download", "task": {"task_id": "task-resume"}},
            started_at=_now(),
            finished_at=_now(),
        )
        with patch("app.web.main.AgentRunner.resume", return_value=result):
            response = self.client.post(
                "/api/agent/resume",
                json={
                    "workdir": str(self.workdir),
                    "task_id": result.task_id,
                    "auto_confirm": False,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["task_id"], result.task_id)
        self.assertEqual(payload["status"], TaskStatus.AWAITING_CONFIRMATION.value)
        self.assertEqual(payload["data"]["pending_step"], "download")


if __name__ == "__main__":
    unittest.main()
