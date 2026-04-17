from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from app.adapters.yt_dlp_adapter import yt_dlp_base
from app.core.download_workspace_service import FAILED_URLS_FILENAME, persist_download_session_ref
from app.core.models import DownloadSessionRef
from app.core.report_service import chunked, extract_video_id, normalize_text, write_download_report_csv
from app.core.subprocess_utils import hidden_process_kwargs


def has_independent_subtitle_track(base_cmd: Sequence[str], url: str, timeout_sec: int = 25) -> Optional[bool]:
    cmd = list(base_cmd) + ["--skip-download", "--no-playlist", "-J", url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            **hidden_process_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    subs = data.get("subtitles")
    auto = data.get("automatic_captions")
    has_subs = isinstance(subs, dict) and any(bool(v) for v in subs.values())
    has_auto = isinstance(auto, dict) and any(bool(v) for v in auto.values())
    return bool(has_subs or has_auto)


def cleanup_subtitle_artifacts(download_dir: Path, video_ids: Sequence[str]) -> int:
    id_set = {v.strip() for v in video_ids if v and v.strip()}
    if not id_set or not download_dir.exists():
        return 0
    subtitle_exts = {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".lrc", ".srv1", ".srv2", ".srv3", ".json3"}
    removed = 0
    for fp in download_dir.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in subtitle_exts:
            continue
        name = fp.name
        if not any(f"[{vid}]" in name for vid in id_set):
            continue
        try:
            fp.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def sanitize_name(s: str) -> str:
    x = normalize_text(s)
    x = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", x).strip("._-")
    return x[:96] if x else "task"


def organize_sidecar_files(videos_dir: Path, json_dir: Path, desc_dir: Path) -> Tuple[int, int]:
    moved_json = 0
    moved_desc = 0
    if not videos_dir.exists():
        return moved_json, moved_desc
    for fp in list(videos_dir.rglob("*")):
        if not fp.is_file():
            continue
        target: Optional[Path] = None
        if fp.name.endswith(".info.json"):
            target = json_dir / fp.name
            moved_json += 1
        elif fp.name.endswith(".description"):
            target = desc_dir / fp.name
            moved_desc += 1
        if target is None:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            fp.replace(target)
        except Exception:
            pass
    return moved_json, moved_desc


def _parse_int(value: str) -> int:
    text = normalize_text(value).replace(",", "")
    return int(text) if text.isdigit() else 0


def parse_progress_line(line: str, *, fallback_label: str = "", fallback_video_id: str = "") -> Optional[dict[str, Any]]:
    text = (line or "").strip()
    marker = "download:[PROG] "
    if not text.startswith(marker):
        return None
    parts = text[len(marker):].split("|")
    if len(parts) < 6:
        return None
    percent_text = normalize_text(parts[1]).replace("%", "").strip()
    try:
        percent = float(percent_text)
    except ValueError:
        percent = 0.0
    video_id = normalize_text(parts[0]) or fallback_video_id
    total_bytes = _parse_int(parts[3]) or _parse_int(parts[4])
    return {
        "phase": "downloading",
        "percent": max(0.0, min(percent, 100.0)),
        "downloaded_bytes": _parse_int(parts[2]),
        "total_bytes": total_bytes,
        "speed_text": normalize_text(parts[5]),
        "current_video_id": video_id,
        "current_video_label": fallback_label,
    }


def download_option_args(
    mode: str,
    include_audio: bool,
    video_container: str,
    max_height: Optional[int],
    max_bitrate_kbps: Optional[int],
    audio_format: str,
    audio_quality: Optional[int],
) -> List[str]:
    args: List[str] = []
    m = (mode or "video").strip().lower()
    vc = (video_container or "auto").strip().lower()
    af = (audio_format or "best").strip().lower()

    if m == "audio":
        args += ["-x"]
        if af != "best":
            args += ["--audio-format", af]
        if audio_quality is not None:
            args += ["--audio-quality", str(audio_quality)]
        return args

    if isinstance(max_height, int) and max_height > 0:
        if include_audio:
            fmt = f"bv*[height={max_height}]+ba/b[height={max_height}]"
        else:
            fmt = f"bv*[height={max_height}]/b[height={max_height}]"
    else:
        video_part = "bv*"
        if isinstance(max_bitrate_kbps, int) and max_bitrate_kbps > 0:
            video_part += f"[tbr<={max_bitrate_kbps}]"
        fmt = f"{video_part}+ba/b" if include_audio else video_part
    args += ["-f", fmt]

    if vc in {"mp4", "mkv", "webm"}:
        if include_audio:
            args += ["--merge-output-format", vc]
        else:
            args += ["--remux-video", vc]
    return args


def download_selected(
    binary: str,
    items: Sequence[dict],
    download_dir: Path,
    archive_file: Path,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    extra_args: Sequence[str] | None = None,
    download_mode: str = "video",
    include_audio: bool = True,
    video_container: str = "auto",
    max_height: Optional[int] = None,
    max_bitrate_kbps: Optional[int] = None,
    audio_format: str = "best",
    audio_quality: Optional[int] = None,
    sponsorblock_remove: str = "",
    batch_size: int = 25,
    concurrent_videos: int = 1,
    concurrent_fragments: int = 4,
    download_session_name: str = "",
    task_id: str = "",
    on_log: Optional[Callable[[str, str, Optional[dict[str, Any]]], None]] = None,
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> None:
    urls = [normalize_text(item.get("watch_url")) for item in items if item.get("selected")]
    urls = [u for u in urls if u]
    if not urls:
        print("[INFO] 没有命中的可下载 URL，跳过下载。")
        return
    url_to_label: Dict[str, str] = {}
    for item in items:
        if not item.get("selected"):
            continue
        u = normalize_text(item.get("watch_url"))
        if not u:
            continue
        t = normalize_text(item.get("title"))
        vid = normalize_text(item.get("video_id")) or extract_video_id(u)
        label = t or (f"id={vid}" if vid else u)
        url_to_label[u] = label

    download_dir.mkdir(parents=True, exist_ok=True)
    session_seed = sanitize_name(download_session_name or archive_file.parent.name or "task")
    if download_session_name:
        session_dir = download_dir / session_seed
    else:
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = download_dir / f"{session_ts}_{session_seed}"
    videos_dir = session_dir / "videos"
    json_dir = session_dir / "json"
    desc_dir = session_dir / "description"
    videos_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    desc_dir.mkdir(parents=True, exist_ok=True)
    base = yt_dlp_base(binary=binary, cookies_from_browser=cookies_from_browser, cookies_file=cookies_file, extra_args=extra_args)
    base_no_cookies = yt_dlp_base(binary=binary, cookies_from_browser=None, cookies_file=None, extra_args=extra_args)
    template = str(videos_dir / "%(title)s [%(id)s].%(ext)s")
    option_args = download_option_args(
        mode=download_mode,
        include_audio=include_audio,
        video_container=video_container,
        max_height=max_height,
        max_bitrate_kbps=max_bitrate_kbps,
        audio_format=audio_format,
        audio_quality=audio_quality,
    )
    sblock_args: List[str] = []
    if sponsorblock_remove.strip():
        sblock_args = ["--sponsorblock-remove", sponsorblock_remove.strip()]
    subtitle_policy_args = ["--no-write-subs", "--no-write-auto-subs", "--no-embed-subs"]
    progress_args = [
        "--newline",
        "--progress-template",
        "download:[PROG] %(info.id)s|%(progress._percent_str)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s",
    ]
    dl_parallel_args: List[str] = []
    if isinstance(concurrent_fragments, int) and concurrent_fragments > 1:
        dl_parallel_args += ["--concurrent-fragments", str(concurrent_fragments)]
    had_success = False
    errors: List[str] = []
    log_lock = threading.Lock()
    failed_urls: List[str] = []
    failed_reason_map: Dict[str, str] = {}
    print("[INFO] 画面中的烧录字幕(硬字幕)无法由 yt-dlp 剔除，本流程不会尝试处理硬字幕。")

    def _log(msg: str) -> None:
        with log_lock:
            print(msg, flush=True)
        if on_log is not None:
            on_log(msg, "stdout", None)

    def _summarize_error_text(msg: str) -> str:
        txt = (msg or "").strip()
        if not txt:
            return "unknown download error"
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        err_lines = [ln for ln in lines if "ERROR:" in ln or ln.startswith("ERROR")]
        if err_lines:
            return " | ".join(err_lines[-3:])
        bad_keys = ("HTTP Error", "403", "429", "timed out", "Unable to download", "Unsupported URL")
        bad_lines = [ln for ln in lines if any(k in ln for k in bad_keys)]
        if bad_lines:
            return " | ".join(bad_lines[-2:])
        return lines[-1][:400]

    def _classify_failure_reason(text: str) -> str:
        t = (text or "").lower()
        if not t:
            return "未知错误"
        if "no video formats found" in t or "no formats found" in t:
            return "无可用视频格式"
        if "private video" in t or "this video is private" in t:
            return "视频私有不可访问"
        if "members-only" in t or "membership" in t:
            return "会员专享限制"
        if "sign in to confirm your age" in t or "age-restricted" in t:
            return "年龄限制"
        if "video unavailable" in t:
            return "视频不可用/下架"
        if "403" in t or "forbidden" in t:
            return "访问被拒绝(403)"
        if "429" in t or "too many requests" in t:
            return "请求过于频繁(429)"
        if "timed out" in t or "timeout" in t or "connection reset" in t or "network is unreachable" in t:
            return "网络连接异常"
        if "unable to extract" in t or "unsupported url" in t or "extractor" in t:
            return "解析失败"
        if "copyright" in t or "blocked in your country" in t or "geo" in t:
            return "版权/地区限制"
        if "sponsorblock" in t:
            return "SponsorBlock相关失败"
        return "其他错误"

    def _run_download_once(
        cmd: Sequence[str],
        stream_output: bool,
        *,
        fallback_label: str = "",
        fallback_video_id: str = "",
    ) -> Tuple[int, str]:
        if stream_output:
            proc = subprocess.Popen(
                list(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **hidden_process_kwargs(),
            )
            out_chunks: List[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                out_chunks.append(line)
                clean_line = line.rstrip("\r\n")
                progress = parse_progress_line(clean_line, fallback_label=fallback_label, fallback_video_id=fallback_video_id)
                if progress is not None:
                    if on_progress is not None:
                        on_progress(progress)
                    if on_log is not None:
                        on_log(clean_line, "progress", progress)
                    with log_lock:
                        print(clean_line, flush=True)
                    continue
                _log(clean_line)
            proc.wait()
            return proc.returncode, "".join(out_chunks).strip()
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_process_kwargs(),
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, text.strip()

    def _process_group(group: Sequence[str], stream_output: bool, task_idx: int, total_tasks: int) -> Tuple[bool, List[str]]:
        local_errors: List[str] = []
        group_head = group[0] if group else "<empty>"
        group_vid = extract_video_id(group_head)
        group_label = url_to_label.get(group_head, extract_video_id(group_head) or group_head)
        _log(f"[Q] 开始任务 {task_idx}/{total_tasks} | 视频数: {len(group)} | 视频: {group_label} | id: {group_vid or '-'}")
        soft_sub_ids: List[str] = []
        soft_sub_count = 0
        unknown_sub_count = 0
        for u in group:
            has_sub = has_independent_subtitle_track(base, u)
            if has_sub is None and (cookies_from_browser or cookies_file):
                has_sub = has_independent_subtitle_track(base_no_cookies, u)
            vid = extract_video_id(u)
            if has_sub is True:
                soft_sub_count += 1
                if vid:
                    soft_sub_ids.append(vid)
            elif has_sub is None:
                unknown_sub_count += 1
        if soft_sub_count > 0:
            _log(
                f"[INFO] 本批次检测到 {soft_sub_count} 个视频存在独立字幕轨(subtitles/automatic_captions)，"
                "已禁用字幕下载/嵌入，并将在下载后清理可能残留的字幕文件。"
            )
        if unknown_sub_count > 0:
            _log(
                f"[WARN] 本批次有 {unknown_sub_count} 个视频字幕轨探测失败，"
                "将继续下载，但仍强制禁用字幕下载/嵌入。"
            )

        if cookies_from_browser or cookies_file:
            _log("[INFO] 下载批次使用 cookies。")
        cmd = list(base) + [
            "--download-archive",
            str(archive_file),
            "--no-overwrites",
            "--write-info-json",
            "--write-description",
            "--ignore-errors",
            "--no-abort-on-error",
            "--restrict-filenames",
            "-o",
            template,
            *option_args,
            *progress_args,
            *dl_parallel_args,
            *sblock_args,
            *subtitle_policy_args,
            *group,
        ]
        code, msg = _run_download_once(
            cmd,
            stream_output=stream_output,
            fallback_label=group_label,
            fallback_video_id=group_vid,
        )
        if code == 0:
            removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
            if removed > 0:
                _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
            if on_progress is not None:
                on_progress(
                    {
                        "phase": "completed",
                        "percent": 100.0,
                        "downloaded_bytes": 0,
                        "total_bytes": 0,
                        "speed_text": "",
                        "current_video_id": group_vid,
                        "current_video_label": group_label,
                    }
                )
            _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功 | 视频: {group_label} | id: {group_vid or '-'}")
            return True, local_errors

        msg = msg or "unknown download error"
        concise = _summarize_error_text(msg)
        local_errors.append(f"视频={group_label} | url={group_head} | {concise}")

        if "No video formats found" in msg and (cookies_from_browser or cookies_file):
            _log("[WARN] 检测到 'No video formats found'，尝试不带 cookies 重试该批次...")
            retry_cmd = list(base_no_cookies) + [
                "--download-archive",
                str(archive_file),
                "--no-overwrites",
                "--write-info-json",
                "--write-description",
                "--ignore-errors",
                "--no-abort-on-error",
                "--restrict-filenames",
                "-o",
                template,
                *option_args,
                *progress_args,
                *dl_parallel_args,
                *sblock_args,
                *subtitle_policy_args,
                *group,
            ]
            retry_code, retry_msg = _run_download_once(
                retry_cmd,
                stream_output=stream_output,
                fallback_label=group_label,
                fallback_video_id=group_vid,
            )
            if retry_code == 0:
                removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
                if removed > 0:
                    _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
                if on_progress is not None:
                    on_progress(
                        {
                            "phase": "completed",
                            "percent": 100.0,
                            "downloaded_bytes": 0,
                            "total_bytes": 0,
                            "speed_text": "",
                            "current_video_id": group_vid,
                            "current_video_label": group_label,
                        }
                    )
                _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功(重试后) | 视频: {group_label} | id: {group_vid or '-'}")
                return True, local_errors
            retry_msg = retry_msg or "retry failed"
            local_errors.append(f"视频={group_label} | url={group_head} | retry_without_cookies_failed: {_summarize_error_text(retry_msg)}")

        if sblock_args:
            _log("[WARN] 检测到失败，尝试禁用 SponsorBlock 后重试该任务...")
            retry_no_sb_cmd = list(base) + [
                "--download-archive",
                str(archive_file),
                "--no-overwrites",
                "--write-info-json",
                "--write-description",
                "--ignore-errors",
                "--no-abort-on-error",
                "--restrict-filenames",
                "-o",
                template,
                *option_args,
                *progress_args,
                *dl_parallel_args,
                *subtitle_policy_args,
                *group,
            ]
            no_sb_code, no_sb_msg = _run_download_once(
                retry_no_sb_cmd,
                stream_output=stream_output,
                fallback_label=group_label,
                fallback_video_id=group_vid,
            )
            if no_sb_code == 0:
                removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
                if removed > 0:
                    _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
                if on_progress is not None:
                    on_progress(
                        {
                            "phase": "completed",
                            "percent": 100.0,
                            "downloaded_bytes": 0,
                            "total_bytes": 0,
                            "speed_text": "",
                            "current_video_id": group_vid,
                            "current_video_label": group_label,
                        }
                    )
                _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功(禁用 SponsorBlock 重试后) | 视频: {group_label} | id: {group_vid or '-'}")
                return True, local_errors
            no_sb_msg = no_sb_msg or "retry_without_sponsorblock_failed"
            local_errors.append(
                f"视频={group_label} | url={group_head} | retry_without_sponsorblock_failed: {_summarize_error_text(no_sb_msg)}"
            )

        removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
        if removed > 0:
            _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
        _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 失败 | 视频: {group_label} | id: {group_vid or '-'}")
        with log_lock:
            failed_reason_map[group_head] = _classify_failure_reason(local_errors[-1] if local_errors else "")
        return False, local_errors

    cv = max(1, int(concurrent_videos or 1))
    if cv <= 1:
        groups = list(chunked(urls, batch_size))
        total_tasks = len(groups)
        for idx, group in enumerate(groups, start=1):
            ok, local_errors = _process_group(group, stream_output=True, task_idx=idx, total_tasks=total_tasks)
            if ok:
                had_success = True
            errors.extend(local_errors)
    else:
        print(f"[INFO] 并发下载模式：并发视频数={cv}，分片并发={max(1, int(concurrent_fragments or 1))}")
        groups = [[u] for u in urls]
        total_tasks = len(groups)
        failed_tasks = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=cv) as ex:
            futures = [ex.submit(_process_group, g, True, i + 1, total_tasks) for i, g in enumerate(groups)]
            for fut in concurrent.futures.as_completed(futures):
                ok, local_errors = fut.result()
                if ok:
                    had_success = True
                errors.extend(local_errors)
                if local_errors:
                    failed_tasks += 1
                    with log_lock:
                        tail = local_errors[-1]
                        print(f"[WARN] 并发任务失败(任务 {failed_tasks}/{total_tasks}): {tail}", flush=True)
                    m = re.search(r"url=(https?://\S+)\s*\|", tail)
                    if m:
                        failed_url = m.group(1)
                        failed_urls.append(failed_url)
                        with log_lock:
                            if failed_url not in failed_reason_map:
                                failed_reason_map[failed_url] = _classify_failure_reason(tail)

    if failed_urls:
        failed_file = session_dir / FAILED_URLS_FILENAME
        uniq = []
        seen = set()
        for u in failed_urls:
            if u in seen:
                continue
            seen.add(u)
            uniq.append(u)
        failed_file.write_text("\n".join(uniq) + "\n", encoding="utf-8")
        print(f"[WARN] 本次有 {len(uniq)} 个 URL 下载失败，已写入: {failed_file}")
    else:
        failed_file = session_dir / FAILED_URLS_FILENAME

    moved_json, moved_desc = organize_sidecar_files(videos_dir, json_dir, desc_dir)
    print(f"[INFO] 下载产物目录: {session_dir}")
    if moved_json or moved_desc:
        print(f"[INFO] 已整理附属文件: json={moved_json} | description={moved_desc}")

    report_csv = write_download_report_csv(
        session_dir=session_dir,
        download_dir=session_dir,
        items=items,
        failed_urls=failed_urls,
        failed_reason_map=failed_reason_map,
    )
    print(f"[INFO] 下载结果汇总: {report_csv}")
    persist_download_session_ref(
        archive_file.parent,
        DownloadSessionRef(
            session_dir=str(session_dir),
            report_csv=str(report_csv),
            failed_urls_file=str(failed_file) if failed_file.exists() else "",
            source_task_id=str(task_id or ""),
            updated_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    if not had_success:
        if on_progress is not None:
            on_progress(
                {
                    "phase": "failed",
                    "percent": 0.0,
                    "downloaded_bytes": 0,
                    "total_bytes": 0,
                    "speed_text": "",
                    "current_video_id": "",
                    "current_video_label": "",
                }
            )
        tail = errors[-1] if errors else "unknown download error"
        raise RuntimeError(f"下载未成功完成（全部批次失败）。最近错误:\n{tail}")
    if on_progress is not None:
        on_progress(
            {
                "phase": "completed",
                "percent": 100.0,
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "speed_text": "",
                "current_video_id": "",
                "current_video_label": "",
            }
        )
