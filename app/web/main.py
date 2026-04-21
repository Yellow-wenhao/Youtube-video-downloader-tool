from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.planner import PlannerRuntimeError
from app.agent.langgraph_runtime import GraphCheckpointStore
from app.agent.runner import AgentRunner, AgentRunnerError, AgentRunnerPlanningError
from app.agent.session_store import SessionStore
from app.agent.llm_planner import test_llm_connection
from app.core.app_paths import app_version, default_download_dir, default_workdir
from app.core.download_workspace_service import (
    build_retry_task_payload,
    build_download_task_payload,
    collect_result_artifact_paths,
    download_workspace_paths,
    load_download_session,
    load_download_results,
    resolve_retry_failed_urls_file,
)
from app.core.task_service import TaskStore
from app.core.review_service import (
    candidate_selection_key,
    compact_preview,
    format_duration_label,
    is_low_similarity,
    load_review_items,
    review_summary,
    save_review_selection,
    summarize_reasons,
    thumbnail_url,
)
from app.web.failure_diagnosis import build_task_failure_diagnosis
from app.web.runtime_host import runtime_host
from app.web.schemas import (
    AppBootstrapResponse,
    AgentConnectionTestRequest,
    AgentPlanRequest,
    AgentResumeRequest,
    AgentRunRequest,
    DeleteTaskResponse,
    DownloadResultsResponse,
    DownloadSessionView,
    DownloadedVideoView,
    DownloadSettingsView,
    HealthResponse,
    OpenPathRequest,
    PanelStateView,
    QueueOverviewView,
    RetryDownloadSessionRequest,
    TaskCardView,
    TaskDetailView,
    TaskEventView,
    TaskFailureDiagnosisView,
    TaskFocusSummaryView,
    TaskGraphDebugResponse,
    TaskLifecycleResponse,
    TaskListResponse,
    TaskLogsResponse,
    TaskMetricsView,
    TaskLogLineView,
    TaskResultView,
    TaskReviewItemView,
    TaskReviewResponse,
    TaskReviewSelectionUpdateRequest,
    TaskReviewSummaryView,
    TaskDownloadLaunchResponse,
    TaskDownloadProgressView,
    TaskExecutionInsightView,
    TaskExecutionStepView,
    TaskWorkspaceConfirmationView,
    TaskWorkspaceDownloadEntryView,
    TaskStepView,
    TaskStatusPollResponse,
    TaskSummaryView,
)
from app.core.models import StepStatus, TaskDownloadProgress, TaskResult, TaskSpec, TaskStatus, TaskStep, TaskSummary


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    runtime_host.start()
    yield
    runtime_host.shutdown()


app = FastAPI(title="YouTube Downloader Web Workspace", version=app_version(), lifespan=_lifespan)

STATIC_DIR = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def track_runtime_activity(request, call_next):
    request_name = f"{request.method} {request.url.path}"
    runtime_host.request_started(request_name)
    try:
        response = await call_next(request)
    finally:
        runtime_host.request_finished(request_name)
    return response


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/api/bootstrap", response_model=AppBootstrapResponse)
def app_bootstrap() -> AppBootstrapResponse:
    workdir = default_workdir()
    return AppBootstrapResponse(
        product_mode="web-first",
        workdir=str(workdir),
        recommended_download_dir=str(default_download_dir()),
        workdir_source="system_default",
    )


@app.post("/api/agent/test-connection")
def agent_test_connection(payload: AgentConnectionTestRequest) -> dict:
    try:
        return test_llm_connection(payload.model_dump())
    except PlannerRuntimeError as exc:
        return exc.to_payload()
    except Exception as exc:
        return _error_payload(
            exc,
            user_title="LLM 连接测试失败",
            user_message="当前无法完成连接测试。",
            user_recovery="请检查 Provider、Base URL、网络和 API Key 后重试。",
            phase="connection",
        )


@app.post("/api/agent/plan")
def agent_plan(payload: AgentPlanRequest) -> dict:
    runner = AgentRunner()
    try:
        task = runner.plan(
            payload.user_request,
            payload.workdir,
            defaults=payload.model_dump(exclude={"user_request", "workdir"}),
        )
    except AgentRunnerPlanningError as exc:
        return exc.to_payload()
    except Exception as exc:
        return _error_payload(
            exc,
            user_title="Agent 计划生成失败",
            user_message="规划阶段发生了未分类错误。",
            user_recovery="请先重试；如果持续失败，请检查配置或更换模型。",
            phase="planning",
        )
    return _serialize(runner.explain(task) | {"workdir": payload.workdir})


@app.post("/api/agent/run")
def agent_run(payload: AgentRunRequest) -> dict:
    runner = AgentRunner()
    try:
        result = runner.run(
            payload.user_request,
            payload.workdir,
            auto_confirm=payload.auto_confirm,
            defaults=payload.model_dump(exclude={"user_request", "workdir", "auto_confirm"}),
        )
    except AgentRunnerError as exc:
        return exc.to_payload()
    except Exception as exc:
        return _error_payload(
            exc,
            user_title="Agent 运行失败",
            user_message="任务执行阶段发生了未分类错误。",
            user_recovery="请查看当前配置和日志后重试。",
            phase="runtime",
        )
    return _serialize(result)


@app.post("/api/agent/resume")
def agent_resume(payload: AgentResumeRequest) -> dict:
    runner = AgentRunner()
    try:
        result = runner.resume(
            payload.workdir,
            task_id=payload.task_id,
            auto_confirm=payload.auto_confirm,
        )
    except AgentRunnerError as exc:
        return exc.to_payload()
    except Exception as exc:
        return _error_payload(
            exc,
            user_title="恢复任务失败",
            user_message="当前任务无法继续恢复执行。",
            user_recovery="请检查任务状态、当前配置和日志后重试。",
            phase="runtime",
        )
    return _serialize(result)


@app.post("/api/system/open-path")
def system_open_path(payload: OpenPathRequest) -> dict:
    raw_path = (payload.path or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="Path is required")
    target = Path(raw_path).expanduser()
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {target}")
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        return _error_payload(
            exc,
            user_title="打开目录失败",
            user_message="当前无法打开这个路径。",
            user_recovery="请确认路径仍然存在，并检查系统权限后重试。",
            phase="system_open_path",
        )
    return {"ok": True, "path": str(target)}


@app.get("/api/settings/download", response_model=DownloadSettingsView)
def get_download_settings(workdir: str) -> DownloadSettingsView:
    session = SessionStore(workdir)
    defaults = session.get_defaults()
    return _build_download_settings_view(workdir, defaults)


@app.post("/api/settings/download", response_model=DownloadSettingsView)
def save_download_settings(payload: DownloadSettingsView) -> DownloadSettingsView:
    session = SessionStore(payload.workdir)
    session.update_defaults(
        {
            "download_dir": payload.download_dir,
            "download_mode": payload.download_mode,
            "include_audio": payload.include_audio,
            "video_container": payload.video_container,
            "max_height": payload.max_height,
            "audio_format": payload.audio_format,
            "audio_quality": payload.audio_quality,
            "concurrent_videos": payload.concurrent_videos,
            "concurrent_fragments": payload.concurrent_fragments,
            "sponsorblock_remove": payload.sponsorblock_remove,
            "clean_video": payload.clean_video,
        }
    )
    return _build_download_settings_view(payload.workdir, session.get_defaults())


@app.get("/api/tasks", response_model=TaskListResponse)
def list_tasks(
    workdir: str,
    limit: int = Query(default=20, ge=1, le=200),
    status: str = Query(default=""),
    needs_attention: bool = Query(default=False),
    q: str = Query(default=""),
    sort: str = Query(default="updated_desc"),
) -> TaskListResponse:
    store = TaskStore(workdir)
    summaries = store.list_summaries(limit=200)
    summaries = _sort_summaries(summaries, sort=sort)
    filtered_summaries = [
        summary for summary in summaries
        if _summary_matches_filters(summary, status=status, needs_attention=needs_attention, query_text=q)
    ][:limit]
    items = [_build_task_card(store, summary) for summary in filtered_summaries]
    return TaskListResponse(
        items=items,
        queue=_build_queue_overview(summaries),
        workdir=workdir,
        count=len(items),
    )


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, workdir: str) -> dict:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    return _serialize(task)


