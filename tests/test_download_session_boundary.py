from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.session_store import SessionStore
from app.core.download_workspace_service import (
    SESSION_METADATA_FILENAME,
    load_download_results,
    persist_download_session_ref,
    resolve_download_session_pointers,
    resolve_retry_failed_urls_file,
)
from app.core.models import DownloadSessionRef, StepStatus, TaskResult, TaskStatus, TaskStep
from app.core.task_service import TaskStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DownloadSessionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path("D:/YTBDLP/build/test_download_session_boundary") / uuid.uuid4().hex
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.download_dir = self.workdir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.workdir, True)

    def test_session_store_persists_last_download_session_ref(self) -> None:
        store = SessionStore(self.workdir)
        ref = DownloadSessionRef(
            session_dir=str(self.workdir / "downloads" / "session-a"),
            report_csv=str(self.workdir / "downloads" / "session-a" / "07_download_report.csv"),
            failed_urls_file=str(self.workdir / "06_failed_urls.txt"),
            source_task_id="task-123",
            updated_at=_now(),
        )

        store.set_last_download_session(ref)
        loaded = store.get_last_download_session()

        self.assertEqual(loaded, ref)

    def test_persist_and_resolve_download_session_ref_uses_session_store(self) -> None:
        session_dir = self.workdir / "downloads" / "session-b"
        report_csv = session_dir / "07_download_report.csv"
        failed_urls_file = self.workdir / "06_failed_urls.txt"
        session_dir.mkdir(parents=True, exist_ok=True)
        report_csv.write_text("header\n", encoding="utf-8")
        failed_urls_file.write_text("https://example.com/video\n", encoding="utf-8")

        ref = persist_download_session_ref(
            self.workdir,
            DownloadSessionRef(
                session_dir=str(session_dir),
                report_csv=str(report_csv),
                failed_urls_file=str(failed_urls_file),
                source_task_id="task-456",
            ),
        )

        resolved = resolve_download_session_pointers(self.workdir)

        self.assertEqual(resolved.session_dir, str(session_dir))
        self.assertEqual(resolved.report_csv, str(report_csv))
        self.assertEqual(resolved.failed_urls_file, str(failed_urls_file))
        self.assertEqual(resolved.source_task_id, "task-456")
        self.assertTrue(ref.updated_at)
        self.assertEqual(SessionStore(self.workdir).get_last_download_session().session_dir, str(session_dir))
        self.assertTrue((session_dir / SESSION_METADATA_FILENAME).exists())

    def test_task_store_extracts_download_session_ref_from_result(self) -> None:
        store = TaskStore(self.workdir)
        task = store.create_task(
            title="Download Task",
            user_request="download files",
            intent="download",
            params={},
            steps=[],
        )
        session_dir = self.workdir / "downloads" / "session-c"
        report_csv = session_dir / "07_download_report.csv"
        failed_urls_file = self.workdir / "06_failed_urls.txt"
        store.save_result(
            TaskResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                message="done",
                data={
                    "step_results": {
                        "download": {
                            "session_dir": str(session_dir),
                            "report_csv": str(report_csv),
                            "failed_urls_file": str(failed_urls_file),
                        }
                    }
                },
                started_at=_now(),
                finished_at=_now(),
            )
        )

        ref = store.load_download_session_ref(task.task_id)

        self.assertEqual(ref.session_dir, str(session_dir))
        self.assertEqual(ref.report_csv, str(report_csv))
        self.assertEqual(ref.failed_urls_file, str(failed_urls_file))

    def test_download_results_retry_metadata_prefers_session_local_failed_urls(self) -> None:
        session_dir = self.workdir / "downloads" / "session-retry"
        videos_dir = session_dir / "videos"
        report_csv = session_dir / "07_download_report.csv"
        failed_urls_file = session_dir / "06_failed_urls.txt"
        videos_dir.mkdir(parents=True, exist_ok=True)
        report_csv.write_text(
            "\ufeff视频id,视频原标题,视频在YouTube上传的时间,视频url,视频是否下载成功\n"
            "vid-ok,Alpha,20240101,https://www.youtube.com/watch?v=vid-ok,是\n"
            "vid-fail,Beta,20240102,https://www.youtube.com/watch?v=vid-fail,否\n",
            encoding="utf-8-sig",
        )
        failed_urls_file.write_text("https://www.youtube.com/watch?v=vid-fail\n", encoding="utf-8")

        snapshot = load_download_results(self.workdir, params={"download_dir": self.download_dir})

        self.assertTrue(snapshot.available)
        self.assertEqual(snapshot.sessions[0].session_dir, str(session_dir))
        self.assertEqual(snapshot.sessions[0].failed_urls_file, str(failed_urls_file))
        self.assertTrue(snapshot.sessions[0].retry_available)
        self.assertEqual(
            resolve_retry_failed_urls_file(
                self.workdir,
                session_dir,
                params={"download_dir": self.download_dir},
            ),
            str(failed_urls_file),
        )

    def test_download_results_link_sessions_back_to_task_store_when_metadata_missing(self) -> None:
        session_dir = self.workdir / "downloads" / "session-task-link"
        videos_dir = session_dir / "videos"
        report_csv = session_dir / "07_download_report.csv"
        videos_dir.mkdir(parents=True, exist_ok=True)
        report_csv.write_text(
            "\ufeff视频id,视频原标题,视频在YouTube上传的时间,视频url,视频是否下载成功\n"
            "vid-ok,Alpha,20240101,https://www.youtube.com/watch?v=vid-ok,是\n",
            encoding="utf-8-sig",
        )
        task_store = TaskStore(self.workdir)
        task = task_store.create_task(
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
                    result={"session_dir": str(session_dir), "report_csv": str(report_csv)},
                )
            ],
        )
        task.status = TaskStatus.SUCCEEDED
        task_store.save_task(task)
        task_store.save_result(
            TaskResult(
                task_id=task.task_id,
                status=TaskStatus.SUCCEEDED,
                message="done",
                data={
                    "step_results": {
                        "download": {
                            "session_dir": str(session_dir),
                            "report_csv": str(report_csv),
                        }
                    }
                },
                started_at=_now(),
                finished_at=_now(),
            )
        )

        snapshot = load_download_results(self.workdir, params={"download_dir": self.download_dir})

        self.assertEqual(snapshot.sessions[0].source_task_id, task.task_id)
        self.assertEqual(snapshot.sessions[0].source_task_title, task.title)
        self.assertEqual(snapshot.sessions[0].source_task_status, TaskStatus.SUCCEEDED.value)
        self.assertTrue(snapshot.sessions[0].source_task_available)


if __name__ == "__main__":
    unittest.main()
