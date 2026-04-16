from __future__ import annotations

import csv
from pathlib import Path

from app.core.download_workspace_service import resolve_download_session_pointers
from app.core.environment_service import inspect_runtime_environment
from app.tools.schemas import CheckRuntimeEnvInput, CheckRuntimeEnvOutput, GetTaskStatusInput, GetTaskStatusOutput


def get_task_status(input_data: GetTaskStatusInput) -> GetTaskStatusOutput:
    workdir = Path(input_data.workdir)
    details: dict[str, object] = {
        "workdir": str(workdir),
        "search_candidates_exists": (workdir / "01_search_candidates.jsonl").exists(),
        "detailed_candidates_exists": (workdir / "02_detailed_candidates.jsonl").exists(),
        "selected_csv_exists": (workdir / "04_selected_for_review.csv").exists(),
        "selected_urls_exists": (workdir / "05_selected_urls.txt").exists(),
    }
    status = "empty"

    pointers = resolve_download_session_pointers(workdir, session_dir=input_data.session_dir)
    session_dir = pointers.session_dir
    if session_dir:
        session_path = Path(session_dir)
        report_csv = Path(pointers.report_csv) if pointers.report_csv else session_path / "07_download_report.csv"
        details["session_dir"] = str(session_path)
        details["report_csv_exists"] = report_csv.exists()
        if report_csv.exists():
            success_count = 0
            failed_count = 0
            with report_csv.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if row.get("视频是否下载成功") == "是":
                        success_count += 1
                    else:
                        failed_count += 1
            details["success_count"] = success_count
            details["failed_count"] = failed_count
            status = "downloaded"
        else:
            status = "download_started"
    elif details["selected_urls_exists"]:
        status = "ready_to_download"
    elif details["detailed_candidates_exists"]:
        status = "detailed"
    elif details["search_candidates_exists"]:
        status = "searched"

    return GetTaskStatusOutput(status=status, details=details)


def check_runtime_env(input_data: CheckRuntimeEnvInput) -> CheckRuntimeEnvOutput:
    status = inspect_runtime_environment(
        yt_dlp_binary=input_data.yt_dlp_binary,
        ffmpeg_binary=input_data.ffmpeg_binary,
    )
    return CheckRuntimeEnvOutput(
        yt_dlp_found=status.yt_dlp_found,
        ffmpeg_found=status.ffmpeg_found,
        yt_dlp_binary=status.yt_dlp_binary,
        ffmpeg_binary=status.ffmpeg_binary,
    )
