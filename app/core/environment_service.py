from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeEnvironmentStatus:
    yt_dlp_binary: str
    ffmpeg_binary: str
    yt_dlp_found: bool
    ffmpeg_found: bool
    yt_dlp_resolved_path: str = ""
    ffmpeg_resolved_path: str = ""


def inspect_runtime_environment(
    yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
) -> RuntimeEnvironmentStatus:
    yt_dlp_resolved_path = shutil.which(yt_dlp_binary) or ""
    ffmpeg_resolved_path = shutil.which(ffmpeg_binary) or ""
    return RuntimeEnvironmentStatus(
        yt_dlp_binary=yt_dlp_binary,
        ffmpeg_binary=ffmpeg_binary,
        yt_dlp_found=bool(yt_dlp_resolved_path),
        ffmpeg_found=bool(ffmpeg_resolved_path),
        yt_dlp_resolved_path=yt_dlp_resolved_path,
        ffmpeg_resolved_path=ffmpeg_resolved_path,
    )
