from __future__ import annotations

import csv
import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agent.planner import PlanDraft
from app.agent.runner import AgentRunner
from app.agent.session_store import SessionStore
from app.core.download_workspace_service import persist_download_session_ref
from app.core.models import DownloadSessionRef, StepStatus, TaskStep


class _PlannerProbe:
    planner_name = "probe"

    def __init__(self) -> None:
        self.seen_defaults: dict | None = None

    def build_plan(self, user_request: str, workdir: str | Path, defaults: dict | None = None) -> PlanDraft:
        self.seen_defaults = dict(defaults or {})
        return PlanDraft(
            title="Probe Task",
            intent="search_pipeline",
            params={
                "query": "robotics",
                "display_query": "robotics",
                "topic_phrase": "robotics",
                "queries": ["robotics humanoid demo"],
                "search_limit": 42,
                "metadata_workers": 3,
                "min_duration": 180,
                "year_from": 2023,
                "year_to": 2025,
                "download_mode": "video",
                "include_audio": True,
                "full_csv": False,
            },
            steps=[
                TaskStep(
                    step_id="search",
                    title="Search videos",
                    tool_name="search_videos",
                    payload={"queries": ["robotics humanoid demo"], "workdir": str(workdir)},
                    status=StepStatus.PENDING,
                )
            ],
        )


class SessionStorePreferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path("D:/YTBDLP/build/test_session_store_preferences") / uuid.uuid4().hex
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.workdir, True)

    def test_load_normalizes_new_preference_sections_and_legacy_top_level_keys(self) -> None:
        raw = {
            "defaults": {"download_dir": str(self.workdir / "downloads")},
            "last_task_id": "task-001",
            "recent_task_preferences": {"query": "legacy"},
            "recent_result_context": {"task_id": "task-old"},
        }
        path = self.workdir / ".agent" / "session.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

        store = SessionStore(self.workdir)

        self.assertEqual(store.get_recent_task_preferences()["query"], "legacy")
        self.assertEqual(store.get_recent_result_context()["task_id"], "task-old")
        self.assertEqual(store.get_common_filter_preferences(), {})

    def test_runner_plan_passes_memory_context_and_updates_preferences(self) -> None:
        session = SessionStore(self.workdir)
        session.update_recent_result_context({"task_id": "task-prev", "latest_session_name": "20250401_prev"})
        session.update_common_filter_preferences({"search_limit": 18, "min_duration": 90})

        planner = _PlannerProbe()
        runner = AgentRunner(registry=object(), planner=planner)  # type: ignore[arg-type]

        task = runner.plan(
            "找一些机器人演示视频",
            self.workdir,
            defaults={"llm_provider": "openai", "llm_model": "gpt-5.4"},
        )

        self.assertIsNotNone(planner.seen_defaults)
        self.assertEqual(planner.seen_defaults["recent_result_context"]["task_id"], "task-prev")
        self.assertEqual(planner.seen_defaults["common_filter_preferences"]["search_limit"], 18)

        recent_task = session.get_recent_task_preferences()
        filter_prefs = session.get_common_filter_preferences()

        self.assertEqual(recent_task["task_id"], task.task_id)
        self.assertEqual(recent_task["user_request"], "找一些机器人演示视频")
        self.assertEqual(recent_task["llm_provider"], "openai")
        self.assertEqual(recent_task["llm_model"], "gpt-5.4")
        self.assertEqual(filter_prefs["search_limit"], 42)
        self.assertEqual(filter_prefs["min_duration"], 180)
        self.assertEqual(filter_prefs["year_from"], 2023)
        self.assertEqual(filter_prefs["year_to"], 2025)

    def test_persist_download_session_ref_updates_recent_result_context(self) -> None:
        session_dir = self.workdir / "downloads" / "20250416_robotics"
        session_dir.mkdir(parents=True, exist_ok=True)
        report_csv = session_dir / "07_download_report.csv"
        with report_csv.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["视频id", "视频原标题", "视频url", "视频是否下载成功", "视频在YouTube上传的时间"])
            writer.writeheader()
            writer.writerow({"视频id": "vid-a", "视频原标题": "Robot A", "视频url": "https://a", "视频是否下载成功": "是", "视频在YouTube上传的时间": "20240101"})
            writer.writerow({"视频id": "vid-b", "视频原标题": "Robot B", "视频url": "https://b", "视频是否下载成功": "否", "视频在YouTube上传的时间": "20240201"})
        failed_urls = self.workdir / "06_failed_urls.txt"
        failed_urls.write_text("https://b\n", encoding="utf-8")

        persist_download_session_ref(
            self.workdir,
            DownloadSessionRef(
                session_dir=str(session_dir),
                report_csv=str(report_csv),
                failed_urls_file=str(failed_urls),
                source_task_id="task-download-1",
            ),
        )

        recent_result = SessionStore(self.workdir).get_recent_result_context()

        self.assertEqual(recent_result["task_id"], "task-download-1")
        self.assertEqual(recent_result["session_dir"], str(session_dir))
        self.assertEqual(recent_result["latest_session_name"], "20250416_robotics")
        self.assertEqual(recent_result["video_count"], 2)
        self.assertEqual(recent_result["success_count"], 1)
        self.assertEqual(recent_result["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
