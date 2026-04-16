from __future__ import annotations

from typing import Any

from app.core.models import TaskResult, TaskSpec, TaskStatus, TaskSummary


DOWNLOAD_TOOLS = {"start_download", "retry_failed_downloads"}


def build_task_failure_diagnosis(
    task: TaskSpec | None,
    result: TaskResult | None,
    *,
    summary: TaskSummary | None = None,
) -> dict[str, Any] | None:
    task_failed = bool(task is not None and task.status == TaskStatus.FAILED)
    result_failed = bool(result is not None and result.status == TaskStatus.FAILED)
    if not task_failed and not result_failed:
        return None

    data = result.data if result is not None and isinstance(result.data, dict) else {}
    step = _resolve_failed_step(task, data)
    failed_step = str(data.get("failed_step") or getattr(step, "step_id", "") or "")
    failed_step_title = str(data.get("failed_step_title") or getattr(step, "title", "") or "")
    tool_name = str(data.get("tool_name") or getattr(step, "tool_name", "") or "")
    error_type = str(data.get("error_type") or "")
    failure_origin = str(data.get("failure_origin") or "")
    raw_message = _coalesce(
        result.message if result is not None else "",
        getattr(step, "message", "") if step is not None else "",
        summary.last_message if summary is not None else "",
    )
    mapped = _build_direct_mapping(data)
    if mapped is None:
        mapped = _classify_failure(
            tool_name=tool_name,
            failed_step_title=failed_step_title,
            raw_message=raw_message,
            error_type=error_type,
            failure_origin=failure_origin,
        )

    return {
        "category": str(mapped.get("category") or "unknown"),
        "title": str(mapped.get("title") or "任务执行失败"),
        "summary": str(mapped.get("summary") or raw_message or "任务执行失败，建议先查看日志定位失败步骤。"),
        "recovery": str(mapped.get("recovery") or ""),
        "actions": _coerce_actions(mapped.get("actions")),
        "failed_step": failed_step,
        "failed_step_title": failed_step_title,
        "tool_name": tool_name,
        "error_type": error_type,
        "failure_origin": failure_origin,
    }


def _resolve_failed_step(task: TaskSpec | None, data: dict[str, Any]):
    if task is None:
        return None
    target = str(data.get("failed_step") or "").strip()
    if target:
        for step in task.steps:
            if step.step_id == target:
                return step
    for step in task.steps:
        if step.status.value == "failed":
            return step
    for step in task.steps:
        if step.status.value in {"running", "awaiting_confirmation"}:
            return step
    return task.steps[-1] if task.steps else None


def _build_direct_mapping(data: dict[str, Any]) -> dict[str, Any] | None:
    title = str(data.get("user_title") or "")
    summary = str(data.get("user_message") or "")
    recovery = str(data.get("user_recovery") or "")
    actions = _coerce_actions(data.get("user_actions"))
    category = str(data.get("error_category") or "")
    if not any([title, summary, recovery, actions, category]):
        return None
    return {
        "category": category or "unknown",
        "title": title or "任务执行失败",
        "summary": summary or "任务执行失败，当前无法继续。",
        "recovery": recovery,
        "actions": actions or ["查看日志", "重试"],
    }


def _classify_failure(
    *,
    tool_name: str,
    failed_step_title: str,
    raw_message: str,
    error_type: str,
    failure_origin: str,
) -> dict[str, Any]:
    step_label = failed_step_title or tool_name or "当前步骤"
    message_lower = raw_message.lower()

    if failure_origin == "payload_resolution" or "无法解析上下文占位符" in raw_message:
        return {
            "category": "payload_resolution",
            "title": "任务上下文解析失败",
            "summary": f"任务在“{step_label}”前无法拼出完整输入，说明前置步骤没有产出这个步骤需要的字段。",
            "recovery": "请先查看日志确认前置步骤是否成功完成；如果这是旧任务或中间文件已变化，建议重新创建任务后再执行。",
            "actions": ["查看日志", "重新创建任务"],
        }

    if tool_name in DOWNLOAD_TOOLS and ("items_path" in raw_message and "urls_file" in raw_message):
        return {
            "category": "download_input",
            "title": "下载输入不完整",
            "summary": "任务已经进入下载阶段，但当前没有拿到可用的视频列表或 URL 文件，因此无法开始下载。",
            "recovery": "请先回到审核页确认至少保留了 1 条视频；如果相关文件被移动或删除，需要重新生成筛选结果后再发起下载。",
            "actions": ["返回审核页", "重新发起下载", "查看日志"],
        }

    if tool_name in DOWNLOAD_TOOLS and (
        error_type == "FileNotFoundError"
        or "未找到 jsonl 文件" in raw_message
        or "no such file" in message_lower
        or "系统找不到指定的文件" in raw_message
    ):
        return {
            "category": "download_source_missing",
            "title": "下载源文件不存在",
            "summary": "下载任务需要读取候选视频或 URL 列表，但对应的工作区文件当前不存在。",
            "recovery": "请检查 workdir 内的审核结果文件是否仍在；如果这是较早的任务目录，建议重新筛选或重新创建下载任务。",
            "actions": ["检查工作区文件", "重新筛选", "重新创建下载任务"],
        }

    if tool_name in DOWNLOAD_TOOLS and (
        "yt-dlp" in message_lower or "ffmpeg" in message_lower
    ) and (
        "not found" in message_lower
        or "找不到" in raw_message
        or "missing" in message_lower
        or "不是内部或外部命令" in raw_message
        or "无法找到" in raw_message
    ):
        return {
            "category": "download_environment",
            "title": "下载环境不可用",
            "summary": "任务已经进入下载阶段，但本机当前缺少可用的下载工具或工具路径不可访问。",
            "recovery": "请检查 yt-dlp 和 ffmpeg 是否已正确安装，并确认当前配置里的二进制路径有效后再重试。",
            "actions": ["检查 yt-dlp", "检查 ffmpeg", "重试下载"],
        }

    if tool_name in DOWNLOAD_TOOLS and (
        "cookies" in message_lower
        or "sign in" in message_lower
        or "private video" in message_lower
        or "403" in message_lower
        or "unavailable" in message_lower
        or "login" in message_lower
    ):
        return {
            "category": "download_access",
            "title": "视频访问受限",
            "summary": "下载流程已经启动，但目标视频当前不可访问，或需要登录态 / cookies 才能继续。",
            "recovery": "请先确认视频链接仍可访问；如果需要登录态访问，请检查 cookies 设置，然后再重试下载。",
            "actions": ["检查视频可访问性", "检查 cookies", "重试下载"],
        }

    if tool_name in DOWNLOAD_TOOLS:
        return {
            "category": "download_execution",
            "title": "下载执行失败",
            "summary": f"任务在“{step_label}”阶段启动了下载，但下载过程中返回错误，当前未能正常完成。",
            "recovery": "请先查看日志确认是单个视频失败还是整体下载环境异常，再检查下载目录、网络和工具配置后重试。",
            "actions": ["查看日志", "检查下载目录", "重试下载"],
        }

    return {
        "category": "runtime",
        "title": "任务执行失败",
        "summary": f"任务在“{step_label}”阶段中断，当前无法继续执行。",
        "recovery": "请先查看日志确认具体失败点；如果问题来自配置、输入或外部环境，修正后重新运行任务。",
        "actions": ["查看日志", "重新运行任务"],
    }


def _coerce_actions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    actions: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            actions.append(text)
    return actions


def _coalesce(*values: str) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
