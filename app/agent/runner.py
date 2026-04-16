from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agent.planner import AgentPlanner, PlannerRuntimeError, create_default_planner
from app.agent.policies import step_requires_confirmation
from app.agent.session_store import SessionStore
from app.core.app_paths import default_workdir
from app.core.models import StepStatus, TaskResult, TaskSpec, TaskStatus
from app.core.task_service import TaskStore
from app.tools.registry import ToolRegistry, create_default_registry


class AgentRunner:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        planner: AgentPlanner | None = None,
    ) -> None:
        self.registry = registry or create_default_registry()
        self.planner = planner or create_default_planner()

    def plan(self, user_request: str, workdir: str | Path, defaults: dict[str, Any] | None = None) -> TaskSpec:
        store = TaskStore(workdir)
        session = SessionStore(workdir)
        merged_defaults = session.get_defaults()
        merged_defaults.update(session.planner_memory_context())
        merged_defaults["workdir"] = str(Path(workdir))
        if defaults:
            merged_defaults.update(defaults)
        try:
            draft = self.planner.build_plan(user_request, workdir, merged_defaults)
        except Exception as exc:
            raise AgentRunnerPlanningError.from_exception(exc) from exc
        task = store.create_task(
            title=draft.title,
            user_request=user_request,
            intent=draft.intent,
            params=draft.params,
            steps=draft.steps,
        )
        session.set_last_task_id(task.task_id)
        session.update_defaults(self._session_defaults_from_params(draft.params))
        session.remember_planned_task(task, user_request=user_request, runtime_defaults=merged_defaults)
        return task

    def run(
        self,
        user_request: str,
        workdir: str | Path,
        *,
        auto_confirm: bool = False,
        defaults: dict[str, Any] | None = None,
    ) -> TaskResult:
        task = self.plan(user_request, workdir, defaults=defaults)
        return self.execute_task(task, TaskStore(workdir), SessionStore(workdir), auto_confirm=auto_confirm)

    def resume(self, workdir: str | Path, task_id: str = "", *, auto_confirm: bool = False) -> TaskResult:
        store = TaskStore(workdir)
        session = SessionStore(workdir)
        resume_task_id = task_id or session.get_last_task_id() or store.latest_task_id()
        if not resume_task_id:
            raise ValueError("没有可恢复的任务")
        task = store.load_task(resume_task_id)
        return self.execute_task(task, store, session, auto_confirm=auto_confirm)

    def explain(self, task: TaskSpec) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "title": task.title,
            "intent": task.intent,
            "status": task.status.value,
            "needs_confirmation": task.needs_confirmation,
            "steps": [
                {
                    "step_id": step.step_id,
                    "title": step.title,
                    "tool_name": step.tool_name,
                    "requires_confirmation": step.requires_confirmation,
                    "status": step.status.value,
                }
                for step in task.steps
            ],
        }

    def execute_task(self, task: TaskSpec, store: TaskStore, session: SessionStore, *, auto_confirm: bool) -> TaskResult:
        return self._execute_task(task, store, session, auto_confirm=auto_confirm)

    def _execute_task(self, task: TaskSpec, store: TaskStore, session: SessionStore, *, auto_confirm: bool) -> TaskResult:
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            result = store.load_result(task.task_id)
            if result is not None:
                return result

        context: dict[str, Any] = {
            "task": {
                "task_id": task.task_id,
                "workdir": task.workdir,
                "intent": task.intent,
            },
            "steps": {},
        }
        for step in task.steps:
            if step.status == StepStatus.COMPLETED and step.result:
                context["steps"][step.step_id] = step.result

        if task.status != TaskStatus.RUNNING:
            store.set_task_status(task, TaskStatus.RUNNING, "Task execution started")

        for index, step in enumerate(task.steps):
            if step.status == StepStatus.COMPLETED:
                continue
            if step.status == StepStatus.SKIPPED:
                continue
            if step_requires_confirmation(step) and not auto_confirm:
                task.needs_confirmation = True
                store.set_step_status(task, index, StepStatus.AWAITING_CONFIRMATION, f"Awaiting confirmation for {step.title}")
                store.set_task_status(task, TaskStatus.AWAITING_CONFIRMATION, f"Confirmation required before {step.tool_name}")
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.AWAITING_CONFIRMATION,
                    message=f"确认后才能继续执行: {step.title}",
                    data={
                        "pending_step": step.step_id,
                        "task": self.explain(task),
                        "task_paths": store.task_paths(task.task_id),
                    },
                    started_at=task.created_at,
                    finished_at=self._now(),
                )
                store.save_result(result)
                session.set_last_task_id(task.task_id)
                session.remember_task_result(task, result)
                return result

            store.set_step_status(task, index, StepStatus.RUNNING, f"Running {step.tool_name}")
            resolved_payload: Any = {}
            failure_origin = "tool_execution"
            try:
                resolved_payload = self._resolve_payload(step.payload, context)
                if step.tool_name in {"start_download", "retry_failed_downloads"} and isinstance(resolved_payload, dict):
                    resolved_payload["task_id"] = task.task_id
                output = self.registry.execute(step.tool_name, resolved_payload)
            except Exception as exc:
                if isinstance(exc, KeyError) and "无法解析上下文占位符" in str(exc):
                    failure_origin = "payload_resolution"
                error_text = str(exc)
                task.needs_confirmation = False
                store.set_step_status(
                    task,
                    index,
                    StepStatus.FAILED,
                    error_text,
                    result={
                        "error": error_text,
                        "error_type": exc.__class__.__name__,
                        "failure_origin": failure_origin,
                    },
                )
                store.set_task_status(task, TaskStatus.FAILED, f"Step failed: {step.title}")
                result = TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    message=error_text,
                    data={
                        "failed_step": step.step_id,
                        "failed_step_title": step.title,
                        "tool_name": step.tool_name,
                        "resolved_payload": resolved_payload,
                        "error_type": exc.__class__.__name__,
                        "failure_origin": failure_origin,
                        "task": self.explain(task),
                        "task_paths": store.task_paths(task.task_id),
                    },
                    started_at=task.created_at,
                    finished_at=self._now(),
                )
                store.save_result(result)
                session.set_last_task_id(task.task_id)
                session.remember_task_result(task, result)
                return result

            context["steps"][step.step_id] = output
            task.current_step_index = index + 1
            task.needs_confirmation = False
            store.set_step_status(task, index, StepStatus.COMPLETED, f"Completed {step.tool_name}", result=output)

        store.set_task_status(task, TaskStatus.SUCCEEDED, "Task completed successfully")
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            message="Task completed successfully",
            data={
                "task": self.explain(task),
                "step_results": context["steps"],
                "task_paths": store.task_paths(task.task_id),
            },
            started_at=task.created_at,
            finished_at=self._now(),
        )
        store.save_result(result)
        session.set_last_task_id(task.task_id)
        session.remember_task_result(task, result)
        return result

    def _resolve_payload(self, value: Any, context: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._resolve_payload(val, context) for key, val in value.items()}
        if isinstance(value, list):
            return [self._resolve_payload(item, context) for item in value]
        if isinstance(value, str):
            matches = re.findall(r"\{\{([^{}]+)\}\}", value)
            if not matches:
                return value
            if value.strip().startswith("{{") and value.strip().endswith("}}") and len(matches) == 1:
                return self._lookup_context(matches[0].strip(), context)
            resolved = value
            for match in matches:
                replacement = self._lookup_context(match.strip(), context)
                resolved = resolved.replace("{{" + match + "}}", str(replacement))
            return resolved
        return value

    def _lookup_context(self, path: str, context: dict[str, Any]) -> Any:
        current: Any = context
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
                continue
            raise KeyError(f"无法解析上下文占位符: {path}")
        return current

    def _session_defaults_from_params(self, params: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "binary",
            "cookies_from_browser",
            "cookies_file",
            "extra_args",
            "metadata_workers",
            "min_duration",
            "download_dir",
            "download_mode",
            "include_audio",
            "video_container",
            "max_height",
            "max_bitrate_kbps",
            "audio_format",
            "audio_quality",
            "sponsorblock_remove",
            "clean_video",
            "concurrent_videos",
            "concurrent_fragments",
            "download_session_name",
            "full_csv",
            "search_limit",
        }
        return {key: value for key, value in params.items() if key in allowed}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class AgentRunnerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        user_message: str,
        user_title: str = "",
        user_recovery: str = "",
        user_actions: list[str] | None = None,
        error_category: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.user_message = user_message
        self.user_title = user_title
        self.user_recovery = user_recovery
        self.user_actions = list(user_actions or [])
        self.error_category = error_category
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "agent_runner_error",
            "code": self.code,
            "phase": self.phase,
            "message": str(self),
            "error_category": self.error_category,
            "user_title": self.user_title,
            "user_message": self.user_message,
            "user_recovery": self.user_recovery,
            "user_actions": self.user_actions,
            "details": self.details,
        }


