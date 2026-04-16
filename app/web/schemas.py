from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    product_mode: str = "web-first"


class AppBootstrapResponse(BaseModel):
    product_mode: str = "web-first"
    workdir: str
    recommended_download_dir: str
    workdir_source: str = "system_default"


class AgentConnectionTestRequest(BaseModel):
    llm_provider: str = Field(default="")
    llm_base_url: str = Field(default="")
    llm_model: str = Field(default="")
    llm_api_key: str = Field(default="")


class AgentPlanRequest(AgentConnectionTestRequest):
    user_request: str
    workdir: str


class AgentRunRequest(AgentPlanRequest):
    auto_confirm: bool = False


class AgentResumeRequest(AgentConnectionTestRequest):
    workdir: str
    task_id: str = ""
    auto_confirm: bool = False


class OpenPathRequest(BaseModel):
    path: str


class DownloadSettingsView(BaseModel):
    workdir: str
    download_dir: str = ""
    download_mode: str = "video"
    include_audio: bool = True
    video_container: str = "auto"
    max_height: int | None = None
    audio_format: str = "best"
    audio_quality: int | None = None
    concurrent_videos: int = 1
    concurrent_fragments: int = 4
    sponsorblock_remove: str = ""
    clean_video: bool = False


class TaskQuery(BaseModel):
    workdir: str
    limit: int = 20


class AgentErrorResponse(BaseModel):
    ok: bool = False
    code: str
    error_category: str = "unknown"
    message: str
    user_title: str = ""
    user_message: str
    user_recovery: str = ""
    user_actions: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


class TaskStepView(BaseModel):
    step_id: str
    title: str
    tool_name: str
    status: str
    requires_confirmation: bool = False
    message: str = ""
    has_result: bool = False


class TaskMetricsView(BaseModel):
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    pending_steps: int = 0
    awaiting_confirmation_steps: int = 0
    event_count: int = 0


class TaskCardView(BaseModel):
    task_id: str
    title: str
    status: str
    status_label: str
    status_tone: str
    updated_at: str = ""
    created_at: str = ""
    last_message: str = ""
    needs_confirmation: bool = False
    current_step_title: str = ""
    current_step_status: str = ""
    progress_text: str = ""
    badge_text: str = ""
    metrics: TaskMetricsView = Field(default_factory=TaskMetricsView)


class QueueOverviewView(BaseModel):
    total: int = 0
    planned: int = 0
    running: int = 0
    awaiting_confirmation: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    needs_attention: int = 0


class TaskListResponse(BaseModel):
    items: list[TaskCardView] = Field(default_factory=list)
    queue: QueueOverviewView = Field(default_factory=QueueOverviewView)
    workdir: str
    count: int = 0


class TaskSummaryView(BaseModel):
    task_id: str
    title: str = ""
    status: str
    updated_at: str = ""
    created_at: str = ""
    current_step_index: int = 0
    needs_confirmation: bool = False
    last_message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class TaskFailureDiagnosisView(BaseModel):
    category: str = "unknown"
    title: str = ""
    summary: str = ""
    recovery: str = ""
    actions: list[str] = Field(default_factory=list)
    failed_step: str = ""
    failed_step_title: str = ""
    tool_name: str = ""
    error_type: str = ""
    failure_origin: str = ""


class TaskResultView(BaseModel):
    task_id: str
    status: str
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
    has_data: bool = False
    data: dict[str, Any] = Field(default_factory=dict)
    failure: TaskFailureDiagnosisView | None = None


class TaskDownloadProgressView(BaseModel):
    phase: str = ""
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_text: str = ""
    current_video_id: str = ""
    current_video_label: str = ""
    updated_at: str = ""


class TaskWorkspaceConfirmationView(BaseModel):
    required: bool = False
    step_title: str = ""
    cta_label: str = ""


class TaskWorkspaceDownloadEntryView(BaseModel):
    path: str = ""
    label: str = ""
    ready: bool = False


class PanelStateView(BaseModel):
    state: str = "empty"
    tone: str = "neutral"
    eyebrow: str = ""
    title: str = ""
    message: str = ""
    action_label: str = ""
    action: str = ""
    action_style: str = "btn2"


class TaskReviewItemView(BaseModel):
    selection_key: str
    video_id: str = ""
    title: str = ""
    channel: str = ""
    watch_url: str = ""
    thumbnail_url: str = ""
    upload_date: str = ""
    duration_seconds: int | None = None
    duration_label: str = ""
    description_preview: str = ""
    reasons_summary: str = ""
    selected: bool = False
    agent_selected: bool = False
    manual_review: bool = False
    selection_modified: bool = False
    low_similarity: bool = False
    score: int | None = None
    vector_score: float | None = None
    status_label: str = ""
    status_tone: str = "neutral"
    decision_label: str = ""
    decision_detail: str = ""


class TaskReviewSummaryView(BaseModel):
    total_count: int = 0
    selected_count: int = 0
    agent_selected_count: int = 0
    manual_review_count: int = 0
    low_similarity_count: int = 0
    modified_count: int = 0


