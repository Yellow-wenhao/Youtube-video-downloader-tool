from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent.session_store import SessionStore
from app.core.models import StepStatus, TaskResult, TaskSpec, TaskStatus, TaskStep
from app.core.task_service import TaskStore
from app.tools.schemas import CheckRuntimeEnvInput
from app.tools.status_tools import check_runtime_env
from app.web.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DownloadWorkspaceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)
        self.download_dir = self.workdir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.store = TaskStore(self.workdir)
        self.client = TestClient(app)

    def _create_source_task(self, *, task_id: str = "source-task") -> TaskSpec:
        task = TaskSpec(
            task_id=task_id,
            title="Source Task",
            user_request="download reviewed videos",
            intent="search_pipeline",
            workdir=str(self.workdir),
            created_at=_now(),
            updated_at=_now(),
            status=TaskStatus.SUCCEEDED,
            params={
                "binary": "legacy-binary",
                "download_dir": str(self.workdir / "legacy-downloads"),
                "concurrent_videos": 9,
                "include_audio": False,
            },
            steps=[
                TaskStep(
                    step_id="filter",
                    title="筛选视频",
                    tool_name="filter_videos",
                    status=StepStatus.COMPLETED,
                )
            ],
            current_step_index=1,
            needs_confirmation=False,
        )
        self.store.save_task(task)
        return task

    def _write_selected_candidates(self) -> None:
        rows = [
            {
                "video_id": "vid-a",
                "title": "Alpha",
                "watch_url": "https://www.youtube.com/watch?v=vid-a",
                "selected": True,
            },
            {
                "video_id": "vid-b",
                "title": "Beta",
                "watch_url": "https://www.youtube.com/watch?v=vid-b",
                "selected": False,
            },
        ]
        with (self.workdir / "03_scored_candidates.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_report(self, session_dir: Path, rows: list[dict[str, str]]) -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        videos_dir = session_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        report_path = session_dir / "07_download_report.csv"
        with report_path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["视频id", "视频原标题", "视频在YouTube上传的时间", "视频url", "视频是否下载成功"],
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_results_api_returns_empty_panel_state_when_no_sessions_exist(self) -> None:
        SessionStore(self.workdir).update_defaults({"download_dir": str(self.download_dir)})

        response = self.client.get("/api/results", params={"workdir": str(self.workdir)})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["total_sessions"], 0)
        self.assertEqual(payload["total_videos"], 0)
        self.assertEqual(payload["sessions"], [])
        self.assertTrue(payload["empty_message"])
        self.assertEqual(payload["panel_state"]["state"], "empty")
        self.assertEqual(payload["panel_state"]["tone"], "neutral")
        self.assertEqual(payload["panel_state"]["title"], "这里还没有已下载视频")
        self.assertEqual(payload["panel_state"]["action"], "focus-run")

    def test_download_selected_creates_task_with_shared_download_payload(self) -> None:
        source_task = self._create_source_task()
        self._write_selected_candidates()
        SessionStore(self.workdir).update_defaults(
            {
                "download_dir": str(self.download_dir),
                "binary": "yt-dlp-custom",
                "concurrent_videos": 3,
                "concurrent_fragments": 6,
                "include_audio": True,
            }
        )

        with patch("app.web.main._run_task_in_background") as run_background:
            response = self.client.post(
                "/api/tasks/source-task/download-selected",
                params={"workdir": str(self.workdir)},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        run_background.assert_called_once_with(str(self.workdir), payload["task_id"], auto_confirm=True)
        self.assertEqual(payload["source_task_id"], source_task.task_id)
        self.assertEqual(payload["status"], "planned")
        self.assertIn("准备下载 1 条已勾选视频", payload["message"])

        created_task = self.store.load_task(payload["task_id"])
        self.assertEqual(created_task.intent, "download_selected_reviewed_videos")
        self.assertEqual(created_task.status, TaskStatus.PLANNED)
        self.assertEqual(created_task.steps[0].tool_name, "start_download")
        step_payload = created_task.steps[0].payload
        self.assertEqual(step_payload["workdir"], str(self.workdir))
        self.assertEqual(step_payload["download_dir"], str(self.download_dir))
        self.assertEqual(step_payload["items_path"], str(self.workdir / "03_scored_candidates.jsonl"))
        self.assertEqual(step_payload["binary"], "yt-dlp-custom")
        self.assertEqual(step_payload["concurrent_videos"], 3)
        self.assertEqual(step_payload["concurrent_fragments"], 6)
        self.assertTrue(step_payload["include_audio"])

    def test_download_selected_rejects_task_already_waiting_for_confirmation(self) -> None:
        task = self._create_source_task()
        task.status = TaskStatus.AWAITING_CONFIRMATION
        task.needs_confirmation = True
        task.steps[0].requires_confirmation = True
        task.steps[0].status = StepStatus.AWAITING_CONFIRMATION
        self.store.save_task(task)
        self._write_selected_candidates()

        with patch("app.web.main._run_task_in_background") as run_background:
            response = self.client.post(
                "/api/tasks/source-task/download-selected",
                params={"workdir": str(self.workdir)},
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("等待下载确认", response.text)
        run_background.assert_not_called()

    def test_download_selected_rejects_running_task_before_selection_finishes(self) -> None:
        task = self._create_source_task()
        task.status = TaskStatus.RUNNING
        task.steps[0].status = StepStatus.RUNNING
        self.store.save_task(task)
        self._write_selected_candidates()

        with patch("app.web.main._run_task_in_background") as run_background:
            response = self.client.post(
                "/api/tasks/source-task/download-selected",
                params={"workdir": str(self.workdir)},
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("仍在运行中", response.text)
        run_background.assert_not_called()

    def test_download_selected_rejects_when_no_selected_items_exist(self) -> None:
        self._create_source_task()
        with (self.workdir / "03_scored_candidates.jsonl").open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {
                    "video_id": "vid-a",
                    "title": "Alpha",
                    "watch_url": "https://www.youtube.com/watch?v=vid-a",
                    "selected": False,
                },
                ensure_ascii=False,
            ) + "\n")

        with patch("app.web.main._run_task_in_background") as run_background:
            response = self.client.post(
                "/api/tasks/source-task/download-selected",
                params={"workdir": str(self.workdir)},
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("没有已勾选的视频", response.text)
        run_background.assert_not_called()

    def test_results_api_groups_sessions_from_shared_workspace_service(self) -> None:
        SessionStore(self.workdir).update_defaults({"download_dir": str(self.download_dir)})
        older_session = self.download_dir / "20250101_010101_alpha"
        newer_session = self.download_dir / "20250102_020202_beta"
        linked_task = self.store.create_task(
            title="下载已勾选视频 · Source Task",
            user_request="download reviewed videos",
            intent="download_selected_reviewed_videos",
            params={},
            steps=[
                TaskStep(
                    step_id="download",
                    title="下载已勾选视频",
                    tool_name="start_download",
                    status=StepStatus.COMPLETED,
                    result={"session_dir": str(newer_session)},
                )
            ],
        )
        linked_task.status = TaskStatus.SUCCEEDED
        self.store.save_task(linked_task)
        self.store.save_result(
            TaskResult(
                task_id=linked_task.task_id,
                status=TaskStatus.SUCCEEDED,
                message="done",
                data={
                    "step_results": {
                        "download": {
                            "session_dir": str(newer_session),
                        }
                    }
                },
                started_at=_now(),
                finished_at=_now(),
            )
        )

        self._write_report(
            older_session,
            [
                {
                    "视频id": "vid-old",
                    "视频原标题": "Older Video",
                    "视频在YouTube上传的时间": "20240101",
                    "视频url": "https://www.youtube.com/watch?v=vid-old",
                    "视频是否下载成功": "是",
                }
            ],
        )
        old_media = older_session / "videos" / "Older Video [vid-old].mp4"
        old_media.write_bytes(b"old")

        self._write_report(
            newer_session,
            [
                {
                    "视频id": "vid-new",
                    "视频原标题": "New Video",
                    "视频在YouTube上传的时间": "20240202",
                    "视频url": "https://www.youtube.com/watch?v=vid-new",
                    "视频是否下载成功": "是",
                },
                {
                    "视频id": "vid-fail",
                    "视频原标题": "Failed Video",
                    "视频在YouTube上传的时间": "20240203",
                    "视频url": "https://www.youtube.com/watch?v=vid-fail",
                    "视频是否下载成功": "否",
                },
            ],
        )
        new_media = newer_session / "videos" / "New Video [vid-new].mp4"
        new_media.write_bytes(b"newer-file")
        (newer_session / "06_failed_urls.txt").write_text(
            "https://www.youtube.com/watch?v=vid-fail\n",
            encoding="utf-8",
        )

        old_ts = datetime(2025, 1, 1, 1, 1, 1, tzinfo=timezone.utc).timestamp()
        new_ts = datetime(2025, 1, 2, 2, 2, 2, tzinfo=timezone.utc).timestamp()
        os.utime(older_session, (old_ts, old_ts))
        os.utime(newer_session, (new_ts, new_ts))

        response = self.client.get("/api/results", params={"workdir": str(self.workdir)})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["available"])
        self.assertEqual(payload["total_sessions"], 2)
        self.assertEqual(payload["total_videos"], 3)
        self.assertEqual(payload["sessions"][0]["session_name"], newer_session.name)
        self.assertIsNone(payload["panel_state"])
        self.assertEqual(payload["sessions"][0]["success_count"], 1)
        self.assertEqual(payload["sessions"][0]["failed_count"], 1)
        self.assertEqual(payload["sessions"][0]["video_count"], 2)
        self.assertTrue(payload["sessions"][0]["retry_available"])
        self.assertEqual(payload["sessions"][0]["failed_urls_file"], str(newer_session / "06_failed_urls.txt"))
        self.assertEqual(payload["sessions"][0]["source_task_id"], linked_task.task_id)
        self.assertEqual(payload["sessions"][0]["source_task_title"], linked_task.title)
        self.assertEqual(payload["sessions"][0]["source_task_status"], TaskStatus.SUCCEEDED.value)
        self.assertTrue(payload["sessions"][0]["source_task_available"])
        self.assertEqual(payload["sessions"][0]["source_task_user_request"], linked_task.user_request)
        self.assertEqual(payload["sessions"][0]["source_task_intent"], linked_task.intent)
        self.assertEqual(payload["sessions"][0]["items"][0]["file_path"], str(new_media))
        self.assertEqual(payload["sessions"][0]["items"][1]["success"], False)
        self.assertEqual(payload["sessions"][1]["items"][0]["file_path"], str(old_media))
        self.assertEqual(payload["sessions"][1]["video_count"], 1)
        self.assertEqual(payload["sessions"][1]["success_count"], 1)
        self.assertEqual(payload["sessions"][1]["failed_count"], 0)
        self.assertFalse(payload["sessions"][1]["retry_available"])

    def test_retry_session_api_creates_retry_task_from_session_failed_urls(self) -> None:
        SessionStore(self.workdir).update_defaults(
            {
                "download_dir": str(self.download_dir),
                "binary": "yt-dlp-custom",
                "concurrent_videos": 2,
                "concurrent_fragments": 5,
            }
        )
        session_dir = self.download_dir / "20250103_030303_retry-source"
        self._write_report(
            session_dir,
            [
                {
                    "视频id": "vid-fail",
                    "视频原标题": "Failed Video",
                    "视频在YouTube上传的时间": "20240203",
                    "视频url": "https://www.youtube.com/watch?v=vid-fail",
                    "视频是否下载成功": "否",
                }
            ],
        )
        failed_urls_path = session_dir / "06_failed_urls.txt"
        failed_urls_path.write_text("https://www.youtube.com/watch?v=vid-fail\n", encoding="utf-8")

        with patch("app.web.main._run_task_in_background") as run_background:
            response = self.client.post(
                "/api/results/retry-session",
                json={"workdir": str(self.workdir), "session_dir": str(session_dir)},
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        run_background.assert_called_once()

        created_task = self.store.load_task(payload["task_id"])
        self.assertEqual(created_task.intent, "retry_failed_downloads")
        self.assertEqual(created_task.steps[0].tool_name, "retry_failed_downloads")
        step_payload = created_task.steps[0].payload
        self.assertEqual(step_payload["workdir"], str(self.workdir))
        self.assertEqual(step_payload["download_dir"], str(self.download_dir))
        self.assertEqual(Path(step_payload["failed_urls_file"]).resolve(), failed_urls_path.resolve())
        self.assertEqual(step_payload["binary"], "yt-dlp-custom")
        self.assertEqual(step_payload["concurrent_videos"], 2)
        self.assertEqual(step_payload["concurrent_fragments"], 5)

    def test_retry_session_api_rejects_session_without_retry_file(self) -> None:
        SessionStore(self.workdir).update_defaults({"download_dir": str(self.download_dir)})
        session_dir = self.download_dir / "20250104_040404_no-retry"
        self._write_report(
            session_dir,
            [
                {
                    "视频id": "vid-fail",
                    "视频原标题": "Failed Video",
                    "视频在YouTube上传的时间": "20240203",
                    "视频url": "https://www.youtube.com/watch?v=vid-fail",
                    "视频是否下载成功": "否",
                }
            ],
        )

        response = self.client.post(
            "/api/results/retry-session",
            json={"workdir": str(self.workdir), "session_dir": str(session_dir)},
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("失败 URL", response.text)

    @patch("app.core.environment_service.shutil.which")
    def test_runtime_env_check_uses_shared_environment_service(self, which_mock) -> None:
        which_mock.side_effect = lambda binary: {
            "yt-dlp": "C:/tools/yt-dlp.exe",
            "ffmpeg": "",
        }.get(binary, "")

        output = check_runtime_env(CheckRuntimeEnvInput(yt_dlp_binary="yt-dlp", ffmpeg_binary="ffmpeg"))

        self.assertTrue(output.yt_dlp_found)
        self.assertFalse(output.ffmpeg_found)
        self.assertEqual(output.yt_dlp_binary, "yt-dlp")
        self.assertEqual(output.ffmpeg_binary, "ffmpeg")


if __name__ == "__main__":
    unittest.main()