@app.get("/api/tasks/{task_id}/summary")
def get_task_summary(task_id: str, workdir: str) -> dict:
    store = TaskStore(workdir)
    summary = store.load_summary(task_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Task summary not found: {task_id}")
    return _serialize(_build_summary_view(summary))


@app.get("/api/tasks/{task_id}/events")
def get_task_events(task_id: str, workdir: str) -> dict:
    store = TaskStore(workdir)
    _load_task_or_404(store, task_id)
    events = store.load_events(task_id)
    return {
        "items": [_serialize(_build_event_view(event)) for event in events],
        "count": len(events),
        "task_id": task_id,
        "workdir": workdir,
    }


@app.get("/api/tasks/{task_id}/logs", response_model=TaskLogsResponse)
def get_task_logs(
    task_id: str,
    workdir: str,
    limit: int = Query(default=200, ge=1, le=1000),
) -> TaskLogsResponse:
    store = TaskStore(workdir)
    _load_task_or_404(store, task_id)
    logs = store.load_logs(task_id, limit=limit)
    return TaskLogsResponse(
        task_id=task_id,
        workdir=workdir,
        items=[_build_log_view(item) for item in logs],
        count=len(logs),
        panel_state=_logs_panel_state(len(logs)),
    )


@app.get("/api/tasks/{task_id}/result")
def get_task_result(task_id: str, workdir: str) -> dict:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    result = store.load_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task result not found: {task_id}")
    summary = store.load_summary(task_id)
    return _serialize(_build_result_view(result, task=task, summary=summary))


@app.get("/api/tasks/{task_id}/focus-summary", response_model=TaskFocusSummaryView)
def get_task_focus_summary(task_id: str, workdir: str) -> TaskFocusSummaryView:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    return _build_focus_summary(store, task)


@app.get("/api/tasks/{task_id}/graph-debug", response_model=TaskGraphDebugResponse)
def get_task_graph_debug(task_id: str, workdir: str) -> TaskGraphDebugResponse:
    if not _graph_debug_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    return _build_graph_debug_response(task)


@app.get("/api/tasks/{task_id}/lifecycle", response_model=TaskLifecycleResponse)
def get_task_lifecycle(
    task_id: str,
    workdir: str,
    events_limit: int = Query(default=20, ge=1, le=200),
) -> TaskLifecycleResponse:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    summary = store.load_summary(task_id)
    result = store.load_result(task_id)
    events = store.load_events(task_id, limit=events_limit)
    download_progress = store.load_download_progress(task_id)
    failure = _build_failure_view(task, result, summary=summary)
    workspace = _build_workspace_state(
        task,
        summary=summary,
        result=result,
        download_progress=download_progress,
        failure=failure,
    )
    return TaskLifecycleResponse(
        task=_build_task_detail(
            store,
            task,
            summary=summary,
            event_count=len(store.load_events(task_id)),
            events=events,
        ),
        summary=_build_summary_view(summary) if summary is not None else None,
        result=_build_result_view(result, task=task, summary=summary) if result is not None else None,
        failure=failure,
        execution=_build_execution_insight(task, events=events),
        focus_summary=_build_focus_summary(store, task),
        events_tail=[_build_event_view(event) for event in events],
        events_tail_count=len(events),
        download_progress=_build_download_progress_view(download_progress),
        workspace_stage=workspace["workspace_stage"],
        workspace_stage_label=workspace["workspace_stage_label"],
        primary_message=workspace["primary_message"],
        confirmation=workspace["confirmation"],
        download_entry=workspace["download_entry"],
    )


@app.get("/api/tasks/{task_id}/poll", response_model=TaskStatusPollResponse)
def poll_task_status(
    task_id: str,
    workdir: str,
    events_limit: int = Query(default=12, ge=1, le=100),
    ) -> TaskStatusPollResponse:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    summary = store.load_summary(task_id)
    result = store.load_result(task_id)
    events = store.load_events(task_id, limit=events_limit)
    download_progress = store.load_download_progress(task_id)
    metrics = _compute_metrics(task, event_count=len(store.load_events(task_id)))
    current_step_title, current_step_status = _current_step(task)
    failure = _build_failure_view(task, result, summary=summary)
    workspace = _build_workspace_state(
        task,
        summary=summary,
        result=result,
        download_progress=download_progress,
        failure=failure,
    )
    return TaskStatusPollResponse(
        task_id=task.task_id,
        status=task.status.value,
        status_label=_status_label(task.status.value),
        status_tone=_status_tone(task.status.value),
        needs_confirmation=task.needs_confirmation,
        progress_text=_progress_text(task, metrics),
        active_elapsed_seconds=_compute_active_elapsed_seconds(store, task),
        current_step_title=current_step_title,
        current_step_status=current_step_status,
        summary=_build_summary_view(summary) if summary is not None else None,
        failure=failure,
        execution=_build_execution_insight(task, events=events),
        focus_summary=_build_focus_summary(store, task),
        events_tail=[_build_event_view(event) for event in events],
        events_tail_count=len(events),
        download_progress=_build_download_progress_view(download_progress),
        logs_tail_count=store.logs_count(task_id),
        workspace_stage=workspace["workspace_stage"],
        workspace_stage_label=workspace["workspace_stage_label"],
        primary_message=workspace["primary_message"],
        confirmation=workspace["confirmation"],
        download_entry=workspace["download_entry"],
    )


@app.get("/api/tasks/{task_id}/review", response_model=TaskReviewResponse)
def get_task_review(task_id: str, workdir: str) -> TaskReviewResponse:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    return _build_review_response(store, task)


@app.post("/api/tasks/{task_id}/review-selection", response_model=TaskReviewResponse)
def update_task_review_selection(task_id: str, payload: TaskReviewSelectionUpdateRequest) -> TaskReviewResponse:
    store = TaskStore(payload.workdir)
    task = _load_task_or_404(store, task_id)
    review_state = _build_review_response(store, task)
    if not review_state.editable:
        raise HTTPException(status_code=409, detail="当前阶段不允许修改下载选择")
    save_review_selection(Path(payload.workdir), payload.selected_keys)
    return _build_review_response(store, task)


@app.post("/api/tasks/{task_id}/download-selected", response_model=TaskDownloadLaunchResponse)
def launch_selected_download(task_id: str, workdir: str) -> TaskDownloadLaunchResponse:
    store = TaskStore(workdir)
    source_task = _load_task_or_404(store, task_id)
    if source_task.status == TaskStatus.AWAITING_CONFIRMATION:
        raise HTTPException(status_code=409, detail="当前任务已经在等待下载确认，请直接继续该任务。")
    if source_task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=409, detail="当前任务仍在运行中，请等待筛选完成后再发起下载。")

    selected_count = _count_selected_items(Path(workdir) / "03_scored_candidates.jsonl")
    if selected_count <= 0:
        raise HTTPException(status_code=409, detail="当前没有已勾选的视频，无法开始下载。")

    download_task = _create_download_task_from_selection(source_task)
    _run_task_in_background(workdir, download_task.task_id, auto_confirm=True)
    return TaskDownloadLaunchResponse(
        task_id=download_task.task_id,
        source_task_id=source_task.task_id,
        status=download_task.status.value,
        message=f"已创建下载任务，准备下载 {selected_count} 条已勾选视频。",
    )


@app.get("/api/results", response_model=DownloadResultsResponse)
def get_download_results(workdir: str) -> DownloadResultsResponse:
    return _build_download_results_response(workdir)


