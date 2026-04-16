from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys
import shutil
import uuid
from contextlib import contextmanager

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.runner import AgentRunner
from app.agent.session_store import SessionStore
from app.core.models import StepStatus, TaskResult, TaskSpec, TaskStatus, TaskStep
from app.core.task_service import TaskStore
from app.web.failure_diagnosis import build_task_failure_diagnosis


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _workspace_tempdir():
    base = ROOT_DIR / ".tmp_test_runs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"case_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _DummyRegistry:
    def execute(self, tool_name: str, payload):
        return {"tool_name": tool_name, "payload": payload}


class TaskFailureDiagnosisTests(unittest.TestCase):
    def _task(self, workdir: Path, *, status: TaskStatus = TaskStatus.FAILED, payload: dict | None = None) -> TaskSpec:
        return TaskSpec(
            task_id="task-001",
            title="下载任务",
            user_request="download videos",
            intent="download",
            workdir=str(workdir),
            created_at=_now(),
            updated_at=_now(),
            status=status,
            steps=[
                TaskStep(
                    step_id="download",
                    title="下载已勾选视频",
                    tool_name="start_download",
                    payload=payload or {},
                    status=StepStatus.FAILED if status == TaskStatus.FAILED else StepStatus.PENDING,
                    message="step failed",
                )
            ],
            current_step_index=0,
            needs_confirmation=False,
        )

    def test_download_input_failure_has_user_facing_recovery(self) -> None:
        with _workspace_tempdir() as tmp:
            task = self._task(Path(tmp))
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                message="必须提供 items_path 或 urls_file",
                data={
                    "failed_step": "download",
                    "failed_step_title": "下载已勾选视频",
                    "tool_name": "start_download",
                    "error_type": "ValueError",
                    "failure_origin": "tool_execution",
                },
                started_at=_now(),
                finished_at=_now(),
            )

            failure = build_task_failure_diagnosis(task, result)

            self.assertIsNotNone(failure)
            self.assertEqual(failure["category"], "download_input")
            self.assertIn("下载输入不完整", failure["title"])
            self.assertIn("审核页", failure["recovery"])
            self.assertIn("返回审核页", failure["actions"])

    def test_explicit_user_fields_are_preserved(self) -> None:
        with _workspace_tempdir() as tmp:
            task = self._task(Path(tmp))
            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                message="planner error",
                data={
                    "error_category": "connection",
                    "user_title": "连接失败",
                    "user_message": "当前无法连到远端服务。",
                    "user_recovery": "请检查网络后重试。",
                    "user_actions": ["重试", "检查网络"],
                },
                started_at=_now(),
                finished_at=_now(),
            )

            failure = build_task_failure_diagnosis(task, result)

            self.assertIsNotNone(failure)
            self.assertEqual(failure["category"], "connection")
            self.assertEqual(failure["title"], "连接失败")
            self.assertEqual(failure["summary"], "当前无法连到远端服务。")
            self.assertEqual(failure["recovery"], "请检查网络后重试。")
            self.assertEqual(failure["actions"], ["重试", "检查网络"])

    def test_runner_persists_payload_resolution_failure(self) -> None:
        with _workspace_tempdir() as tmp:
            workdir = Path(tmp)
            store = TaskStore(workdir)
            session = SessionStore(workdir)
            runner = AgentRunner(registry=_DummyRegistry())
            task = self._task(workdir, status=TaskStatus.PLANNED, payload={"items_path": "{{steps.search.output_path}}"})
            task.steps[0].status = StepStatus.PENDING
            store.save_task(task)

            result = runner.execute_task(task, store, session, auto_confirm=True)
            failure = build_task_failure_diagnosis(task, result)

            self.assertEqual(result.status, TaskStatus.FAILED)
            self.assertEqual(result.data["failure_origin"], "payload_resolution")
            self.assertEqual(result.data["error_type"], "KeyError")
            self.assertIsNotNone(failure)
            self.assertEqual(failure["category"], "payload_resolution")
            self.assertIn("前置步骤", failure["recovery"])


if __name__ == "__main__":
    unittest.main()
