from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Dict, Type

from app.tools.download_tools import retry_failed_downloads, start_download
from app.tools.schemas import (
    BuildVectorIndexInput,
    CheckRuntimeEnvInput,
    FetchVideoDetailsInput,
    FilterVideosInput,
    GetTaskStatusInput,
    KnnSearchInput,
    PrepareDownloadListInput,
    RetryFailedDownloadsInput,
    SearchVideosInput,
    StartDownloadInput,
)
from app.tools.search_tools import fetch_video_details_tool, filter_videos_tool, prepare_download_list, search_videos
from app.tools.status_tools import check_runtime_env, get_task_status
from app.tools.vector_tools import build_vector_index, knn_search


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, dict[str, Any]] = {}

    def register(self, name: str, description: str, input_model: Type[Any], handler: Callable[[Any], Any]) -> None:
        self._tools[name] = {
            "description": description,
            "input_model": input_model,
            "handler": handler,
        }

    def specs(self) -> dict[str, dict[str, str]]:
        return {
            name: {
                "description": meta["description"],
                "input_model": meta["input_model"].__name__,
            }
            for name, meta in self._tools.items()
        }

    def execute(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"未注册的工具: {name}")
        meta = self._tools[name]
        input_data = meta["input_model"](**payload)
        result = meta["handler"](input_data)
        if is_dataclass(result):
            return asdict(result)
        if isinstance(result, dict):
            return result
        raise TypeError(f"工具 {name} 返回了不支持的结果类型: {type(result)!r}")


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register("search_videos", "按关键词搜索 YouTube 视频并去重。", SearchVideosInput, search_videos)
    registry.register("fetch_video_details", "抓取候选视频的详细元数据。", FetchVideoDetailsInput, fetch_video_details_tool)
    registry.register("filter_videos", "按规则筛选候选视频。", FilterVideosInput, filter_videos_tool)
    registry.register("prepare_download_list", "导出 CSV、URL 列表和打分 JSONL。", PrepareDownloadListInput, prepare_download_list)
    registry.register("build_vector_index", "为候选视频构建本地向量索引。", BuildVectorIndexInput, build_vector_index)
    registry.register("knn_search", "基于查询文本执行 KNN 相似度搜索。", KnnSearchInput, knn_search)
    registry.register("start_download", "下载已筛选或指定 URL 的视频。", StartDownloadInput, start_download)
    registry.register("retry_failed_downloads", "重试失败 URL 列表。", RetryFailedDownloadsInput, retry_failed_downloads)
    registry.register("get_task_status", "读取当前工作目录或下载会话状态。", GetTaskStatusInput, get_task_status)
    registry.register("check_runtime_env", "检查 yt-dlp 和 ffmpeg 是否可用。", CheckRuntimeEnvInput, check_runtime_env)
    return registry
