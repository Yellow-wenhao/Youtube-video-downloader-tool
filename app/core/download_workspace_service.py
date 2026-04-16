from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.core.models import DownloadSessionRef
from app.core.review_service import thumbnail_url

SCORED_ITEMS_FILENAME = "03_scored_candidates.jsonl"
DOWNLOAD_ARCHIVE_FILENAME = "download_archive.txt"
FAILED_URLS_FILENAME = "06_failed_urls.txt"
DOWNLOAD_REPORT_FILENAME = "07_download_report.csv"
LAST_SESSION_FILENAME = "08_last_download_session.txt"
SESSION_METADATA_FILENAME = "09_download_session.json"


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _merged_download_params(
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged = dict(params or {})
    merged.update(dict(defaults or {}))
    return merged


@dataclass(frozen=True)
class DownloadWorkspacePaths:
    workdir: Path
    download_dir: Path
    items_path: Path
    archive_file: Path
    failed_urls_file: Path
    last_session_marker: Path


@dataclass(frozen=True)
class DownloadedVideoRecord:
    video_id: str = ""
    title: str = ""
    upload_date: str = ""
    watch_url: str = ""
    success: bool = False
    file_path: str = ""
    thumbnail_url: str = ""
    file_size_bytes: int = 0


@dataclass(frozen=True)
class DownloadSessionRecord:
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
    items: list[DownloadedVideoRecord] = field(default_factory=list)


@dataclass(frozen=True)
class DownloadResultsSnapshot:
    workdir: str
    download_dir: str
    available: bool = False
    total_sessions: int = 0
    total_videos: int = 0
    empty_message: str = ""
    sessions: list[DownloadSessionRecord] = field(default_factory=list)


@dataclass(frozen=True)
class DownloadSessionTaskLink:
    task_id: str = ""
    task_title: str = ""
    task_status: str = ""
    task_available: bool = False
    task_user_request: str = ""
    task_intent: str = ""


def download_workspace_paths(
    workdir: str | Path,
    *,
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    items_path: str | Path | None = None,
) -> DownloadWorkspacePaths:
    workdir_path = Path(workdir)
    merged = _merged_download_params(defaults, params)
    raw_download_dir = merged.get("download_dir") or (workdir_path / "downloads")
    raw_items_path = items_path or merged.get("items_path") or (workdir_path / SCORED_ITEMS_FILENAME)
    return DownloadWorkspacePaths(
        workdir=workdir_path,
        download_dir=Path(str(raw_download_dir)),
        items_path=Path(str(raw_items_path)),
        archive_file=workdir_path / DOWNLOAD_ARCHIVE_FILENAME,
        failed_urls_file=workdir_path / FAILED_URLS_FILENAME,
        last_session_marker=workdir_path / LAST_SESSION_FILENAME,
    )


def build_download_task_payload(
    workdir: str | Path,
    *,
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    items_path: str | Path | None = None,
) -> dict[str, object]:
    merged = _merged_download_params(defaults, params)
    paths = download_workspace_paths(workdir, defaults=defaults, params=params, items_path=items_path)
    return {
        "workdir": str(paths.workdir),
        "download_dir": str(paths.download_dir),
        "items_path": str(paths.items_path),
        "binary": str(merged.get("binary") or "yt-dlp"),
        "cookies_from_browser": str(merged.get("cookies_from_browser") or ""),
        "cookies_file": str(merged.get("cookies_file") or ""),
        "extra_args": list(merged.get("extra_args") or []),
        "download_mode": str(merged.get("download_mode") or "video"),
        "include_audio": bool(merged.get("include_audio", True)),
        "video_container": str(merged.get("video_container") or "auto"),
        "max_height": merged.get("max_height"),
        "max_bitrate_kbps": merged.get("max_bitrate_kbps"),
        "audio_format": str(merged.get("audio_format") or "best"),
        "audio_quality": merged.get("audio_quality"),
        "sponsorblock_remove": str(merged.get("sponsorblock_remove") or ""),
        "clean_video": bool(merged.get("clean_video", False)),
        "concurrent_videos": _coerce_positive_int(merged.get("concurrent_videos"), 1),
        "concurrent_fragments": _coerce_positive_int(merged.get("concurrent_fragments"), 4),
        "download_session_name": str(merged.get("download_session_name") or ""),
    }


def build_retry_task_payload(
    workdir: str | Path,
    *,
    failed_urls_file: str | Path,
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    download_session_name: str = "",
) -> dict[str, object]:
    merged = _merged_download_params(defaults, params)
    paths = download_workspace_paths(workdir, defaults=defaults, params=params)
    return {
        "workdir": str(paths.workdir),
        "download_dir": str(paths.download_dir),
        "failed_urls_file": str(failed_urls_file),
        "binary": str(merged.get("binary") or "yt-dlp"),
        "cookies_from_browser": str(merged.get("cookies_from_browser") or ""),
        "cookies_file": str(merged.get("cookies_file") or ""),
        "extra_args": list(merged.get("extra_args") or []),
        "download_mode": str(merged.get("download_mode") or "video"),
        "include_audio": bool(merged.get("include_audio", True)),
        "video_container": str(merged.get("video_container") or "auto"),
        "max_height": merged.get("max_height"),
        "max_bitrate_kbps": merged.get("max_bitrate_kbps"),
        "audio_format": str(merged.get("audio_format") or "best"),
        "audio_quality": merged.get("audio_quality"),
        "sponsorblock_remove": str(merged.get("sponsorblock_remove") or ""),
        "concurrent_videos": _coerce_positive_int(merged.get("concurrent_videos"), 1),
        "concurrent_fragments": _coerce_positive_int(merged.get("concurrent_fragments"), 4),
        "download_session_name": str(download_session_name or ""),
    }


def extract_result_session_dir(result_or_data: Any) -> str:
    return extract_download_session_ref(result_or_data).session_dir


def extract_download_session_ref(result_or_data: Any) -> DownloadSessionRef:
    data = getattr(result_or_data, "data", result_or_data)
    if not isinstance(data, Mapping):
        return DownloadSessionRef()
    value = str(data.get("session_dir") or "").strip()
    if value:
        return DownloadSessionRef(
            session_dir=value,
            report_csv=str(data.get("report_csv") or ""),
            failed_urls_file=str(data.get("failed_urls_file") or ""),
            source_task_id=str(data.get("source_task_id") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )
    nested = data.get("step_results")
    if isinstance(nested, Mapping):
        for step_result in nested.values():
            if not isinstance(step_result, Mapping):
                continue
            value = str(step_result.get("session_dir") or "").strip()
            if value:
                return DownloadSessionRef(
                    session_dir=value,
                    report_csv=str(step_result.get("report_csv") or ""),
                    failed_urls_file=str(step_result.get("failed_urls_file") or ""),
                    source_task_id=str(step_result.get("source_task_id") or ""),
                    updated_at=str(step_result.get("updated_at") or ""),
                )
    return DownloadSessionRef()


def resolve_download_session_pointers(
    workdir: str | Path,
    *,
    session_dir: str = "",
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> DownloadSessionRef:
    paths = download_workspace_paths(workdir, defaults=defaults, params=params)
    from app.agent.session_store import SessionStore

    stored_ref = SessionStore(paths.workdir).get_last_download_session()
    requested_session_dir = session_dir.strip()
    raw_session_dir = requested_session_dir or stored_ref.session_dir
    if requested_session_dir and requested_session_dir != stored_ref.session_dir:
        report_csv = ""
        failed_urls_file = ""
        source_task_id = ""
        updated_at = ""
    else:
        report_csv = stored_ref.report_csv
        failed_urls_file = stored_ref.failed_urls_file
        source_task_id = stored_ref.source_task_id
        updated_at = stored_ref.updated_at

    if not raw_session_dir and paths.last_session_marker.exists():
        try:
            raw_session_dir = paths.last_session_marker.read_text(encoding="utf-8").strip()
        except Exception:
            raw_session_dir = ""

    if raw_session_dir:
        session_failed_urls_file = Path(raw_session_dir) / FAILED_URLS_FILENAME
        session_ref = _read_download_session_metadata(raw_session_dir)
        report_path = Path(raw_session_dir) / DOWNLOAD_REPORT_FILENAME
        if not report_csv and session_ref.report_csv:
            report_csv = session_ref.report_csv
        if not report_csv and report_path.exists():
            report_csv = str(report_path)
        if session_ref.failed_urls_file:
            failed_urls_file = session_ref.failed_urls_file
        if session_failed_urls_file.exists():
            failed_urls_file = str(session_failed_urls_file)
        if not source_task_id and session_ref.source_task_id:
            source_task_id = session_ref.source_task_id
        if not updated_at and session_ref.updated_at:
            updated_at = session_ref.updated_at

    if not failed_urls_file and not raw_session_dir and paths.failed_urls_file.exists():
        failed_urls_file = str(paths.failed_urls_file)

    return DownloadSessionRef(
        session_dir=raw_session_dir,
        report_csv=report_csv,
        failed_urls_file=failed_urls_file,
        source_task_id=source_task_id,
        updated_at=updated_at,
    )


def persist_download_session_ref(
    workdir: str | Path,
    ref: DownloadSessionRef,
    *,
    keep_legacy_marker: bool = True,
) -> DownloadSessionRef:
    paths = download_workspace_paths(workdir)
    from app.agent.session_store import SessionStore

    session_ref = DownloadSessionRef(
        session_dir=str(ref.session_dir or ""),
        report_csv=str(ref.report_csv or ""),
        failed_urls_file=str(ref.failed_urls_file or ""),
        source_task_id=str(ref.source_task_id or ""),
        updated_at=str(ref.updated_at or datetime.now(timezone.utc).isoformat()),
    )
    session_store = SessionStore(paths.workdir)
    session_store.set_last_download_session(session_ref)
    result_context: dict[str, Any] = {
        "task_id": session_ref.source_task_id,
        "session_dir": session_ref.session_dir,
        "report_csv": session_ref.report_csv,
        "failed_urls_file": session_ref.failed_urls_file,
        "download_dir": str(paths.download_dir),
        "updated_at": session_ref.updated_at,
    }
    if session_ref.session_dir:
        session_path = Path(session_ref.session_dir)
        _write_download_session_metadata(session_path, session_ref)
        task_link = resolve_download_session_task_link(paths.workdir, session_path)
        result_context["latest_session_name"] = session_path.name
        loaded_session = load_download_session(session_path)
        result_context.update(
            {
                "video_count": loaded_session.video_count,
                "success_count": loaded_session.success_count,
                "failed_count": loaded_session.failed_count,
                "source_task_id": task_link.task_id or loaded_session.source_task_id,
                "source_task_title": task_link.task_title or loaded_session.source_task_title,
                "source_task_status": task_link.task_status or loaded_session.source_task_status,
                "source_task_user_request": task_link.task_user_request or loaded_session.source_task_user_request,
                "source_task_intent": task_link.task_intent or loaded_session.source_task_intent,
            }
        )
    session_store.update_recent_result_context(result_context)
    if keep_legacy_marker and session_ref.session_dir:
        try:
            paths.last_session_marker.write_text(session_ref.session_dir, encoding="utf-8")
        except Exception:
            pass
    return session_ref


def resolve_retry_failed_urls_file(
    workdir: str | Path,
    session_dir: str | Path,
    *,
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
) -> str:
    resolved = resolve_download_session_pointers(
        workdir,
        session_dir=str(session_dir),
        defaults=defaults,
        params=params,
    )
    candidate = str(resolved.failed_urls_file or "").strip()
    if not candidate:
        return ""
    if not _file_has_lines(Path(candidate)):
        return ""
    return candidate


def resolve_download_session_task_link(
    workdir: str | Path,
    session_dir: str | Path,
) -> DownloadSessionTaskLink:
    session_path = Path(session_dir)
    task_links, task_links_by_id = _build_download_session_task_links(workdir)
    metadata_ref = _read_download_session_metadata(session_path)
    normalized_path = _normalize_path(session_path)
    if metadata_ref.source_task_id:
        return task_links_by_id.get(
            metadata_ref.source_task_id,
            DownloadSessionTaskLink(task_id=metadata_ref.source_task_id),
        )
    return task_links.get(normalized_path, DownloadSessionTaskLink())


def collect_result_artifact_paths(result_or_data: Any) -> list[Path]:
    data = getattr(result_or_data, "data", result_or_data)
    collected: dict[str, Path] = {}

    def _walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"session_dir", "report_csv", "failed_urls_file"} and isinstance(item, str) and item.strip():
                    try:
                        collected[item] = Path(item).expanduser().resolve()
                    except Exception:
                        continue
                else:
                    _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(data)
    return list(collected.values())


def load_download_results(
    workdir: str | Path,
    *,
    defaults: Mapping[str, Any] | None = None,
    params: Mapping[str, Any] | None = None,
    limit: int = 12,
) -> DownloadResultsSnapshot:
    paths = download_workspace_paths(workdir, defaults=defaults, params=params)
    if not paths.download_dir.exists():
        return DownloadResultsSnapshot(
            workdir=str(paths.workdir),
            download_dir=str(paths.download_dir),
            available=False,
            empty_message="当前还没有下载结果。完成下载后，这里会按会话展示已下载视频。",
        )

    session_dirs = [path for path in paths.download_dir.iterdir() if path.is_dir()]
    session_dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    task_links, task_links_by_id = _build_download_session_task_links(paths.workdir)
    sessions = [
        load_download_session(
            path,
            session_task_link=task_links.get(_normalize_path(path), DownloadSessionTaskLink()),
            task_links_by_id=task_links_by_id,
        )
        for path in session_dirs[: max(limit, 0)]
    ]
    total_videos = sum(session.video_count for session in sessions)
    return DownloadResultsSnapshot(
        workdir=str(paths.workdir),
        download_dir=str(paths.download_dir),
        available=bool(sessions),
        total_sessions=len(sessions),
        total_videos=total_videos,
        empty_message="" if sessions else "当前还没有下载结果。完成下载后，这里会按会话展示已下载视频。",
        sessions=sessions,
    )


def load_download_session(
    session_dir: str | Path,
    *,
    session_task_link: DownloadSessionTaskLink | None = None,
    task_links_by_id: Mapping[str, DownloadSessionTaskLink] | None = None,
) -> DownloadSessionRecord:
    session_path = Path(session_dir)
    report_path = session_path / DOWNLOAD_REPORT_FILENAME
    failed_urls_path = session_path / FAILED_URLS_FILENAME
    metadata_ref = _read_download_session_metadata(session_path)
    rows = _read_download_report_rows(report_path)
    videos_dir = session_path / "videos"
    items: list[DownloadedVideoRecord] = []
    success_count = 0
    failed_count = 0

    for row in rows:
        video_id = str(row.get("视频id") or "").strip()
        success = str(row.get("视频是否下载成功") or "").strip() == "是"
        if success:
            success_count += 1
        else:
            failed_count += 1
        file_path = _find_downloaded_video_file(videos_dir, video_id)
        items.append(
            DownloadedVideoRecord(
                video_id=video_id,
                title=str(row.get("视频原标题") or "").strip(),
                upload_date=str(row.get("视频在YouTube上传的时间") or "").strip(),
                watch_url=str(row.get("视频url") or "").strip(),
                success=success,
                file_path=str(file_path) if file_path is not None else "",
                thumbnail_url=thumbnail_url(video_id),
                file_size_bytes=file_path.stat().st_size if file_path is not None and file_path.exists() else 0,
            )
        )

    created_at = datetime.fromtimestamp(session_path.stat().st_mtime, tz=timezone.utc).isoformat()
    linked_task_id = str(metadata_ref.source_task_id or "")
    source_task_link = DownloadSessionTaskLink()
    if linked_task_id and isinstance(task_links_by_id, Mapping):
        source_task_link = task_links_by_id.get(linked_task_id, DownloadSessionTaskLink(task_id=linked_task_id))
    elif session_task_link is not None:
        source_task_link = session_task_link
        linked_task_id = source_task_link.task_id
    return DownloadSessionRecord(
        session_name=session_path.name,
        session_dir=str(session_path),
        created_at=created_at,
        report_path=str(report_path) if report_path.exists() else "",
        failed_urls_file=str(failed_urls_path) if failed_urls_path.exists() else "",
        retry_available=_file_has_lines(failed_urls_path),
        source_task_id=linked_task_id,
        source_task_title=source_task_link.task_title,
        source_task_status=source_task_link.task_status,
        source_task_available=source_task_link.task_available,
        source_task_user_request=source_task_link.task_user_request,
        source_task_intent=source_task_link.task_intent,
        video_count=len(items),
        success_count=success_count,
        failed_count=failed_count,
        items=items,
    )


def _read_download_report_rows(report_path: Path) -> list[dict[str, str]]:
    if not report_path.exists():
        return []
    try:
        with report_path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    except Exception:
        return []


def _find_downloaded_video_file(videos_dir: Path, video_id: str) -> Path | None:
    clean_id = (video_id or "").strip()
    if not clean_id or not videos_dir.exists():
        return None
    for path in videos_dir.iterdir():
        if path.is_file() and f"[{clean_id}]" in path.name:
            return path
    return None


def _build_download_session_task_links(
    workdir: str | Path,
) -> tuple[dict[str, DownloadSessionTaskLink], dict[str, DownloadSessionTaskLink]]:
    from app.core.task_service import TaskStore

    store = TaskStore(workdir)
    by_session_dir: dict[str, DownloadSessionTaskLink] = {}
    by_task_id: dict[str, DownloadSessionTaskLink] = {}
    for summary in store.list_summaries(limit=None):
        task = store.load_task(summary.task_id)
        link = DownloadSessionTaskLink(
            task_id=summary.task_id,
            task_title=summary.title,
            task_status=summary.status.value,
            task_available=True,
            task_user_request=task.user_request,
            task_intent=task.intent,
        )
        by_task_id[summary.task_id] = link
        session_ref = store.load_download_session_ref(summary.task_id)
        if not session_ref.session_dir:
            continue
        key = _normalize_path(session_ref.session_dir)
        if key and key not in by_session_dir:
            by_session_dir[key] = link
    return by_session_dir, by_task_id


def _read_download_session_metadata(session_dir: str | Path) -> DownloadSessionRef:
    metadata_path = Path(session_dir) / SESSION_METADATA_FILENAME
    if not metadata_path.exists():
        return DownloadSessionRef()
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return DownloadSessionRef()
    if not isinstance(payload, dict):
        return DownloadSessionRef()
    return DownloadSessionRef(
        session_dir=str(payload.get("session_dir") or session_dir),
        report_csv=str(payload.get("report_csv") or ""),
        failed_urls_file=str(payload.get("failed_urls_file") or ""),
        source_task_id=str(payload.get("source_task_id") or ""),
        updated_at=str(payload.get("updated_at") or ""),
    )


def _write_download_session_metadata(session_dir: str | Path, ref: DownloadSessionRef) -> None:
    session_path = Path(session_dir)
    metadata_path = session_path / SESSION_METADATA_FILENAME
    payload = {
        "session_dir": str(ref.session_dir or session_path),
        "report_csv": str(ref.report_csv or ""),
        "failed_urls_file": str(ref.failed_urls_file or ""),
        "source_task_id": str(ref.source_task_id or ""),
        "updated_at": str(ref.updated_at or ""),
    }
    try:
        metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _normalize_path(path: str | Path) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(path)


def _file_has_lines(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return any(line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    except Exception:
        return False
