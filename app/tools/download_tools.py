from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.core.download_workspace_service import download_workspace_paths, resolve_download_session_pointers
from app.core.download_service import download_selected
from app.core.report_service import load_url_title_map_from_csv, load_urls_file
from app.core.models import TaskDownloadProgress
from app.core.task_service import TaskStore
from app.tools.schemas import RetryFailedDownloadsInput, StartDownloadInput, StartDownloadOutput


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"未找到 JSONL 文件: {path}")
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        out.append(json.loads(s))
    return out


def _resolve_items(input_data: StartDownloadInput) -> List[Dict[str, Any]]:
    workdir = Path(input_data.workdir)
    if input_data.items_path:
        return _load_jsonl(Path(input_data.items_path))
    if input_data.urls_file:
        urls = load_urls_file(Path(input_data.urls_file))
        url_title_map = load_url_title_map_from_csv(workdir)
        return [{"selected": True, "watch_url": u, "title": url_title_map.get(u, "")} for u in urls]
    raise ValueError("必须提供 items_path 或 urls_file")


def start_download(input_data: StartDownloadInput) -> StartDownloadOutput:
    workdir = Path(input_data.workdir)
    items = _resolve_items(input_data)
    archive_file = download_workspace_paths(
        workdir,
        params={"download_dir": input_data.download_dir, "items_path": input_data.items_path},
    ).archive_file
    sblock_remove = input_data.sponsorblock_remove.strip()
    if input_data.clean_video and not sblock_remove:
        sblock_remove = "sponsor,selfpromo,intro,outro,interaction"
    store = TaskStore(workdir)
    if input_data.task_id:
        store.clear_download_progress(input_data.task_id)

    def _on_log(message: str, kind: str, data: dict[str, Any] | None = None) -> None:
        if not input_data.task_id:
            return
        store.append_log(input_data.task_id, kind=kind, message=message, data=data)

    def _on_progress(payload: dict[str, Any]) -> None:
        if not input_data.task_id:
            return
        store.save_download_progress(
            TaskDownloadProgress(
                task_id=input_data.task_id,
                phase=str(payload.get("phase") or ""),
                percent=float(payload.get("percent") or 0.0),
                downloaded_bytes=int(payload.get("downloaded_bytes") or 0),
                total_bytes=int(payload.get("total_bytes") or 0),
                speed_text=str(payload.get("speed_text") or ""),
                current_video_id=str(payload.get("current_video_id") or ""),
                current_video_label=str(payload.get("current_video_label") or ""),
            )
        )

    download_selected(
        binary=input_data.binary,
        items=items,
        download_dir=Path(input_data.download_dir),
        archive_file=archive_file,
        cookies_from_browser=input_data.cookies_from_browser or None,
        cookies_file=input_data.cookies_file or None,
        extra_args=input_data.extra_args,
        download_mode=input_data.download_mode,
        include_audio=input_data.include_audio,
        video_container=input_data.video_container,
        max_height=input_data.max_height,
        max_bitrate_kbps=input_data.max_bitrate_kbps,
        audio_format=input_data.audio_format,
        audio_quality=input_data.audio_quality,
        sponsorblock_remove=sblock_remove,
        concurrent_videos=input_data.concurrent_videos,
        concurrent_fragments=input_data.concurrent_fragments,
        download_session_name=input_data.download_session_name,
        task_id=input_data.task_id,
        on_log=_on_log,
        on_progress=_on_progress,
    )
    pointers = resolve_download_session_pointers(workdir)
    return StartDownloadOutput(
        status="completed",
        session_dir=pointers.session_dir,
        report_csv=pointers.report_csv,
        failed_urls_file=pointers.failed_urls_file,
    )


def retry_failed_downloads(input_data: RetryFailedDownloadsInput) -> StartDownloadOutput:
    start_input = StartDownloadInput(
        workdir=input_data.workdir,
        task_id=input_data.task_id,
        download_dir=input_data.download_dir,
        urls_file=input_data.failed_urls_file,
        binary=input_data.binary,
        cookies_from_browser=input_data.cookies_from_browser,
        cookies_file=input_data.cookies_file,
        extra_args=list(input_data.extra_args),
        download_mode=input_data.download_mode,
        include_audio=input_data.include_audio,
        video_container=input_data.video_container,
        max_height=input_data.max_height,
        max_bitrate_kbps=input_data.max_bitrate_kbps,
        audio_format=input_data.audio_format,
        audio_quality=input_data.audio_quality,
        sponsorblock_remove=input_data.sponsorblock_remove,
        clean_video=False,
        concurrent_videos=input_data.concurrent_videos,
        concurrent_fragments=input_data.concurrent_fragments,
        download_session_name=input_data.download_session_name,
    )
    return start_download(start_input)
