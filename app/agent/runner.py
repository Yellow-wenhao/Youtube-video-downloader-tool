from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agent.langgraph_runtime import LangGraphAgentRuntime
from app.agent.planner import AgentPlanner, PlannerRuntimeError, create_default_planner
from app.core.app_paths import default_workdir
from app.core.models import TaskResult, TaskSpec, TaskStatus
from app.tools.registry import ToolRegistry, create_default_registry


class AgentRunner:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        planner: AgentPlanner | None = None,
    ) -> None:
        self.registry = registry or create_default_registry()
        self.planner = planner or create_default_planner()
        self._runtime: LangGraphAgentRuntime | None = None

    def _get_runtime(self) -> LangGraphAgentRuntime:
        if self._runtime is None:
            self._runtime = LangGraphAgentRuntime(self.registry, self.planner)
        return self._runtime

    def plan(self, user_request: str, workdir: str | Path, defaults: dict[str, Any] | None = None) -> TaskSpec:
        try:
            return self._get_runtime().plan(user_request, workdir, defaults=defaults)
        except Exception as exc:
            raise AgentRunnerPlanningError.from_exception(exc) from exc

    def run(
        self,
        user_request: str,
        workdir: str | Path,
        *,
        auto_confirm: bool = False,
        defaults: dict[str, Any] | None = None,
    ) -> TaskResult:
        return self._get_runtime().run(
            user_request,
            workdir,
            auto_confirm=auto_confirm,
            defaults=defaults,
        )

    def resume(self, workdir: str | Path, task_id: str = "", *, auto_confirm: bool = False) -> TaskResult:
        return self._get_runtime().resume(workdir, task_id=task_id, auto_confirm=auto_confirm)

    def explain(self, task: TaskSpec) -> dict[str, Any]:
        return self._get_runtime().explain(task)


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
    parser = argparse.ArgumentParser(description="Agent runner for the local YouTube Downloader workspace")
    parser.add_argument("request", help="Natural-language request for the agent")
    parser.add_argument(
        "--workdir",
        default=str(default_workdir()),
        help="Agent workdir (defaults to the local application workspace directory)",
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
