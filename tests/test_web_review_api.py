from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.models import StepStatus, TaskSpec, TaskStatus, TaskStep
from app.core.task_service import TaskStore
from app.web.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReviewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workdir = Path(self.tmp.name)
        self.store = TaskStore(self.workdir)
        self.client = TestClient(app)

    def _create_task(self, *, task_id: str = "review-task", status: TaskStatus = TaskStatus.AWAITING_CONFIRMATION) -> TaskSpec:
        task = TaskSpec(
            task_id=task_id,
            title="Review Task",
            user_request="review candidates before download",
            intent="download",
            workdir=str(self.workdir),
            created_at=_now(),
            updated_at=_now(),
            status=status,
            steps=[
                TaskStep(
                    step_id="download",
                    title="下载视频",
                    tool_name="start_download",
                    requires_confirmation=True,
                    status=StepStatus.AWAITING_CONFIRMATION if status == TaskStatus.AWAITING_CONFIRMATION else StepStatus.COMPLETED,
                    message="await review",
                )
            ],
            current_step_index=0,
            needs_confirmation=status == TaskStatus.AWAITING_CONFIRMATION,
        )
        self.store.save_task(task)
        return task

    def _write_candidates(self) -> None:
        rows = [
            {
                "video_id": "vid-a",
                "title": "Alpha",
                "channel": "Channel A",
                "watch_url": "https://www.youtube.com/watch?v=vid-a",
                "upload_date": "20250101",
                "duration": 125,
                "description_preview": "alpha preview",
                "reasons": "语义相似度: 通过 | 自动推荐通过",
                "vector_score": 0.22,
                "vector_threshold": 0.08,
                "selected": True,
                "manual_review": False,
                "score": 18,
            },
            {
                "video_id": "vid-b",
                "title": "Beta",
                "channel": "Channel B",
                "watch_url": "https://www.youtube.com/watch?v=vid-b",
                "upload_date": "20240101",
                "duration": 300,
                "description_preview": "beta preview",
                "reasons": "语义相似度: 偏低 | 当前未加入下载",
                "vector_score": 0.03,
                "vector_threshold": 0.08,
                "selected": False,
                "manual_review": True,
                "score": 2,
            },
        ]
        path = self.workdir / "03_scored_candidates.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _write_fallback_key_candidates(self) -> None:
        rows = [
            {
                "title": "URL keyed item",
                "channel": "Channel U",
                "watch_url": "https://www.youtube.com/watch?v=url-only",
                "selected": False,
                "manual_review": False,
            },
            {
                "title": "Row keyed item",
                "channel": "Channel R",
                "watch_url": "",
                "selected": True,
                "manual_review": False,
            },
        ]
        path = self.workdir / "03_scored_candidates.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_review_endpoint_returns_candidate_cards(self) -> None:
        self._create_task()
        self._write_candidates()

        response = self.client.get("/api/tasks/review-task/review", params={"workdir": str(self.workdir)})

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["available"])
        self.assertTrue(payload["editable"])
        self.assertEqual(payload["summary"]["total_count"], 2)
        self.assertEqual(payload["summary"]["selected_count"], 1)
        self.assertEqual(payload["summary"]["manual_review_count"], 1)
        self.assertEqual(payload["summary"]["low_similarity_count"], 1)
        self.assertEqual(payload["items"][0]["selection_key"], "video:vid-a")
        self.assertEqual(payload["items"][0]["thumbnail_url"], "https://i.ytimg.com/vi/vid-a/hqdefault.jpg")
        self.assertEqual(payload["items"][0]["duration_label"], "2:05")

    def test_review_selection_update_persists_jsonl_and_selected_urls(self) -> None:
        self._create_task()
        self._write_candidates()

        response = self.client.post(
            "/api/tasks/review-task/review-selection",
            json={"workdir": str(self.workdir), "selected_keys": ["video:vid-b"]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["summary"]["selected_count"], 1)
        self.assertEqual(payload["summary"]["modified_count"], 2)

        selected_urls = (self.workdir / "05_selected_urls.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(selected_urls, ["https://www.youtube.com/watch?v=vid-b"])

        saved_rows = [
            json.loads(line)
            for line in (self.workdir / "03_scored_candidates.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(saved_rows[0]["agent_selected"], True)
        self.assertEqual(saved_rows[0]["selected"], False)
        self.assertEqual(saved_rows[1]["agent_selected"], False)
        self.assertEqual(saved_rows[1]["selected"], True)

    def test_review_selection_update_round_trips_in_followup_review_response(self) -> None:
        self._create_task()
        self._write_candidates()

        update_response = self.client.post(
            "/api/tasks/review-task/review-selection",
            json={"workdir": str(self.workdir), "selected_keys": ["video:vid-b"]},
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        update_payload = update_response.json()
        self.assertEqual(update_payload["summary"]["selected_count"], 1)
        self.assertEqual(update_payload["summary"]["modified_count"], 2)
        self.assertEqual([item["selection_key"] for item in update_payload["items"]], ["video:vid-a", "video:vid-b"])
        self.assertEqual([item["selected"] for item in update_payload["items"]], [False, True])

        review_response = self.client.get("/api/tasks/review-task/review", params={"workdir": str(self.workdir)})
        self.assertEqual(review_response.status_code, 200, review_response.text)
        review_payload = review_response.json()
        self.assertEqual(review_payload["summary"]["selected_count"], 1)
        self.assertEqual(review_payload["summary"]["modified_count"], 2)
        self.assertEqual([item["selection_key"] for item in review_payload["items"]], ["video:vid-a", "video:vid-b"])
        self.assertEqual([item["selected"] for item in review_payload["items"]], [False, True])
        self.assertEqual(
            (self.workdir / "05_selected_urls.txt").read_text(encoding="utf-8").splitlines(),
            ["https://www.youtube.com/watch?v=vid-b"],
        )

    def test_review_selection_update_supports_url_and_row_selection_keys(self) -> None:
        self._create_task()
        self._write_fallback_key_candidates()

        initial = self.client.get("/api/tasks/review-task/review", params={"workdir": str(self.workdir)})
        self.assertEqual(initial.status_code, 200, initial.text)
        initial_payload = initial.json()
        self.assertEqual([item["selection_key"] for item in initial_payload["items"]], ["url:https://www.youtube.com/watch?v=url-only", "row:1"])
        self.assertEqual([item["selected"] for item in initial_payload["items"]], [False, True])

        update_response = self.client.post(
            "/api/tasks/review-task/review-selection",
            json={
                "workdir": str(self.workdir),
                "selected_keys": ["url:https://www.youtube.com/watch?v=url-only"],
            },
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        update_payload = update_response.json()
        self.assertEqual(update_payload["summary"]["selected_count"], 1)
        self.assertEqual([item["selected"] for item in update_payload["items"]], [True, False])
        self.assertEqual(
            (self.workdir / "05_selected_urls.txt").read_text(encoding="utf-8").splitlines(),
            ["https://www.youtube.com/watch?v=url-only"],
        )

        saved_rows = [
            json.loads(line)
            for line in (self.workdir / "03_scored_candidates.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(saved_rows[0]["selected"])
        self.assertFalse(saved_rows[1]["selected"])

    def test_review_selection_update_rejects_completed_task(self) -> None:
        self._create_task(status=TaskStatus.RUNNING)
        self._write_candidates()
        review_response = self.client.get("/api/tasks/review-task/review", params={"workdir": str(self.workdir)})
        self.assertEqual(review_response.status_code, 200, review_response.text)
        self.assertFalse(review_response.json()["editable"])

        response = self.client.post(
            "/api/tasks/review-task/review-selection",
            json={"workdir": str(self.workdir), "selected_keys": ["video:vid-a"]},
        )

        self.assertEqual(response.status_code, 409, response.text)

    def test_review_selection_allows_succeeded_search_task(self) -> None:
        self._create_task(status=TaskStatus.SUCCEEDED)
        self._write_candidates()

        response = self.client.get("/api/tasks/review-task/review", params={"workdir": str(self.workdir)})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["editable"])


if __name__ == "__main__":
    unittest.main()