class AgentRunnerPlanningError(AgentRunnerError):
    @classmethod
    def from_exception(cls, exc: Exception) -> "AgentRunnerPlanningError":
        if isinstance(exc, PlannerRuntimeError):
            return cls(
                str(exc),
                code=exc.code,
                phase=exc.phase,
                error_category=exc.error_category,
                user_title=exc.user_title,
                user_message=exc.user_message,
                user_recovery=exc.user_recovery,
                user_actions=exc.user_actions,
                details=exc.details,
            )
        return cls(
            str(exc),
            code="planner_unknown_error",
            phase="planning",
            error_category="unknown",
            user_title="Agent 计划生成失败",
            user_message="Agent 在生成计划时遇到未分类错误，当前无法继续执行。",
            user_recovery="请先重试；如果持续失败，请检查当前配置或改用其他模型。",
            user_actions=["重试", "检查配置", "更换模型"],
            details={},
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent runner for the YouTube downloader")
    parser.add_argument("request", help="Natural-language request for the agent")
    parser.add_argument(
        "--workdir",
        default=str(default_workdir()),
        help="Agent workdir (defaults to the local YTBDLP workspace directory)",
    )
    parser.add_argument("--auto-confirm", action="store_true", help="Automatically approve download steps")
    parser.add_argument("--resume-task-id", default="", help="Resume an existing task by id")
    args = parser.parse_args(argv)

    runner = AgentRunner()
    if args.resume_task_id:
        result = runner.resume(args.workdir, task_id=args.resume_task_id, auto_confirm=args.auto_confirm)
    else:
        result = runner.run(args.request, args.workdir, auto_confirm=args.auto_confirm)
    print(json.dumps({
        "task_id": result.task_id,
        "status": result.status.value,
        "message": result.message,
        "data": result.data,
    }, ensure_ascii=False, indent=2))
    return 0 if result.status in {TaskStatus.SUCCEEDED, TaskStatus.AWAITING_CONFIRMATION} else 1


if __name__ == "__main__":
    raise SystemExit(main())
