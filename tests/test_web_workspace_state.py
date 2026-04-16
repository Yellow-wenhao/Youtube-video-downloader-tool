from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.agent.session_store import SessionStore
from app.core.models import TaskDownloadProgress, TaskResult, TaskSpec, TaskStatus, TaskStep, StepStatus
from app.core.task_service import TaskStore
from app.web.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkspaceStateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)
        self.download_dir = self.workdir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        SessionStore(self.workdir).update_defaults({"download_dir": str(self.download_dir)})
        self.store = TaskStore(self.workdir)
        self.client = TestClient(app)

    def _create_task(
        self,
        *,
        task_id: str,
        task_status: TaskStatus,
        step_status: StepStatus,
        tool_name: str = "start_download",
        requires_confirmation: bool = False,
    ) -> TaskSpec:
        task = TaskSpec(
            task_id=task_id,
            title=f"Task {task_id}",
            user_request="download sample videos",
            intent="download",
            workdir=str(self.workdir),
            created_at=_now(),
            updated_at=_now(),
            status=task_status,
            steps=[
                TaskStep(
                    step_id="download_step",
                    title="下载视频",
                    tool_name=tool_name,
                    requires_confirmation=requires_confirmation,
                    status=step_status,
                    message="step message",
                )
            ],
            current_step_index=0,
            needs_confirmation=task_status == TaskStatus.AWAITING_CONFIRMATION,
        )
        self.store.save_task(task)
        return task

    def _save_progress(self, task_id: str, *, phase: str, percent: float = 30.0) -> None:
        self.store.save_download_progress(
            TaskDownloadProgress(
                task_id=task_id,
                phase=phase,
                percent=percent,
                downloaded_bytes=1024 * 1024,
                total_bytes=4 * 1024 * 1024,
                speed_text="2.1 MiB/s",
                current_video_id="vid-001",
                current_video_label="Demo Video",
                updated_at=_now(),
            )
        )

    def _save_result(self, task_id: str, *, status: TaskStatus, message: str, session_dir: str = "") -> None:
        data = {"session_dir": session_dir} if session_dir else {}
        self.store.save_result(
            TaskResult(
                task_id=task_id,
                status=status,
                message=message,
                data=data,
                started_at=_now(),
                finished_at=_now(),
            )
        )

    def _get_lifecycle(self, task_id: str) -> dict:
        response = self.client.get(f"/api/tasks/{task_id}/lifecycle", params={"workdir": str(self.workdir)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _get_poll(self, task_id: str) -> dict:
        response = self.client.get(f"/api/tasks/{task_id}/poll", params={"workdir": str(self.workdir)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _assert_stage_snapshot(
        self,
        task_id: str,
        *,
        expected_stage: str,
        expected_label: str,
        expected_ready: bool,
        confirmation_required: bool,
    ) -> tuple[dict, dict]:
        lifecycle = self._get_lifecycle(task_id)
        poll = self._get_poll(task_id)
        self.assertEqual(lifecycle["workspace_stage"], expected_stage)
        self.assertEqual(poll["workspace_stage"], expected_stage)
        self.assertEqual(lifecycle["workspace_stage_label"], expected_label)
        self.assertEqual(poll["workspace_stage_label"], expected_label)
        self.assertEqual(bool(lifecycle.get("confirmation")), confirmation_required)
        self.assertEqual(bool(poll.get("confirmation")), confirmation_required)
        self.assertEqual(lifecycle["download_entry"]["ready"], expected_ready)
        self.assertEqual(poll["download_entry"]["ready"], expected_ready)
        self.assertTrue(lifecycle["primary_message"])
        self.assertTrue(poll["primary_message"])
        return lifecycle, poll

    def test_workspace_stage_mapping_across_lifecycle_and_poll(self) -> None:
        ready_session_dir = self.download_dir / "task-completed"
        ready_session_dir.mkdir(parents=True, exist_ok=True)

        cases = [
            {
                "task_id": "awaiting",
                "task_status": TaskStatus.AWAITING_CONFIRMATION,
                "step_status": StepStatus.AWAITING_CONFIRMATION,
                "requires_confirmation": True,
                "expected_stage": "awaiting_confirmation",
                "expected_ready": False,
                "expected_confirmation": True,
            },
            {
                "task_id": "preparing",
                "task_status": TaskStatus.RUNNING,
                "step_status": StepStatus.RUNNING,
                "expected_stage": "preparing_download",
                "expected_ready": False,
                "expected_confirmation": False,
            },
            {
                "task_id": "downloading",
                "task_status": TaskStatus.RUNNING,
                "step_status": StepStatus.RUNNING,
                "progress_phase": "downloading",
                "expected_stage": "downloading",
                "expected_ready": False,
                "expected_confirmation": False,
            },
            {
                "task_id": "finalizing",
                "task_status": TaskStatus.RUNNING,
                "step_status": StepStatus.RUNNING,
                "progress_phase": "completed",
                "expected_stage": "finalizing",
                "expected_ready": False,
                "expected_confirmation": False,
            },
            {
                "task_id": "completed",
                "task_status": TaskStatus.SUCCEEDED,
                "step_status": StepStatus.COMPLETED,
                "progress_phase": "completed",
                "result_status": TaskStatus.SUCCEEDED,
                "result_message": "Task completed successfully",
                "session_dir": str(ready_session_dir),
                "expected_stage": "completed",
                "expected_ready": True,
                "expected_confirmation": False,
            },
            {
                "task_id": "failed",
                "task_status": TaskStatus.FAILED,
                "step_status": StepStatus.FAILED,
                "result_status": TaskStatus.FAILED,
                "result_message": "download failed",
                "expected_stage": "failed",
                "expected_ready": False,
                "expected_confirmation": False,
            },
        ]

        for case in cases:
            with self.subTest(case=case["task_id"]):
                self._create_task(
                    task_id=case["task_id"],
                    task_status=case["task_status"],
                    step_status=case["step_status"],
                    requires_confirmation=case.get("requires_confirmation", False),
                )
                if case.get("progress_phase"):
                    self._save_progress(case["task_id"], phase=case["progress_phase"])
                if case.get("result_status"):
                    self._save_result(
                        case["task_id"],
                        status=case["result_status"],
                        message=case["result_message"],
                        session_dir=case.get("session_dir", ""),
                    )

                lifecycle = self._get_lifecycle(case["task_id"])
                poll = self._get_poll(case["task_id"])

                self.assertEqual(lifecycle["workspace_stage"], case["expected_stage"])
                self.assertEqual(poll["workspace_stage"], case["expected_stage"])
                self.assertEqual(lifecycle["workspace_stage_label"], poll["workspace_stage_label"])
                self.assertEqual(bool(lifecycle.get("confirmation")), case["expected_confirmation"])
                self.assertEqual(bool(poll.get("confirmation")), case["expected_confirmation"])
                self.assertTrue(lifecycle["primary_message"])
                self.assertTrue(poll["primary_message"])
                self.assertEqual(lifecycle["download_entry"]["ready"], case["expected_ready"])
                self.assertEqual(poll["download_entry"]["ready"], case["expected_ready"])
                self.assertEqual(lifecycle["download_entry"]["path"], poll["download_entry"]["path"])

    def test_completed_stage_prefers_session_dir_for_download_entry(self) -> None:
        session_dir = self.download_dir / "task-output"
        session_dir.mkdir(parents=True, exist_ok=True)
        self._create_task(
            task_id="done",
            task_status=TaskStatus.SUCCEEDED,
            step_status=StepStatus.COMPLETED,
        )
        self._save_result(
            "done",
            status=TaskStatus.SUCCEEDED,
            message="all good",
            session_dir=str(session_dir),
        )

        lifecycle = self._get_lifecycle("done")

        self.assertEqual(lifecycle["workspace_stage"], "completed")
        self.assertEqual(lifecycle["download_entry"]["path"], str(session_dir))
        self.assertTrue(lifecycle["download_entry"]["ready"])
        self.assertEqual(lifecycle["download_entry"]["label"], "打开已下载视频")

    def test_workspace_stage_transition_sequence_from_confirmation_to_completion(self) -> None:
        session_dir = self.download_dir / "transition-done"
        session_dir.mkdir(parents=True, exist_ok=True)
        task = self._create_task(
            task_id="transition-seq",
            task_status=TaskStatus.AWAITING_CONFIRMATION,
            step_status=StepStatus.AWAITING_CONFIRMATION,
            requires_confirmation=True,
        )

        lifecycle, poll = self._assert_stage_snapshot(
            "transition-seq",
            expected_stage="awaiting_confirmation",
            expected_label="等待确认下载",
            expected_ready=False,
            confirmation_required=True,
        )
        self.assertIn("确认", lifecycle["primary_message"])
        self.assertIn("确认", poll["primary_message"])

        task = self.store.set_step_status(
            task,
            0,
            StepStatus.RUNNING,
            message="confirmed and starting download",
        )
        task.needs_confirmation = False
        task = self.store.set_task_status(task, TaskStatus.RUNNING, message="download is starting")

        lifecycle, poll = self._assert_stage_snapshot(
            "transition-seq",
            expected_stage="preparing_download",
            expected_label="准备下载中",
            expected_ready=False,
            confirmation_required=False,
        )
        self.assertIn("准备下载", lifecycle["primary_message"])
        self.assertIn("准备下载", poll["primary_message"])

        self._save_progress("transition-seq", phase="downloading", percent=42.0)
        lifecycle, poll = self._assert_stage_snapshot(
            "transition-seq",
            expected_stage="downloading",
            expected_label="正在下载",
            expected_ready=False,
            confirmation_required=False,
        )
        self.assertIn("正在下载", lifecycle["primary_message"])
        self.assertEqual(lifecycle["download_progress"]["phase"], "downloading")
        self.assertEqual(poll["download_progress"]["phase"], "downloading")

        self._save_progress("transition-seq", phase="completed", percent=100.0)
        lifecycle, poll = self._assert_stage_snapshot(
            "transition-seq",
            expected_stage="finalizing",
            expected_label="整理下载结果",
            expected_ready=False,
            confirmation_required=False,
        )
        self.assertIn("整理", lifecycle["primary_message"])
        self.assertEqual(lifecycle["download_progress"]["phase"], "completed")
        self.assertEqual(poll["download_progress"]["phase"], "completed")

        task = self.store.set_step_status(
            task,
            0,
            StepStatus.COMPLETED,
            message="download finished",
            result={"session_dir": str(session_dir)},
        )
        task = self.store.set_task_status(task, TaskStatus.SUCCEEDED, message="task succeeded")
        self._save_result(
            "transition-seq",
            status=TaskStatus.SUCCEEDED,
            message="下载已完成，可以直接打开目录查看视频。",
            session_dir=str(session_dir),
        )

        lifecycle, poll = self._assert_stage_snapshot(
            "transition-seq",
            expected_stage="completed",
            expected_label="下载已完成",
            expected_ready=True,
            confirmation_required=False,
        )
        self.assertEqual(lifecycle["download_entry"]["path"], str(session_dir))
        self.assertEqual(poll["download_entry"]["path"], str(session_dir))
        self.assertIn("打开目录", lifecycle["primary_message"])

    def test_workspace_stage_transition_sequence_to_failure(self) -> None:
        task = self._create_task(
            task_id="transition-fail",
            task_status=TaskStatus.RUNNING,
            step_status=StepStatus.RUNNING,
        )

        lifecycle, poll = self._assert_stage_snapshot(
            "transition-fail",
            expected_stage="preparing_download",
            expected_label="准备下载中",
            expected_ready=False,
            confirmation_required=False,
        )
        self.assertIn("准备下载", lifecycle["primary_message"])
        self.assertIn("准备下载", poll["primary_message"])

        task = self.store.set_step_status(
            task,
            0,
            StepStatus.FAILED,
            message="download step failed",
        )
        task = self.store.set_task_status(task, TaskStatus.FAILED, message="task failed")
        self._save_result(
            "transition-fail",
            status=TaskStatus.FAILED,
            message="download failed",
        )

        lifecycle, poll = self._assert_stage_snapshot(
            "transition-fail",
            expected_stage="failed",
            expected_label="任务失败",
            expected_ready=False,
            confirmation_required=False,
        )
        self.assertTrue(lifecycle["primary_message"])
        self.assertTrue(poll["primary_message"])
        self.assertIsNotNone(lifecycle.get("failure"))
        self.assertIsNotNone(poll.get("failure"))
        self.assertFalse(lifecycle.get("confirmation"))
        self.assertFalse(poll.get("confirmation"))


if __name__ == "__main__":
    unittest.main()
