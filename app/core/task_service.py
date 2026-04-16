from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.core.models import (
    DownloadSessionRef,
    StepStatus,
    TaskDownloadProgress,
    TaskEvent,
    TaskLogLine,
    TaskResult,
    TaskSpec,
    TaskStatus,
    TaskStep,
    TaskSummary,
)
from app.core.download_workspace_service import extract_download_session_ref


class TaskStore:
    def __init__(self, workdir: str | Path) -> None:
        self.workdir = Path(workdir)
        self.root_dir = self.workdir / ".agent"
        self.tasks_dir = self.root_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _task_dir(self, task_id: str) -> Path:
        return self.tasks_dir / task_id

    def _json_default(self, value: Any) -> Any:
        if isinstance(value, (TaskStatus, StepStatus)):
            return value.value
        raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default), encoding="utf-8")

    def _read_json(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _step_from_dict(self, data: dict[str, Any]) -> TaskStep:
        return TaskStep(
            step_id=data["step_id"],
            title=data.get("title", ""),
            tool_name=data.get("tool_name", ""),
            payload=data.get("payload") or {},
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            status=StepStatus(data.get("status", StepStatus.PENDING.value)),
            message=data.get("message", ""),
            result=data.get("result") or {},
        )

    def _task_from_dict(self, data: dict[str, Any]) -> TaskSpec:
        return TaskSpec(
            task_id=data["task_id"],
            title=data.get("title", ""),
            user_request=data.get("user_request", ""),
            intent=data.get("intent", ""),
            workdir=data.get("workdir", str(self.workdir)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            status=TaskStatus(data.get("status", TaskStatus.DRAFT.value)),
            params=data.get("params") or {},
            steps=[self._step_from_dict(step) for step in data.get("steps") or []],
            current_step_index=int(data.get("current_step_index", 0)),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
        )

    def _result_from_dict(self, data: dict[str, Any]) -> TaskResult:
        return TaskResult(
            task_id=data["task_id"],
            status=TaskStatus(data.get("status", TaskStatus.DRAFT.value)),
            message=data.get("message", ""),
            data=data.get("data") or {},
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
        )

    def _log_from_dict(self, data: dict[str, Any]) -> TaskLogLine:
        return TaskLogLine(
            log_id=data["log_id"],
            task_id=data["task_id"],
            timestamp=data.get("timestamp", ""),
            kind=data.get("kind", "info"),
            message=data.get("message", ""),
            data=data.get("data") or {},
        )

    def _progress_from_dict(self, data: dict[str, Any]) -> TaskDownloadProgress:
        return TaskDownloadProgress(
            task_id=data["task_id"],
            phase=data.get("phase", ""),
            percent=float(data.get("percent", 0.0) or 0.0),
            downloaded_bytes=int(data.get("downloaded_bytes", 0) or 0),
            total_bytes=int(data.get("total_bytes", 0) or 0),
            speed_text=data.get("speed_text", ""),
            current_video_id=data.get("current_video_id", ""),
            current_video_label=data.get("current_video_label", ""),
            updated_at=data.get("updated_at", ""),
        )

    def _summary_from_dict(self, data: dict[str, Any]) -> TaskSummary:
        return TaskSummary(
            task_id=data["task_id"],
            status=TaskStatus(data.get("status", TaskStatus.DRAFT.value)),
            title=data.get("title", ""),
            workdir=data.get("workdir", str(self.workdir)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            current_step_index=int(data.get("current_step_index", 0)),
            needs_confirmation=bool(data.get("needs_confirmation", False)),
            last_message=data.get("last_message", ""),
            details=data.get("details") or {},
        )

    def _event_from_dict(self, data: dict[str, Any]) -> TaskEvent:
        return TaskEvent(
            event_id=data["event_id"],
            task_id=data["task_id"],
            timestamp=data.get("timestamp", ""),
            event_type=data.get("event_type", ""),
            message=data.get("message", ""),
            level=data.get("level", "info"),
            data=data.get("data") or {},
        )

    def create_task(
        self,
        title: str,
        user_request: str,
        intent: str,
        params: dict[str, Any],
        steps: list[TaskStep],
    ) -> TaskSpec:
        now = self._now()
        task = TaskSpec(
            task_id=uuid.uuid4().hex[:12],
            title=title,
            user_request=user_request,
            intent=intent,
            workdir=str(self.workdir),
            created_at=now,
            updated_at=now,
            status=TaskStatus.PLANNED,
            params=params,
            steps=steps,
            current_step_index=0,
            needs_confirmation=any(step.requires_confirmation for step in steps),
        )
        self.save_task(task)
        self.append_event(task.task_id, "task_created", f"Task created: {title}", data={"intent": intent})
        return task

    def save_task(self, task: TaskSpec) -> None:
        task.updated_at = self._now()
        self._write_json(self._task_dir(task.task_id) / "spec.json", asdict(task))
        self.save_summary(
            TaskSummary(
                task_id=task.task_id,
                status=task.status,
                title=task.title,
                workdir=task.workdir,
                created_at=task.created_at,
                updated_at=task.updated_at,
                current_step_index=task.current_step_index,
                needs_confirmation=task.needs_confirmation,
                details={"intent": task.intent, "step_count": len(task.steps)},
            )
        )

    def load_task(self, task_id: str) -> TaskSpec:
        return self._task_from_dict(self._read_json(self._task_dir(task_id) / "spec.json"))

    def save_result(self, result: TaskResult) -> None:
        self._write_json(self._task_dir(result.task_id) / "result.json", asdict(result))

    def load_result(self, task_id: str) -> TaskResult | None:
        path = self._task_dir(task_id) / "result.json"
        if not path.exists():
            return None
        return self._result_from_dict(self._read_json(path))

    def load_download_session_ref(self, task_id: str) -> DownloadSessionRef:
        result = self.load_result(task_id)
        if result is None:
            return DownloadSessionRef()
        return extract_download_session_ref(result)

    def save_download_progress(self, progress: TaskDownloadProgress) -> None:
        if not progress.updated_at:
            progress.updated_at = self._now()
        self._write_json(self._task_dir(progress.task_id) / "progress.json", asdict(progress))

    def load_download_progress(self, task_id: str) -> TaskDownloadProgress | None:
        path = self._task_dir(task_id) / "progress.json"
        if not path.exists():
            return None
        return self._progress_from_dict(self._read_json(path))

    def clear_download_progress(self, task_id: str) -> None:
        path = self._task_dir(task_id) / "progress.json"
        if path.exists():
            path.unlink(missing_ok=True)

    def save_summary(self, summary: TaskSummary) -> None:
        self._write_json(self._task_dir(summary.task_id) / "summary.json", asdict(summary))

    def load_summary(self, task_id: str) -> TaskSummary | None:
        path = self._task_dir(task_id) / "summary.json"
        if not path.exists():
            return None
        return self._summary_from_dict(self._read_json(path))

    def list_summaries(self, limit: int | None = 20) -> list[TaskSummary]:
        summaries: list[TaskSummary] = []
        for summary_file in sorted(self.tasks_dir.glob("*/summary.json"), reverse=True):
            summaries.append(self._summary_from_dict(self._read_json(summary_file)))
            if limit is not None and len(summaries) >= limit:
                break
        summaries.sort(key=lambda item: item.updated_at, reverse=True)
        return summaries

    def append_event(
        self,
        task_id: str,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            event_id=uuid.uuid4().hex[:12],
            task_id=task_id,
            timestamp=self._now(),
            event_type=event_type,
            message=message,
            level=level,
            data=data or {},
        )
        path = self._task_dir(task_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False, default=self._json_default) + "\n")
        summary = self.load_summary(task_id)
        if summary is not None:
            summary.updated_at = event.timestamp
            summary.last_message = message
            self.save_summary(summary)
        return event

    def load_events(self, task_id: str, limit: int | None = None) -> list[TaskEvent]:
        path = self._task_dir(task_id) / "events.jsonl"
        if not path.exists():
            return []
        events: list[TaskEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            events.append(self._event_from_dict(json.loads(s)))
        if limit is not None and limit >= 0:
            return events[-limit:]
        return events

    def append_log(
        self,
        task_id: str,
        kind: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> TaskLogLine:
        log = TaskLogLine(
            log_id=uuid.uuid4().hex[:12],
            task_id=task_id,
            timestamp=self._now(),
            kind=kind or "info",
            message=message,
            data=data or {},
        )
        path = self._task_dir(task_id) / "logs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(log), ensure_ascii=False, default=self._json_default) + "\n")
        return log

    def load_logs(self, task_id: str, limit: int | None = None) -> list[TaskLogLine]:
        path = self._task_dir(task_id) / "logs.jsonl"
        if not path.exists():
            return []
        logs: list[TaskLogLine] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            logs.append(self._log_from_dict(json.loads(s)))
        if limit is not None and limit >= 0:
            return logs[-limit:]
        return logs

    def logs_count(self, task_id: str) -> int:
        return len(self.load_logs(task_id))

    def set_task_status(self, task: TaskSpec, status: TaskStatus, message: str = "") -> TaskSpec:
        task.status = status
        self.save_task(task)
        if message:
            self.append_event(task.task_id, "task_status", message, data={"status": status.value})
        return task

    def set_step_status(
        self,
        task: TaskSpec,
        step_index: int,
        status: StepStatus,
        message: str = "",
        result: dict[str, Any] | None = None,
    ) -> TaskSpec:
        step = task.steps[step_index]
        step.status = status
        if message:
            step.message = message
        if result is not None:
            step.result = result
        task.current_step_index = step_index
        self.save_task(task)
        event_type = "step_status"
        payload = {"step_id": step.step_id, "tool_name": step.tool_name, "status": status.value}
        if result is not None:
            payload["result_keys"] = sorted(result.keys())
        self.append_event(task.task_id, event_type, message or f"{step.step_id}: {status.value}", data=payload)
        return task

    def latest_task_id(self) -> str:
        summaries = self.list_summaries(limit=1)
        return summaries[0].task_id if summaries else ""

    def task_paths(self, task_id: str) -> dict[str, str]:
        task_dir = self._task_dir(task_id)
        return {
            "task_dir": str(task_dir),
            "spec": str(task_dir / "spec.json"),
            "summary": str(task_dir / "summary.json"),
            "events": str(task_dir / "events.jsonl"),
            "logs": str(task_dir / "logs.jsonl"),
            "progress": str(task_dir / "progress.json"),
            "result": str(task_dir / "result.json"),
        }

    def delete_task_dir(self, task_id: str) -> None:
        task_dir = self._task_dir(task_id)
        if task_dir.exists():
            shutil.rmtree(task_dir, ignore_errors=True)
