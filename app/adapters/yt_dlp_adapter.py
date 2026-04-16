from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence


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
    cmd = [binary, "--no-warnings", "--ignore-no-formats-error"]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if extra_args:
        cmd += [str(a) for a in extra_args if str(a).strip()]
    return cmd

