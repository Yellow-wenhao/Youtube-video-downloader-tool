from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


@dataclass(frozen=True)
class YtDlpContext:
    binary: str
    cookies_from_browser: Optional[str] = None
    cookies_file: Optional[str] = None
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchRequest:
    queries: tuple[str, ...]
    search_limit: int
    workdir: str


@dataclass(frozen=True)
class MetadataFetchRequest:
    workdir: str
    workers: int = 1


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PLANNED = "planned"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


@dataclass
class TaskEvent:
    event_id: str
    task_id: str
    timestamp: str
    event_type: str
    message: str = ""
    level: str = "info"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskLogLine:
    log_id: str
    task_id: str
    timestamp: str
    kind: str = "info"
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskDownloadProgress:
    task_id: str
    phase: str = ""
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed_text: str = ""
    current_video_id: str = ""
    current_video_label: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class DownloadSessionRef:
    session_dir: str = ""
    report_csv: str = ""
    failed_urls_file: str = ""
    source_task_id: str = ""
    updated_at: str = ""


@dataclass
class TaskStep:
    step_id: str
    title: str
    tool_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    status: StepStatus = StepStatus.PENDING
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSpec:
    task_id: str
    title: str
    user_request: str
    intent: str
    workdir: str
    created_at: str
    updated_at: str
    status: TaskStatus = TaskStatus.DRAFT
    params: dict[str, Any] = field(default_factory=dict)
    steps: list[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    needs_confirmation: bool = False


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""


@dataclass
class TaskSummary:
    task_id: str
    status: TaskStatus
    title: str = ""
    workdir: str = ""
    created_at: str = ""
    updated_at: str = ""
    current_step_index: int = 0
    needs_confirmation: bool = False
    last_message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
