from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.langgraph_runtime import GraphCheckpointStore, LangGraphAgentRuntime
from app.agent.planner import PlanDraft
from app.agent.runner import AgentRunner
from app.agent.session_store import SessionStore
from app.core.download_workspace_service import persist_download_session_ref
from app.core.models import DownloadSessionRef, StepStatus, TaskSpec, TaskStatus, TaskStep
from app.core.task_service import TaskStore
from app.tools.registry import ToolRegistry, create_default_registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Planner:
    planner_name = "test_planner"

    def __init__(self, draft: PlanDraft) -> None:
        self.draft = draft

    def build_plan(self, user_request: str, workdir: str | Path, defaults: dict | None = None) -> PlanDraft:
        return self.draft


class LangGraphRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)

    def _runtime(self, draft: PlanDraft, handlers: dict[str, object]) -> LangGraphAgentRuntime:
        registry = ToolRegistry()
        for name, handler in handlers.items():
            registry.register(name, name, dict, handler)
        return LangGraphAgentRuntime(registry, _Planner(draft))

    def _runner(self, draft: PlanDraft, handlers: dict[str, object]) -> AgentRunner:
        registry = ToolRegistry()
        for name, handler in handlers.items():
            registry.register(name, name, dict, handler)
        return AgentRunner(registry=registry, planner=_Planner(draft))

    def _default_runner(self) -> AgentRunner:
        return AgentRunner(
            registry=create_default_registry(),
            planner=_Planner(PlanDraft(title="unused", intent="unused", params={}, steps=[])),
        )

    def test_run_executes_steps_and_returns_success_payload(self) -> None:
        draft = PlanDraft(
            title="demo",
            intent="search_pipeline",
            params={"search_limit": 3},
            steps=[
                TaskStep(step_id="step1", title="one", tool_name="step1", payload={"value": "alpha"}),
                TaskStep(step_id="step2", title="two", tool_name="step2", payload={"from_prev": "{{steps.step1.value}}"}),
            ],
        )
        runtime = self._runtime(
            draft,
            {
                "step1": lambda payload: {"value": payload["value"]},
                "step2": lambda payload: {"echo": payload["from_prev"]},
            },
        )

        result = runtime.run("demo request", self.workdir, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.data["step_results"]["step1"]["value"], "alpha")
        self.assertEqual(result.data["step_results"]["step2"]["echo"], "alpha")
        self.assertIn("task_paths", result.data)

    def test_run_stops_at_confirmation_gate_for_sensitive_tool(self) -> None:
        draft = PlanDraft(
            title="download",
            intent="download",
            params={},
            steps=[
                TaskStep(
                    step_id="download",
                    title="download",
                    tool_name="start_download",
                    payload={"download_dir": str(self.workdir / "downloads")},
                )
            ],
        )
        runtime = self._runtime(
            draft,
            {"start_download": lambda payload: {"should_not_run": True}},
        )

        result = runtime.run("download", self.workdir, auto_confirm=False)

        self.assertEqual(result.status, TaskStatus.AWAITING_CONFIRMATION)
        self.assertEqual(result.data["pending_step"], "download")
        self.assertIn("task_paths", result.data)

    def test_payload_resolution_failure_is_mapped_to_payload_resolution(self) -> None:
        draft = PlanDraft(
            title="broken",
            intent="broken",
            params={},
            steps=[
                TaskStep(step_id="step1", title="broken", tool_name="step1", payload={"value": "{{steps.missing.value}}"}),
            ],
        )
        runtime = self._runtime(draft, {"step1": lambda payload: payload})

        result = runtime.run("broken", self.workdir, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.data["failure_origin"], "payload_resolution")
        self.assertEqual(result.data["failed_step"], "step1")

    def test_tool_failure_is_mapped_to_tool_execution(self) -> None:
        draft = PlanDraft(
            title="broken",
            intent="broken",
            params={},
            steps=[TaskStep(step_id="step1", title="broken", tool_name="step1", payload={"value": "x"})],
        )

        def _boom(payload):
            raise RuntimeError("tool failed")

        runtime = self._runtime(draft, {"step1": _boom})

        result = runtime.run("broken", self.workdir, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.data["failure_origin"], "tool_execution")
        self.assertEqual(result.data["error_type"], "RuntimeError")
        self.assertEqual(result.data["resolved_payload"]["value"], "x")

    def test_resume_rehydrates_completed_step_results(self) -> None:
        store = TaskStore(self.workdir)
        task = TaskSpec(
            task_id="resume-task",
            title="resume",
            user_request="resume request",
            intent="resume_intent",
            workdir=str(self.workdir),
            created_at=_now(),
            updated_at=_now(),
            status=TaskStatus.RUNNING,
            params={},
            steps=[
                TaskStep(
                    step_id="step1",
                    title="one",
                    tool_name="step1",
                    status=StepStatus.COMPLETED,
                    result={"value": "alpha"},
                ),
                TaskStep(
                    step_id="step2",
                    title="two",
                    tool_name="step2",
                    payload={"from_prev": "{{steps.step1.value}}"},
                    status=StepStatus.PENDING,
                ),
            ],
        )
        store.save_task(task)
        runtime = self._runtime(
            PlanDraft(title="unused", intent="unused", params={}, steps=[]),
            {"step2": lambda payload: {"echo": payload["from_prev"]}},
        )

        result = runtime.resume(self.workdir, task_id=task.task_id, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.data["step_results"]["step2"]["echo"], "alpha")

    def test_resume_works_without_graph_checkpoint(self) -> None:
        draft = PlanDraft(
            title="plan",
            intent="intent",
            params={},
            steps=[TaskStep(step_id="step1", title="one", tool_name="step1", payload={"value": "ok"})],
        )
        runtime = self._runtime(draft, {"step1": lambda payload: {"value": payload["value"]}})

        task = runtime.plan("plan only", self.workdir)
        GraphCheckpointStore(self.workdir).delete(task.task_id)

        result = runtime.resume(self.workdir, task_id=task.task_id, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.data["step_results"]["step1"]["value"], "ok")

    def test_resume_works_with_valid_graph_checkpoint_present(self) -> None:
        draft = PlanDraft(
            title="plan",
            intent="intent",
            params={},
            steps=[TaskStep(step_id="step1", title="one", tool_name="step1", payload={"value": "ok"})],
        )
        runtime = self._runtime(
            draft,
            {"step1": lambda payload: {"value": payload["value"]}},
        )

        task = runtime.plan("plan only", self.workdir)
        task_id = task.task_id
        checkpoint = GraphCheckpointStore(self.workdir).load(task_id)

        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        node_name, checkpoint_state = checkpoint
        self.assertTrue(node_name)
        self.assertEqual(checkpoint_state["task_id"], task_id)

        resumed = runtime.resume(self.workdir, task_id=task_id, auto_confirm=True)

        self.assertEqual(resumed.status, TaskStatus.SUCCEEDED)
        self.assertEqual(resumed.data["step_results"]["step1"]["value"], "ok")

    def test_plan_then_resume_confirmation_then_complete_persists_taskstore_state(self) -> None:
        session_dir = self.workdir / "downloads" / "session-001"
        draft = PlanDraft(
            title="download reviewed videos",
            intent="download_selected_reviewed_videos",
            params={"download_dir": str(self.workdir / "downloads")},
            steps=[
                TaskStep(
                    step_id="prepare",
                    title="prepare inputs",
                    tool_name="prepare",
                    payload={"query": "alpha"},
                ),
                TaskStep(
                    step_id="download",
                    title="download items",
                    tool_name="start_download",
                    payload={
                        "items": "{{steps.prepare.items}}",
                        "download_dir": str(self.workdir / "downloads"),
                    },
                ),
            ],
        )
        runner = self._runner(
            draft,
            {
                "prepare": lambda payload: {"items": [payload["query"], "beta"]},
                "start_download": lambda payload: {"session_dir": str(session_dir), "count": len(payload["items"])},
            },
        )
        store = TaskStore(self.workdir)
        session = SessionStore(self.workdir)

        planned_task = runner.plan("download alpha videos", self.workdir)

        self.assertEqual(planned_task.status, TaskStatus.PLANNED)
        self.assertEqual(session.get_last_task_id(), planned_task.task_id)
        loaded_task = store.load_task(planned_task.task_id)
        self.assertEqual(loaded_task.status, TaskStatus.PLANNED)
        self.assertEqual([step.status for step in loaded_task.steps], [StepStatus.PENDING, StepStatus.PENDING])
        self.assertTrue(Path(store.task_paths(planned_task.task_id)["spec"]).exists())
        self.assertTrue(Path(store.task_paths(planned_task.task_id)["summary"]).exists())
        self.assertIsNone(store.load_result(planned_task.task_id))

        confirmation = runner.resume(self.workdir, task_id=planned_task.task_id, auto_confirm=False)

        self.assertEqual(confirmation.status, TaskStatus.AWAITING_CONFIRMATION)
        self.assertEqual(confirmation.data["pending_step"], "download")
        confirmed_task = store.load_task(planned_task.task_id)
        self.assertEqual(confirmed_task.status, TaskStatus.AWAITING_CONFIRMATION)
        self.assertEqual(confirmed_task.steps[0].status, StepStatus.COMPLETED)
        self.assertEqual(confirmed_task.steps[0].result["items"], ["alpha", "beta"])
        self.assertEqual(confirmed_task.steps[1].status, StepStatus.AWAITING_CONFIRMATION)
        confirmation_result = store.load_result(planned_task.task_id)
        self.assertIsNotNone(confirmation_result)
        assert confirmation_result is not None
        self.assertEqual(confirmation_result.status, TaskStatus.AWAITING_CONFIRMATION)
        self.assertTrue(Path(store.task_paths(planned_task.task_id)["result"]).exists())

        completed = runner.resume(self.workdir, task_id=planned_task.task_id, auto_confirm=True)

        self.assertEqual(completed.status, TaskStatus.SUCCEEDED)
        self.assertEqual(completed.data["step_results"]["prepare"]["items"], ["alpha", "beta"])
        self.assertEqual(completed.data["step_results"]["download"]["count"], 2)
        final_task = store.load_task(planned_task.task_id)
        final_summary = store.load_summary(planned_task.task_id)
        final_result = store.load_result(planned_task.task_id)
        events = store.load_events(planned_task.task_id)
        self.assertEqual(final_task.status, TaskStatus.SUCCEEDED)
        self.assertEqual([step.status for step in final_task.steps], [StepStatus.COMPLETED, StepStatus.COMPLETED])
        self.assertIsNotNone(final_summary)
        assert final_summary is not None
        self.assertEqual(final_summary.status, TaskStatus.SUCCEEDED)
        self.assertIsNotNone(final_result)
        assert final_result is not None
        self.assertEqual(final_result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(session.get_last_task_id(), planned_task.task_id)
        self.assertIn("task_created", [event.event_type for event in events])
        self.assertIn("task_status", [event.event_type for event in events])
        self.assertGreaterEqual(len([event for event in events if event.event_type == "step_status"]), 4)
        task_paths = store.task_paths(planned_task.task_id)
        self.assertTrue(Path(task_paths["events"]).exists())
        self.assertTrue(Path(task_paths["result"]).exists())
        self.assertTrue(GraphCheckpointStore(self.workdir).checkpoint_path(planned_task.task_id).exists())

    def test_run_then_resume_confirm_complete_round_trip(self) -> None:
        draft = PlanDraft(
            title="download flow",
            intent="download_selected_reviewed_videos",
            params={},
            steps=[
                TaskStep(
                    step_id="prepare",
                    title="prepare",
                    tool_name="prepare",
                    payload={"query": "gamma"},
                ),
                TaskStep(
                    step_id="download",
                    title="download",
                    tool_name="start_download",
                    payload={"items": "{{steps.prepare.items}}"},
                ),
            ],
        )
        runner = self._runner(
            draft,
            {
                "prepare": lambda payload: {"items": [payload["query"]]},
                "start_download": lambda payload: {"downloaded": payload["items"]},
            },
        )
        store = TaskStore(self.workdir)

        result = runner.run("download gamma", self.workdir, auto_confirm=False)

        self.assertEqual(result.status, TaskStatus.AWAITING_CONFIRMATION)
        task_id = result.task_id
        paused_task = store.load_task(task_id)
        self.assertEqual(paused_task.steps[0].status, StepStatus.COMPLETED)
        self.assertEqual(paused_task.steps[1].status, StepStatus.AWAITING_CONFIRMATION)
        self.assertEqual(result.data["task"]["status"], TaskStatus.AWAITING_CONFIRMATION.value)

        resumed = runner.resume(self.workdir, task_id=task_id, auto_confirm=True)

        self.assertEqual(resumed.status, TaskStatus.SUCCEEDED)
        self.assertEqual(resumed.data["step_results"]["prepare"]["items"], ["gamma"])
        self.assertEqual(resumed.data["step_results"]["download"]["downloaded"], ["gamma"])
        finished_task = store.load_task(task_id)
        self.assertEqual(finished_task.status, TaskStatus.SUCCEEDED)
        self.assertEqual(finished_task.steps[1].status, StepStatus.COMPLETED)

    def test_resume_falls_back_to_taskstore_when_checkpoint_is_corrupted(self) -> None:
        draft = PlanDraft(
            title="download flow",
            intent="download_selected_reviewed_videos",
            params={},
            steps=[
                TaskStep(
                    step_id="prepare",
                    title="prepare",
                    tool_name="prepare",
                    payload={"query": "delta"},
                ),
                TaskStep(
                    step_id="download",
                    title="download",
                    tool_name="start_download",
                    payload={"items": "{{steps.prepare.items}}"},
                ),
            ],
        )
        runner = self._runner(
            draft,
            {
                "prepare": lambda payload: {"items": [payload["query"], "delta-2"]},
                "start_download": lambda payload: {"downloaded": payload["items"]},
            },
        )
        store = TaskStore(self.workdir)

        paused = runner.run("download delta", self.workdir, auto_confirm=False)
        self.assertEqual(paused.status, TaskStatus.AWAITING_CONFIRMATION)
        checkpoint_path = GraphCheckpointStore(self.workdir).checkpoint_path(paused.task_id)
        checkpoint_path.write_text("{not-valid-json", encoding="utf-8")

        resumed = runner.resume(self.workdir, task_id=paused.task_id, auto_confirm=True)

        self.assertEqual(resumed.status, TaskStatus.SUCCEEDED)
        self.assertEqual(resumed.data["step_results"]["prepare"]["items"], ["delta", "delta-2"])
        self.assertEqual(resumed.data["step_results"]["download"]["downloaded"], ["delta", "delta-2"])
        final_task = store.load_task(paused.task_id)
        self.assertEqual(final_task.status, TaskStatus.SUCCEEDED)

    @patch("app.tools.download_tools.download_selected")
    def test_langgraph_start_download_persists_logs_and_progress(self, download_selected_mock) -> None:
        store = TaskStore(self.workdir)
        runner = self._default_runner()
        items_path = self.workdir / "03_scored_candidates.jsonl"
        items_path.write_text(
            '{"selected": true, "watch_url": "https://www.youtube.com/watch?v=a1", "title": "Alpha", "video_id": "a1"}\n',
            encoding="utf-8",
        )
        session_dir = self.workdir / "downloads" / "session-start"
        report_csv = session_dir / "07_download_report.csv"

        def _fake_download_selected(**kwargs) -> None:
            kwargs["on_log"]("download started", "stdout", {"phase": "queued"})
            kwargs["on_progress"](
                {
                    "phase": "downloading",
                    "percent": 42.5,
                    "downloaded_bytes": 425,
                    "total_bytes": 1000,
                    "speed_text": "1.2MiB/s",
                    "current_video_id": "a1",
                    "current_video_label": "Alpha",
                }
            )
            session_dir.mkdir(parents=True, exist_ok=True)
            report_csv.write_text("ok", encoding="utf-8")
            persist_download_session_ref(
                self.workdir,
                DownloadSessionRef(
                    session_dir=str(session_dir),
                    report_csv=str(report_csv),
                    failed_urls_file="",
                    source_task_id=str(kwargs["task_id"]),
                    updated_at=_now(),
                ),
            )

        download_selected_mock.side_effect = _fake_download_selected
        task = store.create_task(
            title="download",
            user_request="download alpha",
            intent="download_selected_reviewed_videos",
            params={"download_dir": str(self.workdir / "downloads")},
            steps=[
                TaskStep(
                    step_id="download",
                    title="download",
                    tool_name="start_download",
                    payload={
                        "workdir": str(self.workdir),
                        "download_dir": str(self.workdir / "downloads"),
                        "items_path": str(items_path),
                    },
                )
            ],
        )

        result = runner.resume(self.workdir, task_id=task.task_id, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        progress = store.load_download_progress(task.task_id)
        logs = store.load_logs(task.task_id)
        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.phase, "downloading")
        self.assertEqual(progress.current_video_id, "a1")
        self.assertEqual(progress.current_video_label, "Alpha")
        self.assertAlmostEqual(progress.percent, 42.5)
        self.assertTrue(any(log.message == "download started" and log.kind == "stdout" for log in logs))
        self.assertEqual(result.data["step_results"]["download"]["session_dir"], str(session_dir))
        self.assertTrue(Path(store.task_paths(task.task_id)["logs"]).exists())
        self.assertTrue(Path(store.task_paths(task.task_id)["progress"]).exists())

    @patch("app.tools.download_tools.download_selected")
    def test_langgraph_retry_failed_downloads_persists_logs_and_progress(self, download_selected_mock) -> None:
        store = TaskStore(self.workdir)
        runner = self._default_runner()
        failed_urls_file = self.workdir / "06_failed_urls.txt"
        failed_urls_file.write_text("https://www.youtube.com/watch?v=retry-1\n", encoding="utf-8")
        session_dir = self.workdir / "downloads" / "session-retry"
        report_csv = session_dir / "07_download_report.csv"

        def _fake_retry_download(**kwargs) -> None:
            kwargs["on_log"]("retry started", "stdout", {"phase": "retry"})
            kwargs["on_progress"](
                {
                    "phase": "completed",
                    "percent": 100.0,
                    "downloaded_bytes": 2048,
                    "total_bytes": 2048,
                    "speed_text": "done",
                    "current_video_id": "retry-1",
                    "current_video_label": "Retry Video",
                }
            )
            session_dir.mkdir(parents=True, exist_ok=True)
            report_csv.write_text("ok", encoding="utf-8")
            persist_download_session_ref(
                self.workdir,
                DownloadSessionRef(
                    session_dir=str(session_dir),
                    report_csv=str(report_csv),
                    failed_urls_file=str(failed_urls_file),
                    source_task_id=str(kwargs["task_id"]),
                    updated_at=_now(),
                ),
            )

        download_selected_mock.side_effect = _fake_retry_download
        task = store.create_task(
            title="retry",
            user_request="retry failed downloads",
            intent="retry_failed_downloads",
            params={"download_dir": str(self.workdir / "downloads")},
            steps=[
                TaskStep(
                    step_id="retry",
                    title="retry",
                    tool_name="retry_failed_downloads",
                    payload={
                        "workdir": str(self.workdir),
                        "download_dir": str(self.workdir / "downloads"),
                        "failed_urls_file": str(failed_urls_file),
                    },
                )
            ],
        )

        result = runner.resume(self.workdir, task_id=task.task_id, auto_confirm=True)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        progress = store.load_download_progress(task.task_id)
        logs = store.load_logs(task.task_id)
        self.assertIsNotNone(progress)
        assert progress is not None
        self.assertEqual(progress.phase, "completed")
        self.assertEqual(progress.current_video_id, "retry-1")
        self.assertEqual(progress.speed_text, "done")
        self.assertTrue(any(log.message == "retry started" and log.kind == "stdout" for log in logs))
        self.assertEqual(result.data["step_results"]["retry"]["failed_urls_file"], str(failed_urls_file))


if __name__ == "__main__":
    unittest.main()