@app.post("/api/results/retry-session", response_model=TaskDownloadLaunchResponse)
def retry_download_session(payload: RetryDownloadSessionRequest) -> TaskDownloadLaunchResponse:
    retry_session = _load_retryable_download_session(payload.workdir, payload.session_dir)
    retry_task = _create_retry_task_from_session(payload.workdir, retry_session)
    _run_task_in_background(payload.workdir, retry_task.task_id, auto_confirm=True)
    return TaskDownloadLaunchResponse(
        task_id=retry_task.task_id,
        source_task_id="",
        status=retry_task.status.value,
        message=f"已创建失败项重试任务，准备重试 {retry_session.failed_count} 条未成功视频。",
    )


@app.delete("/api/tasks/{task_id}", response_model=DeleteTaskResponse)
def delete_task(task_id: str, workdir: str) -> DeleteTaskResponse:
    store = TaskStore(workdir)
    task = _load_task_or_404(store, task_id)
    if task.status in {TaskStatus.RUNNING, TaskStatus.AWAITING_CONFIRMATION}:
        raise HTTPException(status_code=409, detail="Running tasks cannot be deleted")
    deleted_paths = _delete_task_download_artifacts(store, task_id)
    store.delete_task_dir(task_id)
    return DeleteTaskResponse(
        task_id=task_id,
        deleted_task_dir=True,
        deleted_download_paths=deleted_paths,
    )


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _serialize(value):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _serialize(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _load_task_or_404(store: TaskStore, task_id: str):
    try:
        return store.load_task(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}") from exc


def _status_label(status: str) -> str:
    labels = {
        TaskStatus.DRAFT.value: "草稿",
        TaskStatus.PLANNED.value: "待执行",
        TaskStatus.RUNNING.value: "运行中",
        TaskStatus.AWAITING_CONFIRMATION.value: "等待确认",
        TaskStatus.SUCCEEDED.value: "已完成",
        TaskStatus.FAILED.value: "失败",
        TaskStatus.CANCELLED.value: "已取消",
        StepStatus.PENDING.value: "待执行",
        StepStatus.RUNNING.value: "运行中",
        StepStatus.COMPLETED.value: "已完成",
        StepStatus.FAILED.value: "失败",
        StepStatus.SKIPPED.value: "已跳过",
        StepStatus.AWAITING_CONFIRMATION.value: "等待确认",
    }
    return labels.get(status, status or "-")


def _status_tone(status: str) -> str:
    if status in {TaskStatus.FAILED.value, StepStatus.FAILED.value}:
        return "danger"
    if status in {TaskStatus.AWAITING_CONFIRMATION.value, StepStatus.AWAITING_CONFIRMATION.value}:
        return "warn"
    if status in {TaskStatus.RUNNING.value, StepStatus.RUNNING.value}:
        return "info"
    if status in {TaskStatus.SUCCEEDED.value, StepStatus.COMPLETED.value}:
        return "success"
    return "neutral"


def _compute_metrics(task: TaskSpec, event_count: int) -> TaskMetricsView:
    total_steps = len(task.steps)
    completed_steps = sum(1 for step in task.steps if step.status == StepStatus.COMPLETED)
    failed_steps = sum(1 for step in task.steps if step.status == StepStatus.FAILED)
    awaiting_steps = sum(1 for step in task.steps if step.status == StepStatus.AWAITING_CONFIRMATION)
    pending_steps = max(total_steps - completed_steps - failed_steps - awaiting_steps, 0)
    return TaskMetricsView(
        total_steps=total_steps,
        completed_steps=completed_steps,
        failed_steps=failed_steps,
        pending_steps=pending_steps,
        awaiting_confirmation_steps=awaiting_steps,
        event_count=event_count,
    )


def _current_step(task: TaskSpec) -> tuple[str, str]:
    for step in task.steps:
        if step.status in {StepStatus.RUNNING, StepStatus.AWAITING_CONFIRMATION, StepStatus.FAILED}:
            return step.title, step.status.value
    for step in task.steps:
        if step.status == StepStatus.PENDING:
            return step.title, step.status.value
    if task.steps:
        last = task.steps[-1]
        return last.title, last.status.value
    return "", ""


def _progress_text(task: TaskSpec, metrics: TaskMetricsView) -> str:
    if metrics.total_steps <= 0:
        return "无步骤"
    if task.status == TaskStatus.AWAITING_CONFIRMATION:
        return f"已完成 {metrics.completed_steps}/{metrics.total_steps}，等待确认"
    if task.status == TaskStatus.SUCCEEDED:
        return f"已完成 {metrics.total_steps}/{metrics.total_steps}"
    if task.status == TaskStatus.FAILED:
        return f"已完成 {metrics.completed_steps}/{metrics.total_steps}，执行失败"
    return f"已完成 {metrics.completed_steps}/{metrics.total_steps}"


def _build_step_view(step) -> TaskStepView:
    return TaskStepView(
        step_id=step.step_id,
        title=step.title,
        tool_name=step.tool_name,
        status=step.status.value,
        requires_confirmation=step.requires_confirmation,
        message=step.message,
        has_result=bool(step.result),
    )


def _build_summary_view(summary: TaskSummary) -> TaskSummaryView:
    return TaskSummaryView(
        task_id=summary.task_id,
        title=summary.title,
        status=summary.status.value,
        updated_at=summary.updated_at,
        created_at=summary.created_at,
        current_step_index=summary.current_step_index,
        needs_confirmation=summary.needs_confirmation,
        last_message=summary.last_message,
        details=summary.details,
    )


def _build_failure_view(
    task: TaskSpec | None,
    result: TaskResult | None,
    *,
    summary: TaskSummary | None = None,
) -> TaskFailureDiagnosisView | None:
    payload = build_task_failure_diagnosis(task, result, summary=summary)
    if payload is None:
        return None
    return TaskFailureDiagnosisView(**payload)


def _build_result_view(
    result: TaskResult,
    *,
    task: TaskSpec | None = None,
    summary: TaskSummary | None = None,
) -> TaskResultView:
    return TaskResultView(
        task_id=result.task_id,
        status=result.status.value,
        message=result.message,
        started_at=result.started_at,
        finished_at=result.finished_at,
        has_data=bool(result.data),
        data=result.data,
        failure=_build_failure_view(task, result, summary=summary),
    )


def _build_event_view(event) -> TaskEventView:
    return TaskEventView(
        event_id=event.event_id,
        task_id=event.task_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        level=event.level,
        message=event.message,
        data=event.data,
    )


def _load_graph_checkpoint_state(workdir: str, task_id: str) -> dict[str, Any]:
    try:
        checkpoint = GraphCheckpointStore(workdir).load(task_id)
    except Exception:
        return {}
    if checkpoint is None:
        return {}
    _, state = checkpoint
    return dict(state)


def _graph_debug_enabled() -> bool:
    value = str(os.getenv("YTBDLP_ENABLE_GRAPH_DEBUG", "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _checkpoint_debug_lists(checkpoint_state: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    resolved_payload_keys = sorted(str(key) for key in (checkpoint_state.get("resolved_payloads") or {}).keys())
    step_result_keys = sorted(str(key) for key in (checkpoint_state.get("step_results") or {}).keys())
    runtime_default_keys = sorted(str(key) for key in (checkpoint_state.get("runtime_defaults") or {}).keys())
    return resolved_payload_keys, step_result_keys, runtime_default_keys


def _build_graph_debug_response(task: TaskSpec) -> TaskGraphDebugResponse:
    checkpoint_store = GraphCheckpointStore(task.workdir)
    checkpoint = checkpoint_store.load(task.task_id)
    checkpoint_payload = checkpoint_store.load_payload(task.task_id)
    if checkpoint is None or checkpoint_payload is None:
        return TaskGraphDebugResponse(
            enabled=True,
            task_id=task.task_id,
            task_status=task.status.value,
            planner_name="",
        )
    node_name, checkpoint_state = checkpoint
    resolved_payload_keys, step_result_keys, runtime_default_keys = _checkpoint_debug_lists(checkpoint_state)
    return TaskGraphDebugResponse(
        enabled=True,
        task_id=task.task_id,
        node_name=node_name,
        updated_at=str(checkpoint_payload.get("updated_at") or ""),
        task_status=task.status.value,
        planner_name=str(checkpoint_state.get("planner_name") or ""),
        planner_notes=[str(item) for item in (checkpoint_state.get("planner_notes") or []) if str(item).strip()],
        selected_step_id=str(checkpoint_state.get("selected_step_id") or ""),
        selected_step_index=checkpoint_state.get("selected_step_index"),
        pending_step_id=str(checkpoint_state.get("pending_step_id") or ""),
        failure_origin=str(checkpoint_state.get("failure_origin") or ""),
        last_error=dict(checkpoint_state.get("last_error") or {}),
        resolved_payload_keys=resolved_payload_keys,
        step_result_keys=step_result_keys,
        runtime_default_keys=runtime_default_keys,
    )


def _execution_step_view(step: TaskStep | None) -> TaskExecutionStepView | None:
    if step is None:
        return None
    return TaskExecutionStepView(
        step_id=step.step_id,
        title=step.title,
        tool_name=step.tool_name,
        status=step.status.value,
        status_label=_status_label(step.status.value),
        status_tone=_status_tone(step.status.value),
        message=step.message,
        requires_confirmation=step.requires_confirmation,
    )


def _next_step(task: TaskSpec) -> TaskStep | None:
    active = _active_step(task)
    seen_active = active is None
    for step in task.steps:
        if not seen_active:
            if active is step:
                seen_active = True
            continue
        if step.status == StepStatus.PENDING:
            return step
    return None


def _last_completed_step(task: TaskSpec) -> TaskStep | None:
    for step in reversed(task.steps):
        if step.status == StepStatus.COMPLETED:
            return step
    return None


def _failed_step(task: TaskSpec) -> TaskStep | None:
    for step in task.steps:
        if step.status == StepStatus.FAILED:
            return step
    return None


def _pending_confirmation_step(task: TaskSpec) -> TaskStep | None:
    for step in task.steps:
        if step.status == StepStatus.AWAITING_CONFIRMATION:
            return step
    return None


def _build_execution_insight(
    task: TaskSpec,
    *,
    events: list | None = None,
) -> TaskExecutionInsightView:
    checkpoint_state = _load_graph_checkpoint_state(task.workdir, task.task_id)
    completed_steps = sum(1 for step in task.steps if step.status == StepStatus.COMPLETED)
    recent_event = events[-1] if events else None
    return TaskExecutionInsightView(
        planner_name=str(checkpoint_state.get("planner_name") or ""),
        planner_notes=[str(item) for item in (checkpoint_state.get("planner_notes") or []) if str(item).strip()],
        current_step=_execution_step_view(_active_step(task)),
        next_step=_execution_step_view(_next_step(task)),
        last_completed_step=_execution_step_view(_last_completed_step(task)),
        pending_confirmation_step=_execution_step_view(_pending_confirmation_step(task)),
        failed_step=_execution_step_view(_failed_step(task)),
        recent_event=_build_event_view(recent_event).model_dump() if recent_event is not None else None,
        total_steps=len(task.steps),
        completed_steps=completed_steps,
        remaining_steps=max(len(task.steps) - completed_steps, 0),
    )


def _build_task_detail(
    store: TaskStore,
    task: TaskSpec,
    *,
    summary: TaskSummary | None,
    event_count: int,
    events: list | None = None,
) -> TaskDetailView:
    metrics = _compute_metrics(task, event_count=event_count)
    current_step_title, current_step_status = _current_step(task)
    return TaskDetailView(
        task_id=task.task_id,
        title=task.title,
        user_request=task.user_request,
        intent=task.intent,
        status=task.status.value,
        status_label=_status_label(task.status.value),
        status_tone=_status_tone(task.status.value),
        workdir=task.workdir,
        created_at=task.created_at,
        updated_at=summary.updated_at if summary is not None else task.updated_at,
        current_step_index=task.current_step_index,
        needs_confirmation=task.needs_confirmation,
        current_step_title=current_step_title,
        current_step_status=current_step_status,
        progress_text=_progress_text(task, metrics),
        active_elapsed_seconds=_compute_active_elapsed_seconds(store, task),
        metrics=metrics,
        steps=[_build_step_view(step) for step in task.steps],
        execution=_build_execution_insight(task, events=events),
        params=task.params,
        task_paths=store.task_paths(task.task_id),
        download_progress=_build_download_progress_view(store.load_download_progress(task.task_id)),
    )


def _build_task_card(store: TaskStore, summary: TaskSummary) -> TaskCardView:
    task = store.load_task(summary.task_id)
    event_count = len(store.load_events(summary.task_id))
    metrics = _compute_metrics(task, event_count=event_count)
    current_step_title, current_step_status = _current_step(task)
    return TaskCardView(
        task_id=task.task_id,
        title=summary.title or task.title or "未命名任务",
        status=summary.status.value,
        status_label=_status_label(summary.status.value),
        status_tone=_status_tone(summary.status.value),
        updated_at=summary.updated_at,
        created_at=summary.created_at,
        last_message=summary.last_message,
        needs_confirmation=summary.needs_confirmation,
        current_step_title=current_step_title,
        current_step_status=current_step_status,
        progress_text=_progress_text(task, metrics),
        badge_text="需确认" if summary.needs_confirmation else f"{metrics.completed_steps}/{metrics.total_steps} 步",
        metrics=metrics,
    )


def _build_focus_summary(store: TaskStore, task: TaskSpec) -> TaskFocusSummaryView:
    workdir = Path(task.workdir)
    vector_summary = _agent_vector_summary(workdir / "02b_vector_scored_candidates.jsonl")
    return TaskFocusSummaryView(
        task_id=task.task_id,
        workdir=task.workdir,
        selected_url_count=_count_selected_urls(workdir),
        metadata_total=_count_jsonl_records(workdir / "02_detailed_candidates.jsonl"),
        metadata_ok=_count_jsonl_records(workdir / "02_detailed_candidates.jsonl", predicate=lambda item: not item.get("detail_error")),
        vector_total=int(vector_summary["total"]),
        vector_max_score=float(vector_summary["max_score"]),
        vector_average_score=float(vector_summary["average_score"]),
        vector_low_similarity=int(vector_summary["low_similarity"]),
        vector_threshold=float(vector_summary["threshold"]),
        filter_failure_summary=_summarize_filter_failures(workdir),
        task_paths=store.task_paths(task.task_id),
    )


def _build_queue_overview(summaries: list[TaskSummary]) -> QueueOverviewView:
    overview = QueueOverviewView(total=len(summaries))
    for summary in summaries:
        status = summary.status.value
        if status == TaskStatus.PLANNED.value:
            overview.planned += 1
        elif status == TaskStatus.RUNNING.value:
            overview.running += 1
        elif status == TaskStatus.AWAITING_CONFIRMATION.value:
            overview.awaiting_confirmation += 1
        elif status == TaskStatus.SUCCEEDED.value:
            overview.succeeded += 1
        elif status == TaskStatus.FAILED.value:
            overview.failed += 1
        elif status == TaskStatus.CANCELLED.value:
            overview.cancelled += 1
    overview.needs_attention = overview.awaiting_confirmation + overview.failed
    return overview


def _build_download_settings_view(workdir: str, defaults: dict[str, object] | None) -> DownloadSettingsView:
    payload = defaults or {}
    base_download_dir = default_download_dir()
    return DownloadSettingsView(
        workdir=workdir,
        download_dir=str(payload.get("download_dir") or base_download_dir),
        download_mode=str(payload.get("download_mode") or "video"),
        include_audio=bool(payload.get("include_audio", True)),
        video_container=str(payload.get("video_container") or "auto"),
        max_height=int(payload["max_height"]) if payload.get("max_height") not in {None, ""} else None,
        audio_format=str(payload.get("audio_format") or "best"),
        audio_quality=int(payload["audio_quality"]) if payload.get("audio_quality") not in {None, ""} else None,
        concurrent_videos=max(1, int(payload.get("concurrent_videos") or 1)),
        concurrent_fragments=max(1, int(payload.get("concurrent_fragments") or 4)),
        sponsorblock_remove=str(payload.get("sponsorblock_remove") or ""),
        clean_video=bool(payload.get("clean_video", False)),
    )


def _build_log_view(log) -> TaskLogLineView:
    return TaskLogLineView(
        log_id=log.log_id,
        task_id=log.task_id,
        timestamp=log.timestamp,
        kind=log.kind,
        message=log.message,
        data=log.data,
    )


def _build_download_progress_view(progress: TaskDownloadProgress | None) -> TaskDownloadProgressView | None:
    if progress is None:
        return None
    return TaskDownloadProgressView(
        phase=progress.phase,
        percent=progress.percent,
        downloaded_bytes=progress.downloaded_bytes,
        total_bytes=progress.total_bytes,
        speed_text=progress.speed_text,
        current_video_id=progress.current_video_id,
        current_video_label=progress.current_video_label,
        updated_at=progress.updated_at,
    )


def _status_label(status: str) -> str:
    labels = {
        TaskStatus.DRAFT.value: "草稿",
        TaskStatus.PLANNED.value: "待执行",
        TaskStatus.RUNNING.value: "运行中",
        TaskStatus.AWAITING_CONFIRMATION.value: "等待确认",
        TaskStatus.SUCCEEDED.value: "已完成",
        TaskStatus.FAILED.value: "失败",
        TaskStatus.CANCELLED.value: "已取消",
        StepStatus.PENDING.value: "待执行",
        StepStatus.RUNNING.value: "运行中",
        StepStatus.COMPLETED.value: "已完成",
        StepStatus.FAILED.value: "失败",
        StepStatus.SKIPPED.value: "已跳过",
        StepStatus.AWAITING_CONFIRMATION.value: "等待确认",
    }
    return labels.get(status, status or "-")


def _progress_text(task: TaskSpec, metrics: TaskMetricsView) -> str:
    if metrics.total_steps <= 0:
        return "暂无可执行步骤"
    if task.status == TaskStatus.AWAITING_CONFIRMATION:
        return f"已完成 {metrics.completed_steps}/{metrics.total_steps}，等待确认继续"
    if task.status == TaskStatus.SUCCEEDED:
        return f"已完成 {metrics.total_steps}/{metrics.total_steps}"
    if task.status == TaskStatus.FAILED:
        return f"已完成 {metrics.completed_steps}/{metrics.total_steps}，任务失败"
    return f"已完成 {metrics.completed_steps}/{metrics.total_steps}"


def _active_step(task: TaskSpec):
    for step in task.steps:
        if step.status in {StepStatus.RUNNING, StepStatus.AWAITING_CONFIRMATION, StepStatus.FAILED}:
            return step
    for step in task.steps:
        if step.status == StepStatus.PENDING:
            return step
    if task.steps:
        return task.steps[-1]
    return None


def _is_download_step(step) -> bool:
    if step is None:
        return False
    return step.tool_name in {"start_download", "retry_failed_downloads"}


def _workspace_stage_label(stage: str) -> str:
    labels = {
        "planned": "任务准备中",
        "awaiting_confirmation": "等待确认下载",
        "preparing_download": "准备下载中",
        "downloading": "正在下载",
        "finalizing": "整理下载结果",
        "completed": "下载已完成",
        "failed": "任务失败",
    }
    return labels.get(stage, "任务准备中")


def _panel_state(
    *,
    state: str,
    tone: str,
    eyebrow: str,
    title: str,
    message: str,
    action_label: str = "",
    action: str = "",
    action_style: str = "btn2",
) -> PanelStateView:
    return PanelStateView(
        state=state,
        tone=tone,
        eyebrow=eyebrow,
        title=title,
        message=message,
        action_label=action_label,
        action=action,
        action_style=action_style,
    )


def _review_panel_state(task: TaskSpec, workspace_stage: str, empty_message: str) -> PanelStateView:
    if workspace_stage == "failed":
        return _panel_state(
            state="failed",
            tone="danger",
            eyebrow="需要处理",
            title="候选视频当前不可用",
            message=empty_message or "这次任务未能产出可审核候选。可以先查看失败原因或日志，再决定是否重试。",
            action_label="查看状态",
            action="go-status",
        )
    if workspace_stage in {"preparing_download", "downloading", "finalizing", "completed"}:
        return _panel_state(
            state="empty",
            tone="neutral",
            eyebrow="没有候选",
            title="当前任务没有可审核的视频",
            message=empty_message or "这次任务已经进入下载或收尾阶段，审核面板里没有可继续调整的候选视频。",
            action_label="查看结果",
            action="go-results",
        )
    if workspace_stage in {"planned", "awaiting_confirmation"}:
        return _panel_state(
            state="waiting",
            tone="info",
            eyebrow="等待候选",
            title="候选视频还在准备中",
            message=empty_message or "任务完成搜索和筛选后，这里会显示标题、封面和勾选入口。",
            action_label="查看状态",
            action="go-status",
        )
    return _panel_state(
        state="empty",
        tone="neutral",
        eyebrow="没有候选",
        title="当前任务还没有候选视频",
        message=empty_message or "如果任务还在搜索或筛选，稍后再回来查看；如果已经完成，可以检查日志确认发生了什么。",
        action_label="查看状态",
        action="go-status",
    )


def _results_panel_state(empty_message: str) -> PanelStateView:
    return _panel_state(
        state="empty",
        tone="neutral",
        eyebrow="还没有结果",
        title="这里还没有已下载视频",
        message=empty_message or "完成一次下载后，这里会展示最新会话和可直接打开的视频。",
        action_label="创建新任务",
        action="focus-run",
    )


def _logs_panel_state(count: int) -> PanelStateView | None:
    if count > 0:
        return None
    return _panel_state(
        state="waiting",
        tone="neutral",
        eyebrow="暂无输出",
        title="当前任务暂时没有日志输出",
        message="如果任务刚启动，稍后刷新即可；如果长时间为空，可以回到状态页确认任务是否真的开始执行。",
    )


def _resolve_download_entry(task: TaskSpec, result: TaskResult | None, stage: str) -> TaskWorkspaceDownloadEntryView:
    store = TaskStore(task.workdir)
    session_ref = store.load_download_session_ref(task.task_id)
    session_dir = session_ref.session_dir
    if session_dir:
        path = session_dir
    else:
        defaults = SessionStore(task.workdir).get_defaults()
        path = str(download_workspace_paths(task.workdir, defaults=defaults, params=task.params).download_dir)
    ready = stage == "completed" and Path(path).exists()
    label = "打开已下载视频" if ready else "查看目标目录"
    return TaskWorkspaceDownloadEntryView(path=path, label=label, ready=ready)


def _build_workspace_state(
    task: TaskSpec,
    *,
    summary: TaskSummary | None,
    result: TaskResult | None,
    download_progress: TaskDownloadProgress | None,
    failure: TaskFailureDiagnosisView | None = None,
) -> dict[str, object]:
    metrics = _compute_metrics(task, event_count=0)
    active_step = _active_step(task)
    stage = "planned"

    if task.status == TaskStatus.AWAITING_CONFIRMATION:
        stage = "awaiting_confirmation"
    elif task.status == TaskStatus.SUCCEEDED:
        stage = "completed"
    elif task.status == TaskStatus.FAILED:
        stage = "failed"
    elif task.status == TaskStatus.RUNNING and download_progress is not None and download_progress.phase == "downloading":
        stage = "downloading"
    elif task.status == TaskStatus.RUNNING and download_progress is not None and download_progress.phase == "completed":
        stage = "finalizing"
    elif task.status == TaskStatus.RUNNING and _is_download_step(active_step):
        stage = "preparing_download"
    elif task.status in {TaskStatus.RUNNING, TaskStatus.PLANNED, TaskStatus.DRAFT}:
        stage = "planned"

    stage_label = _workspace_stage_label(stage)
    progress_text = _progress_text(task, metrics)
    last_message = ""
    if result is not None and result.message:
        last_message = result.message
    elif summary is not None and summary.last_message:
        last_message = summary.last_message
    elif active_step is not None and active_step.message:
        last_message = active_step.message

    if failure is None:
        failure = _build_failure_view(task, result, summary=summary)

    if stage == "awaiting_confirmation":
        primary_message = f"当前任务需要你确认后才能开始下载。确认后将继续执行“{active_step.title if active_step else '下载步骤'}”。"
        confirmation = TaskWorkspaceConfirmationView(
            required=True,
            step_title=active_step.title if active_step is not None else "",
            cta_label="确认下载并继续",
        )
    elif stage == "preparing_download":
        primary_message = "已确认，正在准备下载环境并启动下载任务。"
        confirmation = None
    elif stage == "downloading":
        label = download_progress.current_video_label or download_progress.current_video_id or "当前视频"
        speed = download_progress.speed_text or "-"
        primary_message = f"正在下载 {label}，当前速度 {speed}。"
        confirmation = None
    elif stage == "finalizing":
        primary_message = "下载数据已完成，正在整理下载结果和输出目录。"
        confirmation = None
    elif stage == "completed":
        primary_message = result.message if result is not None and result.message else "下载已完成，可以直接打开目录查看视频。"
        confirmation = None
    elif stage == "failed":
        primary_message = (
            failure.summary
            if failure is not None and failure.summary
            else result.message if result is not None and result.message
            else last_message or "任务执行失败，请查看日志。"
        )
        confirmation = None
    else:
        primary_message = last_message or progress_text or "任务已创建，等待开始执行。"
        confirmation = None

    return {
        "workspace_stage": stage,
        "workspace_stage_label": stage_label,
        "primary_message": primary_message,
        "confirmation": confirmation,
        "download_entry": _resolve_download_entry(task, result, stage),
    }


def _review_editable(task: TaskSpec, stage: str) -> bool:
    if stage in {"preparing_download", "downloading", "finalizing"}:
        return False
    workdir = Path(task.workdir)
    return any((workdir / name).exists() for name in {"03_scored_candidates.jsonl", "04_selected_for_review.csv", "05_selected_urls.txt"})


def _review_status(item: dict[str, object]) -> tuple[str, str]:
    selected = bool(item.get("selected"))
    agent_selected = bool(item.get("agent_selected"))
    if bool(item.get("manual_review")):
        return "需复核", "warn"
    if selected and not agent_selected:
        return "手动保留", "info"
    if not selected and agent_selected:
        return "手动排除", "neutral"
    if selected:
        return "待下载", "success"
    if bool(item.get("low_similarity")):
        return "低相似", "danger"
    return "候选观察", "neutral"


def _review_decision(item: dict[str, object]) -> tuple[str, str]:
    selected = bool(item.get("selected"))
    agent_selected = bool(item.get("agent_selected"))
    if bool(item.get("manual_review")):
        return (
            "建议先人工核对",
            "这条结果处在边界区，建议先看标题、来源和摘要，再决定是否保留到下载队列。",
        )
    if bool(item.get("low_similarity")) and not selected:
        return (
            "语义相似度偏低",
            "当前分数低于阈值，默认不建议下载；如果你确认内容相关，可以手动保留。",
        )
    if selected and not agent_selected:
        return (
            "已手动加入下载",
            "这条视频原本不在自动推荐集合中，当前已由你手动保留到下载队列。",
        )
    if not selected and agent_selected:
        return (
            "已手动移出下载",
            "这条视频原本在自动推荐集合中，当前已由你手动排除，不会进入下载。",
        )
    if selected:
        return (
            "自动推荐通过",
            "这条视频已通过当前筛选规则，可以直接进入下载。",
        )
    return (
        "当前未加入下载",
        "这条结果仍保留在候选列表里，但当前不会进入最终下载队列。",
    )


def _build_review_item_view(item: dict[str, object], index: int) -> TaskReviewItemView:
    duration_value = item.get("duration")
    try:
        duration_seconds = int(duration_value) if duration_value not in {None, ""} else None
    except (TypeError, ValueError):
        duration_seconds = None
    low_similarity = is_low_similarity(item)
    selected = bool(item.get("selected"))
    agent_selected = bool(item.get("agent_selected"))
    status_label, status_tone = _review_status(
        {
            "selected": selected,
            "agent_selected": agent_selected,
            "manual_review": bool(item.get("manual_review")),
            "low_similarity": low_similarity,
        }
    )
    decision_label, decision_detail = _review_decision(
        {
            "selected": selected,
            "agent_selected": agent_selected,
            "manual_review": bool(item.get("manual_review")),
            "low_similarity": low_similarity,
        }
    )
    vector_score = item.get("vector_score")
    try:
        vector_score_value = float(vector_score) if vector_score not in {None, ""} else None
    except (TypeError, ValueError):
        vector_score_value = None
    score = item.get("score")
    try:
        score_value = int(score) if score not in {None, ""} else None
    except (TypeError, ValueError):
        score_value = None
    return TaskReviewItemView(
        selection_key=candidate_selection_key(item, index),
        video_id=str(item.get("video_id") or ""),
        title=str(item.get("title") or ""),
        channel=str(item.get("channel") or ""),
        watch_url=str(item.get("watch_url") or ""),
        thumbnail_url=thumbnail_url(str(item.get("video_id") or "")),
        upload_date=str(item.get("upload_date") or ""),
        duration_seconds=duration_seconds,
        duration_label=format_duration_label(duration_seconds),
        description_preview=compact_preview(item.get("description_preview") or item.get("description")),
        reasons_summary=summarize_reasons(item.get("reasons") or item.get("vector_reason")),
        selected=selected,
        agent_selected=agent_selected,
        manual_review=bool(item.get("manual_review")),
        selection_modified=selected != agent_selected,
        low_similarity=low_similarity,
        score=score_value,
        vector_score=vector_score_value,
        status_label=status_label,
        status_tone=status_tone,
        decision_label=decision_label,
        decision_detail=decision_detail,
    )


def _build_review_response(store: TaskStore, task: TaskSpec) -> TaskReviewResponse:
    summary = store.load_summary(task.task_id)
    result = store.load_result(task.task_id)
    download_progress = store.load_download_progress(task.task_id)
    workspace = _build_workspace_state(task, summary=summary, result=result, download_progress=download_progress)
    workdir = Path(task.workdir)
    all_jsonl_path = str(workdir / "03_scored_candidates.jsonl")
    selected_csv_path = str(workdir / "04_selected_for_review.csv")
    selected_urls_path = str(workdir / "05_selected_urls.txt")
    try:
        items = load_review_items(workdir)
    except FileNotFoundError:
        empty_message = "当前还没有可审核的视频候选。完成筛选后，这里会显示标题、封面和下载勾选入口。"
        return TaskReviewResponse(
            task_id=task.task_id,
            workdir=task.workdir,
            available=False,
            editable=False,
            empty_message=empty_message,
            panel_state=_review_panel_state(task, str(workspace["workspace_stage"] or ""), empty_message),
            all_jsonl_path=all_jsonl_path,
            selected_csv_path=selected_csv_path,
            selected_urls_path=selected_urls_path,
        )

    summary_payload = review_summary(items)
    review_items = [_build_review_item_view(item, index) for index, item in enumerate(items)]
    return TaskReviewResponse(
        task_id=task.task_id,
        workdir=task.workdir,
        available=bool(review_items),
        editable=_review_editable(task, str(workspace["workspace_stage"] or "")),
        empty_message="" if review_items else "当前还没有可审核的视频候选。",
        panel_state=None if review_items else _review_panel_state(task, str(workspace["workspace_stage"] or ""), "当前还没有可审核的视频候选。"),
        items=review_items,
        summary=TaskReviewSummaryView(**summary_payload),
        all_jsonl_path=all_jsonl_path,
        selected_csv_path=selected_csv_path,
        selected_urls_path=selected_urls_path,
    )


def _count_selected_items(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            payload = line.strip()
            if not payload:
                continue
            item = json.loads(payload)
            if item.get("selected"):
                total += 1
    except Exception:
        return 0
    return total


def _build_download_session_view(session) -> DownloadSessionView:
    return DownloadSessionView(
        session_name=session.session_name,
        session_dir=session.session_dir,
        created_at=session.created_at,
        report_path=session.report_path,
        failed_urls_file=session.failed_urls_file,
        retry_available=session.retry_available,
        source_task_id=session.source_task_id,
        source_task_title=session.source_task_title,
        source_task_status=session.source_task_status,
        source_task_available=session.source_task_available,
        source_task_user_request=session.source_task_user_request,
        source_task_intent=session.source_task_intent,
        video_count=session.video_count,
        success_count=session.success_count,
        failed_count=session.failed_count,
        items=[
            DownloadedVideoView(
                video_id=item.video_id,
                title=item.title,
                upload_date=item.upload_date,
                watch_url=item.watch_url,
                success=item.success,
                file_path=item.file_path,
                thumbnail_url=item.thumbnail_url,
                file_size_bytes=item.file_size_bytes,
            )
            for item in session.items
        ],
    )


def _build_download_results_response(workdir: str) -> DownloadResultsResponse:
    session = SessionStore(workdir)
    defaults = session.get_defaults()
    snapshot = load_download_results(workdir, defaults=defaults)
    sessions = []
    for item in snapshot.sessions:
        retry_file = resolve_retry_failed_urls_file(workdir, item.session_dir, defaults=defaults)
        if retry_file != item.failed_urls_file or (bool(retry_file) != item.retry_available):
            item = type(item)(
                session_name=item.session_name,
                session_dir=item.session_dir,
                created_at=item.created_at,
                report_path=item.report_path,
                failed_urls_file=retry_file,
                retry_available=bool(retry_file),
                source_task_id=item.source_task_id,
                source_task_title=item.source_task_title,
                source_task_status=item.source_task_status,
                source_task_available=item.source_task_available,
                video_count=item.video_count,
                success_count=item.success_count,
                failed_count=item.failed_count,
                items=item.items,
            )
        sessions.append(item)
    latest = sessions[0] if sessions else None
    session.update_recent_result_context(
        {
            "download_dir": snapshot.download_dir,
            "total_sessions": snapshot.total_sessions,
            "total_videos": snapshot.total_videos,
            "latest_session_name": latest.session_name if latest is not None else "",
            "session_dir": latest.session_dir if latest is not None else "",
            "report_csv": latest.report_path if latest is not None else "",
            "source_task_id": latest.source_task_id if latest is not None else "",
            "source_task_title": latest.source_task_title if latest is not None else "",
            "source_task_status": latest.source_task_status if latest is not None else "",
            "video_count": latest.video_count if latest is not None else 0,
            "success_count": latest.success_count if latest is not None else 0,
            "failed_count": latest.failed_count if latest is not None else 0,
        }
    )
    return DownloadResultsResponse(
        workdir=snapshot.workdir,
        download_dir=snapshot.download_dir,
        available=snapshot.available,
        total_sessions=snapshot.total_sessions,
        total_videos=snapshot.total_videos,
        empty_message=snapshot.empty_message,
        panel_state=None if snapshot.available else _results_panel_state(snapshot.empty_message),
        sessions=[_build_download_session_view(session) for session in sessions],
    )


def _download_task_payload(source_task: TaskSpec) -> dict[str, object]:
    defaults = SessionStore(source_task.workdir).get_defaults()
    return build_download_task_payload(
        source_task.workdir,
        defaults=defaults,
        params=source_task.params,
    )


def _load_retryable_download_session(workdir: str, session_dir: str):
    defaults = SessionStore(workdir).get_defaults()
    paths = download_workspace_paths(workdir, defaults=defaults)
    requested_path = Path(session_dir).expanduser()
    if not requested_path.is_absolute():
        requested_path = paths.download_dir / requested_path
    try:
        resolved_session_dir = requested_path.resolve()
        resolved_download_dir = paths.download_dir.resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="未找到对应的下载会话。")
    if not resolved_session_dir.exists() or not resolved_session_dir.is_dir():
        raise HTTPException(status_code=404, detail="未找到对应的下载会话。")
    if resolved_session_dir != resolved_download_dir and resolved_download_dir not in resolved_session_dir.parents:
        raise HTTPException(status_code=404, detail="未找到对应的下载会话。")
    session = load_download_session(resolved_session_dir)
    if not session.session_dir:
        raise HTTPException(status_code=404, detail="未找到对应的下载会话。")
    retry_file = resolve_retry_failed_urls_file(workdir, session.session_dir, defaults=defaults)
    if not retry_file:
        raise HTTPException(status_code=409, detail="这个下载会话没有可直接重试的失败 URL。")
    if session.failed_count <= 0:
        raise HTTPException(status_code=409, detail="这个下载会话没有失败项，无需重试。")
    if retry_file != session.failed_urls_file or not session.retry_available:
        session = type(session)(
            session_name=session.session_name,
            session_dir=session.session_dir,
            created_at=session.created_at,
            report_path=session.report_path,
            failed_urls_file=retry_file,
            retry_available=True,
            source_task_id=session.source_task_id,
            source_task_title=session.source_task_title,
            source_task_status=session.source_task_status,
            source_task_available=session.source_task_available,
            video_count=session.video_count,
            success_count=session.success_count,
            failed_count=session.failed_count,
            items=session.items,
        )
    return session


def _create_retry_task_from_session(workdir: str, session) -> TaskSpec:
    store = TaskStore(workdir)
    retry_seed = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = build_retry_task_payload(
        workdir,
        defaults=SessionStore(workdir).get_defaults(),
        failed_urls_file=session.failed_urls_file,
        download_session_name=f"retry_{session.session_name}_{retry_seed}",
    )
    return store.create_task(
        title=f"重试失败视频 · {session.session_name or '下载会话'}",
        user_request=f"重试下载失败项: {session.session_name or session.session_dir}",
        intent="retry_failed_downloads",
        params=payload,
        steps=[
            TaskStep(
                step_id="retry_download",
                title="重试失败视频",
                tool_name="retry_failed_downloads",
                payload=payload,
                requires_confirmation=False,
                status=StepStatus.PENDING,
            )
        ],
    )


def _create_download_task_from_selection(source_task: TaskSpec) -> TaskSpec:
    store = TaskStore(source_task.workdir)
    payload = _download_task_payload(source_task)
    return store.create_task(
        title=f"下载已勾选视频 · {source_task.title or source_task.task_id}",
        user_request=f"下载已勾选视频: {source_task.title or source_task.user_request}",
        intent="download_selected_reviewed_videos",
        params=payload,
        steps=[
            TaskStep(
                step_id="download",
                title="下载已勾选视频",
                tool_name="start_download",
                payload=payload,
                requires_confirmation=False,
                status=StepStatus.PENDING,
            )
        ],
    )


def _run_task_worker(workdir: str, task_id: str, auto_confirm: bool) -> None:
    store = TaskStore(workdir)
    task = store.load_task(task_id)
    runner = AgentRunner()
    with runtime_host.background_job(f"task:{task_id}"):
        try:
            runner.resume(workdir, task_id=task_id, auto_confirm=auto_confirm)
        except Exception as exc:
            store.set_task_status(task, TaskStatus.FAILED, f"后台下载任务启动失败: {exc}")
            store.save_result(
                TaskResult(
                    task_id=task.task_id,
                    status=TaskStatus.FAILED,
                    message=str(exc),
                    data={"task_paths": store.task_paths(task.task_id)},
                    started_at=task.created_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
            )


def _run_task_in_background(workdir: str, task_id: str, *, auto_confirm: bool) -> None:
    thread = threading.Thread(
        target=_run_task_worker,
        args=(workdir, task_id, auto_confirm),
        daemon=True,
        name=f"ytbdlp-task-{task_id}",
    )
    thread.start()


def _parse_iso_timestamp(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_active_elapsed_seconds(store: TaskStore, task: TaskSpec) -> float | None:
    events = store.load_events(task.task_id)
    running_started_at: datetime | None = None
    total_seconds = 0.0
    saw_running = False
    now = datetime.now(timezone.utc)

    for event in events:
        if event.event_type != "task_status":
            continue
        status = str((event.data or {}).get("status") or "").strip().lower()
        ts = _parse_iso_timestamp(event.timestamp)
        if ts is None:
            continue
        if status == TaskStatus.RUNNING.value:
            running_started_at = ts
            saw_running = True
            continue
        if running_started_at is not None:
            total_seconds += max((ts - running_started_at).total_seconds(), 0.0)
            running_started_at = None

    if running_started_at is not None:
        total_seconds += max((now - running_started_at).total_seconds(), 0.0)

    if not saw_running:
        return None
    return total_seconds


def _delete_task_download_artifacts(store: TaskStore, task_id: str) -> list[str]:
    result = store.load_result(task_id)
    if result is None:
        return []
    task_dir = Path(store.task_paths(task_id)["task_dir"]).resolve()
    workdir = Path(store.workdir).resolve()
    candidates = {
        str(path): path
        for path in collect_result_artifact_paths(result)
    }

    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    def _looks_shared_workdir_file(path: Path) -> bool:
        if path.is_dir():
            return False
        if not _is_relative_to(path, workdir):
            return False
        return path.parent == workdir

    def _safe_delete(path: Path) -> bool:
        if not path.exists():
            return False
        if path == workdir or path == task_dir or path == workdir.parent or path == Path(path.anchor):
            return False
        if _looks_shared_workdir_file(path):
            return False
        if path.is_dir():
            for protected in {workdir, task_dir, Path.home().resolve()}:
                if path == protected:
                    return False
            import shutil
            shutil.rmtree(path, ignore_errors=True)
            return not path.exists()
        path.unlink(missing_ok=True)
        return not path.exists()

    deleted: list[str] = []
    for raw_path, resolved_path in candidates.items():
        if _safe_delete(resolved_path):
            deleted.append(str(resolved_path))
    return sorted(set(deleted))


def _sort_summaries(summaries: list[TaskSummary], *, sort: str) -> list[TaskSummary]:
    normalized = (sort or "updated_desc").strip().lower()
    if normalized == "created_desc":
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)
    if normalized == "status_grouped":
        rank = {
            TaskStatus.RUNNING.value: 0,
            TaskStatus.AWAITING_CONFIRMATION.value: 1,
            TaskStatus.PLANNED.value: 2,
            TaskStatus.FAILED.value: 3,
            TaskStatus.SUCCEEDED.value: 4,
            TaskStatus.CANCELLED.value: 5,
            TaskStatus.DRAFT.value: 6,
        }
        return sorted(summaries, key=lambda item: (rank.get(item.status.value, 99), item.updated_at), reverse=False)
    return sorted(summaries, key=lambda item: item.updated_at, reverse=True)


def _summary_matches_filters(summary: TaskSummary, *, status: str, needs_attention: bool, query_text: str) -> bool:
    normalized_status = status.strip().lower()
    if normalized_status:
        if normalized_status == "needs_attention":
            if summary.status.value not in {TaskStatus.AWAITING_CONFIRMATION.value, TaskStatus.FAILED.value}:
                return False
        elif summary.status.value != normalized_status:
            return False
    if needs_attention and summary.status.value not in {TaskStatus.AWAITING_CONFIRMATION.value, TaskStatus.FAILED.value}:
        return False
    normalized_query = query_text.strip().lower()
    if normalized_query:
        haystack = "\n".join([
            summary.task_id,
            summary.title,
            summary.last_message,
            str(summary.details.get("intent", "")),
            str(summary.workdir),
        ]).lower()
        if normalized_query not in haystack:
            return False
    return True


def _count_selected_urls(workdir: Path) -> int:
    path = workdir / "05_selected_urls.txt"
    if not path.exists():
        return 0
    try:
        return len([
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and line.strip().startswith("http")
        ])
    except Exception:
        return 0


def _count_jsonl_records(path: Path, predicate=None) -> int:
    if not path.exists():
        return 0
    count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                item = json.loads(s)
            except Exception:
                continue
            if predicate is None or predicate(item):
                count += 1
    except Exception:
        return 0
    return count


def _normalize_filter_reason_label(reason: str) -> str:
    text = (reason or "").strip()
    if not text:
        return ""
    if "关键词核心匹配: 不通过" in text:
        return "关键词未命中"
    if "主题核心词检查: 未命中" in text:
        return "主题词未命中"
    if "YouTube召回兜底入选" in text:
        return "召回兜底入选"
    if "软评分未入选" in text:
        return "软评分不足"
    if "软评分入选" in text:
        return "软评分入选"
    if "详细元数据提取失败" in text:
        return "元数据提取失败"
    if "时长不足" in text:
        return "时长不足"
    if "上传年 " in text or "无上传日期" in text:
        return "年份不匹配/缺失"
    if "直播/直播回放/待开始" in text:
        return "直播或回放"
    if "可用性受限" in text:
        return "可用性受限"
    return text


def _summarize_filter_failures(workdir: Path) -> str:
    scored_path = workdir / "03_scored_candidates.jsonl"
    if not scored_path.exists():
        return ""
    total = 0
    selected = 0
    reason_counts: dict[str, int] = {}
    try:
        for line in scored_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            item = json.loads(s)
            total += 1
            if item.get("selected"):
                selected += 1
                continue
            for part in [seg.strip() for seg in str(item.get("reasons") or "").split(" | ") if seg.strip()]:
                label = _normalize_filter_reason_label(part)
                if label:
                    reason_counts[label] = reason_counts.get(label, 0) + 1
    except Exception:
        return ""
    if total == 0:
        return "没有候选结果。"
    if selected > 0:
        return ""
    top_reasons = sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    if not top_reasons:
        return f"共 {total} 个候选，未生成可下载 URL。"
    summary = "，".join(f"{label}({count})" for label, count in top_reasons)
    return f"共 {total} 个候选，主要原因：{summary}"


def _agent_vector_summary(vector_path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "total": 0,
        "topk": 0,
        "max_score": 0.0,
        "average_score": 0.0,
        "low_similarity": 0,
        "threshold": 0.12,
    }
    if not vector_path.exists():
        return summary
    scores: list[float] = []
    try:
        for line in vector_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                item = json.loads(s)
            except Exception:
                continue
            summary["total"] = int(summary["total"]) + 1
            try:
                score = float(item.get("vector_score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            scores.append(score)
            if item.get("semantic_selected"):
                summary["topk"] = int(summary["topk"]) + 1
            if score < float(summary["threshold"]):
                summary["low_similarity"] = int(summary["low_similarity"]) + 1
    except Exception:
        return summary
    if scores:
        summary["max_score"] = max(scores)
        summary["average_score"] = sum(scores) / len(scores)
    return summary


def _error_payload(
    exc: Exception,
    *,
    user_title: str,
    user_message: str,
    user_recovery: str,
    phase: str,
) -> dict:
    return {
        "kind": "unexpected_error",
        "code": "unexpected_error",
        "phase": phase,
        "message": str(exc),
        "error_category": "unknown",
        "user_title": user_title,
        "user_message": user_message,
        "user_recovery": user_recovery,
        "user_actions": ["重试"],
        "details": {},
    }
