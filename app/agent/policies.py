from __future__ import annotations

from app.core.models import TaskStep


SENSITIVE_TOOLS = {"start_download", "retry_failed_downloads"}


def step_requires_confirmation(step: TaskStep) -> bool:
    return step.requires_confirmation or step.tool_name in SENSITIVE_TOOLS
