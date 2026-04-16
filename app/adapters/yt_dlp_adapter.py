from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from app.core.environment_service import ffmpeg_location, resolve_runtime_binary


def run_command(cmd: Sequence[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise RuntimeError(f"命令执行失败: {' '.join(cmd)}\n{msg}")
    return proc


def yt_dlp_base(
    binary: str,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    resolved = resolve_runtime_binary(binary, fallback_names=("yt-dlp", "yt-dlp.exe"))
    command = resolved.resolved_path or binary
    cmd = [command, "--no-warnings", "--ignore-no-formats-error"]
    ffmpeg_dir = ffmpeg_location()
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if extra_args:
        cmd += [str(a) for a in extra_args if str(a).strip()]
    return cmd
