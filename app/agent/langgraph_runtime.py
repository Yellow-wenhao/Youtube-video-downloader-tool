from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.planner import AgentPlanner, PlanDraft
from app.agent.policies import step_requires_confirmation
from app.agent.session_store import SessionStore
from app.core.models import StepStatus, TaskResult, TaskSpec, TaskStatus, TaskStep
from app.core.task_service import TaskStore
from app.tools.registry import ToolRegistry


class AgentGraphState(TypedDict, total=False):
    entry_mode: str
    execute_after_plan: bool
    auto_confirm: bool
    task_id: str
    workdir: str
    user_request: str
    title: str
    intent: str
    created_at: str
    updated_at: str
    task_status: str
    needs_confirmation: bool
    current_step_index: int
    params: dict[str, Any]
    steps: list[TaskStep]
    step_results: dict[str, dict[str, Any]]
    resolved_payloads: dict[str, Any]
    last_error: dict[str, Any]
    failure_origin: str
    pending_step_id: str
    planner_name: str
    planner_notes: list[str]
    session_memory: dict[str, Any]
    runtime_defaults: dict[str, Any]
    task_paths: dict[str, str]
    selected_step_index: int | None
    selected_step_id: str
    tool_output: dict[str, Any]
    result: TaskResult


class GraphCheckpointStore:
    def __init__(self, workdir: str | Path) -> None:
        self.workdir = Path(workdir)
        self.root_dir = self.workdir / ".agent" / "graph"
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_path(self, task_id: str) -> Path:
        return self.root_dir / f"{task_id}.json"

    def save(self, task_id: str, node_name: str, state: AgentGraphState) -> None:
        if not task_id:
            return
        payload = {
            "task_id": task_id,
            "node_name": node_name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "state": self._serialize(state),
        }
        self.checkpoint_path(task_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default),
            encoding="utf-8",
        )

    def delete(self, task_id: str) -> None:
        if task_id:
            self.checkpoint_path(task_id).unlink(missing_ok=True)

    def load(self, task_id: str) -> tuple[str, AgentGraphState] | None:
        payload = self.load_payload(task_id)
        if payload is None:
            return None
        node_name = payload.get("node_name")
        state = payload.get("state")
        if not isinstance(node_name, str) or not isinstance(state, dict):
            return None
        if state.get("task_id") and state.get("task_id") != task_id:
            return None
        return node_name, AgentGraphState(**state)

    def load_payload(self, task_id: str) -> dict[str, Any] | None:
        if not task_id:
            return None
        path = self.checkpoint_path(task_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._serialize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._serialize(item) for item in value]
        if is_dataclass(value):
            return self._serialize(asdict(value))
        if isinstance(value, Enum):
            return value.value
        return value

    def _json_default(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


class LangGraphAgentRuntime:
    def __init__(self, registry: ToolRegistry, planner: AgentPlanner) -> None:
        self.registry = registry
        self.planner = planner
        self._graph = self._build_graph()

    def plan(self, user_request: str, workdir: str | Path, defaults: dict[str, Any] | None = None) -> TaskSpec:
        state = self._graph.invoke(
            AgentGraphState(
                entry_mode="plan",
                execute_after_plan=False,
                auto_confirm=False,
                workdir=str(Path(workdir)),
                user_request=user_request,
                params={},
                steps=[],
                step_results={},
                resolved_payloads={},
                planner_notes=[],
                session_memory={},
                runtime_defaults=dict(defaults or {}),
                task_paths={},
            )
        )
        return self._task_from_state(state)

    def run(
        self,
        user_request: str,
        workdir: str | Path,
        *,
        auto_confirm: bool = False,
        defaults: dict[str, Any] | None = None,
    ) -> TaskResult:
        state = self._graph.invoke(
            AgentGraphState(
                entry_mode="plan",
                execute_after_plan=True,
                auto_confirm=auto_confirm,
                workdir=str(Path(workdir)),
                user_request=user_request,
                params={},
                steps=[],
                step_results={},
                resolved_payloads={},
                planner_notes=[],
                session_memory={},
                runtime_defaults=dict(defaults or {}),
                task_paths={},
            )
        )
        return state["result"]

    def resume(self, workdir: str | Path, *, task_id: str = "", auto_confirm: bool = False) -> TaskResult:
        store = TaskStore(workdir)
        session = SessionStore(workdir)
        resume_task_id = task_id or session.get_last_task_id() or store.latest_task_id()
        if not resume_task_id:
            raise ValueError("没有可恢复的任务")

        task = store.load_task(resume_task_id)
        if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            result = store.load_result(task.task_id)
            if result is not None:
                return result

        checkpoint = GraphCheckpointStore(workdir).load(resume_task_id)
        checkpoint_state = checkpoint[1] if checkpoint is not None else {}

        state = self._graph.invoke(
            AgentGraphState(
                entry_mode="resume",
                execute_after_plan=True,
                auto_confirm=auto_confirm,
                task_id=resume_task_id,
                workdir=str(Path(workdir)),
                user_request=task.user_request,
                params=task.params,
                steps=task.steps,
                step_results=dict(checkpoint_state.get("step_results") or {}),
                resolved_payloads=dict(checkpoint_state.get("resolved_payloads") or {}),
                planner_notes=[],
                session_memory={},
                runtime_defaults={},
                task_paths=dict(checkpoint_state.get("task_paths") or store.task_paths(resume_task_id)),
            )
        )
        return state["result"]

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

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("plan_request", self._plan_request)
        graph.add_node("persist_planned_task", self._persist_planned_task)
        graph.add_node("hydrate_resume_state", self._hydrate_resume_state)
        graph.add_node("select_next_step", self._select_next_step)
        graph.add_node("check_confirmation_gate", self._check_confirmation_gate)
        graph.add_node("resolve_step_payload", self._resolve_step_payload)
        graph.add_node("execute_tool_step", self._execute_tool_step)
        graph.add_node("persist_step_success", self._persist_step_success)
        graph.add_node("persist_step_failure", self._persist_step_failure)
        graph.add_node("finalize_confirmation", self._finalize_confirmation)
        graph.add_node("finalize_success", self._finalize_success)
        graph.add_node("finalize_failure", self._finalize_failure)

        graph.add_conditional_edges(START, self._route_entry, {"plan": "load_context", "resume": "hydrate_resume_state"})
        graph.add_edge("load_context", "plan_request")
        graph.add_edge("plan_request", "persist_planned_task")
        graph.add_conditional_edges(
            "persist_planned_task",
            self._route_after_persist,
            {"execute": "select_next_step", "stop": END},
        )
        graph.add_edge("hydrate_resume_state", "select_next_step")
        graph.add_conditional_edges(
            "select_next_step",
            self._route_after_select_step,
            {"success": "finalize_success", "step": "check_confirmation_gate"},
        )
        graph.add_conditional_edges(
            "check_confirmation_gate",
            self._route_after_confirmation_check,
            {"confirm": "finalize_confirmation", "continue": "resolve_step_payload"},
        )
        graph.add_conditional_edges(
            "resolve_step_payload",
            self._route_after_resolution,
            {"failure": "persist_step_failure", "continue": "execute_tool_step"},
        )
        graph.add_conditional_edges(
            "execute_tool_step",
            self._route_after_tool_execution,
            {"failure": "persist_step_failure", "success": "persist_step_success"},
        )
        graph.add_edge("persist_step_success", "select_next_step")
        graph.add_edge("persist_step_failure", "finalize_failure")
        graph.add_edge("finalize_confirmation", END)
        graph.add_edge("finalize_success", END)
        graph.add_edge("finalize_failure", END)
        return graph.compile()

    def _route_entry(self, state: AgentGraphState) -> str:
        return "resume" if state.get("entry_mode") == "resume" else "plan"

    def _route_after_persist(self, state: AgentGraphState) -> str:
        return "execute" if state.get("execute_after_plan") else "stop"

    def _route_after_select_step(self, state: AgentGraphState) -> str:
        return "success" if state.get("selected_step_index") is None else "step"

    def _route_after_confirmation_check(self, state: AgentGraphState) -> str:
        return "confirm" if state.get("pending_step_id") else "continue"

    def _route_after_resolution(self, state: AgentGraphState) -> str:
        return "failure" if state.get("last_error") else "continue"

    def _route_after_tool_execution(self, state: AgentGraphState) -> str:
        return "failure" if state.get("last_error") else "success"

    def _load_context(self, state: AgentGraphState) -> AgentGraphState:
        workdir = state["workdir"]
        session = SessionStore(workdir)
        session_memory = session.planner_memory_context()
        merged_defaults = session.get_defaults()
        merged_defaults.update(session_memory)
        merged_defaults["workdir"] = workdir
        merged_defaults.update(state.get("runtime_defaults") or {})
        updates: AgentGraphState = {
            "session_memory": session_memory,
            "runtime_defaults": merged_defaults,
            "task_status": TaskStatus.DRAFT.value,
        }
        self._save_checkpoint(state, updates, "load_context")
        return updates

    def _plan_request(self, state: AgentGraphState) -> AgentGraphState:
        draft: PlanDraft = self.planner.build_plan(
            state.get("user_request", ""),
            state["workdir"],
            state.get("runtime_defaults"),
        )
        updates: AgentGraphState = {
            "title": draft.title,
            "intent": draft.intent,
            "params": draft.params,
            "steps": draft.steps,
            "planner_name": draft.planner_name,
            "planner_notes": list(draft.planner_notes or []),
            "needs_confirmation": any(step.requires_confirmation for step in draft.steps),
            "current_step_index": 0,
            "task_status": TaskStatus.PLANNED.value,
            "step_results": {},
            "resolved_payloads": {},
            "pending_step_id": "",
            "last_error": {},
            "failure_origin": "",
        }
        self._save_checkpoint(state, updates, "plan_request")
        return updates

    def _persist_planned_task(self, state: AgentGraphState) -> AgentGraphState:
        store = TaskStore(state["workdir"])
        session = SessionStore(state["workdir"])
        task = store.create_task(
            title=state.get("title", ""),
            user_request=state.get("user_request", ""),
            intent=state.get("intent", ""),
            params=state.get("params") or {},
            steps=state.get("steps") or [],
        )
        session.set_last_task_id(task.task_id)
        session.update_defaults(self._session_defaults_from_params(task.params))
        session.remember_planned_task(
            task,
            user_request=state.get("user_request", ""),
            runtime_defaults=state.get("runtime_defaults"),
        )
        updates = self._task_updates(task)
        updates["task_paths"] = store.task_paths(task.task_id)
        self._save_checkpoint(state, updates, "persist_planned_task")
        return updates

    def _hydrate_resume_state(self, state: AgentGraphState) -> AgentGraphState:
        store = TaskStore(state["workdir"])
        task = store.load_task(state["task_id"])
        step_results = dict(state.get("step_results") or {})
        for step in task.steps:
            if step.status == StepStatus.COMPLETED and step.result:
                step_results[step.step_id] = dict(step.result or {})
        updates = self._task_updates(task)
        updates["step_results"] = step_results
        updates["resolved_payloads"] = dict(state.get("resolved_payloads") or {})
        updates["task_paths"] = store.task_paths(task.task_id)
        updates["pending_step_id"] = ""
        updates["last_error"] = {}
        updates["failure_origin"] = ""
        self._save_checkpoint(state, updates, "hydrate_resume_state")
        return updates

    def _select_next_step(self, state: AgentGraphState) -> AgentGraphState:
        steps = state.get("steps") or []
        start_index = max(0, int(state.get("current_step_index") or 0))
        selected_index: int | None = None
        for index in list(range(start_index, len(steps))) + list(range(0, start_index)):
            if steps[index].status not in {StepStatus.COMPLETED, StepStatus.SKIPPED}:
                selected_index = index
                break
        updates: AgentGraphState = {
            "selected_step_index": selected_index,
            "selected_step_id": steps[selected_index].step_id if selected_index is not None else "",
            "pending_step_id": "",
            "tool_output": {},
            "last_error": {},
            "failure_origin": "",
        }
        self._save_checkpoint(state, updates, "select_next_step")
        return updates

    def _check_confirmation_gate(self, state: AgentGraphState) -> AgentGraphState:
        step_index = int(state["selected_step_index"])
        task = self._task_from_state(state)
        step = task.steps[step_index]
        if step_requires_confirmation(step) and not state.get("auto_confirm", False):
            store = TaskStore(task.workdir)
            task.needs_confirmation = True
            store.set_step_status(task, step_index, StepStatus.AWAITING_CONFIRMATION, f"Awaiting confirmation for {step.title}")
            store.set_task_status(task, TaskStatus.AWAITING_CONFIRMATION, f"Confirmation required before {step.tool_name}")
            updates = self._task_updates(task)
            updates["pending_step_id"] = step.step_id
            updates["task_paths"] = store.task_paths(task.task_id)
            self._save_checkpoint(state, updates, "check_confirmation_gate")
            return updates
        updates: AgentGraphState = {"pending_step_id": "", "needs_confirmation": False}
        self._save_checkpoint(state, updates, "check_confirmation_gate")
        return updates

    def _resolve_step_payload(self, state: AgentGraphState) -> AgentGraphState:
        step_index = int(state["selected_step_index"])
        step = (state.get("steps") or [])[step_index]
        context = self._build_context(state)
        try:
            resolved_payload = self._resolve_payload(step.payload, context)
        except Exception as exc:
            updates: AgentGraphState = {
                "resolved_payloads": dict(state.get("resolved_payloads") or {}),
                "last_error": {"message": str(exc), "error_type": exc.__class__.__name__},
                "failure_origin": "payload_resolution",
                "tool_output": {},
            }
            self._save_checkpoint(state, updates, "resolve_step_payload")
            return updates

        resolved_payloads = dict(state.get("resolved_payloads") or {})
        resolved_payloads[step.step_id] = resolved_payload
        updates = {"resolved_payloads": resolved_payloads, "last_error": {}, "failure_origin": ""}
        self._save_checkpoint(state, updates, "resolve_step_payload")
        return updates

    def _execute_tool_step(self, state: AgentGraphState) -> AgentGraphState:
        step_index = int(state["selected_step_index"])
        task = self._task_from_state(state)
        store = TaskStore(task.workdir)
        step = task.steps[step_index]
        if task.status != TaskStatus.RUNNING:
            store.set_task_status(task, TaskStatus.RUNNING, "Task execution started")
        store.set_step_status(task, step_index, StepStatus.RUNNING, f"Running {step.tool_name}")
        resolved_payload = dict((state.get("resolved_payloads") or {}).get(step.step_id) or {})
        if step.tool_name in {"start_download", "retry_failed_downloads"}:
            resolved_payload["task_id"] = task.task_id
        try:
            output = self.registry.execute(step.tool_name, resolved_payload)
        except Exception as exc:
            updates = self._task_updates(task)
            updates["last_error"] = {"message": str(exc), "error_type": exc.__class__.__name__}
            updates["failure_origin"] = "tool_execution"
            updates["tool_output"] = {}
            updates["resolved_payloads"] = dict(state.get("resolved_payloads") or {})
            self._save_checkpoint(state, updates, "execute_tool_step")
            return updates

        updates = self._task_updates(task)
        updates["tool_output"] = output
        updates["last_error"] = {}
        updates["failure_origin"] = ""
        self._save_checkpoint(state, updates, "execute_tool_step")
        return updates

    def _persist_step_success(self, state: AgentGraphState) -> AgentGraphState:
        step_index = int(state["selected_step_index"])
        task = self._task_from_state(state)
        store = TaskStore(task.workdir)
        step = task.steps[step_index]
        output = dict(state.get("tool_output") or {})
        task.needs_confirmation = False
        store.set_step_status(task, step_index, StepStatus.COMPLETED, f"Completed {step.tool_name}", result=output)
        task.current_step_index = step_index + 1
        store.save_task(task)
        step_results = dict(state.get("step_results") or {})
        step_results[step.step_id] = output
        updates = self._task_updates(task)
        updates["step_results"] = step_results
        updates["tool_output"] = {}
        updates["task_paths"] = store.task_paths(task.task_id)
        self._save_checkpoint(state, updates, "persist_step_success")
        return updates

    def _persist_step_failure(self, state: AgentGraphState) -> AgentGraphState:
        step_index = int(state["selected_step_index"])
        task = self._task_from_state(state)
        store = TaskStore(task.workdir)
        step = task.steps[step_index]
        error_payload = {
            "error": str((state.get("last_error") or {}).get("message") or ""),
            "error_type": str((state.get("last_error") or {}).get("error_type") or "RuntimeError"),
            "failure_origin": state.get("failure_origin") or "tool_execution",
        }
        task.needs_confirmation = False
        store.set_step_status(task, step_index, StepStatus.FAILED, error_payload["error"], result=error_payload)
        store.set_task_status(task, TaskStatus.FAILED, f"Step failed: {step.title}")
        updates = self._task_updates(task)
        updates["task_paths"] = store.task_paths(task.task_id)
        updates["selected_step_id"] = step.step_id
        updates["selected_step_index"] = step_index
        self._save_checkpoint(state, updates, "persist_step_failure")
        return updates

    def _finalize_confirmation(self, state: AgentGraphState) -> AgentGraphState:
        store = TaskStore(state["workdir"])
        session = SessionStore(state["workdir"])
        task = self._task_from_state(state)
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.AWAITING_CONFIRMATION,
            message=f"确认后才能继续执行: {task.steps[int(state['selected_step_index'])].title}",
            data={
                "pending_step": state.get("pending_step_id", ""),
                "task": self.explain(task),
                "task_paths": store.task_paths(task.task_id),
            },
            started_at=task.created_at,
            finished_at=self._now(),
        )
        store.save_result(result)
        session.set_last_task_id(task.task_id)
        session.remember_task_result(task, result)
        updates: AgentGraphState = {
            "result": result,
            "task_status": TaskStatus.AWAITING_CONFIRMATION.value,
            "task_paths": store.task_paths(task.task_id),
        }
        self._save_checkpoint(state, updates, "finalize_confirmation")
        return updates

    def _finalize_success(self, state: AgentGraphState) -> AgentGraphState:
        store = TaskStore(state["workdir"])
        session = SessionStore(state["workdir"])
        task = self._task_from_state(state)
        store.set_task_status(task, TaskStatus.SUCCEEDED, "Task completed successfully")
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.SUCCEEDED,
            message="Task completed successfully",
            data={
                "task": self.explain(task),
                "step_results": dict(state.get("step_results") or {}),
                "task_paths": store.task_paths(task.task_id),
            },
            started_at=task.created_at,
            finished_at=self._now(),
        )
        store.save_result(result)
        session.set_last_task_id(task.task_id)
        session.remember_task_result(task, result)
        updates = self._task_updates(task)
        updates["result"] = result
        updates["task_paths"] = store.task_paths(task.task_id)
        self._save_checkpoint(state, updates, "finalize_success")
        return updates

    def _finalize_failure(self, state: AgentGraphState) -> AgentGraphState:
        store = TaskStore(state["workdir"])
        session = SessionStore(state["workdir"])
        task = self._task_from_state(state)
        step_index = int(state["selected_step_index"])
        step = task.steps[step_index]
        resolved_payload = dict((state.get("resolved_payloads") or {}).get(step.step_id) or {})
        error_payload = state.get("last_error") or {}
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.FAILED,
            message=str(error_payload.get("message") or ""),
            data={
                "failed_step": step.step_id,
                "failed_step_title": step.title,
                "tool_name": step.tool_name,
                "resolved_payload": resolved_payload,
                "error_type": str(error_payload.get("error_type") or "RuntimeError"),
                "failure_origin": state.get("failure_origin") or "tool_execution",
                "task": self.explain(task),
                "task_paths": store.task_paths(task.task_id),
            },
            started_at=task.created_at,
            finished_at=self._now(),
        )
        store.save_result(result)
        session.set_last_task_id(task.task_id)
        session.remember_task_result(task, result)
        updates = self._task_updates(task)
        updates["result"] = result
        updates["task_paths"] = store.task_paths(task.task_id)
        self._save_checkpoint(state, updates, "finalize_failure")
        return updates

    def _task_from_state(self, state: AgentGraphState) -> TaskSpec:
        return TaskSpec(
            task_id=state.get("task_id", ""),
            title=state.get("title", ""),
            user_request=state.get("user_request", ""),
            intent=state.get("intent", ""),
            workdir=state.get("workdir", ""),
            created_at=state.get("created_at", ""),
            updated_at=state.get("updated_at", ""),
            status=TaskStatus(state.get("task_status", TaskStatus.DRAFT.value)),
            params=dict(state.get("params") or {}),
            steps=list(state.get("steps") or []),
            current_step_index=int(state.get("current_step_index") or 0),
            needs_confirmation=bool(state.get("needs_confirmation", False)),
        )

    def _task_updates(self, task: TaskSpec) -> AgentGraphState:
        return {
            "task_id": task.task_id,
            "title": task.title,
            "user_request": task.user_request,
            "intent": task.intent,
            "workdir": task.workdir,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "task_status": task.status.value,
            "params": task.params,
            "steps": task.steps,
            "current_step_index": task.current_step_index,
            "needs_confirmation": task.needs_confirmation,
        }

    def _build_context(self, state: AgentGraphState) -> dict[str, Any]:
        return {
            "task": {
                "task_id": state.get("task_id", ""),
                "workdir": state.get("workdir", ""),
                "intent": state.get("intent", ""),
            },
            "steps": dict(state.get("step_results") or {}),
        }

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

    def _save_checkpoint(self, state: AgentGraphState, updates: AgentGraphState, node_name: str) -> None:
        merged: AgentGraphState = dict(state)
        merged.update(updates)
        task_id = merged.get("task_id", "")
        if task_id:
            GraphCheckpointStore(merged["workdir"]).save(task_id, node_name, merged)

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
            "year_from",
            "year_to",
            "topic_phrase",
        }
        return {key: value for key, value in params.items() if key in allowed}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