class TaskReviewResponse(BaseModel):
    task_id: str
    workdir: str
    available: bool = False
    editable: bool = False
    empty_message: str = ""
    panel_state: PanelStateView | None = None
    items: list[TaskReviewItemView] = Field(default_factory=list)
    summary: TaskReviewSummaryView = Field(default_factory=TaskReviewSummaryView)
    all_jsonl_path: str = ""
    selected_csv_path: str = ""
    selected_urls_path: str = ""


class TaskReviewSelectionUpdateRequest(BaseModel):
    workdir: str
    selected_keys: list[str] = Field(default_factory=list)


class TaskDownloadLaunchResponse(BaseModel):
    task_id: str
    source_task_id: str
    status: str = "planned"
    message: str = ""


class RetryDownloadSessionRequest(BaseModel):
    workdir: str
    session_dir: str


class DownloadedVideoView(BaseModel):
    video_id: str = ""
    title: str = ""
    upload_date: str = ""
    watch_url: str = ""
    success: bool = False
    file_path: str = ""
    thumbnail_url: str = ""
    file_size_bytes: int = 0


class DownloadSessionView(BaseModel):
    session_name: str
    session_dir: str
    created_at: str = ""
    report_path: str = ""
    failed_urls_file: str = ""
    retry_available: bool = False
    source_task_id: str = ""
    source_task_title: str = ""
    source_task_status: str = ""
    source_task_available: bool = False
    source_task_user_request: str = ""
    source_task_intent: str = ""
    video_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    items: list[DownloadedVideoView] = Field(default_factory=list)


class DownloadResultsResponse(BaseModel):
    workdir: str
    download_dir: str
    available: bool = False
    total_sessions: int = 0
    total_videos: int = 0
    empty_message: str = ""
    panel_state: PanelStateView | None = None
    sessions: list[DownloadSessionView] = Field(default_factory=list)


class TaskEventView(BaseModel):
    event_id: str
    task_id: str
    timestamp: str
    event_type: str
    level: str = "info"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class TaskLogLineView(BaseModel):
    log_id: str
    task_id: str
    timestamp: str
    kind: str = "info"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class TaskLogsResponse(BaseModel):
    task_id: str
    workdir: str
    items: list[TaskLogLineView] = Field(default_factory=list)
    count: int = 0
    panel_state: PanelStateView | None = None


class DeleteTaskResponse(BaseModel):
    ok: bool = True
    task_id: str
    deleted_task_dir: bool = False
    deleted_download_paths: list[str] = Field(default_factory=list)


class TaskDetailView(BaseModel):
    task_id: str
    title: str
    user_request: str = ""
    intent: str = ""
    status: str
    status_label: str
    status_tone: str
    workdir: str
    created_at: str = ""
    updated_at: str = ""
    current_step_index: int = 0
    needs_confirmation: bool = False
    current_step_title: str = ""
    current_step_status: str = ""
    progress_text: str = ""
    active_elapsed_seconds: float | None = None
    metrics: TaskMetricsView = Field(default_factory=TaskMetricsView)
    steps: list[TaskStepView] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    task_paths: dict[str, str] = Field(default_factory=dict)
    download_progress: TaskDownloadProgressView | None = None


class TaskFocusSummaryView(BaseModel):
    task_id: str
    workdir: str
    selected_url_count: int = 0
    metadata_total: int = 0
    metadata_ok: int = 0
    vector_total: int = 0
    vector_max_score: float = 0.0
    vector_average_score: float = 0.0
    vector_low_similarity: int = 0
    vector_threshold: float = 0.12
    filter_failure_summary: str = ""
    task_paths: dict[str, str] = Field(default_factory=dict)


class TaskLifecycleResponse(BaseModel):
    task: TaskDetailView
    summary: TaskSummaryView | None = None
    result: TaskResultView | None = None
    failure: TaskFailureDiagnosisView | None = None
    focus_summary: TaskFocusSummaryView | None = None
    events_tail: list[TaskEventView] = Field(default_factory=list)
    events_tail_count: int = 0
    download_progress: TaskDownloadProgressView | None = None
    workspace_stage: str = "planned"
    workspace_stage_label: str = ""
    primary_message: str = ""
    confirmation: TaskWorkspaceConfirmationView | None = None
    download_entry: TaskWorkspaceDownloadEntryView | None = None


class TaskStatusPollResponse(BaseModel):
    task_id: str
    status: str
    status_label: str
    status_tone: str
    needs_confirmation: bool = False
    progress_text: str = ""
    active_elapsed_seconds: float | None = None
    current_step_title: str = ""
    current_step_status: str = ""
    summary: TaskSummaryView | None = None
    failure: TaskFailureDiagnosisView | None = None
    focus_summary: TaskFocusSummaryView | None = None
    events_tail: list[TaskEventView] = Field(default_factory=list)
    events_tail_count: int = 0
    download_progress: TaskDownloadProgressView | None = None
    logs_tail_count: int = 0
    workspace_stage: str = "planned"
    workspace_stage_label: str = ""
    primary_message: str = ""
    confirmation: TaskWorkspaceConfirmationView | None = None
    download_entry: TaskWorkspaceDownloadEntryView | None = None
