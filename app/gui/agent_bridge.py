from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from PySide6 import QtCore

from app.agent.runner import AgentRunner, AgentRunnerError
from app.core.task_service import TaskStore


class _ResumeWorker(QtCore.QObject):
    finished = QtCore.Signal(dict)
    error = QtCore.Signal(dict)

    def __init__(self, runner: AgentRunner, workdir: str, task_id: str, auto_confirm: bool) -> None:
        super().__init__()
        self.runner = runner
        self.workdir = workdir
        self.task_id = task_id
        self.auto_confirm = auto_confirm

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self.runner.resume(self.workdir, task_id=self.task_id, auto_confirm=self.auto_confirm)
            self.finished.emit(_to_jsonable(result))
        except Exception as exc:
            self.error.emit(_error_payload(exc))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _to_jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


class AgentBridge(QtCore.QObject):
    planned = QtCore.Signal(dict)
    task_summary = QtCore.Signal(dict)
    task_event = QtCore.Signal(dict)
    confirmation_required = QtCore.Signal(dict)
    completed = QtCore.Signal(dict)
    error = QtCore.Signal(dict)
    busy_changed = QtCore.Signal(bool)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.runner = AgentRunner()
        self._thread: Optional[QtCore.QThread] = None
        self._worker: Optional[_ResumeWorker] = None
        self._monitor = QtCore.QTimer(self)
        self._monitor.setInterval(350)
        self._monitor.timeout.connect(self._poll_current_task)
        self._current_task_id = ""
        self._current_workdir = ""
        self._seen_event_count = 0
        self._last_summary_updated_at = ""
        self._busy = False

    def current_task_id(self) -> str:
        return self._current_task_id

    def current_workdir(self) -> str:
        return self._current_workdir

    def is_busy(self) -> bool:
        return self._busy

    def submit_request(
        self,
        user_request: str,
        workdir: str,
        auto_confirm: bool = False,
        defaults: Optional[dict[str, Any]] = None,
    ) -> None:
        if self._busy:
            raise RuntimeError("Agent 当前正在执行任务，请先等待完成。")
        try:
            task = self.runner.plan(user_request, workdir, defaults=defaults)
        except Exception as exc:
            self.error.emit(_error_payload(exc))
            return
        self._set_current(task.task_id, workdir)
        self.planned.emit(_to_jsonable(task))
        self._start_worker(task.task_id, workdir, auto_confirm=auto_confirm)

    def resume_task(self, task_id: str, workdir: str, auto_confirm: bool = False) -> None:
        if self._busy:
            raise RuntimeError("Agent 当前正在执行任务，请先等待完成。")
        self._set_current(task_id, workdir)
        self._start_worker(task_id, workdir, auto_confirm=auto_confirm)

    def continue_current(self) -> None:
        if not self._current_task_id or not self._current_workdir:
            raise RuntimeError("当前没有可继续的 Agent 任务。")
        self.resume_task(self._current_task_id, self._current_workdir, auto_confirm=True)

    def refresh_current(self) -> None:
        if not self._current_task_id or not self._current_workdir:
            return
        self._poll_current_task(force=True)

    def _set_current(self, task_id: str, workdir: str) -> None:
        self._current_task_id = task_id
        self._current_workdir = str(Path(workdir))
        self._seen_event_count = 0
        self._last_summary_updated_at = ""

    def _start_worker(self, task_id: str, workdir: str, auto_confirm: bool) -> None:
        self._cleanup_worker()
        self._busy = True
        self.busy_changed.emit(True)
        self._monitor.start()
        thread = QtCore.QThread(self)
        worker = _ResumeWorker(self.runner, workdir, task_id, auto_confirm)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_worker_finished)
        worker.finished.connect(thread.quit)
        worker.error.connect(self._on_worker_error)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._cleanup_worker)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    @QtCore.Slot(dict)
    def _on_worker_finished(self, payload: dict) -> None:
        self._poll_current_task(force=True)
        self._monitor.stop()
        self._busy = False
        self.busy_changed.emit(False)
        status = str(payload.get("status") or "")
        if status == "awaiting_confirmation":
            self.confirmation_required.emit(payload)
        else:
            self.completed.emit(payload)

    @QtCore.Slot(dict)
    def _on_worker_error(self, payload: dict) -> None:
        self._monitor.stop()
        self._busy = False
        self.busy_changed.emit(False)
        self.error.emit(payload)

    def _poll_current_task(self, force: bool = False) -> None:
        if not self._current_task_id or not self._current_workdir:
            return
        try:
            store = TaskStore(self._current_workdir)
            summary = store.load_summary(self._current_task_id)
            if summary is not None and (force or str(getattr(summary, "updated_at", "")) != self._last_summary_updated_at):
                self._last_summary_updated_at = str(getattr(summary, "updated_at", ""))
                self.task_summary.emit(_to_jsonable(summary))
            events = store.load_events(self._current_task_id)
            if force:
                start_index = self._seen_event_count
            else:
                start_index = self._seen_event_count
            for event in events[start_index:]:
                self.task_event.emit(_to_jsonable(event))
            self._seen_event_count = len(events)
        except Exception:
            # polling is best-effort; errors are surfaced by the worker result path
            return


def _error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AgentRunnerError):
        return exc.to_payload()
    if isinstance(exc, RuntimeError):
        return {
            "kind": "runtime_error",
            "code": "runtime_error",
            "phase": "runtime",
            "message": str(exc),
            "user_message": str(exc),
            "details": {},
        }
    return {
        "kind": "unexpected_error",
        "code": "unexpected_error",
        "phase": "runtime",
        "message": str(exc),
        "user_message": "Agent 运行时发生未预期错误。",
        "details": {},
    }
